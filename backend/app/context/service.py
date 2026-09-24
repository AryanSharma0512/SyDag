"""
Location context: the public data SoilSignal gathers for a field's coordinates.

Each source is cached (see cache.py) and runs independently, so a slow, failing
or unconfigured source only affects its own part of the response.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx2 as httpx

from app.config import Settings
from app.context.cache import Cached, ContextCache
from app.context.geo import fetch_county
from app.context.http import NoData, NotConfigured, UpstreamError
from app.context.soil import fetch_soil_profile
from app.context.weather import SOURCE as WEATHER_SOURCE
from app.context.weather import DailyObservation, fetch_daily, find_station, summarize
from app.context.yield_history import fetch_yield_history
from app.schemas import (
    ContextPart,
    County,
    LocationContext,
    ObservedWeather,
    SoilProfile,
    WeatherStation,
    YieldHistory,
)

log = logging.getLogger(__name__)

# Bump when a cached, normalized format changes so old entries are ignored.
CACHE_VERSION = "v1"
SOIL_TTL = None  # soil surveys are revised yearly at most
COUNTY_TTL = None
STATION_TTL = timedelta(days=30)
YIELD_TTL = timedelta(days=14)
RECENT_WEATHER_TTL = timedelta(hours=6)
SETTLED_WEATHER_TTL = timedelta(days=30)
SETTLE_DAYS = 10  # daily observations older than this rarely change

NASS_KEY_MESSAGE = (
    "County yields need a free USDA NASS API key. Set SOILSIGNAL_NASS_API_KEY on the backend."
)


def _loc(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


class LocationContextService:
    def __init__(self, client: httpx.Client, cache: ContextCache, settings: Settings) -> None:
        self.client = client
        self.cache = cache
        self.settings = settings

    def _cached(
        self, name: str, key: str, ttl: timedelta | None, fetch: Callable[[], Any]
    ) -> Cached:
        return self.cache.get_or_fetch(f"{name}-{CACHE_VERSION}", key, ttl, fetch)

    def season_start(self, day: date) -> date:
        month, dom = (int(p) for p in self.settings.season_start.split("-"))
        return date(day.year, month, dom)

    # -- sources ---------------------------------------------------------------

    def soil(self, lat: float, lon: float) -> tuple[SoilProfile, Cached]:
        entry = self._cached(
            "soil",
            _loc(lat, lon),
            SOIL_TTL,
            lambda: fetch_soil_profile(self.client, lat, lon).model_dump(mode="json"),
        )
        return SoilProfile.model_validate(entry.value), entry

    def county(self, lat: float, lon: float) -> County:
        entry = self._cached(
            "county",
            _loc(lat, lon),
            COUNTY_TTL,
            lambda: fetch_county(self.client, lat, lon).model_dump(mode="json"),
        )
        return County.model_validate(entry.value)

    def weather(self, lat: float, lon: float, dates: list[date]) -> tuple[ObservedWeather, Cached]:
        """One station and one daily series cover every requested date."""
        starts = {d: self.season_start(d) for d in dates}
        first = min(min(starts.values()), min(dates) - timedelta(days=29))
        today = datetime.now(UTC).date()
        last = min(max(dates), today)
        station_entry = self._cached(
            "station",
            f"{_loc(lat, lon)}|{first}|{last}",
            STATION_TTL,
            lambda: find_station(self.client, lat, lon, first, last).model_dump(mode="json"),
        )
        station = WeatherStation.model_validate(station_entry.value)
        settled = last < today - timedelta(days=SETTLE_DAYS)
        series_entry = self._cached(
            "weather-daily",
            f"{station.id}|{first}|{last}",
            SETTLED_WEATHER_TTL if settled else RECENT_WEATHER_TTL,
            lambda: [
                [o.day.isoformat(), o.prcp_in, o.tmax_f, o.tmin_f]
                for o in fetch_daily(self.client, station.id, first, last)
            ],
        )
        days = [
            DailyObservation(date.fromisoformat(d), p, hi, lo)
            for d, p, hi, lo in series_entry.value
        ]
        if not days:
            raise NoData(f"NOAA has no observations from {station.name} for these dates")
        observed = ObservedWeather(
            station=station,
            summaries=[summarize(days, d, starts[d]) for d in dates],
            source=WEATHER_SOURCE,
            retrieved_at=series_entry.retrieved_at.isoformat(timespec="seconds"),
        )
        return observed, series_entry

    def yield_history(
        self, lat: float, lon: float, through_year: int
    ) -> tuple[YieldHistory, Cached]:
        if self.settings.nass_api_key is None:
            raise NotConfigured(NASS_KEY_MESSAGE)
        api_key = self.settings.nass_api_key.get_secret_value()
        county = self.county(lat, lon)
        entry = self._cached(
            "nass-yield",
            f"{county.fips}|{through_year}",
            YIELD_TTL,
            lambda: fetch_yield_history(self.client, api_key, county, through_year).model_dump(
                mode="json"
            ),
        )
        return YieldHistory.model_validate(entry.value), entry

    # -- everything for one field ----------------------------------------------

    def location_context(self, lat: float, lon: float, dates: list[date]) -> LocationContext:
        with ThreadPoolExecutor(max_workers=4) as pool:
            soil = pool.submit(_part, ContextPart[SoilProfile], lambda: self.soil(lat, lon))
            weather = pool.submit(
                _part, ContextPart[ObservedWeather], lambda: self.weather(lat, lon, dates)
            )
            # County yields for the seasons before the one being forecast.
            history = pool.submit(
                _part,
                ContextPart[YieldHistory],
                lambda: self.yield_history(lat, lon, min(dates).year - 1),
            )
            county = pool.submit(self._county_or_none, lat, lon)
        return LocationContext(
            latitude=lat,
            longitude=lon,
            county=county.result(),
            soil=soil.result(),
            weather=weather.result(),
            yield_history=history.result(),
        )

    def _county_or_none(self, lat: float, lon: float) -> County | None:
        try:
            return self.county(lat, lon)
        except (NoData, UpstreamError):
            return None


def _part[T](
    part_type: type[ContextPart[T]], run: Callable[[], tuple[T, Cached]]
) -> ContextPart[T]:
    try:
        data, entry = run()
    except NotConfigured as err:
        return part_type(status="not_configured", message=str(err))
    except NoData as err:
        return part_type(status="unavailable", message=f"{str(err)[:1].upper()}{str(err)[1:]}.")
    except UpstreamError as err:
        return part_type(
            status="unavailable", message=f"{err.service} did not respond. Try again shortly."
        )
    except Exception:
        log.exception("location context source failed")
        return part_type(status="unavailable", message="This data could not be loaded.")
    message = None
    if entry.stale:
        message = (
            f"The source did not respond, so this is the copy from {entry.retrieved_at:%b %-d, %Y}."
        )
    return part_type(status="ok", data=data, message=message)
