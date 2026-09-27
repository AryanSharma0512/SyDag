"""
Provisional scorer: how much a weather trajectory would stress maize, until the yield
model scores trajectories itself.

The outlook's favorable / typical / adverse categories are terciles of a score over the
historical trajectories. The intended score is the SoilSignal yield model's prediction
under each trajectory (see scenarios.couple_yield). Until a weather-sensitive yield model
exists, the score is a published crop-water relationship with no fitted or hand-picked
weights:

    rainfed    relative yield from water supply, FAO-33: for each growth period in the
               horizon, 1 - Ky x (1 - ETa/ETc), multiplied together. ETc is SoilSignal's
               crop demand (Hargreaves ET0 x Kc by growing degree days); ETa comes from an
               FAO-56 root-zone water balance whose capacity is the site's SSURGO available
               water storage and which starts full on the season start date.
    irrigated  degree days above 29 C, each weighted by its growth period's Ky (irrigation
               removes water supply as the limiting factor; heat remains).

Known limits, stated in the outlook's category basis: rain beyond what the root zone holds
drains away (it is neither rewarded nor penalized, so waterlogging is not scored); direct
heat damage to pollination is not in the rainfed score; stages come from reference
planting and fixed GDD milestones, not the hybrid.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np

from app.features import thresholds as t
from app.weather_outlook.features import (
    DailyArrays,
    crop_water_use,
    gdd_since_planting,
    silking_index,
)

STAGES = ("vegetative", "flowering", "yield_formation", "ripening")
KY = {
    "vegetative": t.KY_VEGETATIVE,
    "flowering": t.KY_FLOWERING,
    "yield_formation": t.KY_YIELD_FORMATION,
    "ripening": t.KY_RIPENING,
}
# End of the Kc mid-season plateau (app.features.weather.crop_coefficient): the boundary
# between yield formation and ripening.
MID_SEASON_END_GDD = t.GDD_SILKING + (t.GDD_BLACK_LAYER - t.GDD_SILKING) / 2


def stage_calendar(season: DailyArrays, planting: date) -> np.ndarray:
    """Growth period per day (index into STAGES, -1 before planting or after maturity)."""
    cum = gdd_since_planting(season, planting)
    start = (planting - season.first).days
    silk = silking_index(season, planting)
    w = t.SILKING_WINDOW_DAYS
    out = np.full(len(season), -1)
    for i in range(max(0, start), len(season)):
        if cum[i] >= t.GDD_BLACK_LAYER:
            break
        if silk is None or i < silk - w:
            out[i] = 0
        elif i <= silk + w:
            out[i] = 1
        elif cum[i] < MID_SEASON_END_GDD:
            out[i] = 2
        else:
            out[i] = 3
    return out


def water_balance(
    etc: np.ndarray, precip: np.ndarray, capacity_mm: float, start_depletion: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """FAO-56 single-layer root-zone balance. Returns end-of-day depletion (mm) and actual
    evapotranspiration (mm/day). Missing rain counts as none; missing demand as none."""
    p = t.DEPLETION_FRACTION_P
    readily = p * capacity_mm
    depletion = np.empty(len(etc))
    eta = np.empty(len(etc))
    dr = start_depletion
    for i, (demand, rain) in enumerate(zip(etc, precip, strict=True)):
        demand = 0.0 if np.isnan(demand) else demand
        rain = 0.0 if np.isnan(rain) else rain
        ks = 1.0 if dr <= readily else max(0.0, (capacity_mm - dr) / ((1 - p) * capacity_mm))
        eta[i] = ks * demand
        dr = min(capacity_mm, max(0.0, dr - rain + eta[i]))
        depletion[i] = dr
    return depletion, eta


def season_demand(season: DailyArrays, planting: date) -> np.ndarray:
    """Evaporative demand for the water balance: crop demand from planting, and the
    initial-stage coefficient over bare soil before planting."""
    etc = crop_water_use(season, planting)
    start = (planting - season.first).days
    if start > 0:
        etc[: min(start, len(season))] = t.KC_INITIAL * season.et0[: min(start, len(season))]
    return etc


@dataclass(frozen=True)
class StressScore:
    score: float  # higher is better for the crop
    details: dict[str, float]


def score_trajectory(
    season: DailyArrays,
    as_of: date,
    end: date,
    planting: date,
    capacity_mm: float,
    irrigated: bool,
) -> StressScore:
    """Score the horizon (days after as_of through end) of a season series that holds the
    observed days through as_of followed by one trajectory, continued to the season end
    so growth stages near the horizon's end are known."""
    i0 = (as_of - season.first).days + 1
    i1 = (end - season.first).days + 1
    stages = stage_calendar(season, planting)[i0:i1]
    if irrigated:
        weights = np.array([KY[STAGES[s]] if s >= 0 else 0.0 for s in stages])
        heat = float(np.sum(season.kdd[i0:i1] * weights))
        return StressScore(round(-heat, 2), {"stage_weighted_kdd_29c": round(heat, 2)})
    demand = season_demand(season, planting)
    depletion, eta = water_balance(demand, season.precip_mm, capacity_mm)
    etc = np.nan_to_num(demand[i0:i1])
    actual = eta[i0:i1]
    relative = 1.0
    details: dict[str, float] = {}
    for index, name in enumerate(STAGES):
        mask = stages == index
        need = float(etc[mask].sum())
        if need <= 0:
            continue
        ratio = float(actual[mask].sum()) / need
        factor = max(0.0, 1 - KY[name] * (1 - ratio))
        details[f"et_ratio_{name}"] = round(ratio, 4)
        relative *= factor
    end_depletion = float(depletion[i1 - 1]) if i1 > 0 else 0.0
    details["relative_yield_water"] = round(relative, 4)
    details["depletion_at_end_mm"] = round(end_depletion, 1)
    details["depletion_at_as_of_mm"] = round(float(depletion[i0 - 1]) if i0 > 0 else 0.0, 1)
    # Exact ties in water-limited yield (typically: no stress at all) are ordered by the
    # soil water left for the rest of the season.
    return StressScore(round(relative, 4) - 1e-6 * end_depletion / capacity_mm, details)


def depletion_through(
    season: DailyArrays, as_of: date, planting: date, capacity_mm: float
) -> float:
    """Root-zone depletion at the end of as_of from the observed season (a descriptor)."""
    i = (as_of - season.first).days + 1
    if i <= 0:
        return 0.0
    demand = season_demand(season, planting)[:i]
    depletion, _ = water_balance(demand, season.precip_mm[:i], capacity_mm)
    return float(depletion[-1])
