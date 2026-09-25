"""
End to end: practice dataset -> feature pipeline -> trained model -> exported artifact ->
FastAPI. The forecast the API serves for a showcase plot must equal the prediction the
training run made for that same held-out plot. No yield is typed in anywhere.
"""

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.providers import get_provider, get_registry
from soilsignal_ml import BACKEND_ROOT
from soilsignal_ml.models.train import CANDIDATES, load_cutoffs

BUNDLE = BACKEND_ROOT / "data" / "practice" / "shrestha2024.json"
MODELS = sorted((BACKEND_ROOT / "artifacts").glob("soilsignal-maize-*"))


@pytest.fixture
def api(monkeypatch, tmp_path):
    if not BUNDLE.exists() or not MODELS or not CANDIDATES.exists():
        pytest.skip("needs a local training run, its export and the showcase bundle")
    model_dir = tmp_path / "models"
    for folder in MODELS:
        shutil.copytree(folder, model_dir / folder.name)
    monkeypatch.setenv("SOILSIGNAL_DATA_SOURCE", "model")
    monkeypatch.setenv("SOILSIGNAL_MODEL_DIR", str(model_dir))
    for cache in (get_settings, get_provider, get_registry):
        cache.cache_clear()
    yield TestClient(app)
    for cache in (get_provider, get_registry):
        cache.cache_clear()


@pytest.mark.parametrize("cfg", load_cutoffs(), ids=lambda c: c["name"])
def test_api_serves_the_training_runs_held_out_prediction(api, cfg):
    summary = json.loads((CANDIDATES / cfg["name"] / "summary.json").read_text())
    predicted = {r["plot_id"]: r["predicted"] for r in summary["holdout_predictions"]}
    bundle = json.loads(BUNDLE.read_text())
    year = bundle["season_year"]
    for field in bundle["fields"]:
        forecast = api.get(f"/api/fields/{field['plot_id'].lower()}/forecast").json()
        snap = next(s for s in forecast["snapshots"] if s["date"] == f"{year}-{cfg['as_of']}")
        assert snap["yield"] == pytest.approx(predicted[field["plot_id"]], abs=0.051)
