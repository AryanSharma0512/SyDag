"""Every model family trains, predicts finite values, and survives export and reload."""

import numpy as np
import pandas as pd
import pytest

from app.model.artifact import ModelArtifact
from app.model.contract import (
    FeatureSchema,
    FeatureSpec,
    Metrics,
    ModelMetadata,
    PredictionInterval,
)
from app.model.export import save_artifact
from soilsignal_ml.evaluation.uncertainty import coverage, interval_offsets
from soilsignal_ml.models.train import LADDER, prepare, select

NUMERIC = ["nitrogen_lb_ac", "ndvi_current", "rain_30d_mm"]
CATEGORICAL = ["genotype"]


@pytest.mark.parametrize("spec", LADDER, ids=lambda s: s.name)
def test_model_trains_and_reloads(spec, frame, tmp_path):
    X = prepare(frame, NUMERIC, CATEGORICAL)
    y = frame["final_yield"].to_numpy()
    model = spec.make(dict(spec.defaults), NUMERIC, CATEGORICAL, 0).fit(X, y)
    pred = model.predict(X)
    assert np.isfinite(pred).all()

    schema = FeatureSchema(
        features=[
            FeatureSpec(
                name=c,
                dtype="category" if c in CATEGORICAL else "float",
                nullable=c not in CATEGORICAL,
                category="Vegetation",
            )
            for c in X.columns
        ]
    )
    meta = ModelMetadata(
        model_id=f"test-{spec.name}",
        algorithm=spec.algorithm,
        target="yield",
        metrics=Metrics(rmse=1, mae=1, r2=0.5),
        validation="test",
        feature_count=len(X.columns),
        trained_at="2026-09-24T00:00:00+00:00",
        as_of="07-31",
        interval=PredictionInterval(level=0.9, lower_offset=-10, upper_offset=10),
    )
    artifact = ModelArtifact.load(save_artifact(model, meta, schema, tmp_path))
    assert artifact.schema.names == list(X.columns)  # feature order matches the schema
    rows = [
        {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()}
        for r in X.head(5).to_dict(orient="records")
    ]
    served = [p.yield_ for p in artifact.predict(rows)]
    assert served == pytest.approx(np.round(pred[:5], 1), abs=0.051)


def test_interval_offsets_cover_the_requested_share():
    rng = np.random.default_rng(1)
    residuals = rng.normal(0, 10, 2000)
    lo, hi = interval_offsets(residuals, 0.9)
    assert lo < 0 < hi
    fresh = rng.normal(0, 10, 5000)
    assert coverage(fresh, np.zeros_like(fresh), (lo, hi)) == pytest.approx(0.9, abs=0.02)


def test_simpler_model_wins_when_close():
    from soilsignal_ml.models.train import Evaluation

    def ev(spec, mae, std=0.0):
        return Evaluation(
            spec, {}, np.array([]), [], {"cv_mae": mae, "cv_mae_std": std}, (0, 0), 0.9, 0.0
        )

    by_name = {s.name: s for s in LADDER}
    close = [ev(by_name["random_forest"], 20.3), ev(by_name["catboost"], 20.0)]
    assert select(close, 0.03).spec.name == "random_forest"
    clear = [ev(by_name["random_forest"], 25.0), ev(by_name["catboost"], 20.0)]
    assert select(clear, 0.03).spec.name == "catboost"


def test_consistent_model_beats_erratic_one():
    """Brief §45: 10.3 ± 2 is preferred to 9.5 ± 8."""
    from soilsignal_ml.models.train import Evaluation

    def ev(spec, mae, std):
        return Evaluation(
            spec, {}, np.array([]), [], {"cv_mae": mae, "cv_mae_std": std}, (0, 0), 0.9, 0.0
        )

    by_name = {s.name: s for s in LADDER}
    erratic, steady = ev(by_name["ridge"], 9.5, 8.0), ev(by_name["catboost"], 10.3, 2.0)
    assert select([erratic, steady], 0.03).spec.name == "catboost"


def test_prepare_casts_types(frame):
    X = prepare(frame, NUMERIC, CATEGORICAL)
    assert X["genotype"].map(type).eq(str).all()
    assert pd.api.types.is_float_dtype(X["ndvi_current"])
