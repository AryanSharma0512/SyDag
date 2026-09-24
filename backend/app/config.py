from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings, overridable with SOILSIGNAL_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="SOILSIGNAL_", env_file=".env", extra="ignore")

    version: str = "0.1.0"
    mock_data_path: Path = BACKEND_ROOT / "data" / "mock" / "fields.json"
    # One subdirectory per exported model (see app/model/contract.py).
    model_dir: Path = BACKEND_ROOT / "artifacts"

    # Location context (/api/context/*)
    cache_dir: Path = BACKEND_ROOT / "cache"
    context_timeout_seconds: float = 20.0
    # Free key from https://quickstats.nass.usda.gov/api; county yields stay off without it.
    nass_api_key: SecretStr | None = None
    # Season totals (growing degree days, heat days, dry spells) count from this date each year.
    season_start: str = "05-01"

    @field_validator("nass_api_key", mode="before")
    @classmethod
    def _blank_key_is_unset(cls, value: object) -> object:
        # Compose passes an empty string when the key isn't set.
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
