"""
API response contract.

Mirrors src/types/agricultural.ts one-to-one. Python attributes are snake_case;
JSON is camelCase via the alias generator, so responses match the TypeScript
types exactly. If you change a model here, change the TS type too (and vice versa).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _json_name(name: str) -> str:
    # `yield` is a Python keyword, so those attributes are spelled `yield_`.
    return "yield" if name == "yield_" else to_camel(name)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=_json_name, populate_by_name=True, extra="forbid")


GrowthStage = Literal["Emergence", "Vegetative", "Reproductive", "Grain Fill", "Maturity"]
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
    cation_exchange_capacity: float | None = None  # meq/100g; not every source reports it
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
    category: Literal["Vegetation", "Weather", "Soil", "Temporal", "Management", "History"]
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
    # What the 16 cells are, e.g. "16 neighbouring trial plots, each forecast by the model".
    description: str | None = None
    # "model": every zone value comes from data or the model; "illustrative": demo layer.
    provenance: Literal["illustrative", "model"] | None = None


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
    # Absent before the first crop image: there is nothing to map yet.
    spatial: SpatialContext | None = None


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
    name: str  # e.g. "Competition multispectral observations"
    short_name: str  # e.g. "Hackathon data", "PRISM / NOAA"
    purpose: str  # e.g. "Crop observations", "Weather"
    # `challenge` sources are provided by the hackathon; `practice` is the public research
    # dataset used until then; `public` sources are government data SoilSignal fetches;
    # `model` is SoilSignal's own model output; `candidate` sources are not connected yet.
    role: Literal["challenge", "practice", "public", "model", "candidate"]
    status_label: str  # e.g. "Challenge-provided"
    detail: str


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
    models_loaded: int
    # Plain label for the data behind the forecasts, e.g. "Practice data" or "Demo data".
    dataset_label: str


class ModelInfo(ApiModel):
    model_id: str
    algorithm: str
    target: str
    unit: str
    validation: str
    rmse: float
    mae: float
    r2: float
    trained_at: str
    as_of: str | None
    interval_level: float
    features: list[str]


FeatureInput = float | int | str | None


class PredictRequest(ApiModel):
    features: dict[str, FeatureInput]
    # Pick a model explicitly, or let the API choose the model valid on this ISO date.
    model_id: str | None = None
    as_of_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class PredictResponse(ApiModel):
    model_id: str
    yield_: float
    unit: str
    lower_bound: float
    upper_bound: float
    interval_level: float
    confidence: float
    confidence_rating: Literal["LOW", "MODERATE", "HIGH"]
    drivers: list[FeatureImportanceItem]


# ---- Location context: public data for a field's coordinates -----------------
# Served by /api/context/*. Values are normalized from USDA and NOAA services;
# `retrievedAt` is when SoilSignal fetched them.


class County(ApiModel):
    name: str  # e.g. "Tippecanoe County"
    state_code: str  # e.g. "IN"
    state_name: str
    fips: str  # 5-digit state + county code, e.g. "18157"


class SoilProfile(ApiModel):
    map_unit_key: str
    map_unit_name: str  # e.g. "Chalmers silty clay loam"
    series: str  # dominant soil component, e.g. "Chalmers"
    component_percent: float  # share of the map unit, 0-100
    taxonomic_class: str | None
    texture: str | None  # surface horizon, e.g. "Silty clay loam"
    drainage: str | None  # e.g. "Poorly drained"
    hydrologic_group: str | None  # e.g. "B/D"
    available_water_capacity: float | None  # cm of water per cm of soil, top 100 cm
    available_water_storage_cm: float | None  # total plant-available water, top 100 cm
    available_water_class: Literal["Low", "Moderate", "High"] | None
    organic_matter: float | None  # %, surface horizon
    ph: float | None  # surface horizon, 1:1 water
    root_zone_depth_cm: float | None  # to the first restrictive layer, else profile depth
    slope_percent: float | None
    source: str
    retrieved_at: str


class WeatherStation(ApiModel):
    id: str  # GHCN-Daily station id, e.g. "USC00129430"
    name: str
    latitude: float
    longitude: float
    distance_km: float


class WeatherSummary(ApiModel):
    as_of: str  # ISO date the summary describes
    observed_through: str | None  # last day with observations on or before as_of
    rainfall_last_7_days_mm: float
    rainfall_last_30_days_mm: float
    avg_temp_last_30_days_f: float | None
    season_start: str  # ISO date the season totals count from
    gdd_since_season_start: float  # growing degree days, base 50 °F, cap 86 °F
    heat_days: int  # days reaching 95 °F or more since season start
    longest_dry_spell_days: int  # longest run of days under 1 mm of rain since season start
    data_completeness: float  # share of season days with rain and temperature records, 0-1


class ObservedWeather(ApiModel):
    station: WeatherStation
    summaries: list[WeatherSummary]  # one per requested date, in request order
    source: str
    retrieved_at: str


class YieldYear(ApiModel):
    year: int
    yield_: float


class YieldHistory(ApiModel):
    county: County
    years: list[YieldYear]  # oldest first
    five_year_average: float | None  # mean of the 5 most recent years
    unit: str
    source: str
    retrieved_at: str


class ContextPart[T](ApiModel):
    """One data source's result. The sources fail independently, so a missing
    key or an unresponsive service affects only its own part."""

    status: Literal["ok", "unavailable", "not_configured"]
    data: T | None = None
    message: str | None = None  # why the data is missing, in plain language


class LocationContext(ApiModel):
    latitude: float
    longitude: float
    county: County | None
    soil: ContextPart[SoilProfile]
    weather: ContextPart[ObservedWeather]
    yield_history: ContextPart[YieldHistory]
