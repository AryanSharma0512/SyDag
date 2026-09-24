"""
Point-in-time feature assembly: FieldInputs + forecast date -> model feature row.

The only entry point training and serving use. Inputs dated after the forecast
date are dropped first, then the assertion below checks that nothing later got
through, so a forecast for July 31 can never see August rain or imagery.
"""

import math
from dataclasses import dataclass, replace
from datetime import date

import numpy as np

from app.features.inputs import FieldInputs
from app.features.soil import soil_features, soil_weather_interactions
from app.features.temporal import growth_stage, temporal_features
from app.features.vegetation import canopy_features
from app.features.weather import weather_features

FeatureValue = float | str | None


class LeakageError(AssertionError):
    """An input dated after the forecast date reached feature engineering."""


def visible_inputs(inputs: FieldInputs, as_of: date) -> FieldInputs:
    """The inputs as they would have looked on as_of."""
    return replace(
        inputs,
        canopy=tuple(o for o in inputs.canopy if o.day <= as_of),
        canopy_reference=tuple(o for o in inputs.canopy_reference if o.day <= as_of),
        weather=tuple(d for d in inputs.weather if d.day <= as_of),
        county_yields={y: v for y, v in inputs.county_yields.items() if y < inputs.season_year},
    )


def assert_point_in_time(inputs: FieldInputs, as_of: date) -> None:
    late = [f"canopy image {o.day}" for o in inputs.canopy if o.day > as_of]
    late += [f"reference image {o.day}" for o in inputs.canopy_reference if o.day > as_of]
    late += [f"weather {d.day}" for d in inputs.weather if d.day > as_of]
    late += [f"county yield {y}" for y in inputs.county_yields if y >= inputs.season_year]
    if late:
        raise LeakageError(f"inputs after {as_of}: {', '.join(late[:5])}")


def history_features(county_yields: dict[int, float], season_year: int) -> dict[str, float]:
    past = sorted((y, v) for y, v in county_yields.items() if y < season_year)
    out: dict[str, float] = {}
    recent = [v for _, v in past[-5:]]
    if len(recent) >= 3:
        out["county_yield_5yr_avg"] = float(np.mean(recent))
    if past and past[-1][0] == season_year - 1:
        out["county_yield_prev_year"] = float(past[-1][1])
    last10 = past[-10:]
    if len(last10) >= 5:
        years = np.array([y for y, _ in last10], dtype=float)
        out["county_yield_trend"] = float(np.polyfit(years, [v for _, v in last10], 1)[0])
    return out


def _management(values: dict[str, FeatureValue]) -> dict[str, FeatureValue]:
    out: dict[str, FeatureValue] = {}
    for key, value in values.items():
        if isinstance(value, bool):
            out[key] = float(value)
        elif isinstance(value, int | float):
            out[key] = float(value)
        else:
            out[key] = value
    return out


@dataclass(frozen=True)
class SeasonStatus:
    gdd_since_planting: float
    stage: str
    silking: date | None


def build_features(inputs: FieldInputs, as_of: date) -> dict[str, FeatureValue]:
    """Every feature computable from what was known on as_of. Features that can't be
    computed yet (no image, silking not reached) are left out; the model's schema
    decides which of them it needs and whether they may be missing."""
    visible = visible_inputs(inputs, as_of)
    assert_point_in_time(visible, as_of)

    weather, silking = weather_features(
        visible.weather, visible.planting_date, as_of, visible.latitude
    )
    soil = soil_features(visible.soil)
    features: dict[str, FeatureValue] = {}
    features.update(temporal_features(visible.planting_date, as_of))
    features.update(_management(dict(visible.management)))
    features.update(weather)
    features.update(soil)
    features.update(soil_weather_interactions(soil, weather))
    features.update(history_features(dict(visible.county_yields), visible.season_year))
    features.update(canopy_features(visible.canopy, visible.canopy_reference, as_of, silking))
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in features.items()}


def season_status(inputs: FieldInputs, as_of: date) -> SeasonStatus:
    visible = visible_inputs(inputs, as_of)
    weather, silking = weather_features(
        visible.weather, visible.planting_date, as_of, visible.latitude
    )
    gdd = float(weather.get("gdd_since_planting", 0.0))
    return SeasonStatus(gdd_since_planting=gdd, stage=growth_stage(gdd), silking=silking)
