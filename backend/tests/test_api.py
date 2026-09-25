import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.providers import get_provider

client = TestClient(app)
MOCK_DATA = json.loads(get_settings().mock_data_path.read_text())
FIELD_IDS = [f["field"]["id"] for f in MOCK_DATA]


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {
        "status": "ok",
        "version": get_settings().version,
        "dataSource": "mock",
        "modelsLoaded": 0,
        "datasetLabel": "Demo data",
    }


def test_model_source_without_models_fails_loudly(monkeypatch, tmp_path):
    """No silent fallback: a model data source that can't serve returns 503, and
    health says so instead of pretending to be mock or model."""
    monkeypatch.setenv("SOILSIGNAL_DATA_SOURCE", "model")
    monkeypatch.setenv("SOILSIGNAL_PRACTICE_DATA_DIR", str(tmp_path / "none"))
    get_settings.cache_clear()
    get_provider.cache_clear()
    res = client.get("/api/fields")
    assert res.status_code == 503
    assert "Forecasts are unavailable" in res.json()["detail"]
    health = client.get("/api/health").json()
    assert (health["dataSource"], health["modelsLoaded"]) == ("unavailable", 0)


def test_list_fields_returns_every_mock_field():
    res = client.get("/api/fields")
    assert res.status_code == 200
    assert [f["id"] for f in res.json()] == FIELD_IDS


@pytest.mark.parametrize("field_id", FIELD_IDS)
def test_forecast_matches_frontend_mock_exactly(field_id):
    """The API must return byte-for-byte what the frontend mock contains, so swapping
    DEMO_MODE off in the dashboard changes nothing visible."""
    expected = next(f for f in MOCK_DATA if f["field"]["id"] == field_id)
    res = client.get(f"/api/fields/{field_id}/forecast")
    assert res.status_code == 200
    assert res.json() == expected


def test_get_field():
    res = client.get("/api/fields/purdue-104")
    assert res.status_code == 200
    assert res.json()["name"] == "Purdue Plot 104"


def test_weather_defaults_to_latest_snapshot():
    snapshots = MOCK_DATA[0]["snapshots"]
    res = client.get(f"/api/fields/{FIELD_IDS[0]}/weather")
    assert res.json() == snapshots[-1]["weather"]


def test_weather_for_specific_snapshot():
    snapshot = MOCK_DATA[0]["snapshots"][1]
    res = client.get(f"/api/fields/{FIELD_IDS[0]}/weather", params={"snapshotId": snapshot["id"]})
    assert res.json() == snapshot["weather"]


def test_soil():
    res = client.get(f"/api/fields/{FIELD_IDS[0]}/soil")
    assert res.json() == MOCK_DATA[0]["snapshots"][0]["soil"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/fields/nope",
        "/api/fields/nope/forecast",
        "/api/fields/nope/weather",
        "/api/fields/nope/soil",
        "/api/fields/purdue-104/weather?snapshotId=nope",
    ],
)
def test_unknown_ids_return_404(path):
    res = client.get(path)
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]
