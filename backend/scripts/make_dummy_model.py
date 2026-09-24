"""
Train throwaway models on synthetic data and export them in the artifact format.

Produces one model per season cutoff, each seeing only the features available by
that date, so later models have narrower intervals. This exercises the whole
serving path before the challenge dataset exists, and doubles as a reference for
how the ML pipeline should call save_artifact().

    cd backend && uv run python -m scripts.make_dummy_model [--out artifacts]
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from app.model.contract import (
    FeatureSchema,
    FeatureSpec,
    Metrics,
    ModelMetadata,
    PredictionInterval,
)
from app.model.export import save_artifact

# name, label, category, direction, first cutoff at which the feature is observable
_FEATURE_TABLE = [
    ("soil_awc_cm", "Available water capacity", "Soil", "positive", "06-15"),
    ("gdd_accumulated", "Accumulated GDD", "Weather", "positive", "06-15"),
    ("ndvi_early_mean", "NDVI early season", "Vegetation", "positive", "06-15"),
    ("ndvi_mid_mean", "NDVI mid-season", "Vegetation", "positive", "07-15"),
    ("rain_30d_mm", "30-day rainfall", "Weather", "positive", "07-15"),
    ("heat_days_95f", "Days above 95°F", "Weather", "negative", "07-15"),
    ("ndre_slope", "NDRE slope", "Vegetation", "positive", "08-15"),
    ("ndvi_peak", "NDVI peak", "Vegetation", "positive", "08-15"),
]
FEATURES = [
    (FeatureSpec(name=n, label=lbl, category=cat, direction=d), available)
    for n, lbl, cat, d, available in _FEATURE_TABLE
]
CUTOFFS = ["06-15", "07-15", "08-15"]
INTERVAL_LEVEL = 0.9


def synthetic_plots(n: int, seed: int) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        {
            "soil_awc_cm": rng.uniform(12, 28, n),
            "gdd_accumulated": rng.normal(1250, 120, n),
            "ndvi_early_mean": rng.uniform(0.3, 0.6, n),
            "ndvi_mid_mean": rng.uniform(0.55, 0.9, n),
            "rain_30d_mm": rng.gamma(4, 15, n),
            "heat_days_95f": rng.poisson(3, n).astype(float),
            "ndre_slope": rng.normal(0.004, 0.0015, n),
            "ndvi_peak": rng.uniform(0.7, 0.95, n),
        }
    )
    y = (
        40
        + 0.8 * X["soil_awc_cm"]
        + 0.02 * X["gdd_accumulated"]
        + 60 * X["ndvi_early_mean"]
        + 90 * X["ndvi_mid_mean"]
        + 0.15 * X["rain_30d_mm"]
        - 3.0 * X["heat_days_95f"]
        + 2500 * X["ndre_slope"]
        + 40 * X["ndvi_peak"]
        + rng.normal(0, 6, n)
    )
    return X, y.rename("yield_bu_ac")


def train(cutoff: str, X: pd.DataFrame, y: pd.Series, out: Path) -> Path:
    specs = [spec for spec, available in FEATURES if available <= cutoff]
    cols = [s.name for s in specs]
    X_tr, X_val, y_tr, y_val = train_test_split(X[cols], y, test_size=0.25, random_state=0)
    model = GradientBoostingRegressor(random_state=0).fit(X_tr, y_tr)

    pred = model.predict(X_val)
    residuals = y_val.to_numpy() - pred
    alpha = (1 - INTERVAL_LEVEL) / 2
    metadata = ModelMetadata(
        model_id=f"dummy-{cutoff}",
        algorithm="gradient_boosting",
        target="yield_bu_ac",
        metrics=Metrics(
            rmse=round(float(np.sqrt(mean_squared_error(y_val, pred))), 2),
            mae=round(float(mean_absolute_error(y_val, pred)), 2),
            r2=round(float(r2_score(y_val, pred)), 3),
        ),
        validation="random holdout (synthetic data)",
        feature_count=len(cols),
        trained_at=datetime.now(UTC).isoformat(timespec="seconds"),
        as_of=cutoff,
        interval=PredictionInterval(
            level=INTERVAL_LEVEL,
            lower_offset=round(min(0.0, float(np.quantile(residuals, alpha))), 2),
            upper_offset=round(max(0.0, float(np.quantile(residuals, 1 - alpha))), 2),
        ),
    )
    return save_artifact(model, metadata, FeatureSchema(features=specs), out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    default_out = Path(__file__).resolve().parent.parent / "artifacts"
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args()

    X, y = synthetic_plots(n=1200, seed=42)
    for cutoff in CUTOFFS:
        path = train(cutoff, X, y, args.out)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
