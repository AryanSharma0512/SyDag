"""
Challenge dataset -> the canonical tables (plots, observations, sites; weather, soil and
county yields are then fetched by `ingest` like for any dataset).

Reads the outputs of `python -m soilsignal_ml challenge` (ml/data/challenge/) and, for the
vegetation indices, either a per-image feature table from the spectral stage
(ml/data/challenge/satellite_features.parquet: image_id plus any of ndvi, ndre, gndvi, evi,
and nir = mean NIR reflectance)
or, when that is absent, the satellite GeoTIFFs themselves: per-pixel indices over the plot's
valid pixels (no padding), averaged, with reflectance = DN x 1e-4.

Plots kept for training are those with a usable satellite image and coordinates, as in the
practice dataset. UAV images are listed in ml/data/challenge/ but not used here: they are
RGB only and not radiometrically comparable between flights.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from app.features.vegetation import INDEX_NAMES, compute_indices
from soilsignal_ml.ingest.canonical import PLOT_COLUMNS, SOIL_COLUMNS, CanonicalDataset
from soilsignal_ml.ingest.challenge import OUT_ROOT, RAW_ROOT
from soilsignal_ml.ingest.imagery import SATELLITE_BANDS, SATELLITE_REFLECTANCE_SCALE

EXTRA_PLOT_COLUMNS = [
    "experiment",
    "range",
    "row",
    "practice_plot_id",
    "stand_count",
    "days_to_anthesis",
    "gdd_to_anthesis",
]


def image_indices(path: Path) -> dict[str, float]:
    """Mean of each per-pixel index over the plot's pixels (all six bands non-zero), and the
    mean NIR reflectance (the dashboard shows it; showcase reads it as `nir`)."""
    import tifffile

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


class ChallengeDatasetAdapter:
    name = "challenge2022"

    def __init__(self, out_root: Path = OUT_ROOT, raw_root: Path = RAW_ROOT) -> None:
        self.out_root = out_root
        self.raw_root = raw_root

    def _indices(self, sat: pd.DataFrame) -> pd.DataFrame:
        features = self.out_root / "satellite_features.parquet"
        if features.exists():
            f = pd.read_parquet(features)
            cols = ["image_id", *[i for i in (*INDEX_NAMES, "nir") if i in f]]
            return sat.merge(f[cols], on="image_id", how="inner")
        rows = []
        for r in sat.itertuples():
            path = self.raw_root / r.image_path
            if path.exists():
                rows.append({"image_id": r.image_id, **image_indices(path)})
        if not rows:
            raise FileNotFoundError(
                f"no satellite images under {self.raw_root} and no {features}: download the "
                "challenge folder there, or run the spectral stage first"
            )
        return sat.merge(pd.DataFrame(rows), on="image_id", how="inner")

    def build(self) -> CanonicalDataset:
        plots = pd.read_parquet(self.out_root / "plots.parquet")
        sat = pd.read_parquet(self.out_root / "satellite_manifest.parquet")
        sites = pd.read_parquet(self.out_root / "sites.parquet")

        sat = sat[sat["use"]]
        obs = self._indices(sat)
        # time_point: the image's order at its site (1-6), as in the practice dataset.
        obs = obs.assign(source="satellite", time_point=obs["tp_index"].astype(int))[
            [
                "plot_id",
                "date",
                "source",
                "time_point",
                *[i for i in (*INDEX_NAMES, "nir") if i in obs],
            ]
        ]
        for i in (*INDEX_NAMES, "nir"):
            if i not in obs:
                obs[i] = np.nan

        p = plots.rename(columns={"total_stand_count": "stand_count"}).copy()
        # Fill plots share their site + experiment's planting date (planting_date_source).
        p["planting_date"] = p["planting_date_filled"]
        keep = p["plot_id"].isin(obs["plot_id"]) & p["latitude"].notna()
        p = p.loc[keep, PLOT_COLUMNS + EXTRA_PLOT_COLUMNS].reset_index(drop=True)
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
                ],
            },
        )
