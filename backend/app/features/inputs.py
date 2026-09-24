"""
Raw inputs for one field (or plot) and one season, before feature engineering.

Every time-stamped input carries the day it became available. build_features()
only reads inputs available on or before the forecast date and asserts it.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

ManagementValue = float | str | None


@dataclass(frozen=True)
class DailyWeather:
    day: date
    tmax_f: float | None
    tmin_f: float | None
    prcp_mm: float | None


@dataclass(frozen=True)
class CanopyObservation:
    """Vegetation indices from one image of the field, e.g. {"ndvi": 0.81}.
    Only indices the sensor's bands support are present; none are filled in."""

    day: date
    values: Mapping[str, float]


@dataclass(frozen=True)
class SoilInputs:
    available_water_storage_cm: float | None  # plant-available water, top 100 cm
    organic_matter: float | None  # %
    ph: float | None
    root_zone_depth_cm: float | None
    drainage: str | None  # NRCS drainage class
    slope_percent: float | None


@dataclass(frozen=True)
class FieldInputs:
    season_year: int
    planting_date: date
    latitude: float
    # Decided at or before planting: e.g. genotype, nitrogen_lb_ac, irrigated.
    management: Mapping[str, ManagementValue] = field(default_factory=dict)
    canopy: Sequence[CanopyObservation] = ()
    # Mean of the other plots imaged on the same day (same site), for relative vigor.
    canopy_reference: Sequence[CanopyObservation] = ()
    weather: Sequence[DailyWeather] = ()
    soil: SoilInputs | None = None
    # Published county yields by year (bu/ac). A year's figure is published the
    # following February, so only years before season_year are ever used.
    county_yields: Mapping[int, float] = field(default_factory=dict)
