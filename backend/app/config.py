from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings, overridable with SOILSIGNAL_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="SOILSIGNAL_", env_file=".env", extra="ignore")

    version: str = "0.1.0"
    mock_data_path: Path = BACKEND_ROOT / "data" / "mock" / "fields.json"
    # One subdirectory per exported model (see app/model/contract.py).
    model_dir: Path = BACKEND_ROOT / "artifacts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
