"""
Forecast data providers.

Routes depend on the ForecastProvider protocol only. Today the mock provider
serves the demo dataset; once the challenge model exists, a model-backed
provider implementing the same protocol replaces it without touching routes.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from app.config import get_settings
from app.schemas import FieldForecast, FieldMeta


class ForecastProvider(Protocol):
    name: str

    def list_fields(self) -> list[FieldMeta]: ...

    def get_forecast(self, field_id: str) -> FieldForecast | None: ...


class MockForecastProvider:
    """Serves the demo dataset exported from the frontend (npm run export:mock)."""

    name = "mock"

    def __init__(self, data_path: Path) -> None:
        raw = json.loads(data_path.read_text())
        forecasts = TypeAdapter(list[FieldForecast]).validate_python(raw)
        self._forecasts = {f.field.id: f for f in forecasts}

    def list_fields(self) -> list[FieldMeta]:
        return [f.field for f in self._forecasts.values()]

    def get_forecast(self, field_id: str) -> FieldForecast | None:
        return self._forecasts.get(field_id)


@lru_cache
def get_provider() -> ForecastProvider:
    return MockForecastProvider(get_settings().mock_data_path)
