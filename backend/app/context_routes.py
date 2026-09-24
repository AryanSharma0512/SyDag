"""
/api/context/*: public agronomic data for a coordinate. The frontend never calls
USDA or NOAA itself; it gets these normalized, cached responses instead.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.context.cache import get_context_cache
from app.context.http import NoData, NotConfigured, UpstreamError, get_http_client
from app.context.service import LocationContextService
from app.schemas import LocationContext, ObservedWeather, SoilProfile, YieldHistory

router = APIRouter(prefix="/api/context")

Lat = Annotated[float, Query(ge=-90, le=90, description="Latitude, WGS84")]
Lon = Annotated[float, Query(ge=-180, le=180, description="Longitude, WGS84")]


def get_context_service() -> LocationContextService:
    return LocationContextService(get_http_client(), get_context_cache(), get_settings())


Service = Annotated[LocationContextService, Depends(get_context_service)]


def _http_error(err: Exception) -> HTTPException:
    if isinstance(err, NotConfigured):
        return HTTPException(status_code=503, detail=str(err))
    if isinstance(err, NoData):
        return HTTPException(status_code=404, detail=str(err))
    if isinstance(err, UpstreamError):
        return HTTPException(status_code=502, detail=f"{err.service} did not respond")
    raise err


@router.get("/soil")
def soil(lat: Lat, lon: Lon, service: Service) -> SoilProfile:
    """Dominant soil at the point, from USDA NRCS SSURGO."""
    try:
        return service.soil(lat, lon)[0]
    except (NotConfigured, NoData, UpstreamError) as err:
        raise _http_error(err) from err


@router.get("/weather")
def weather(
    lat: Lat,
    lon: Lon,
    service: Service,
    as_of: Annotated[date, Query(alias="date", description="Summarize weather up to this day")],
) -> ObservedWeather:
    """Rainfall, temperature, growing degree days, heat days and dry spells from the
    nearest NOAA station, as of a date."""
    try:
        return service.weather(lat, lon, [as_of])[0]
    except (NotConfigured, NoData, UpstreamError) as err:
        raise _http_error(err) from err


@router.get("/yield-history")
def yield_history(
    lat: Lat,
    lon: Lon,
    service: Service,
    through_year: Annotated[int | None, Query(alias="throughYear", ge=1900, le=2100)] = None,
) -> YieldHistory:
    """County corn yields by year from USDA NASS, through `throughYear` (default: last year)."""
    try:
        year = through_year if through_year is not None else date.today().year - 1
        return service.yield_history(lat, lon, year)[0]
    except (NotConfigured, NoData, UpstreamError) as err:
        raise _http_error(err) from err


@router.get("/all")
def all_context(
    lat: Lat,
    lon: Lon,
    service: Service,
    dates: Annotated[
        list[date],
        Query(alias="date", min_length=1, max_length=24, description="Repeat for several dates"),
    ],
) -> LocationContext:
    """Soil, weather for each date, and county yield history in one response. Sources
    fail independently: each part reports its own status."""
    return service.location_context(lat, lon, dates)
