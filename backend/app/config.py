from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings, overridable with YIELDLENS_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="YIELDLENS_", env_file=".env", extra="ignore")

    version: str = "0.1.0"
    mock_data_path: Path = BACKEND_ROOT / "data" / "mock" / "fields.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
