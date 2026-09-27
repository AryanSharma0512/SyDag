"""
A weather history library: daily records for each site plus the manifest that says which
station they come from and which seasons may serve as analogs.

Written by the ML pipeline (`python -m soilsignal_ml.weather_outlook history`), one
directory per library under data/weather_history/. Every site uses one station for every
season; the manifest lists the seasons that passed quality control and why the others
were left out.
"""

import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.features import thresholds as t
from app.features.inputs import DailyWeather
from app.features.weather import degree_days_above, hargreaves_et0_mm, modified_gdd

DAILY_FILE = "daily.csv.gz"
MANIFEST_FILE = "manifest.json"


def c_to_f(value: float) -> float:
    return value * 9 / 5 + 32


class LibraryError(Exception):
    """A weather history library is missing or inconsistent."""


@dataclass(frozen=True)
class SiteInfo:
    name: str
    latitude: float
    longitude: float
    irrigated: bool
    reference_planting: str  # MM-DD
    root_zone_water_mm: float
    station: dict[str, Any]
    seasons: tuple[int, ...]  # seasons that passed QC: the analog candidates
    excluded_seasons: dict[int, str]
    observed_through: date
    # False: every season weighs the same (the backtest found no gain from analogs here).
    analog_weighting: bool = True
    # Calendar month -> (tmax, tmin) degrees C added to exported trajectories when the
    # library station is a proxy for the site (measured over the overlap with the on-site
    # station). Empty when the library station is the site's own.
    temperature_adjustment: dict[int, tuple[float, float]] = field(default_factory=dict)

    def planting(self, year: int) -> date:
        return month_day(year, self.reference_planting)


def month_day(year: int, mm_dd: str) -> date:
    """The same month-day in another year; 29 February becomes the 28th."""
    month, day = (int(p) for p in mm_dd.split("-"))
    if month == 2 and day == 29 and not _leap(year):
        day = 28
    return date(year, month, day)


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


class SiteRecord:
    """One site's daily record on a continuous calendar, with the per-day agronomic
    quantities precomputed by the SoilSignal feature formulas (app.features.weather)."""

    def __init__(self, info: SiteInfo, frame: pd.DataFrame) -> None:
        self.info = info
        frame = frame.sort_values("date")
        self.first = frame["date"].iloc[0]
        last = frame["date"].iloc[-1]
        n = (last - self.first).days + 1
        index = np.array([(d - self.first).days for d in frame["date"]])

        def column(name: str) -> np.ndarray:
            out = np.full(n, np.nan)
            out[index] = frame[name].to_numpy(dtype=float)
            return out

        self.tmax_c = column("tmax_c")
        self.tmin_c = column("tmin_c")
        self.precip_mm = column("precip_mm")
        self.n = n

    @property
    def last(self) -> date:
        return self.first + timedelta(self.n - 1)

    def index(self, day: date) -> int:
        return (day - self.first).days

    @cached_property
    def tmax_f(self) -> np.ndarray:
        return self.tmax_c * 9 / 5 + 32

    @cached_property
    def tmin_f(self) -> np.ndarray:
        return self.tmin_c * 9 / 5 + 32

    @cached_property
    def temps_ok(self) -> np.ndarray:
        return ~np.isnan(self.tmax_c) & ~np.isnan(self.tmin_c)

    @cached_property
    def gdd(self) -> np.ndarray:
        """Modified GDD (86/50 F) per day; 0 where a temperature is missing, as in
        app.features.weather.DailySeries."""
        return np.array(
            [
                modified_gdd(hi, lo) if ok else 0.0
                for hi, lo, ok in zip(self.tmax_f, self.tmin_f, self.temps_ok, strict=True)
            ]
        )

    @cached_property
    def kdd(self) -> np.ndarray:
        """Degree days above 29 C per day (single sine), as in weather_features."""
        return np.array(
            [
                degree_days_above(hi, lo, t.KILLING_DEGREE_BASE_C) if ok else 0.0
                for hi, lo, ok in zip(self.tmax_c, self.tmin_c, self.temps_ok, strict=True)
            ]
        )

    @cached_property
    def et0(self) -> np.ndarray:
        """Hargreaves reference evapotranspiration, mm/day (NaN where a temperature is
        missing)."""
        lat = self.info.latitude
        return np.array(
            [
                hargreaves_et0_mm(self.first + timedelta(i), lat, hi, lo) if ok else np.nan
                for i, (hi, lo, ok) in enumerate(
                    zip(self.tmax_f, self.tmin_f, self.temps_ok, strict=True)
                )
            ]
        )

    def daily_weather(self, first: date, last: date) -> list[DailyWeather]:
        """Records from first through last as the feature pipeline's DailyWeather (F, mm)."""
        out = []
        for i in range(max(0, self.index(first)), min(self.n, self.index(last) + 1)):
            day = self.first + timedelta(i)
            out.append(
                DailyWeather(
                    day=day,
                    tmax_f=None if math.isnan(self.tmax_f[i]) else float(self.tmax_f[i]),
                    tmin_f=None if math.isnan(self.tmin_f[i]) else float(self.tmin_f[i]),
                    prcp_mm=None if math.isnan(self.precip_mm[i]) else float(self.precip_mm[i]),
                )
            )
        return out


class WeatherLibrary:
    def __init__(self, directory: Path) -> None:
        manifest_path = directory / MANIFEST_FILE
        daily_path = directory / DAILY_FILE
        if not manifest_path.exists() or not daily_path.exists():
            raise LibraryError(f"no weather history library in {directory}")
        self.directory = directory
        self.manifest = json.loads(manifest_path.read_text())
        self.name: str = self.manifest["library"]
        self.label: str = self.manifest.get("label", self.name)
        self.settings: dict[str, Any] = self.manifest.get("outlook", {})
        frame = pd.read_csv(daily_path)
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        self.sites: dict[str, SiteInfo] = {}
        self._records: dict[str, SiteRecord] = {}
        for name, raw in self.manifest["sites"].items():
            info = _site_info(name, raw)
            rows = frame[frame["site"] == name]
            if rows.empty:
                raise LibraryError(f"{self.name}: no daily records for {name}")
            self.sites[name] = info
            self._records[name] = SiteRecord(info, rows)

    def site(self, name: str) -> SiteInfo:
        match = self._match(name)
        return self.sites[match]

    def record(self, name: str) -> SiteRecord:
        return self._records[self._match(name)]

    def _match(self, name: str) -> str:
        for key in self.sites:
            if key.lower() == name.lower():
                return key
        raise KeyError(name)


def _site_info(name: str, raw: dict[str, Any]) -> SiteInfo:
    adjustment = (raw["station"].get("overlap") or {}).get("monthly_temperature_adjustment_c")
    months: dict[int, tuple[float, float]] = {}
    if adjustment:
        for month in range(1, 13):
            months[month] = (
                float(adjustment["tmax_c"].get(str(month), 0.0)),
                float(adjustment["tmin_c"].get(str(month), 0.0)),
            )
    return SiteInfo(
        name=name,
        latitude=float(raw["latitude"]),
        longitude=float(raw["longitude"]),
        irrigated=bool(raw["irrigated"]),
        reference_planting=raw["reference_planting"],
        root_zone_water_mm=float(raw["root_zone_water_mm"]),
        station=raw["station"],
        seasons=tuple(sorted(int(s) for s in raw["seasons"])),
        excluded_seasons={int(k): v for k, v in raw.get("excluded_seasons", {}).items()},
        observed_through=date.fromisoformat(raw["observed_through"]),
        analog_weighting=bool(raw.get("analog_weighting", True)),
        temperature_adjustment=months,
    )
