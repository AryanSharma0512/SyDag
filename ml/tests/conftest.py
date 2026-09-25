import numpy as np
import pandas as pd
import pytest

import soilsignal_ml  # noqa: F401  (puts backend/ on the import path)
from soilsignal_ml.ingest.canonical import PROCESSED, CanonicalDataset

DATASET = "shrestha2024"


@pytest.fixture(scope="session")
def dataset() -> CanonicalDataset:
    if not (PROCESSED / DATASET / "plots.csv").exists():
        pytest.skip("practice dataset not ingested (python -m soilsignal_ml ingest)")
    return CanonicalDataset.load(DATASET)


@pytest.fixture
def frame() -> pd.DataFrame:
    """Small synthetic training frame: 3 sites x 2 fields x 20 plots."""
    rng = np.random.default_rng(0)
    rows = []
    for s, site in enumerate(["A", "B", "C"]):
        for f in range(2):
            for p in range(20):
                ndvi = rng.uniform(0.4, 0.9)
                rows.append(
                    {
                        "plot_id": f"{site}-{f}-{p}",
                        "field_id": f"{site}-{f}",
                        "site_id": site,
                        "year": 2022,
                        "genotype": f"H{p % 5}",
                        "nitrogen_lb_ac": float(rng.choice([0, 75, 150])),
                        "ndvi_current": ndvi if p % 7 else np.nan,
                        "rain_30d_mm": 40.0 + 10 * s,
                        "final_yield": 60 + 150 * ndvi + 20 * s + rng.normal(0, 5),
                    }
                )
    return pd.DataFrame(rows)
