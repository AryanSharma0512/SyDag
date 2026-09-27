from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.config import get_settings
from app.forecast.evaluation import imagery_ablation
from app.model.artifact import ArtifactError, FeatureValidationError, ModelArtifact, ModelRegistry
from app.providers import ForecastProvider, ProviderError, get_provider, get_registry
from app.results import PENDING, FinalResults, PlotForecast, ResultsError, load_results
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
from app.sites import SiteForecasts, SiteWeather, TrialSite, load_sites
from app.weather_outlook.history import LibraryError
from app.weather_outlook.service import OutlookRequestError, get_engine, weather_outlook

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
def list_fields(provider: Provider, site: str | None = None) -> list[FieldMeta]:
    """The featured plots. With `site`, every plot with a forecast at that trial site
    (the location selector's plot list). Every plot in /api/decisions resolves by id below."""
    if site is None:
        return provider.list_fields()
    return [f for f in provider.list_plots() if (f.site or "").lower() == site.lower()]


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


@router.get("/weather-outlook")
def get_weather_outlook(
    site: str,
    as_of_date: Annotated[date, Query(alias="asOfDate")],
    horizon_days: Annotated[str, Query(alias="horizonDays")] = "60",
    planting_date: Annotated[date | None, Query(alias="plantingDate")] = None,
    library: str | None = None,
) -> dict:
    """Historical analog outlook for a site, date and horizon (30, 60, 90 or `season`):
    probabilities of favorable / typical / adverse maize weather, the weather those
    historical trajectories brought, and how many seasons it rests on. Contract:
    backend/app/weather_outlook/contract.py (versioned by `contractVersion`)."""
    try:
        return weather_outlook(site, as_of_date, horizon_days, planting_date, library)
    except OutlookRequestError as err:
        raise HTTPException(status_code=err.status, detail=str(err)) from err


def _final_results():
    try:
        return load_results(get_settings().model_dir)
    except ResultsError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err


@router.get("/results")
def get_results() -> FinalResults:
    """The frozen final results (app/results.py), without the per-plot forecasts.
    `pending` until artifacts/final_results.json exists; 503 if it is malformed."""
    loaded = _final_results()
    return loaded.summary if loaded else PENDING


@router.get("/results/plots")
def get_result_plots(site: str, season: int | None = None) -> list[PlotForecast]:
    """Per-plot forecasts from the final results for one site (and season). Empty while
    the results are pending or when the site has none."""
    loaded = _final_results()
    return loaded.plots(site, season) if loaded else []


@router.get("/sites", response_model_exclude_none=True)
def list_sites() -> list[TrialSite]:
    """The trial sites (data/trial_sites.json) with what this deployment can show for
    each: weather history for the outlook, and plots with forecasts. Each part is filled
    independently, so a missing weather library or model never hides the sites."""
    settings = get_settings()
    try:
        library = get_engine(settings.weather_outlook_library).library
    except LibraryError:
        library = None
    try:
        live = get_provider().list_plots()
    except (ProviderError, ArtifactError):
        live = []
    try:
        final = load_results(settings.model_dir)
    except ResultsError:
        final = None

    out = []
    for site in load_sites(settings.sites_file):
        key = site.id.lower()
        weather = None
        if library is not None:
            match = next((s for s in library.sites.values() if s.name.lower() == key), None)
            if match is not None and match.seasons:
                weather = SiteWeather(
                    library_site=match.name,
                    seasons=len(match.seasons),
                    first_season=min(match.seasons),
                    last_season=max(match.seasons),
                    station=match.station.get("name"),
                    analog_weighting=match.analog_weighting,
                )
        live_here = [f for f in live if (f.site or "").lower() == key]
        final_here = (
            [c for c in final.summary.plot_counts if c.site.lower() == key] if final else []
        )
        site_series = [s for s in final.summary.sites if s.site.lower() == key] if final else []
        seasons = (
            {f.season for f in live_here}
            | {c.season for c in final_here}
            | {s.season for s in site_series}
        )
        out.append(
            site.model_copy(
                update={
                    "weather": weather,
                    "forecasts": SiteForecasts(
                        live_plots=len(live_here),
                        final_plots=sum(c.plots for c in final_here),
                        final_site_forecast=bool(site_series),
                        seasons=sorted(seasons),
                    ),
                }
            )
        )
    return out


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
