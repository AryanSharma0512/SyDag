"""
API response contract.

Mirrors src/types/agricultural.ts one-to-one. Python attributes are snake_case;
JSON is camelCase via the alias generator, so responses match the TypeScript
types exactly. If you change a model here, change the TS type too (and vice versa).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


def _json_name(name: str) -> str:
    # `yield` is a Python keyword, so those attributes are spelled `yield_`.
    return "yield" if name == "yield_" else to_camel(name)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=_json_name, populate_by_name=True, extra="forbid")


GrowthStage = Literal["Emergence", "Vegetative", "Reproductive", "Maturity"]
Influence = Literal["positive", "negative", "neutral"]


class FieldMeta(ApiModel):
    id: str
    name: str
    crop: str
    season: int
    latitude: float
    longitude: float
    location: str
    acreage: float
    regional_baseline: float  # bu/ac 5-year average
    soil_classification: str
    irrigation_status: Literal["Dryland", "Center Pivot", "Drip"]


class WeatherContext(ApiModel):
    rainfall_30_day: float  # mm
    rainfall_comparison: float  # % delta vs 30-year normal
    rainfall_status: Literal["deficit", "normal", "surplus"]
    gdd_accumulated: float
    gdd_comparison: float  # % delta
    heat_exposure_days: int  # days > 95°F
    dry_spell_days: int  # longest dry run this season
    updated_ago: str
    avg_temperature_f: float
    et0_demand_mm: float  # reference evapotranspiration


class SoilContext(ApiModel):
    awc: Literal["Low", "Moderate", "High"]
    drainage: str
    organic_matter: float  # %
    ph: float
    dominant_texture: str
    cation_exchange_capacity: float  # meq/100g
    root_zone_depth_cm: float
    source: str


class ModelExplanation(ApiModel):
    id: str
    title: str
    influence: Influence
    influence_label: Literal[
        "Positive influence", "Negative influence", "Neutral / buffering influence"
    ]
    description: str
    metric_reference: str | None = None


class FeatureImportanceItem(ApiModel):
    name: str
    weight: float  # percentage 0-100
    category: Literal["Vegetation", "Weather", "Soil", "Temporal"]
    direction: Influence


class SpatialZone(ApiModel):
    id: str
    name: str
    grid_row: int
    grid_col: int
    predicted_yield: float  # bu/ac
    ndvi: float
    rainfall_30_day: float  # mm
    soil: str
    heat_stress_index: float  # 0.0-1.0
    satellite_reflectance: float  # 0.0-1.0


class Bounds(ApiModel):
    north: float
    south: float
    east: float
    west: float


class SpatialContext(ApiModel):
    zones: list[SpatialZone]
    resolution_meters: float
    tile_date: str
    satellite_platform: str
    bounds: Bounds


class ForecastSnapshot(ApiModel):
    id: str
    date: str  # ISO date, e.g. '2026-07-22'
    display_date: str  # e.g. 'Jul 22'
    stage: GrowthStage
    stage_subtext: str
    yield_: float
    unit: str
    lower_bound: float
    upper_bound: float
    confidence: float  # percentage 0-100
    confidence_rating: Literal["LOW", "MODERATE", "HIGH"]
    generated_at: str
    weather: WeatherContext
    soil: SoilContext
    explanations: list[ModelExplanation]
    feature_importance: list[FeatureImportanceItem]
    spatial: SpatialContext


class EventMarker(ApiModel):
    date: str
    display_date: str
    title: str
    type: Literal["rain", "heat", "dry", "management", "recovery"]
    summary: str
    hover_detail: str


class VegetationObservation(ApiModel):
    date: str
    display_date: str
    ndvi: float
    ndre: float
    regional_baseline_ndvi: float
    gndvi: float | None = None
    evi: float | None = None
    is_forecast_date_point: bool | None = None


class YearlyYield(ApiModel):
    year: int
    yield_: float
    type: Literal["historical", "forecast"]


class HistoricalContext(ApiModel):
    regional_5_year_avg: float
    regional_delta_pct: float
    yearly_yields: list[YearlyYield]


class DataSource(ApiModel):
    id: str
    name: str
    source: str
    resolution: str
    last_observation: str
    status: Literal["active", "degraded", "cached"]
    badge: str


class ForecastMetadata(ApiModel):
    forecast_generated_at: str
    dataset_version: str
    last_satellite_pass: str | None = None


class FieldForecast(ApiModel):
    field: FieldMeta
    story_description: str
    snapshots: list[ForecastSnapshot]
    full_vegetation_series: list[VegetationObservation]
    vegetation_timeline: list[VegetationObservation] | None = None
    events: list[EventMarker]
    historical: HistoricalContext
    sources: list[DataSource]
    spatial: SpatialContext | None = None
    feature_importance: list[FeatureImportanceItem] | None = None
    metadata: ForecastMetadata | None = None


class Health(ApiModel):
    status: Literal["ok"]
    version: str
    data_source: str
