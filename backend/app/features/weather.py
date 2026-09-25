"""
Weather features from daily observations, counted from planting to the forecast date.

Only days on or before the forecast date are read. Stage windows (around silking,
grain fill) use a silking date estimated from growing degree days observed so far,
so a window that has not started yet produces no feature rather than a guess.
"""

import math
from collections.abc import Sequence
from datetime import date, timedelta

import numpy as np

from app.features import thresholds as t
from app.features.inputs import DailyWeather


def f_to_c(value: float) -> float:
    return (value - 32) * 5 / 9


def modified_gdd(tmax_f: float, tmin_f: float) -> float:
    """Modified growing degree days, 86/50 °F method."""
    hi = min(max(tmax_f, t.GDD_BASE_F), t.GDD_CAP_F)
    lo = min(max(tmin_f, t.GDD_BASE_F), t.GDD_CAP_F)
    return (hi + lo) / 2 - t.GDD_BASE_F


def degree_days_above(tmax_c: float, tmin_c: float, base_c: float) -> float:
    """Degree days above a threshold, assuming a sine-shaped daily temperature curve
    (single-sine method, Baskerville & Emin 1969)."""
    if tmax_c <= base_c:
        return 0.0
    mean = (tmax_c + tmin_c) / 2
    if tmin_c >= base_c:
        return mean - base_c
    amplitude = (tmax_c - tmin_c) / 2
    theta = math.asin((base_c - mean) / amplitude)
    return ((mean - base_c) * (math.pi / 2 - theta) + amplitude * math.cos(theta)) / math.pi


def extraterrestrial_radiation_mm(day: date, latitude: float) -> float:
    """Daily extraterrestrial radiation as mm/day of evaporation equivalent (FAO-56 eq. 21)."""
    doy = day.timetuple().tm_yday
    phi = math.radians(latitude)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    delta = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    ra_mj = (
        (24 * 60 / math.pi)
        * 0.0820
        * dr
        * (ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws))
    )
    return 0.408 * ra_mj


def hargreaves_et0_mm(day: date, latitude: float, tmax_f: float, tmin_f: float) -> float:
    """Reference evapotranspiration from temperature only (FAO-56 eq. 52)."""
    tmax, tmin = f_to_c(tmax_f), f_to_c(tmin_f)
    spread = max(0.0, tmax - tmin)
    et0 = 0.0023 * ((tmax + tmin) / 2 + 17.8) * math.sqrt(spread)
    return max(0.0, et0 * extraterrestrial_radiation_mm(day, latitude))


def crop_coefficient(gdd_since_planting: float) -> float:
    """FAO-56 single crop coefficient for field maize, staged by growing degree days."""
    mid_end = t.GDD_SILKING + (t.GDD_BLACK_LAYER - t.GDD_SILKING) / 2
    if gdd_since_planting < t.GDD_KC_RISE_START:
        return t.KC_INITIAL
    if gdd_since_planting < t.GDD_SILKING:
        share = (gdd_since_planting - t.GDD_KC_RISE_START) / (t.GDD_SILKING - t.GDD_KC_RISE_START)
        return t.KC_INITIAL + share * (t.KC_MID - t.KC_INITIAL)
    if gdd_since_planting < mid_end:
        return t.KC_MID
    if gdd_since_planting < t.GDD_BLACK_LAYER:
        share = (gdd_since_planting - mid_end) / (t.GDD_BLACK_LAYER - mid_end)
        return t.KC_MID + share * (t.KC_END - t.KC_MID)
    return t.KC_END


def _longest_run(flags: np.ndarray) -> int:
    longest = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    return longest


def _trailing_run(flags: np.ndarray) -> int:
    run = 0
    for flag in flags[::-1]:
        if not flag:
            break
        run += 1
    return run


class DailySeries:
    """Planting-to-date daily arrays; days without a record are NaN."""

    def __init__(
        self, days: Sequence[DailyWeather], planting: date, as_of: date, latitude: float
    ) -> None:
        by_day = {d.day: d for d in days if planting <= d.day <= as_of}
        n = max(0, (as_of - planting).days + 1)
        self.dates = [planting + timedelta(i) for i in range(n)]

        def column(attr: str) -> np.ndarray:
            return np.array(
                [
                    v
                    if (obs := by_day.get(d)) is not None and (v := getattr(obs, attr)) is not None
                    else np.nan
                    for d in self.dates
                ],
                dtype=float,
            )

        self.tmax = column("tmax_f")
        self.tmin = column("tmin_f")
        self.prcp = column("prcp_mm")
        temps = ~np.isnan(self.tmax) & ~np.isnan(self.tmin)
        self.gdd = np.array(
            [
                modified_gdd(hi, lo) if ok else 0.0
                for hi, lo, ok in zip(self.tmax, self.tmin, temps, strict=True)
            ]
        )
        self.gdd_cum = np.cumsum(self.gdd)
        et0 = np.array(
            [
                hargreaves_et0_mm(d, latitude, hi, lo) if ok else np.nan
                for d, hi, lo, ok in zip(self.dates, self.tmax, self.tmin, temps, strict=True)
            ]
        )
        self.etc = et0 * np.array([crop_coefficient(g) for g in self.gdd_cum])
        self.complete = temps & ~np.isnan(self.prcp)

    def silking_date(self) -> date | None:
        reached = np.nonzero(self.gdd_cum >= t.GDD_SILKING)[0]
        return self.dates[int(reached[0])] if reached.size else None

    def window(self, first: date, last: date) -> slice:
        start = max(0, (first - self.dates[0]).days) if self.dates else 0
        stop = min(len(self.dates), (last - self.dates[0]).days + 1) if self.dates else 0
        return slice(start, max(start, stop))


def _sum(values: np.ndarray) -> float:
    return float(np.nansum(values)) if values.size else 0.0


def _mean(values: np.ndarray) -> float:
    return float(np.nanmean(values)) if values.size and not np.isnan(values).all() else math.nan


def _max(values: np.ndarray) -> float:
    return float(np.nanmax(values)) if values.size and not np.isnan(values).all() else math.nan


def weather_features(
    days: Sequence[DailyWeather], planting: date, as_of: date, latitude: float
) -> tuple[dict[str, float], date | None]:
    """Weather features from planting through as_of, and the estimated silking date
    (None if silking has not been reached by as_of)."""
    if as_of < planting:
        return {}, None
    s = DailySeries(days, planting, as_of, latitude)

    def last(n: int) -> slice:
        return slice(max(0, len(s.dates) - n), len(s.dates))

    rain, tmax, tmin = s.prcp, s.tmax, s.tmin
    heat = tmax >= t.HEAT_STRESS_F
    warm_night = tmin >= t.WARM_NIGHT_F
    wet = rain >= t.DRY_DAY_MM
    dry = rain < t.DRY_DAY_MM
    meaningful = np.nonzero(rain >= t.MEANINGFUL_RAIN_MM)[0]
    kdd = np.array(
        [
            degree_days_above(f_to_c(hi), f_to_c(lo), t.KILLING_DEGREE_BASE_C)
            if not (np.isnan(hi) or np.isnan(lo))
            else 0.0
            for hi, lo in zip(tmax, tmin, strict=True)
        ]
    )
    deficit = s.etc - np.nan_to_num(rain)
    tmean = (tmax + tmin) / 2

    features = {
        "gdd_since_planting": float(s.gdd_cum[-1]),
        "rain_7d_mm": _sum(rain[last(7)]),
        "rain_14d_mm": _sum(rain[last(14)]),
        "rain_30d_mm": _sum(rain[last(30)]),
        "rain_60d_mm": _sum(rain[last(60)]),
        "rain_since_planting_mm": _sum(rain),
        "days_since_meaningful_rain": float(
            len(s.dates) - 1 - meaningful[-1] if meaningful.size else len(s.dates)
        ),
        "longest_dry_spell_days": float(_longest_run(dry)),
        "current_dry_spell_days": float(_trailing_run(dry)),
        "max_consecutive_wet_days": float(_longest_run(wet)),
        "very_heavy_rain_days": float(np.sum(rain >= t.VERY_HEAVY_RAIN_MM)),
        "tmean_7d_f": _mean(tmean[last(7)]),
        "tmean_30d_f": _mean(tmean[last(30)]),
        "tmax_mean_7d_f": _mean(tmax[last(7)]),
        "tmax_max_7d_f": _max(tmax[last(7)]),
        "tmax_max_30d_f": _max(tmax[last(30)]),
        "heat_days_since_planting": float(np.sum(heat)),
        "heat_days_30d": float(np.sum(heat[last(30)])),
        "max_consecutive_heat_days": float(_longest_run(heat)),
        "killing_degree_days_29c": float(kdd.sum()),
        "warm_nights_since_planting": float(np.sum(warm_night)),
        "warm_nights_30d": float(np.sum(warm_night[last(30)])),
        "crop_water_use_since_planting_mm": _sum(s.etc),
        "water_deficit_30d_mm": _sum(deficit[last(30)]),
        "water_deficit_since_planting_mm": _sum(deficit),
        "weather_completeness": float(s.complete.mean()) if len(s.dates) else 0.0,
    }

    silking = s.silking_date()
    if silking is not None:
        pre = s.window(planting, silking - timedelta(t.SILKING_WINDOW_DAYS + 1))
        around = s.window(
            silking - timedelta(t.SILKING_WINDOW_DAYS), silking + timedelta(t.SILKING_WINDOW_DAYS)
        )
        features["rain_before_silking_mm"] = _sum(rain[pre])
        features["rain_around_silking_mm"] = _sum(rain[around])
        features["heat_days_around_silking"] = float(np.sum(heat[around]))
        features["water_deficit_around_silking_mm"] = _sum(deficit[around])
        fill_start = silking + timedelta(t.SILKING_WINDOW_DAYS + 1)
        if fill_start <= as_of:
            fill = s.window(fill_start, as_of)
            features["rain_grain_fill_mm"] = _sum(rain[fill])
            features["heat_days_grain_fill"] = float(np.sum(heat[fill]))
            features["warm_nights_grain_fill"] = float(np.sum(warm_night[fill]))
            features["water_deficit_grain_fill_mm"] = _sum(deficit[fill])
    return features, silking
