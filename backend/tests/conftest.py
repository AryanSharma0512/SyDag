import pytest

from app.config import get_settings
from app.context.cache import get_context_cache
from app.providers import get_provider, get_registry


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_provider.cache_clear()
    get_registry.cache_clear()
    get_context_cache.cache_clear()


@pytest.fixture(autouse=True)
def isolated_model_dir(tmp_path, monkeypatch):
    """Point the API at an empty per-test artifacts dir so local artifacts never leak in."""
    model_dir = tmp_path / "artifacts"
    model_dir.mkdir()
    monkeypatch.setenv("SOILSIGNAL_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("SOILSIGNAL_CACHE_DIR", str(tmp_path / "context-cache"))
    monkeypatch.delenv("SOILSIGNAL_NASS_API_KEY", raising=False)
    _clear_caches()
    yield model_dir
    _clear_caches()
