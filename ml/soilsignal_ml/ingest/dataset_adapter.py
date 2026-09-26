"""
Dataset adapters: each turns one source's files into the CanonicalDataset.

PublicDatasetAdapter   Shrestha et al. (2024), multistate maize hybrid trials with
                       Pléiades Neo satellite imagery (the practice dataset).
HackathonDatasetAdapter  The SyDAg26 challenge data, once released.

Swapping datasets means writing an adapter, never touching features or training.
"""

import io
import json
import re
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd
import tifffile
from pyproj import Transformer

from app.features.vegetation import compute_indices
from soilsignal_ml.ingest.canonical import CanonicalDataset
from soilsignal_ml.ingest.remote_zip import RemoteZip

Progress = Callable[[str], None]


class DatasetAdapter(Protocol):
    name: str

    def build(self, progress: Progress = print) -> CanonicalDataset:
        """Fetch and normalize the source into the canonical tables."""
        ...


# ---- Shrestha et al. (2024) ---------------------------------------------------------

ZENODO_URL = "https://zenodo.org/records/11167576/files/DataPublication_final.zip?download=1"
ROOT = "DataPublication_final/"
CITATION = (
    "Shrestha N., Powadi A., Davis J., et al. (2024). Crop performance, aerial, and "
    "satellite data from multistate maize yield trials. Dryad/Zenodo, "
    "doi:10.5061/dryad.905qftttm. CC0 1.0."
)
# Satellite bands in file order. The README lists NIR first, but the example notebook's
# pixel loop and the spectra agree on this order: NIR is by far the brightest band over
# green canopy, and red exceeds green once the crop senesces.
BANDS = ("red", "green", "blue", "nir", "red_edge", "deep_blue")
REFLECTANCE_SCALE = 10_000  # 16-bit surface reflectance x 10,000
SITES = {
    "Ames": ("Ames", "IA"),
    "Crawfordsville": ("Crawfordsville", "IA"),
    "Lincoln": ("Lincoln", "NE"),
    "MOValley": ("Missouri Valley", "IA"),
    "Scottsbluff": ("Scottsbluff", "NE"),
}
IMAGE_NAME = re.compile(
    r"(?P<site>[A-Za-z]+)-TP(?P<tp>\d)-(?P<exp>.+)_(?P<range>\d+)_(?P<row>\d+)\.TIF$", re.I
)


def _experiment(value: object) -> str:
    """Experiment codes differ between files ('Hybrids') and ground truth ('Hyrbrids')."""
    text = str(value).strip().lower()
    return "hybrids" if text in {"hybrids", "hyrbrids"} else text


def plot_id(site: str, experiment: str, rng: int, row: int) -> str:
    return f"{site}-{_experiment(experiment)}-{int(rng)}-{int(row)}"


def _image_stats(data: bytes) -> tuple[dict[str, float], tuple[float, float], str, int]:
    """Mean reflectance per band and mean of each per-pixel index over plot pixels
    (pixels outside the plot are zero in every band), plus the plot centre."""
    with tifffile.TiffFile(io.BytesIO(data)) as tif:
        page = tif.pages[0]
        pixels = page.asarray().astype(float)
        tags = page.tags
        tie = tags["ModelTiepointTag"].value
        scale = tags["ModelPixelScaleTag"].value
        epsg = str(int(page.geotiff_tags["ProjectedCSTypeGeoKey"]))
    height, width, _ = pixels.shape
    valid = (pixels != 0).all(axis=2)
    bands = {b: pixels[..., i][valid] / REFLECTANCE_SCALE for i, b in enumerate(BANDS)}
    stats = {b: float(v.mean()) if v.size else np.nan for b, v in bands.items()}
    for name, values in compute_indices(bands).items():
        stats[name] = float(np.nanmean(values)) if np.isfinite(values).any() else np.nan
    x = tie[3] + scale[0] * width / 2
    y = tie[4] - scale[1] * height / 2
    return stats, (x, y), epsg, int(valid.sum())


class PublicDatasetAdapter:
    name = "shrestha2024"

    def __init__(self, url: str = ZENODO_URL) -> None:
        self.url = url

    def build(self, progress: Progress = print) -> CanonicalDataset:
        remote = RemoteZip(self.url)
        progress(f"zip index read ({remote.bytes_fetched / 1e6:.1f} MB fetched)")
        truth = pd.read_csv(
            io.BytesIO(remote.read(ROOT + "GroundTruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv"))
        )
        dates = pd.read_excel(io.BytesIO(remote.read(ROOT + "GroundTruth/DateofCollection.xlsx")))
        image_dates = self._image_dates(dates)

        names = [
            n for n in remote.names() if n.startswith(ROOT + "Satellite/") and IMAGE_NAME.search(n)
        ]
        progress(f"streaming {len(names)} plot images (nothing is written to disk)")
        rows, coords = [], {}
        for i, (name, data) in enumerate(remote.iter_members(names), 1):
            m = IMAGE_NAME.search(name)
            site, tp = m["site"], int(m["tp"])
            pid = plot_id(site, m["exp"], int(m["range"]), int(m["row"]))
            stats, xy, epsg, n_pixels = _image_stats(data)
            rows.append(
                {
                    "plot_id": pid,
                    "date": image_dates[(site, tp)],
                    "source": "satellite",
                    "time_point": tp,
                    "n_pixels": n_pixels,
                    **stats,
                }
            )
            coords.setdefault(pid, []).append((epsg, *xy))
            if i % 2000 == 0:
                progress(f"  {i}/{len(names)} images, {remote.bytes_fetched / 1e6:.0f} MB streamed")
        progress(f"imagery done: {remote.bytes_fetched / 1e6:.0f} MB streamed in total")
        observations = pd.DataFrame(rows)
        plots = self._plots(truth, coords)
        unimaged = int(plots["latitude"].isna().sum())
        plots = plots[plots["latitude"].notna()].reset_index(drop=True)
        observations = observations[observations["plot_id"].isin(plots["plot_id"])]
        observations = observations[observations["n_pixels"] > 0].reset_index(drop=True)

        sites = (
            plots.groupby("site_id")
            .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"))
            .reset_index()
        )
        sites["name"] = sites["site_id"].map(lambda s: SITES[s][0])
        sites["state"] = sites["site_id"].map(lambda s: SITES[s][1])
        return CanonicalDataset(
            name=self.name,
            plots=plots,
            observations=observations,
            weather=pd.DataFrame(columns=["site_id", "date", "tmax_f", "tmin_f", "prcp_mm"]),
            soil=pd.DataFrame(columns=["plot_id"]),
            county_yields=pd.DataFrame(columns=["site_id", "year", "yield"]),
            sites=sites,
            provenance={
                "dataset": self.name,
                "citation": CITATION,
                "source_url": self.url,
                "license": "CC0 1.0",
                "retrieved": date.today().isoformat(),
                "bands": list(BANDS),
                "reflectance_scale": REFLECTANCE_SCALE,
                "notes": [
                    "North Platte, NE is excluded by the authors (plot segmentation issues).",
                    "Only satellite imagery is used; the UAV images are RGB only.",
                    "Plot coordinates are the centre of each plot's georeferenced image.",
                    f"{unimaged} ground-truth plots have no satellite image and are dropped.",
                ],
            },
        )

    @staticmethod
    def _image_dates(dates: pd.DataFrame) -> dict[tuple[str, int], date]:
        by_name = {v[0]: k for k, v in SITES.items()} | {k: k for k in SITES}
        out = {}
        for _, r in dates.iterrows():
            # Columns: Location, Date, Image ("Satellite"/"UAV"), time ("TP1"...).
            text = " ".join(str(v) for v in r.iloc[2:] if pd.notna(v))
            match = re.search(r"(Satellite|UAV)\s*TP(\d)", text, re.I)
            site = by_name.get(str(r["Location"]).strip())
            if site and match and match[1].lower() == "satellite":
                out[(site, int(match[2]))] = pd.Timestamp(r["Date"]).date()
        if len(out) != len(SITES) * 6:
            raise ValueError(f"expected 6 satellite dates per site, parsed {len(out)}")
        return out

    @staticmethod
    def _plots(truth: pd.DataFrame, coords: dict) -> pd.DataFrame:
        t = truth.copy()
        t["plot_id"] = [
            plot_id(s, e, r, w)
            for s, e, r, w in zip(t["location"], t["experiment"], t["range"], t["row"], strict=True)
        ]
        # Orientation check: file names are experiment_range_row (README). Fail loudly if
        # the ground truth only lines up the other way round.
        swapped = {
            plot_id(s, e, w, r)
            for s, e, r, w in zip(t["location"], t["experiment"], t["range"], t["row"], strict=True)
        }
        straight_hits = len(set(t["plot_id"]) & set(coords))
        if straight_hits < len(swapped & set(coords)):
            raise ValueError("image names match ground truth only with range/row swapped")
        t["site_id"] = t["location"]
        t["field_id"] = t["site_id"] + "-" + t["experiment"].map(_experiment)
        t["year"] = 2022
        t["planting_date"] = pd.to_datetime(t["plantingDate"]).dt.date
        site_planting = t.groupby("site_id")["planting_date"].agg(
            lambda s: s.dropna().mode().iloc[0]
        )
        t["planting_date"] = t["planting_date"].fillna(t["site_id"].map(site_planting))
        irrigation = t.groupby("site_id")["irrigationProvided"].max()
        t["irrigated"] = t["site_id"].map(irrigation).fillna(0) > 0
        t["nitrogen_lb_ac"] = t["poundsOfNitrogenPerAcre"].astype(float)
        t["genotype"] = t["genotype"].astype("string").str.strip()
        t["final_yield"] = t["yieldPerAcre"]
        t["stand_count"] = t["totalStandCount"]
        t["days_to_anthesis"] = t["daysToAnthesis"]
        t["gdd_to_anthesis"] = t["GDDToAnthesis"]

        transformers: dict[str, Transformer] = {}
        lat, lon = [], []
        for pid in t["plot_id"]:
            pts = coords.get(pid)
            if not pts:
                lat.append(np.nan)
                lon.append(np.nan)
                continue
            epsg = pts[0][0]
            tr = transformers.setdefault(
                epsg, Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
            )
            x, y = np.mean([p[1] for p in pts]), np.mean([p[2] for p in pts])
            lo, la = tr.transform(x, y)
            lat.append(la)
            lon.append(lo)
        t["latitude"], t["longitude"] = lat, lon
        keep = [
            "plot_id",
            "field_id",
            "site_id",
            "year",
            "planting_date",
            "latitude",
            "longitude",
            "genotype",
            "nitrogen_lb_ac",
            "irrigated",
            "final_yield",
            "experiment",
            "range",
            "row",
            "stand_count",
            "days_to_anthesis",
            "gdd_to_anthesis",
        ]
        return t[keep].reset_index(drop=True)


# ---- SyDAg26 challenge data ---------------------------------------------------------


class HackathonDatasetAdapter:
    """SyDAg26 challenge data. `python -m soilsignal_ml challenge` writes the inventory,
    manifests and joins to ml/data/challenge/ (see challenge.py); this turns them into the
    canonical tables. `python -m soilsignal_ml ingest --dataset sydag26` runs both.

    Plots keep only what the ground truth records. Every departure is listed in the
    provenance notes: a missing planting date takes the site's most common one, and plots
    with a duplicated plot_id or without a satellite image (so without a coordinate) are
    left out of the canonical tables (they stay in ml/data/challenge/plots.parquet).
    Observations are satellite only: the UAV images are RGB and support none of the
    indices, so they stay in the UAV manifest for feature extraction."""

    name = "sydag26"

    def __init__(
        self,
        out: Path | None = None,
        raw: Path | None = None,
        bands: tuple[str, ...] = BANDS,
        reflectance_scale: float = REFLECTANCE_SCALE,
        workers: int = 4,
    ) -> None:
        from soilsignal_ml.ingest import challenge

        self.out = out or challenge.OUT
        self.raw = raw or challenge.RAW
        self.bands = bands
        self.reflectance_scale = reflectance_scale
        self.workers = workers

    def build(self, progress: Progress = print) -> CanonicalDataset:
        from soilsignal_ml.ingest import challenge

        if not (self.out / "plots.parquet").exists():
            progress("no challenge outputs yet: running the inventory and joins")
            challenge.build(self.raw, self.out, self.workers)
        manifest = json.loads((self.out / "challenge_manifest.json").read_text())
        plots = pd.read_parquet(self.out / "plots.parquet")
        obs = pd.read_parquet(self.out / "observations.parquet")
        notes: list[str] = []

        duplicated = plots["duplicate_plot_id"].fillna(False).astype(bool)
        no_id = plots["plot_id"].isna()
        no_coord = plots["latitude"].isna() & ~duplicated & ~no_id
        notes.append(
            f"{int(duplicated.sum())} ground-truth rows share a plot_id and "
            f"{int(no_id.sum())} lack site/experiment/range/row; both left out."
        )
        notes.append(f"{int(no_coord.sum())} plots have no satellite image and are left out.")
        p = plots[~duplicated & ~no_id & ~no_coord].copy()

        if "planting_date" not in p:
            p["planting_date"] = pd.NaT
        p["planting_date"] = pd.to_datetime(p["planting_date"], errors="coerce").dt.date
        site_planting = p.groupby("site_id")["planting_date"].agg(
            lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None
        )
        imputed = p["planting_date"].isna()
        p["planting_date"] = p["planting_date"].fillna(p["site_id"].map(site_planting))
        p["planting_date_imputed"] = imputed
        notes.append(
            f"{int(imputed.sum())} plots had no planting date and take their site's most "
            "common one (planting_date_imputed)."
        )
        p["field_id"] = p["site_id"] + "-" + p["year"].astype(str) + "-" + p["experiment"]
        if "irrigated" in p:
            p["irrigated"] = p["irrigated"].astype("boolean")

        sat = obs[(obs["source"] == "satellite") & obs["plot_id"].isin(p["plot_id"])].copy()
        sat = sat.sort_values("n_valid_pixels", ascending=False).drop_duplicates(
            ["plot_id", "date"]
        )
        sat = sat[sat["n_valid_pixels"] > 0]
        progress(f"reading {len(sat)} satellite images for per-image index means")
        paths = [str(self.raw / path) for path in sat["image_path"]]
        with ProcessPoolExecutor(self.workers) as pool:
            stats = list(
                pool.map(
                    _index_means,
                    paths,
                    [self.bands] * len(paths),
                    [self.reflectance_scale] * len(paths),
                    chunksize=16,
                )
            )
        observations = pd.concat(
            [
                sat[
                    ["plot_id", "date", "source", "time_point", "image_path", "n_valid_pixels"]
                ].reset_index(drop=True),
                pd.DataFrame(stats),
            ],
            axis=1,
        )
        observations["date"] = pd.to_datetime(observations["date"]).dt.date

        sites = (
            p.groupby("site_id")
            .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"))
            .reset_index()
        )
        sites["name"] = sites["site_id"].map(lambda s: SITES.get(s, (s, None))[0])
        sites["state"] = sites["site_id"].map(lambda s: SITES.get(s, (s, None))[1])
        keep = [
            c
            for c in (
                "plot_id",
                "field_id",
                "site_id",
                "year",
                "planting_date",
                "latitude",
                "longitude",
                "genotype",
                "nitrogen_lb_ac",
                "irrigated",
                "final_yield",
                "experiment",
                "range",
                "row",
                "stand_count",
                "days_to_anthesis",
                "gdd_to_anthesis",
                "planting_date_imputed",
                "centroid_spread_m",
            )
            if c in p
        ]
        return CanonicalDataset(
            name=self.name,
            plots=p[keep].reset_index(drop=True),
            observations=observations,
            weather=pd.DataFrame(columns=["site_id", "date", "tmax_f", "tmin_f", "prcp_mm"]),
            soil=pd.DataFrame(columns=["plot_id"]),
            county_yields=pd.DataFrame(columns=["site_id", "year", "yield"]),
            sites=sites,
            provenance={
                "dataset": self.name,
                "source": "SyDAg26 IoT4Ag Hackathon challenge data (organizer Drive folder)",
                "challenge_outputs": str(self.out),
                "built": manifest.get("provenance", {}).get("built"),
                "retrieved": date.today().isoformat(),
                "bands": list(self.bands),
                "reflectance_scale": self.reflectance_scale,
                "notes": [
                    *notes,
                    "Plot coordinates are the median valid-pixel centroid of the plot's "
                    "satellite images.",
                    "Image dates come from DateofCollection.xlsx, never from TP numbers.",
                ],
            },
        )


def _index_means(path: str, bands: tuple[str, ...], scale: float) -> dict[str, float]:
    """Mean reflectance per band and mean of each per-pixel index over plot pixels
    (pixels zero in every band are outside the segmented plot)."""
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        pixels = page.asarray()
        axes = page.axes
    if "S" in axes:
        pixels = np.moveaxis(pixels, axes.index("S"), -1)
    pixels = pixels.astype(float)
    if pixels.shape[-1] != len(bands):
        raise ValueError(f"{path}: {pixels.shape[-1]} bands, expected {len(bands)}")
    valid = (pixels != 0).all(axis=2)
    values = {b: pixels[..., i][valid] / scale for i, b in enumerate(bands)}
    stats = {b: float(v.mean()) if v.size else np.nan for b, v in values.items()}
    for name, v in compute_indices(values).items():
        stats[name] = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan
    return stats


ADAPTERS: dict[str, type] = {
    "shrestha2024": PublicDatasetAdapter,
    "sydag26": HackathonDatasetAdapter,
}
