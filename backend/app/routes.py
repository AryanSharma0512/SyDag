from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.config import get_settings
from app.forecast.evaluation import imagery_ablation
from app.model.artifact import ArtifactError, FeatureValidationError, ModelArtifact, ModelRegistry
from app.providers import ForecastProvider, ProviderError, get_provider, get_registry
from app.schemas import (
    DecisionSet,
    FeatureImportanceItem,
    FieldForecast,
    FieldMeta,
    Health,
    HoldoutInfo,
    ImageryAblation,
    ModelInfo,
    PredictRequest,
    PredictResponse,
    SoilContext,
    WeatherContext,
)

router = APIRouter(prefix="/api")


def _provider() -> ForecastProvider:
    try:
        return get_provider()
    except (ProviderError, ArtifactError) as err:
        raise HTTPException(status_code=503, detail=f"Forecasts are unavailable: {err}") from err


Provider = Annotated[ForecastProvider, Depends(_provider)]


def _registry() -> ModelRegistry:
    try:
        registry = get_registry()
    except ArtifactError as err:
        raise HTTPException(
            status_code=503, detail=f"Model artifacts failed to load: {err}"
        ) from err
    if not registry.artifacts:
        raise HTTPException(status_code=503, detail="No model artifacts are loaded")
    return registry


Registry = Annotated[ModelRegistry, Depends(_registry)]


def _forecast_or_404(provider: ForecastProvider, field_id: str) -> FieldForecast:
    forecast = provider.get_forecast(field_id)
    if forecast is None:
        raise HTTPException(status_code=404, detail=f"Field '{field_id}' not found")
    return forecast


@router.get("/health")
def health() -> Health:
    """Always answers, so a broken data source shows up here instead of as a dead API:
    dataSource "unavailable" and modelsLoaded 0 mean forecasts will return 503."""
    try:
        models_loaded = len(get_registry().artifacts)
    except ArtifactError:
        models_loaded = 0
    try:
        provider = get_provider()
        source, label = provider.name, provider.dataset_label
    except (ProviderError, ArtifactError):
        source, label = "unavailable", "Unavailable"
    return Health(
        status="ok",
        version=get_settings().version,
        data_source=source,
        models_loaded=models_loaded,
        dataset_label=label,
    )


# Optional fields the provider leaves unset are omitted, matching `field?: T` in the TS types.
@router.get("/fields", response_model_exclude_none=True)
def list_fields(provider: Provider) -> list[FieldMeta]:
    """The featured plots. Every plot in /api/decisions also resolves by id below."""
    return provider.list_fields()


@router.get("/fields/{field_id}", response_model_exclude_none=True)
def get_field(field_id: str, provider: Provider) -> FieldMeta:
    return _forecast_or_404(provider, field_id).field


@router.get("/fields/{field_id}/forecast", response_model_exclude_none=True)
def get_forecast(field_id: str, provider: Provider) -> FieldForecast:
    return _forecast_or_404(provider, field_id)


@router.get("/fields/{field_id}/weather")
def get_weather(
    field_id: str,
    provider: Provider,
    snapshot_id: Annotated[str | None, Query(alias="snapshotId")] = None,
) -> WeatherContext:
    """Weather as of a forecast snapshot; defaults to the latest snapshot."""
    snapshots = _forecast_or_404(provider, field_id).snapshots
    if snapshot_id is None:
        return snapshots[-1].weather
    for snapshot in snapshots:
        if snapshot.id == snapshot_id:
            return snapshot.weather
    raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")


@router.get("/fields/{field_id}/soil")
def get_soil(field_id: str, provider: Provider) -> SoilContext:
    # Soil properties are static through the season, so any snapshot's copy is representative.
    return _forecast_or_404(provider, field_id).snapshots[0].soil


@router.get("/decisions")
def get_decisions(
    provider: Provider,
    as_of_date: Annotated[date | None, Query(alias="asOfDate")] = None,
) -> DecisionSet:
    """Every plot in the season at one point in time, for choosing where to scout. Each
    plot uses its latest forecast on or before `asOfDate` (default: the latest one), so
    nothing from after that date is used. Same models and features as the dashboard."""
    decisions = provider.get_decisions(as_of_date)
    if decisions is None:
        season = f"the {as_of_date.year} season" if as_of_date else "any season"
        raise HTTPException(status_code=404, detail=f"No plots in {season}")
    if not decisions.plots:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast uses only data available by {decisions.as_of_date}",
        )
    return decisions


@router.get("/evaluation/imagery")
def get_imagery_ablation() -> ImageryAblation:
    """Validation error with and without satellite imagery, once the ML team publishes it."""
    try:
        return imagery_ablation(get_settings().model_dir)
    except (ValidationError, ValueError) as err:
        raise HTTPException(
            status_code=503, detail=f"The imagery comparison could not be read: {err}"
        ) from err


@router.get("/models")
def list_models(registry: Registry) -> list[ModelInfo]:
    return [
        ModelInfo(
            model_id=m.model_id,
            algorithm=m.algorithm,
            target=m.target,
            unit=m.unit,
            validation=m.validation,
            rmse=m.metrics.rmse,
            mae=m.metrics.mae,
            r2=m.metrics.r2,
            trained_at=m.trained_at,
            as_of=m.as_of,
            interval_level=m.interval.level,
            features=a.schema.names,
            dataset=m.dataset,
            holdout=HoldoutInfo(
                group=m.holdout.group,
                mae=m.holdout.metrics.mae,
                rmse=m.holdout.metrics.rmse,
                r2=m.holdout.metrics.r2,
                interval_coverage=m.holdout.interval_coverage,
                n=m.holdout.n,
            )
            if m.holdout
            else None,
        )
        for a in registry.artifacts
        for m in [a.metadata]
    ]


def _select_model(registry: ModelRegistry, req: PredictRequest) -> ModelArtifact:
    if req.model_id is not None:
        artifact = registry.get(req.model_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Model '{req.model_id}' not found")
        return artifact
    if req.as_of_date is not None:
        artifact = registry.for_date(req.as_of_date)
        if artifact is None:
            raise HTTPException(
                status_code=404, detail=f"No model uses only data available by {req.as_of_date}"
            )
        return artifact
    return registry.artifacts[-1]


@router.post("/predict")
def predict(req: PredictRequest, registry: Registry) -> PredictResponse:
    artifact = _select_model(registry, req)
    try:
        [pred] = artifact.predict([req.features])
    except FeatureValidationError as err:
        raise HTTPException(status_code=422, detail=err.problems) from err
    return PredictResponse(
        model_id=artifact.metadata.model_id,
        yield_=pred.yield_,
        unit=artifact.metadata.unit,
        lower_bound=pred.lower_bound,
        upper_bound=pred.upper_bound,
        interval_level=artifact.metadata.interval.level,
        confidence=pred.confidence,
        confidence_rating=pred.confidence_rating,
        drivers=[
            FeatureImportanceItem(
                name=d.label, weight=d.weight, category=d.category, direction=d.direction
            )
            for d in pred.drivers
        ],
    )
