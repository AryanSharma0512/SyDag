"""
Forecast data providers.

Routes depend on the ForecastProvider protocol only. SOILSIGNAL_DATA_SOURCE picks one:

    model  ModelForecastProvider: exported models + raw-input bundles (production)
    mock   MockForecastProvider: the frontend's demo dataset (tests, UI work)

A broken model setup raises instead of falling back to demo data, so the API can
never present mock numbers as model output.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from app.config import get_settings
from app.forecast.builder import ForecastBuilder
from app.forecast.bundle import Bundle
from app.model.artifact import ModelRegistry
from app.schemas import FieldForecast, FieldMeta


class ForecastProvider(Protocol):
    name: str
    dataset_label: str

    def list_fields(self) -> list[FieldMeta]: ...

    def get_forecast(self, field_id: str) -> FieldForecast | None: ...


class MockForecastProvider:
    """Serves the demo dataset exported from the frontend (npm run export:mock)."""

    name = "mock"
    dataset_label = "Demo data"

    def __init__(self, data_path: Path) -> None:
        raw = json.loads(data_path.read_text())
        forecasts = TypeAdapter(list[FieldForecast]).validate_python(raw)
        self._forecasts = {f.field.id: f for f in forecasts}

    def list_fields(self) -> list[FieldMeta]:
        return [f.field for f in self._forecasts.values()]

    def get_forecast(self, field_id: str) -> FieldForecast | None:
        return self._forecasts.get(field_id)


class ProviderError(RuntimeError):
    """The configured data source can't serve forecasts (missing models or bundles)."""


class ModelForecastProvider:
    """Forecasts computed from raw field inputs with the exported models."""

    name = "model"

    def __init__(self, data_dir: Path, registry: ModelRegistry) -> None:
        bundles = sorted(data_dir.glob("*.json")) if data_dir.is_dir() else []
        if not bundles:
            raise ProviderError(f"no input bundles in {data_dir}")
        if not any(a.metadata.as_of for a in registry.artifacts):
            raise ProviderError("no dated model artifacts are loaded")
        self._fields: dict[str, tuple[ForecastBuilder, object]] = {}
        labels = []
        for path in bundles:
            builder = ForecastBuilder(Bundle.load(path), registry)
            labels.append(builder.bundle.source["short_name"])
            for field in builder.bundle.fields:
                self._fields[builder.field_id(field)] = (builder, field)
        self.dataset_label = " + ".join(dict.fromkeys(labels))
        self._cache: dict[str, FieldForecast] = {}

    def list_fields(self) -> list[FieldMeta]:
        return [builder.field_meta(field) for builder, field in self._fields.values()]

    def get_forecast(self, field_id: str) -> FieldForecast | None:
        if field_id not in self._fields:
            return None
        if field_id not in self._cache:
            builder, field = self._fields[field_id]
            self._cache[field_id] = builder.forecast(field)
        return self._cache[field_id]


@lru_cache
def get_provider() -> ForecastProvider:
    """Raises ProviderError (not cached, so the next call retries) if the model data
    source is misconfigured; there is deliberately no fallback to mock data."""
    settings = get_settings()
    if settings.data_source == "mock":
        return MockForecastProvider(settings.mock_data_path)
    return ModelForecastProvider(settings.practice_data_dir, get_registry())


@lru_cache
def get_registry() -> ModelRegistry:
    """Loaded once per process; restart the API after adding or replacing artifacts.
    Raises ArtifactError if any artifact is broken (not cached, so the next call retries)."""
    return ModelRegistry.load(get_settings().model_dir)
