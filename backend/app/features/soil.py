"""
Soil features. Soil is fixed through the season, so these are known at planting.
They enter the model as context; the model, not a rule, decides what they are worth.
"""

import math

from app.features import thresholds as t
from app.features.inputs import SoilInputs


def drainage_rank(drainage: str | None) -> float:
    """0 = excessively drained ... 6 = very poorly drained."""
    if drainage is None:
        return math.nan
    try:
        return float(t.DRAINAGE_ORDER.index(drainage))
    except ValueError:
        return math.nan


def _num(value: float | None) -> float:
    return math.nan if value is None else float(value)


def soil_features(soil: SoilInputs | None) -> dict[str, float]:
    if soil is None:
        return {}
    return {
        "soil_available_water_cm": _num(soil.available_water_storage_cm),
        "soil_organic_matter_pct": _num(soil.organic_matter),
        "soil_ph": _num(soil.ph),
        "soil_root_zone_depth_cm": _num(soil.root_zone_depth_cm),
        "soil_drainage_rank": drainage_rank(soil.drainage),
        "soil_slope_pct": _num(soil.slope_percent),
    }


def soil_weather_interactions(
    soil: dict[str, float], weather: dict[str, float]
) -> dict[str, float]:
    """A few interactions with an agronomic rationale (see agronomy_thresholds.md):
    water demand relative to what the soil can store, and very heavy rain on soils
    prone to saturation."""
    out: dict[str, float] = {}
    storage_mm = soil.get("soil_available_water_cm", math.nan) * 10
    deficit = weather.get("water_deficit_30d_mm")
    if deficit is not None and storage_mm > 0:
        out["water_deficit_30d_share_of_soil_storage"] = deficit / storage_mm
    rank = soil.get("soil_drainage_rank", math.nan)
    heavy = weather.get("very_heavy_rain_days")
    if heavy is not None and not math.isnan(rank):
        poorly = rank >= t.DRAINAGE_ORDER.index(t.POORLY_DRAINED_FROM)
        out["very_heavy_rain_days_on_poorly_drained_soil"] = heavy if poorly else 0.0
    return out
