"""
What the season has brought so far (descriptors, for finding analog seasons) and what one
future weather trajectory would bring (horizon outcomes).

Every quantity is a SoilSignal weather feature: descriptors come straight from
app.features.weather.weather_features; horizon outcomes are the same definitions summed
over the horizon's days, computed on arrays for speed (tests check both give the same
numbers). Nothing here defines a new growing-degree-day, heat or dry-spell formula.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.features import thresholds as t
from app.features.inputs import DailyWeather
from app.features.weather import (
    crop_coefficient,
    degree_days_above,
    hargreaves_et0_mm,
    modified_gdd,
    weather_features,
)
from app.weather_outlook.history import SiteRecord

# Descriptor name -> weather_features key (counted from the season start, not planting).
DESCRIPTOR_SOURCES = {
    "gdd_to_date": "gdd_since_planting",
    "rain_to_date_mm": "rain_since_planting_mm",
    "rain_14d_mm": "rain_14d_mm",
    "rain_30d_mm": "rain_30d_mm",
    "rain_60d_mm": "rain_60d_mm",
    "heat_days_to_date": "heat_days_since_planting",
    "kdd_to_date": "killing_degree_days_29c",
    "warm_nights_to_date": "warm_nights_since_planting",
    "longest_dry_spell_days": "longest_dry_spell_days",
    "current_dry_spell_days": "current_dry_spell_days",
}
DESCRIPTORS = (*DESCRIPTOR_SOURCES, "tmean_30d_c", "root_zone_depletion_mm")

# Horizon outcomes, with the units the contract reports.
OUTCOMES = {
    "precip_mm": "mm",
    "gdd": "GDD (F)",
    "heat_days": "days >= 95 F",
    "kdd_29c": "degree days above 29 C",
    "warm_nights": "nights >= 70 F",
    "longest_dry_spell_days": "days",
    "very_heavy_rain_days": "days >= 20 mm",
    "water_deficit_mm": "mm (crop demand minus rain, from planting)",
    "tmean_c": "C",
}
STAGE_OUTCOMES = (
    "rain_around_silking_mm",
    "heat_days_around_silking",
    "water_deficit_around_silking_mm",
    "rain_grain_fill_mm",
    "heat_days_grain_fill",
    "warm_nights_grain_fill",
    "water_deficit_grain_fill_mm",
)


@dataclass(frozen=True)
class DailyArrays:
    """A run of consecutive days with the per-day SoilSignal quantities."""

    first: date
    tmax_c: np.ndarray
    tmin_c: np.ndarray
    precip_mm: np.ndarray
    gdd: np.ndarray
    kdd: np.ndarray
    et0: np.ndarray

    def __len__(self) -> int:
        return len(self.tmax_c)

    @property
    def tmax_f(self) -> np.ndarray:
        return self.tmax_c * 9 / 5 + 32

    @property
    def tmin_f(self) -> np.ndarray:
        return self.tmin_c * 9 / 5 + 32

    def dates(self) -> list[date]:
        return [self.first + timedelta(i) for i in range(len(self))]

    def redate(self, first: date) -> "DailyArrays":
        return DailyArrays(
            first, self.tmax_c, self.tmin_c, self.precip_mm, self.gdd, self.kdd, self.et0
        )

    def concat(self, other: "DailyArrays") -> "DailyArrays":
        if other.first != self.first + timedelta(len(self)):
            raise ValueError("arrays are not consecutive")
        return DailyArrays(
            self.first,
            *(
                np.concatenate([getattr(self, f), getattr(other, f)])
                for f in ("tmax_c", "tmin_c", "precip_mm", "gdd", "kdd", "et0")
            ),
        )

    def daily_weather(self) -> list[DailyWeather]:
        return [
            DailyWeather(
                day=d,
                tmax_f=None if math.isnan(hi) else float(hi),
                tmin_f=None if math.isnan(lo) else float(lo),
                prcp_mm=None if math.isnan(p) else float(p),
            )
            for d, hi, lo, p in zip(
                self.dates(), self.tmax_f, self.tmin_f, self.precip_mm, strict=True
            )
        ]


def from_record(record: SiteRecord, first: date, last: date) -> DailyArrays:
    """Days first..last of a site record (NaN outside the record)."""
    n = (last - first).days + 1
    i0 = record.index(first)
    out = {}
    for name, source in (
        ("tmax_c", record.tmax_c),
        ("tmin_c", record.tmin_c),
        ("precip_mm", record.precip_mm),
        ("gdd", record.gdd),
        ("kdd", record.kdd),
        ("et0", record.et0),
    ):
        column = np.full(n, np.nan if name not in ("gdd", "kdd") else 0.0)
        lo, hi = max(0, i0), min(record.n, i0 + n)
        if hi > lo:
            column[lo - i0 : hi - i0] = source[lo:hi]
        out[name] = column
    return DailyArrays(first, **out)


def from_daily_weather(
    days: list[DailyWeather], first: date, last: date, latitude: float
) -> DailyArrays:
    """Arrays from DailyWeather records (e.g. a plot's own observations)."""
    by_day = {d.day: d for d in days if first <= d.day <= last}
    n = (last - first).days + 1
    tmax_f = np.full(n, np.nan)
    tmin_f = np.full(n, np.nan)
    precip = np.full(n, np.nan)
    for i in range(n):
        obs = by_day.get(first + timedelta(i))
        if obs is None:
            continue
        tmax_f[i] = np.nan if obs.tmax_f is None else obs.tmax_f
        tmin_f[i] = np.nan if obs.tmin_f is None else obs.tmin_f
        precip[i] = np.nan if obs.prcp_mm is None else obs.prcp_mm
    ok = ~np.isnan(tmax_f) & ~np.isnan(tmin_f)
    tmax_c, tmin_c = (tmax_f - 32) * 5 / 9, (tmin_f - 32) * 5 / 9
    gdd = np.array(
        [modified_gdd(h, lo) if k else 0.0 for h, lo, k in zip(tmax_f, tmin_f, ok, strict=True)]
    )
    kdd = np.array(
        [
            degree_days_above(h, lo, t.KILLING_DEGREE_BASE_C) if k else 0.0
            for h, lo, k in zip(tmax_c, tmin_c, ok, strict=True)
        ]
    )
    et0 = np.array(
        [
            hargreaves_et0_mm(first + timedelta(i), latitude, h, lo) if k else np.nan
            for i, (h, lo, k) in enumerate(zip(tmax_f, tmin_f, ok, strict=True))
        ]
    )
    return DailyArrays(first, tmax_c, tmin_c, precip, gdd, kdd, et0)


def gdd_since_planting(arrays: DailyArrays, planting: date) -> np.ndarray:
    """Cumulative GDD from planting through each day (0 before planting), as
    DailySeries.gdd_cum."""
    start = (planting - arrays.first).days
    out = np.zeros(len(arrays))
    if start < len(arrays):
        lo = max(0, start)
        out[lo:] = np.cumsum(arrays.gdd[lo:])
    return out


def crop_water_use(arrays: DailyArrays, planting: date) -> np.ndarray:
    """Crop demand ETc = Kc x ET0 per day from planting (NaN where temperatures are
    missing, 0 before planting), as DailySeries.etc."""
    cum = gdd_since_planting(arrays, planting)
    kc = np.array([crop_coefficient(g) for g in cum])
    etc = arrays.et0 * kc
    start = (planting - arrays.first).days
    if start > 0:
        etc[: min(start, len(arrays))] = 0.0
    return etc


def _longest_run(flags: np.ndarray) -> int:
    longest = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    return longest


def descriptors(
    record: SiteRecord | None,
    as_of: date,
    season_start: date,
    planting: date,
    current: DailyArrays | None = None,
) -> dict[str, float]:
    """Season-to-date descriptors from the season start through as_of.

    `current` (if given) replaces the library record, e.g. a plot's own weather. Only
    days on or before as_of are read either way."""
    if as_of < season_start:
        return {}
    if current is None:
        assert record is not None
        current = from_record(record, season_start, as_of)
    else:
        current = _clip(current, season_start, as_of)
    latitude = record.info.latitude if record is not None else 0.0
    feats, _ = weather_features(current.daily_weather(), season_start, as_of, latitude)
    out = {name: float(feats[key]) for name, key in DESCRIPTOR_SOURCES.items()}
    tmean = feats.get("tmean_30d_f", math.nan)
    out["tmean_30d_c"] = (tmean - 32) * 5 / 9 if not math.isnan(tmean) else math.nan
    return out


def _clip(arrays: DailyArrays, first: date, last: date) -> DailyArrays:
    """The part of `arrays` between first and last, padded with missing days."""
    n = (last - first).days + 1
    offset = (first - arrays.first).days
    out = {}
    for name in ("tmax_c", "tmin_c", "precip_mm", "gdd", "kdd", "et0"):
        source = getattr(arrays, name)
        column = np.full(n, np.nan if name not in ("gdd", "kdd") else 0.0)
        lo, hi = max(0, offset), min(len(source), offset + n)
        if hi > lo:
            column[lo - offset : hi - offset] = source[lo:hi]
        out[name] = column
    return DailyArrays(first, **out)


def horizon_outcomes(
    season: DailyArrays, as_of: date, end: date, planting: date
) -> dict[str, float]:
    """Outcomes over the days after as_of through end of a season series (observed days
    through as_of, then one trajectory)."""
    i0 = (as_of - season.first).days + 1
    i1 = (end - season.first).days + 1
    rain = season.precip_mm[i0:i1]
    tmax_f = season.tmax_f[i0:i1]
    tmin_f = season.tmin_f[i0:i1]
    etc = crop_water_use(season, planting)[i0:i1]
    deficit = etc - np.nan_to_num(rain)
    # Water deficit counts from planting, like water_deficit_since_planting_mm.
    before_planting = max(0, min(len(deficit), (planting - season.first).days - i0))
    deficit[:before_planting] = 0.0
    tmean = (season.tmax_c[i0:i1] + season.tmin_c[i0:i1]) / 2
    return {
        "precip_mm": float(np.nansum(rain)),
        "gdd": float(season.gdd[i0:i1].sum()),
        "heat_days": float(np.sum(tmax_f >= t.HEAT_STRESS_F)),
        "kdd_29c": float(season.kdd[i0:i1].sum()),
        "warm_nights": float(np.sum(tmin_f >= t.WARM_NIGHT_F)),
        "longest_dry_spell_days": float(_longest_run(rain < t.DRY_DAY_MM)),
        "very_heavy_rain_days": float(np.sum(rain >= t.VERY_HEAVY_RAIN_MM)),
        "water_deficit_mm": float(np.nansum(deficit)),
        "tmean_c": float(np.nanmean(tmean)) if not np.isnan(tmean).all() else math.nan,
    }


def silking_index(season: DailyArrays, planting: date) -> int | None:
    reached = np.nonzero(gdd_since_planting(season, planting) >= t.GDD_SILKING)[0]
    start = (planting - season.first).days
    reached = reached[reached >= start]
    return int(reached[0]) if reached.size else None


def stage_outcomes(season: DailyArrays, end: date, planting: date) -> dict[str, float]:
    """Pollination and grain-fill windows of the whole season (observed + trajectory) as
    weather_features defines them at `end`; empty if silking is not reached by end."""
    last = (end - season.first).days
    silk = silking_index(season, planting)
    if silk is None or silk > last:
        return {}
    w = t.SILKING_WINDOW_DAYS
    start = max(0, (planting - season.first).days)
    around = slice(max(start, silk - w), min(last, silk + w) + 1)
    rain = season.precip_mm
    heat = season.tmax_f >= t.HEAT_STRESS_F
    warm = season.tmin_f >= t.WARM_NIGHT_F
    deficit = crop_water_use(season, planting) - np.nan_to_num(rain)
    out = {
        "rain_around_silking_mm": float(np.nansum(rain[around])),
        "heat_days_around_silking": float(np.sum(heat[around])),
        "water_deficit_around_silking_mm": float(np.nansum(deficit[around])),
    }
    if silk + w + 1 <= last:
        fill = slice(silk + w + 1, last + 1)
        out["rain_grain_fill_mm"] = float(np.nansum(rain[fill]))
        out["heat_days_grain_fill"] = float(np.sum(heat[fill]))
        out["warm_nights_grain_fill"] = float(np.sum(warm[fill]))
        out["water_deficit_grain_fill_mm"] = float(np.nansum(deficit[fill]))
    return out
