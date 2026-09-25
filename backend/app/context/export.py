"""
CSV exports of the normalized location context: the same values /api/context/*
returns, never the raw government responses. Column and property names match the
JSON fields, so a CSV lines up with the API and the Data Explorer tables.
"""

import csv
import io
from collections.abc import Iterable
from typing import Any, Literal

from app.schemas import LocationContext, ObservedWeather, SoilProfile, YieldHistory

ExportType = Literal["weather", "soil", "yield-history", "all"]

WEATHER_COLUMNS = [
    "latitude",
    "longitude",
    "asOf",
    "observedThrough",
    "rainfallLast7DaysMm",
    "rainfallLast30DaysMm",
    "avgTempLast30DaysF",
    "gddSinceSeasonStart",
    "heatDays",
    "longestDrySpellDays",
    "dataCompleteness",
    "seasonStart",
    "stationId",
    "stationName",
    "stationDistanceKm",
    "source",
    "retrievedAt",
]
YIELD_COLUMNS = [
    "latitude",
    "longitude",
    "year",
    "yield",
    "unit",
    "county",
    "stateCode",
    "countyFips",
    "source",
    "retrievedAt",
]
PROPERTY_COLUMNS = ["property", "value"]
ALL_COLUMNS = ["dataset", "record", "property", "value"]


def _cell(value: Any) -> str:
    """Empty for missing values; whole floats without a trailing .0."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _csv(columns: list[str], rows: Iterable[Iterable[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([_cell(v) for v in row] for row in rows)
    return buffer.getvalue()


def _weather_rows(lat: float, lon: float, weather: ObservedWeather) -> list[list[Any]]:
    station = weather.station
    return [
        [
            lat,
            lon,
            s.as_of,
            s.observed_through,
            s.rainfall_last_7_days_mm,
            s.rainfall_last_30_days_mm,
            s.avg_temp_last_30_days_f,
            s.gdd_since_season_start,
            s.heat_days,
            s.longest_dry_spell_days,
            s.data_completeness,
            s.season_start,
            station.id,
            station.name,
            station.distance_km,
            weather.source,
            weather.retrieved_at,
        ]
        for s in weather.summaries
    ]


def _soil_properties(lat: float, lon: float, soil: SoilProfile) -> list[list[Any]]:
    return [
        ["latitude", lat],
        ["longitude", lon],
        *([key, value] for key, value in soil.model_dump(by_alias=True).items()),
    ]


def _yield_rows(lat: float, lon: float, history: YieldHistory) -> list[list[Any]]:
    county = history.county
    return [
        [
            lat,
            lon,
            y.year,
            y.yield_,
            history.unit,
            county.name,
            county.state_code,
            county.fips,
            history.source,
            history.retrieved_at,
        ]
        for y in history.years
    ]


def weather_csv(lat: float, lon: float, weather: ObservedWeather) -> str:
    return _csv(WEATHER_COLUMNS, _weather_rows(lat, lon, weather))


def soil_csv(lat: float, lon: float, soil: SoilProfile) -> str:
    return _csv(PROPERTY_COLUMNS, _soil_properties(lat, lon, soil))


def yield_history_csv(lat: float, lon: float, history: YieldHistory) -> str:
    return _csv(YIELD_COLUMNS, _yield_rows(lat, lon, history))


def all_csv(context: LocationContext) -> str:
    """Every source in one long table (dataset, record, property, value), including
    each source's status, so a failed source is visible rather than silently absent."""
    lat, lon = context.latitude, context.longitude
    rows: list[list[Any]] = [
        ["location", "", "latitude", lat],
        ["location", "", "longitude", lon],
    ]
    if context.county:
        rows += [
            ["location", "", key, value]
            for key, value in context.county.model_dump(by_alias=True).items()
        ]
    parts = [
        ("soil", context.soil),
        ("weather", context.weather),
        ("yieldHistory", context.yield_history),
    ]
    for dataset, part in parts:
        rows.append([dataset, "", "status", part.status])
        if part.message:
            rows.append([dataset, "", "message", part.message])
    if context.soil.data:
        soil = context.soil.data.model_dump(by_alias=True)
        rows += [["soil", "", key, value] for key, value in soil.items()]
    if context.weather.data:
        weather = context.weather.data
        station = weather.station.model_dump(by_alias=True)
        rows += [["weather", "station", key, value] for key, value in station.items()]
        rows += [
            ["weather", "", "source", weather.source],
            ["weather", "", "retrievedAt", weather.retrieved_at],
        ]
        for summary in weather.summaries:
            values = summary.model_dump(by_alias=True)
            rows += [["weather", summary.as_of, key, value] for key, value in values.items()]
    if context.yield_history.data:
        history = context.yield_history.data
        rows += [
            ["yieldHistory", "", "county", history.county.name],
            ["yieldHistory", "", "countyFips", history.county.fips],
            ["yieldHistory", "", "unit", history.unit],
            ["yieldHistory", "", "fiveYearAverage", history.five_year_average],
            ["yieldHistory", "", "source", history.source],
            ["yieldHistory", "", "retrievedAt", history.retrieved_at],
        ]
        rows += [["yieldHistory", y.year, "yield", y.yield_] for y in history.years]
    return _csv(ALL_COLUMNS, rows)
