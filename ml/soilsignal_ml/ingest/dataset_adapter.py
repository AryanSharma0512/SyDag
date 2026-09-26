"""
Dataset adapters: each turns one source's files into the CanonicalDataset.

PublicDatasetAdapter   Shrestha et al. (2024), multistate maize hybrid trials with
                       Pléiades Neo satellite imagery (the practice dataset).
HackathonDatasetAdapter  The SyDAg26 challenge data (dataset "sydag26"), from the tables
                       `python -m soilsignal_ml challenge` writes to ml/data/challenge/.

Swapping datasets means writing an adapter, never touching features or training.
"""

import io
import re
from collections.abc import Callable
from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd
import tifffile
from pyproj import Transformer

from app.features.vegetation import INDEX_NAMES, compute_indices
from soilsignal_ml import ML_ROOT
from soilsignal_ml.ingest.canonical import PLOT_COLUMNS, SOIL_COLUMNS, CanonicalDataset
from soilsignal_ml.ingest.challenge import OUT_ROOT as CHALLENGE_TABLES
from soilsignal_ml.ingest.challenge import RAW_ROOT as CHALLENGE_RAW
from soilsignal_ml.ingest.imagery import SATELLITE_BANDS, SATELLITE_REFLECTANCE_SCALE
from soilsignal_ml.ingest.remote_zip import RemoteZip

Progress = Callable[[str], None]


class DatasetAdapter(Protocol):
    name: str

    def build(self, progress: Progress = print) -> CanonicalDataset:
        """Fetch and normalize the source into the canonical tables."""
        ...


# ---- SyDAg26 challenge data ------------------------------------------------------------

# Agent 2's per-image index means in the canonical observations layout (soilsignal_ml.imagery).
IMAGERY_OBSERVATIONS = ML_ROOT / "data" / "interim" / "imagery" / "canonical_observations.csv"
CHALLENGE_PLOT_EXTRAS = [
    "experiment",
    "range",
    "row",
    "practice_plot_id",
    "stand_count",
    "days_to_anthesis",
    "gdd_to_anthesis",
]


def image_indices(path) -> dict[str, float]:
    """Mean of each per-pixel index over a plot GeoTIFF's valid pixels (all six bands
    non-zero), and the mean NIR reflectance (showcase reads it as `nir`)."""
    cube = tifffile.imread(path).astype(float)  # (rows, cols, 6)
    valid = (cube != 0).all(axis=-1)
    if not valid.any():
        return {}
    bands = {
        name: cube[..., i][valid] * SATELLITE_REFLECTANCE_SCALE
        for i, name in enumerate(SATELLITE_BANDS)
    }
    out = {
        name: float(np.nanmean(values)) if np.isfinite(values).any() else np.nan
        for name, values in compute_indices(bands).items()
    }
    out["nir"] = float(bands["nir"].mean())
    return out


class HackathonDatasetAdapter:
    """SyDAg26 challenge data -> the canonical tables (plots, observations, sites).

    Reads `python -m soilsignal_ml challenge`'s outputs (ml/data/challenge/). Vegetation
    indices come from Agent 2's canonical_observations.csv when it exists (matched on plot_id
    and date), else from the GeoTIFFs under ml/data/raw/challenge/. Plots kept: those with a
    usable satellite image and coordinates, as in the practice dataset. `ingest` then adds
    weather, soil and county yields as separate context tables; none of them enter `plots`.
    UAV images are not used here (RGB only, not calibrated between flights)."""

    name = "sydag26"

    def __init__(
        self,
        tables=CHALLENGE_TABLES,
        raw_root=CHALLENGE_RAW,
        imagery_observations=IMAGERY_OBSERVATIONS,
    ) -> None:
        self.tables = tables
        self.raw_root = raw_root
        self.imagery_observations = imagery_observations

    def _indices(self, sat: pd.DataFrame, progress: Progress) -> pd.DataFrame:
        if self.imagery_observations.exists():
            progress(f"indices from {self.imagery_observations}")
            f = pd.read_csv(self.imagery_observations)
            f["date"] = pd.to_datetime(f["date"]).dt.normalize()
            cols = ["plot_id", "date", *[i for i in (*INDEX_NAMES, "nir") if i in f]]
            return sat.merge(f[cols], on=["plot_id", "date"], how="inner")
        progress(f"indices computed from the GeoTIFFs under {self.raw_root}")
        rows = [
            {"image_id": r.image_id, **image_indices(self.raw_root / r.image_path)}
            for r in sat.itertuples()
            if (self.raw_root / r.image_path).exists()
        ]
        if not rows:
            raise FileNotFoundError(
                f"no satellite images under {self.raw_root} and no {self.imagery_observations}"
            )
        return sat.merge(pd.DataFrame(rows), on="image_id", how="inner")

    def build(self, progress: Progress = print) -> CanonicalDataset:
        plots = pd.read_parquet(self.tables / "plots.parquet")
        sat = pd.read_parquet(self.tables / "satellite_manifest.parquet")
        sites = pd.read_parquet(self.tables / "sites.parquet")

        sat = sat[sat["use"]].assign(date=lambda d: pd.to_datetime(d["date"]).dt.normalize())
        obs = self._indices(sat, progress).assign(source="satellite")
        obs["date"] = obs["date"].dt.date
        values = [i for i in (*INDEX_NAMES, "nir") if i in obs]
        # time_point: the pass number at its site (1-6), as in the practice dataset.
        obs = obs[["plot_id", "date", "source", "time_point", *values]]
        for i in (*INDEX_NAMES, "nir"):
            if i not in obs:
                obs[i] = np.nan

        p = plots.rename(columns={"total_stand_count": "stand_count"}).copy()
        # Fill plots share their site + experiment's planting date (planting_date_source).
        p["planting_date"] = pd.to_datetime(p["planting_date_filled"]).dt.date
        keep = p["plot_id"].isin(obs["plot_id"]) & p["latitude"].notna()
        p = p.loc[keep, PLOT_COLUMNS + CHALLENGE_PLOT_EXTRAS].reset_index(drop=True)
        obs = obs[obs["plot_id"].isin(p["plot_id"])].reset_index(drop=True)
        s = sites[sites["site_id"].isin(p["site_id"])][
            ["site_id", "name", "state", "latitude", "longitude"]
        ].reset_index(drop=True)
        return CanonicalDataset(
            name=self.name,
            plots=p,
            observations=obs,
            weather=pd.DataFrame(columns=["site_id", "date", "tmax_f", "tmin_f", "prcp_mm"]),
            soil=pd.DataFrame(columns=SOIL_COLUMNS),
            county_yields=pd.DataFrame(columns=["site_id", "year", "yield"]),
            sites=s,
            provenance={
                "dataset": self.name,
                "citation": "SyDAg26 IoT4Ag hackathon challenge data (organizers' shared "
                "folder); the plots, images and README match Shrestha N., Powadi A., Davis J., "
                "et al. (2024), doi:10.5061/dryad.905qftttm.",
                "license": "As distributed by the hackathon organizers; satellite imagery "
                "© Airbus DS (2022).",
                "notes": [
                    "Plot key: {year}-{site}-{experiment}-{range}-{row} (ml/data/challenge).",
                    "Acquisition dates from DateofCollection.xlsx; TP numbers differ by site.",
                    "Satellite indices: mean over the plot's pixels of per-pixel indices, "
                    "reflectance = DN x 1e-4.",
                    "Fill plots without a planting date take their site + experiment's date.",
                    "Weather, soil and county yields are context tables, not plot records.",
                ],
            },
        )


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


ADAPTERS: dict[str, type] = {
    "shrestha2024": PublicDatasetAdapter,
    "sydag26": HackathonDatasetAdapter,
}
