import json
import math

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from app.main import app
from app.model.artifact import (
    ArtifactError,
    FeatureValidationError,
    ModelArtifact,
    ModelRegistry,
    confidence_from_interval,
)
from app.model.contract import (
    FeatureSchema,
    FeatureSpec,
    Metrics,
    ModelMetadata,
    PredictionInterval,
)
from app.model.export import save_artifact

client = TestClient(app)

SCHEMA = FeatureSchema(
    features=[
        FeatureSpec(
            name="ndvi_mid", label="NDVI mid-season", category="Vegetation", direction="positive"
        ),
        FeatureSpec(
            name="rain_30d", label="30-day rainfall", category="Weather", direction="positive"
        ),
        FeatureSpec(name="soil_awc", category="Soil", nullable=True),
    ]
)


def _training_frame(n: int = 200, seed: int = 0) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        {
            "ndvi_mid": rng.uniform(0.4, 0.9, n),
            "rain_30d": rng.uniform(10, 120, n),
            "soil_awc": rng.uniform(0.1, 0.25, n),
        }
    )
    y = 100 + 120 * X["ndvi_mid"] + 0.2 * X["rain_30d"] + 30 * X["soil_awc"]
    return X, y.to_numpy()


def _metadata(model_id: str = "test-v1", as_of: str | None = None, **overrides) -> ModelMetadata:
    fields = dict(
        model_id=model_id,
        algorithm="linear",
        target="yield_bu_ac",
        metrics=Metrics(rmse=10.0, mae=8.0, r2=0.8),
        validation="leave-field-out",
        feature_count=3,
        trained_at="2026-09-24T00:00:00Z",
        as_of=as_of,
        interval=PredictionInterval(level=0.9, lower_offset=-12.0, upper_offset=13.0),
    )
    return ModelMetadata(**(fields | overrides))


def _linear_model() -> LinearRegression:
    X, y = _training_frame()
    return LinearRegression().fit(X, y)


ROW = {"ndvi_mid": 0.8, "rain_30d": 60.0, "soil_awc": 0.2}
EXPECTED_POINT = 100 + 120 * 0.8 + 0.2 * 60 + 30 * 0.2  # 214.0


# ---- artifact round trip and prediction -------------------------------------


def test_export_then_load_round_trips(isolated_model_dir):
    path = save_artifact(_linear_model(), _metadata(), SCHEMA, isolated_model_dir)
    assert sorted(p.name for p in path.iterdir()) == [
        "feature_schema.json",
        "metadata.json",
        "model.joblib",
    ]
    artifact = ModelArtifact.load(path)
    assert artifact.metadata == _metadata()
    assert artifact.schema == SCHEMA


def test_predict_applies_interval_offsets():
    artifact = ModelArtifact(_metadata(), SCHEMA, _linear_model())
    [pred] = artifact.predict([ROW])
    assert pred.yield_ == pytest.approx(EXPECTED_POINT, abs=0.1)
    assert pred.lower_bound == pytest.approx(pred.yield_ - 12.0, abs=0.1)
    assert pred.upper_bound == pytest.approx(pred.yield_ + 13.0, abs=0.1)


def test_predict_accepts_null_for_nullable_feature():
    # Tree ensembles in sklearn accept NaN; linear models would not.
    X, y = _training_frame()
    forest = RandomForestRegressor(n_estimators=10, random_state=0).fit(X, y)
    artifact = ModelArtifact(_metadata(), SCHEMA, forest)
    [pred] = artifact.predict([ROW | {"soil_awc": None}])
    assert math.isfinite(pred.yield_)


@pytest.mark.parametrize(
    "row, problem",
    [
        ({"ndvi_mid": 0.8, "rain_30d": 60.0}, "missing features ['soil_awc']"),
        (ROW | {"extra": 1}, "unknown features ['extra']"),
        (ROW | {"ndvi_mid": None}, "'ndvi_mid' may not be null"),
        (ROW | {"rain_30d": "wet"}, "'rain_30d' must be a number"),
        (ROW | {"rain_30d": True}, "'rain_30d' must be a number"),
        (ROW | {"rain_30d": float("inf")}, "'rain_30d' must be finite"),
    ],
)
def test_predict_rejects_bad_input(row, problem):
    artifact = ModelArtifact(_metadata(), SCHEMA, _linear_model())
    with pytest.raises(FeatureValidationError) as exc:
        artifact.predict([row])
    assert any(problem in p for p in exc.value.problems)


@pytest.mark.parametrize(
    "point, lower, upper, expected",
    [
        (184.3, 171.2, 196.7, (86, "HIGH")),  # Purdue 104 mock: shown as 87%
        (160.0, 140.0, 180.0, (75, "MODERATE")),
        (150.0, 80.0, 220.0, (7, "LOW")),
        (0.0, -5.0, 5.0, (0.0, "LOW")),
    ],
)
def test_confidence_from_interval(point, lower, upper, expected):
    assert confidence_from_interval(point, lower, upper) == expected


def test_drivers_prefer_schema_importance_over_estimator():
    schema = FeatureSchema(
        features=[
            f.model_copy(update={"importance": imp})
            for f, imp in zip(SCHEMA.features, [3.0, 1.0, 0.0], strict=True)
        ]
    )
    artifact = ModelArtifact(_metadata(), schema, _linear_model())
    assert [(d.label, d.weight, d.direction) for d in artifact.drivers] == [
        ("NDVI mid-season", 75.0, "positive"),
        ("30-day rainfall", 25.0, "positive"),
        ("soil_awc", 0.0, "neutral"),
    ]


def test_drivers_fall_back_to_feature_importances():
    X, y = _training_frame()
    forest = RandomForestRegressor(n_estimators=10, random_state=0).fit(X, y)
    artifact = ModelArtifact(_metadata(), SCHEMA, forest)
    assert artifact.drivers[0].label == "NDVI mid-season"  # dominant in the synthetic target
    assert sum(d.weight for d in artifact.drivers) == pytest.approx(100, abs=0.2)


def test_linear_model_without_importance_has_no_drivers():
    assert ModelArtifact(_metadata(), SCHEMA, _linear_model()).drivers == []


# ---- artifact consistency checks --------------------------------------------


def test_rejects_feature_count_mismatch():
    with pytest.raises(ArtifactError, match="feature_count=4"):
        ModelArtifact(_metadata(feature_count=4), SCHEMA, _linear_model())


def test_rejects_column_order_mismatch():
    reordered = FeatureSchema(features=list(reversed(SCHEMA.features)))
    with pytest.raises(ArtifactError, match="names and order must match"):
        ModelArtifact(_metadata(), reordered, _linear_model())


def test_rejects_missing_files(isolated_model_dir):
    broken = isolated_model_dir / "broken"
    broken.mkdir()
    (broken / "metadata.json").write_text("{}")
    with pytest.raises(ArtifactError, match="missing model.joblib, feature_schema.json"):
        ModelArtifact.load(broken)


def test_rejects_invalid_metadata(isolated_model_dir):
    path = save_artifact(_linear_model(), _metadata(), SCHEMA, isolated_model_dir)
    meta = json.loads((path / "metadata.json").read_text())
    meta["as_of"] = "July 15"
    (path / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ArtifactError, match="as_of must be 'MM-DD'"):
        ModelArtifact.load(path)


def test_rejects_unsafe_model_id():
    with pytest.raises(ValueError, match="model_id may only contain"):
        _metadata(model_id="../escape")


def test_rejects_duplicate_feature_names():
    with pytest.raises(ValueError, match="duplicate feature names"):
        FeatureSchema(features=[SCHEMA.features[0], SCHEMA.features[0]])


def test_export_refuses_inconsistent_artifact_without_writing(isolated_model_dir):
    with pytest.raises(ArtifactError):
        save_artifact(_linear_model(), _metadata(feature_count=9), SCHEMA, isolated_model_dir)
    assert list(isolated_model_dir.iterdir()) == []


def test_registry_rejects_directory_name_mismatch(isolated_model_dir):
    save_artifact(_linear_model(), _metadata("a"), SCHEMA, isolated_model_dir)
    (isolated_model_dir / "a").rename(isolated_model_dir / "b")
    with pytest.raises(ArtifactError, match="must match"):
        ModelRegistry.load(isolated_model_dir)


def test_registry_ignores_in_progress_exports(isolated_model_dir):
    save_artifact(_linear_model(), _metadata("a"), SCHEMA, isolated_model_dir)
    (isolated_model_dir / ".a.tmp").mkdir()
    (isolated_model_dir / ".a.tmp" / "metadata.json").write_text("{}")
    assert [a.metadata.model_id for a in ModelRegistry.load(isolated_model_dir).artifacts] == ["a"]


def test_registry_on_missing_dir_is_empty(tmp_path):
    assert ModelRegistry.load(tmp_path / "nope").artifacts == []


# ---- point-in-time model selection ------------------------------------------


def _registry(*as_ofs: str | None) -> ModelRegistry:
    model = _linear_model()
    return ModelRegistry(
        [ModelArtifact(_metadata(f"m-{a}", as_of=a), SCHEMA, model) for a in as_ofs]
    )


@pytest.mark.parametrize(
    "date, expected",
    [
        ("2026-06-14", None),  # before any cutoff: nothing is valid yet
        ("2026-06-15", "m-06-15"),  # cutoff day itself is allowed
        ("2026-07-20", "m-07-15"),
        ("2026-09-30", "m-09-01"),
    ],
)
def test_for_date_never_uses_a_later_cutoff(date, expected):
    reg = _registry("09-01", "06-15", "07-15", None)
    chosen = reg.for_date(date)
    assert (chosen.metadata.model_id if chosen else None) == expected


def test_for_date_uses_full_season_model_only_when_no_cutoff_models():
    assert _registry(None).for_date("2026-06-01").metadata.model_id == "m-None"


# ---- API ---------------------------------------------------------------------


def test_model_endpoints_503_without_artifacts():
    assert client.get("/api/models").status_code == 503
    res = client.post("/api/predict", json={"features": ROW})
    assert res.status_code == 503
    assert res.json()["detail"] == "No model artifacts are loaded"


def test_broken_artifact_503_but_mock_endpoints_still_work(isolated_model_dir):
    (isolated_model_dir / "broken").mkdir()
    (isolated_model_dir / "broken" / "metadata.json").write_text("{}")
    res = client.get("/api/models")
    assert res.status_code == 503
    assert "failed to load" in res.json()["detail"]
    assert client.get("/api/health").json()["modelsLoaded"] == 0
    assert client.get("/api/fields/purdue-104/forecast").status_code == 200


@pytest.fixture
def seasonal_models(isolated_model_dir):
    X, y = _training_frame()
    forest = RandomForestRegressor(n_estimators=20, random_state=0).fit(X, y)
    for as_of, offset in [("06-15", 30.0), ("08-01", 10.0)]:
        meta = _metadata(
            f"yield-{as_of}",
            as_of=as_of,
            algorithm="random_forest",
            interval=PredictionInterval(level=0.9, lower_offset=-offset, upper_offset=offset),
        )
        save_artifact(forest, meta, SCHEMA, isolated_model_dir)


def test_list_models(seasonal_models):
    res = client.get("/api/models")
    assert res.status_code == 200
    assert [(m["modelId"], m["asOf"], m["features"]) for m in res.json()] == [
        ("yield-06-15", "06-15", ["ndvi_mid", "rain_30d", "soil_awc"]),
        ("yield-08-01", "08-01", ["ndvi_mid", "rain_30d", "soil_awc"]),
    ]
    assert client.get("/api/health").json()["modelsLoaded"] == 2


def test_predict_as_of_date_picks_point_in_time_model(seasonal_models):
    early = client.post("/api/predict", json={"features": ROW, "asOfDate": "2026-07-01"}).json()
    late = client.post("/api/predict", json={"features": ROW, "asOfDate": "2026-08-15"}).json()
    assert early["modelId"] == "yield-06-15"
    assert late["modelId"] == "yield-08-01"
    # Later model has the narrower interval, so higher confidence.
    assert early["upperBound"] - early["lowerBound"] == pytest.approx(60.0, abs=0.2)
    assert late["upperBound"] - late["lowerBound"] == pytest.approx(20.0, abs=0.2)
    assert late["confidence"] > early["confidence"]


def test_predict_response_shape(seasonal_models):
    res = client.post("/api/predict", json={"features": ROW, "modelId": "yield-08-01"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "modelId",
        "yield",
        "unit",
        "lowerBound",
        "upperBound",
        "intervalLevel",
        "confidence",
        "confidenceRating",
        "drivers",
    }
    assert body["unit"] == "bu/ac"
    assert body["intervalLevel"] == 0.9
    assert body["lowerBound"] < body["yield"] < body["upperBound"]
    assert set(body["drivers"][0]) == {"name", "weight", "category", "direction"}


def test_predict_defaults_to_latest_model(seasonal_models):
    res = client.post("/api/predict", json={"features": ROW})
    assert res.json()["modelId"] == "yield-08-01"


@pytest.mark.parametrize(
    "payload, status, detail",
    [
        ({"features": ROW, "modelId": "nope"}, 404, "Model 'nope' not found"),
        ({"features": ROW, "asOfDate": "2026-05-01"}, 404, "No model uses only data"),
        ({"features": {"ndvi_mid": 0.8}}, 422, "missing features"),
    ],
)
def test_predict_errors(seasonal_models, payload, status, detail):
    res = client.post("/api/predict", json=payload)
    assert res.status_code == status
    assert detail in json.dumps(res.json()["detail"])


def test_predict_rejects_malformed_date(seasonal_models):
    res = client.post("/api/predict", json={"features": ROW, "asOfDate": "July 1"})
    assert res.status_code == 422


def test_dummy_model_script_produces_progressively_narrower_models(tmp_path):
    from scripts.make_dummy_model import CUTOFFS, synthetic_plots, train

    X, y = synthetic_plots(n=300, seed=1)
    for cutoff in CUTOFFS:
        train(cutoff, X, y, tmp_path)
    registry = ModelRegistry.load(tmp_path)
    widths = [
        a.metadata.interval.upper_offset - a.metadata.interval.lower_offset
        for a in registry.artifacts
    ]
    feature_counts = [a.metadata.feature_count for a in registry.artifacts]
    assert [a.metadata.as_of for a in registry.artifacts] == CUTOFFS
    assert feature_counts == sorted(feature_counts)
    assert widths[0] > widths[-1]
