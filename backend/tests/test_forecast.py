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


def test_fields_carry_the_trial_record_from_the_bundle(model_api, bundle):
    for meta in client.get("/api/fields").json():
        plot = next(p for pid, p in bundle.plots.items() if pid.lower() == meta["id"])
        assert meta["hybrid"] == plot.management["genotype"]
        assert meta["nitrogenLbAc"] == plot.management["nitrogen_lb_ac"]
        assert meta["site"] == bundle.site["name"]
        assert meta["plantingDate"] == plot.planting_date.isoformat()
        assert plot.plot_id.endswith(meta["plotId"])


def test_decisions_are_the_dashboard_forecasts_for_every_plot(model_api, bundle):
    """The scouting queue shows exactly what each plot's dashboard shows on that date."""
    for snap_date in ("2022-07-31", "2022-10-15"):
        plots = client.get("/api/decisions", params={"asOfDate": snap_date}).json()["plots"]
        assert len(plots) == len(bundle.plots)
        for field in bundle.fields:
            row = next(p for p in plots if p["fieldId"] == field.plot_id.lower())
            snaps = client.get(f"/api/fields/{row['fieldId']}/forecast").json()["snapshots"]
            i = next(i for i, s in enumerate(snaps) if s["date"] == snap_date)
            assert row["forecastDate"] == snap_date
            assert (row["predictedYield"], row["lowerBound"], row["upperBound"]) == (
                snaps[i]["yield"],
                snaps[i]["lowerBound"],
                snaps[i]["upperBound"],
            )
            assert row["confidence"] == snaps[i]["confidence"]
            assert row["previousForecastDate"] == snaps[i - 1]["date"]
            assert row["changeSincePrevious"] == round(snaps[i]["yield"] - snaps[i - 1]["yield"], 1)


def test_decisions_never_use_a_forecast_from_after_the_date(model_api):
    between = client.get("/api/decisions", params={"asOfDate": "2022-08-20"}).json()
    assert between["asOfDate"] == "2022-08-20"
    assert {p["forecastDate"] for p in between["plots"]} == {"2022-07-31"}
    early = client.get("/api/decisions", params={"asOfDate": "2022-05-01"})
    assert early.status_code == 404
    assert client.get("/api/decisions", params={"asOfDate": "2019-07-31"}).status_code == 404


def test_every_plot_in_the_queue_opens_on_the_dashboard(model_api):
    plots = client.get("/api/decisions").json()["plots"]
    listed = {f["id"] for f in client.get("/api/fields").json()}
    unlisted = next(p for p in plots if p["fieldId"] not in listed)
    forecast = client.get(f"/api/fields/{unlisted['fieldId']}/forecast").json()
    assert forecast["field"]["hybrid"] == unlisted["hybrid"]
    assert forecast["snapshots"][-1]["yield"] == unlisted["predictedYield"]
    zones = forecast["snapshots"][-1]["spatial"]["zones"]
    assert sum(z["name"].endswith("(this plot)") for z in zones) == 1


def test_models_report_their_held_out_accuracy(model_api):
    for info in client.get("/api/models").json():
        artifact = model_api.get(info["modelId"])
        assert info["holdout"]["mae"] == artifact.metadata.holdout.metrics.mae
        assert info["dataset"].startswith("Practice data")
