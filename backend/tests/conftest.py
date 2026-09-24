import pytest

from app.config import get_settings
from app.providers import get_provider, get_registry


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_provider.cache_clear()
    get_registry.cache_clear()


@pytest.fixture(autouse=True)
def isolated_model_dir(tmp_path, monkeypatch):
    """Point the API at an empty per-test artifacts dir so local artifacts never leak in."""
    model_dir = tmp_path / "artifacts"
    model_dir.mkdir()
    monkeypatch.setenv("SOILSIGNAL_MODEL_DIR", str(model_dir))
    _clear_caches()
    yield model_dir
    _clear_caches()
