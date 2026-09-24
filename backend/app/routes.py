from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.providers import ForecastProvider, get_provider
from app.schemas import FieldForecast, FieldMeta, Health, SoilContext, WeatherContext

router = APIRouter(prefix="/api")

Provider = Annotated[ForecastProvider, Depends(get_provider)]


def _forecast_or_404(provider: ForecastProvider, field_id: str) -> FieldForecast:
    forecast = provider.get_forecast(field_id)
    if forecast is None:
        raise HTTPException(status_code=404, detail=f"Field '{field_id}' not found")
    return forecast


@router.get("/health")
def health(provider: Provider) -> Health:
    return Health(status="ok", version=get_settings().version, data_source=provider.name)


@router.get("/fields")
def list_fields(provider: Provider) -> list[FieldMeta]:
    return provider.list_fields()


@router.get("/fields/{field_id}")
def get_field(field_id: str, provider: Provider) -> FieldMeta:
    return _forecast_or_404(provider, field_id).field


# Optional fields the provider leaves unset are omitted, matching `field?: T` in the TS types.
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
