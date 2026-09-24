"""
Observed weather from NOAA NCEI daily summaries (GHCN-Daily, no API key needed).

NOAA provides raw daily rain and temperature; everything the dashboard shows
(rainfall windows, growing degree days, heat days, dry spells) is derived here.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx2 as httpx

from app.context.http import NoData, request_json
from app.schemas import WeatherStation, WeatherSummary

SEARCH_URL = "https://www.ncei.noaa.gov/access/services/search/v1/data"
DATA_URL = "https://www.ncei.noaa.gov/access/services/data/v1"
SERVICE = "NOAA NCEI"
SOURCE = "NOAA NCEI GHCN-Daily"
REQUIRED_TYPES = {"PRCP", "TMAX", "TMIN"}
SEARCH_RADII_DEG = (0.35, 0.8)  # about 35 km, then 80 km

MM_PER_INCH = 25.4
DRY_DAY_INCHES = 0.04  # under 1 mm of rain
HEAT_DAY_F = 95.0
GDD_BASE_F, GDD_CAP_F = 50.0, 86.0  # standard corn method


@dataclass(frozen=True)
class DailyObservation:
    day: date
    prcp_in: float | None
    tmax_f: float | None
    tmin_f: float | None


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 12742 * math.asin(math.sqrt(a))


def find_station(
    client: httpx.Client, lat: float, lon: float, start: date, end: date
) -> WeatherStation:
    """Nearest station with rain and temperature records for the window. Stations whose
    records reach the window's end are preferred over closer ones that stop early."""
    for radius in SEARCH_RADII_DEG:
        north, south, west, east = lat + radius, lat - radius, lon - radius, lon + radius
        data = request_json(
            client,
            SERVICE,
            "GET",
            SEARCH_URL,
            params={
                "dataset": "daily-summaries",
                "bbox": f"{north:.4f},{west:.4f},{south:.4f},{east:.4f}",
                "startDate": f"{start.isoformat()}T00:00:00",
                "endDate": f"{end.isoformat()}T23:59:59",
                "dataTypes": ",".join(sorted(REQUIRED_TYPES)),
                "limit": 50,
            },
        )
        candidates = []
        for result in data.get("results", []):
            types = {t.get("id") for t in result.get("dataTypes", [])}
            stations = result.get("stations") or []
            coords = (result.get("location") or {}).get("coordinates")
            if not REQUIRED_TYPES <= types or not stations or not coords:
                continue
            if result.get("startDate", "")[:10] > start.isoformat():
                continue
            slon, slat = float(coords[0]), float(coords[1])
            distance = _km(lat, lon, slat, slon)
            covers_end = result.get("endDate", "")[:10] >= end.isoformat()
            station = WeatherStation(
                id=stations[0]["id"],
                name=_station_name(stations[0].get("name", stations[0]["id"])),
                latitude=slat,
                longitude=slon,
                distance_km=round(distance, 1),
            )
            candidates.append((not covers_end, distance, station.id, station))
        if candidates:
            return min(candidates, key=lambda c: c[:3])[3]
    raise NoData("no NOAA station with rain and temperature records near this location")


def _station_name(raw: str) -> str:
    """'WEST LAFAYETTE 6 NW, IN US' -> 'West Lafayette 6 NW, IN'."""
    place, _, region = raw.partition(",")
    words = [
        w
        if (any(c.isdigit() for c in w) or w in {"NW", "NE", "SW", "SE", "N", "S", "E", "W"})
        else w.capitalize()
        for w in place.split()
    ]
    state = region.split()[0] if region.split() else ""
    return f"{' '.join(words)}, {state}" if state else " ".join(words)


def _value(row: dict[str, Any], key: str) -> float | None:
    raw = str(row.get(key, "")).strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def fetch_daily(
    client: httpx.Client, station_id: str, start: date, end: date
) -> list[DailyObservation]:
    rows = request_json(
        client,
        SERVICE,
        "GET",
        DATA_URL,
        params={
            "dataset": "daily-summaries",
            "stations": station_id,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dataTypes": ",".join(sorted(REQUIRED_TYPES)),
            "units": "standard",
            "format": "json",
        },
    )
    if not isinstance(rows, list):
        return []
    return [
        DailyObservation(
            day=date.fromisoformat(row["DATE"][:10]),
            prcp_in=_value(row, "PRCP"),
            tmax_f=_value(row, "TMAX"),
            tmin_f=_value(row, "TMIN"),
        )
        for row in rows
        if row.get("DATE")
    ]


def _gdd(tmax: float, tmin: float) -> float:
    hi = min(max(tmax, GDD_BASE_F), GDD_CAP_F)
    lo = min(max(tmin, GDD_BASE_F), GDD_CAP_F)
    return (hi + lo) / 2 - GDD_BASE_F


def summarize(days: list[DailyObservation], as_of: date, season_start: date) -> WeatherSummary:
    by_day = {d.day: d for d in days if d.day <= as_of}

    def window(first: date) -> list[DailyObservation]:
        return [
            by_day[first + timedelta(n)]
            for n in range((as_of - first).days + 1)
            if first + timedelta(n) in by_day
        ]

    last30, last7 = window(as_of - timedelta(29)), window(as_of - timedelta(6))
    season = window(season_start) if season_start <= as_of else []
    season_length = max(0, (as_of - season_start).days + 1)

    def rain_mm(obs: list[DailyObservation]) -> float:
        return round(sum(o.prcp_in for o in obs if o.prcp_in is not None) * MM_PER_INCH, 1)

    means = [
        (o.tmax_f + o.tmin_f) / 2 for o in last30 if o.tmax_f is not None and o.tmin_f is not None
    ]

    longest = run = 0
    for n in range(season_length):
        obs = by_day.get(season_start + timedelta(n))
        run = run + 1 if obs and obs.prcp_in is not None and obs.prcp_in < DRY_DAY_INCHES else 0
        longest = max(longest, run)

    complete = sum(1 for o in season if None not in (o.prcp_in, o.tmax_f, o.tmin_f))
    return WeatherSummary(
        as_of=as_of.isoformat(),
        observed_through=max(by_day).isoformat() if by_day else None,
        rainfall_last_7_days_mm=rain_mm(last7),
        rainfall_last_30_days_mm=rain_mm(last30),
        avg_temp_last_30_days_f=round(sum(means) / len(means), 1) if means else None,
        season_start=season_start.isoformat(),
        gdd_since_season_start=round(
            sum(
                _gdd(o.tmax_f, o.tmin_f)
                for o in season
                if o.tmax_f is not None and o.tmin_f is not None
            )
        ),
        heat_days=sum(1 for o in season if o.tmax_f is not None and o.tmax_f >= HEAT_DAY_F),
        longest_dry_spell_days=longest,
        data_completeness=round(complete / season_length, 2) if season_length else 0.0,
    )
