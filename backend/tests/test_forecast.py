"""Model-backed forecasts: the committed practice bundle and exported models, through the API.

Every number checked here is recomputed independently from the raw inputs with
build_features() and the model registry, so the dashboard can't be showing a typed-in value.
"""

import shutil
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import BACKEND_ROOT, get_settings
from app.features.build import build_features
from app.forecast.bundle import Bundle
from app.main import app
from app.model.artifact import ModelRegistry
from app.providers import get_provider, get_registry

ARTIFACTS = BACKEND_ROOT / "artifacts"
PRACTICE = BACKEND_ROOT / "data" / "practice"
MODELS = sorted(ARTIFACTS.glob("soilsignal-maize-*"))
BUNDLES = sorted(PRACTICE.glob("*.json"))

pytestmark = pytest.mark.skipif(
    not MODELS or not BUNDLES, reason="practice bundle or exported models not present"
)
client = TestClient(app)


@pytest.fixture
def model_api(monkeypatch, tmp_path):
    """The API in production mode, with only the committed practice models loaded."""
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    for folder in MODELS:
        shutil.copytree(folder, model_dir / folder.name)
    monkeypatch.setenv("SOILSIGNAL_DATA_SOURCE", "model")
    monkeypatch.setenv("SOILSIGNAL_MODEL_DIR", str(model_dir))
    get_settings.cache_clear()
    get_provider.cache_clear()
    get_registry.cache_clear()
    yield ModelRegistry.load(model_dir)
    get_provider.cache_clear()
    get_registry.cache_clear()


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return Bundle.load(BUNDLES[0])


def test_health_reports_model_source(model_api):
    health = client.get("/api/health").json()
    assert health["dataSource"] == "model"
    assert health["modelsLoaded"] == len(MODELS)
    assert health["datasetLabel"] == "Practice data"


def test_fields_are_the_bundle_plots(model_api, bundle):
    fields = client.get("/api/fields").json()
    assert [f["id"] for f in fields] == [f.plot_id.lower() for f in bundle.fields]
    assert all("held out of training" in f["location"] for f in fields)
    assert all(f["season"] == bundle.season_year for f in fields)


def test_every_snapshot_is_the_point_in_time_model_on_point_in_time_features(model_api, bundle):
    registry = model_api
    for field in bundle.fields:
        forecast = client.get(f"/api/fields/{field.plot_id.lower()}/forecast").json()
        snapshots = forecast["snapshots"]
        assert [s["date"] for s in snapshots] == sorted(s["date"] for s in snapshots)
        for snap in snapshots:
            as_of = date.fromisoformat(snap["date"])
            artifact = registry.for_date(snap["date"])
            assert artifact.metadata.as_of <= snap["date"][5:]
            features = build_features(bundle.inputs(field.plot_id), as_of)
            [expected] = artifact.predict([{n: features.get(n) for n in artifact.schema.names}])
            assert snap["yield"] == expected.yield_
            assert (snap["lowerBound"], snap["upperBound"]) == (
                expected.lower_bound,
                expected.upper_bound,
            )
            assert snap["confidence"] == expected.confidence
            assert artifact.metadata.model_id in snap["generatedAt"]


def test_map_appears_only_once_the_field_has_been_imaged(model_api, bundle):
    field = bundle.fields[0]
    first_image = min(o.day for o in bundle.plots[field.plot_id].canopy)
    forecast = client.get(f"/api/fields/{field.plot_id.lower()}/forecast").json()
    for snap in forecast["snapshots"]:
        imaged = date.fromisoformat(snap["date"]) >= first_image
        assert ("spatial" in snap) == imaged
        if imaged:
            zones = snap["spatial"]["zones"]
            assert len(zones) == 16 and snap["spatial"]["provenance"] == "model"
            assert sum(z["name"].endswith("(this plot)") for z in zones) == 1


def test_provenance_is_practice_public_and_model_only(model_api, bundle):
    field = bundle.fields[0]
    forecast = client.get(f"/api/fields/{field.plot_id.lower()}/forecast").json()
    roles = {s["role"] for s in forecast["sources"]}
    assert roles == {"practice", "public", "model"}  # nothing claims to be challenge data
    history = forecast["historical"]["yearlyYields"]
    assert all(y["year"] < bundle.season_year for y in history if y["type"] == "historical")


def test_bundle_holds_inputs_not_yields(bundle):
    text = BUNDLES[0].read_text()
    assert "final_yield" not in text and "yieldPerAcre" not in text
    assert all(y < bundle.season_year for y in bundle.county_yields)
