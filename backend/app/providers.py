"""
Forecast data providers.

Routes depend on the ForecastProvider protocol only. SOILSIGNAL_DATA_SOURCE picks one:

    model  ModelForecastProvider: exported models + raw-input bundles (production)
    mock   MockForecastProvider: the frontend's demo dataset (tests, UI work)

A broken model setup raises instead of falling back to demo data, so the API can
never present mock numbers as model output.
"""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from app.config import get_settings
from app.forecast.builder import ForecastBuilder
from app.forecast.bundle import Bundle, ShowcaseField
from app.model.artifact import ModelRegistry
from app.schemas import (
    DecisionSet,
    FeatureImportanceItem,
    FieldForecast,
    FieldMeta,
    ForecastSnapshot,
    PlotDecision,
)


class ForecastProvider(Protocol):
    name: str
    dataset_label: str

    def list_fields(self) -> list[FieldMeta]: ...

    def get_forecast(self, field_id: str) -> FieldForecast | None: ...

    def get_decisions(self, as_of: date | None) -> DecisionSet | None:
        """Every plot in the season of `as_of`, each at its latest forecast on or before
        that date (default: the latest date served). None when no plot is in that season."""
        ...


def _decision_set(
    as_of: date, plots: list[PlotDecision], unit: str = "bu/ac", interval_level: float = 0.9
) -> DecisionSet:
    return DecisionSet(
        as_of_date=as_of.isoformat(), unit=unit, interval_level=interval_level, plots=plots
    )


def _top_negative(items: list[FeatureImportanceItem]) -> str | None:
    ranked = sorted(items, key=lambda f: -f.weight)
    return next((f.name for f in ranked if f.direction == "negative"), None)


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

    def get_decisions(self, as_of: date | None) -> DecisionSet | None:
        if as_of is None:
            as_of = max(date.fromisoformat(f.snapshots[-1].date) for f in self._forecasts.values())
        plots = []
        for f in self._forecasts.values():
            if f.field.season != as_of.year:
                continue
            eligible = [s for s in f.snapshots if date.fromisoformat(s.date) <= as_of]
            if eligible:
                plots.append(self._decision(f.field, eligible[-1], eligible[-2:-1]))
        seasons = {f.field.season for f in self._forecasts.values()}
        return _decision_set(as_of, plots) if as_of.year in seasons else None

    @staticmethod
    def _decision(
        field: FieldMeta, s: ForecastSnapshot, previous: list[ForecastSnapshot]
    ) -> PlotDecision:
        prior = previous[0] if previous else None
        return PlotDecision(
            field_id=field.id,
            plot_id=field.plot_id,
            name=field.name,
            site=field.site,
            season=field.season,
            hybrid=field.hybrid,
            nitrogen_lb_ac=field.nitrogen_lb_ac,
            irrigation_status=field.irrigation_status,
            forecast_date=s.date,
            predicted_yield=s.yield_,
            lower_bound=s.lower_bound,
            upper_bound=s.upper_bound,
            confidence=s.confidence,
            confidence_rating=s.confidence_rating,
            previous_forecast_date=prior.date if prior else None,
            previous_yield=prior.yield_ if prior else None,
            change_since_previous=round(s.yield_ - prior.yield_, 1) if prior else None,
            top_negative_driver=_top_negative(s.feature_importance),
        )


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
        self._registry = registry
        self._builders: list[ForecastBuilder] = []
        # The showcase fields are listed; every other bundled plot is reachable by id
        # (the scouting queue links to them).
        self._fields: dict[str, tuple[ForecastBuilder, ShowcaseField]] = {}
        self._plots: dict[str, tuple[ForecastBuilder, ShowcaseField]] = {}
        labels = []
        for path in bundles:
            builder = ForecastBuilder(Bundle.load(path), registry)
            self._builders.append(builder)
            labels.append(builder.bundle.source["short_name"])
            for field in builder.bundle.fields:
                self._fields[builder.field_id(field)] = (builder, field)
            for pid in builder.bundle.plots:
                field = builder.plot_field(pid)
                self._plots[builder.field_id(field)] = (builder, field)
        self.dataset_label = " + ".join(dict.fromkeys(labels))
        self._cache: dict[str, FieldForecast] = {}

    def list_fields(self) -> list[FieldMeta]:
        return [builder.field_meta(field) for builder, field in self._fields.values()]

    def get_forecast(self, field_id: str) -> FieldForecast | None:
        if field_id not in self._plots:
            return None
        if field_id not in self._cache:
            builder, field = self._plots[field_id]
            self._cache[field_id] = builder.forecast(field)
        return self._cache[field_id]

    def get_decisions(self, as_of: date | None) -> DecisionSet | None:
        if as_of is None:
            as_of = max(d for b in self._builders for d in b.dates)
        season = [b for b in self._builders if b.bundle.season_year == as_of.year]
        if not season:
            return None
        plots = [p for b in season for p in b.decisions(as_of)]
        artifact = self._registry.for_date(as_of.isoformat())
        if artifact is None:
            return _decision_set(as_of, plots)
        meta = artifact.metadata
        return _decision_set(as_of, plots, meta.unit, meta.interval.level)


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
