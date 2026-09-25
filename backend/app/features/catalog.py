"""
What each feature means: its dashboard category, its ablation group, and the plain
phrases used when it drives a forecast ("Rainfall deficit, last 30 days").

Phrases describe association, not cause: a driver is a signal the model leaned on.
"""

from dataclasses import dataclass
from typing import Literal

from app.features.vegetation import INDEX_NAMES

Category = Literal["Vegetation", "Weather", "Soil", "Temporal", "Management", "History"]
# Ablation groups. "soil_weather" features need both soil and weather to exist.
Group = Literal["crop", "weather", "soil", "soil_weather", "history", "management", "temporal"]
Dtype = Literal["float", "int", "category"]


@dataclass(frozen=True)
class FeatureInfo:
    name: str
    label: str
    category: Category
    group: Group
    high: str  # phrase when the value is above typical
    low: str  # phrase when the value is below typical
    dtype: Dtype = "float"


_INDEX_LABELS = {
    "ndvi": "canopy greenness (NDVI)",
    "ndre": "canopy chlorophyll (NDRE)",
    "gndvi": "green canopy index (GNDVI)",
    "evi": "enhanced vegetation index (EVI)",
}


def _vegetation() -> list[FeatureInfo]:
    out = [
        FeatureInfo(
            "canopy_images_to_date",
            "Images of the crop so far",
            "Vegetation",
            "crop",
            "Many crop images so far",
            "Few crop images so far",
        ),
        FeatureInfo(
            "days_since_canopy_image",
            "Days since the last crop image",
            "Vegetation",
            "crop",
            "Crop image is not recent",
            "Recent crop image",
        ),
    ]
    for index in INDEX_NAMES:
        x = _INDEX_LABELS[index]
        cap = x[0].upper() + x[1:]
        out += [
            FeatureInfo(
                f"{index}_current",
                f"{cap}, latest image",
                "Vegetation",
                "crop",
                f"Strong {x}",
                f"Weak {x}",
            ),
            FeatureInfo(
                f"{index}_mean_to_date",
                f"{cap}, season average so far",
                "Vegetation",
                "crop",
                f"Strong {x} through the season",
                f"Weak {x} through the season",
            ),
            FeatureInfo(
                f"{index}_max_to_date",
                f"Peak {x} so far",
                "Vegetation",
                "crop",
                f"High peak {x}",
                f"Low peak {x}",
            ),
            FeatureInfo(
                f"{index}_min_to_date",
                f"Lowest {x} so far",
                "Vegetation",
                "crop",
                f"No weak spell in {x}",
                f"Weak spell in {x}",
            ),
            FeatureInfo(
                f"{index}_change_from_previous",
                f"Change in {x} since the previous image",
                "Vegetation",
                "crop",
                f"{cap} declining less than typical",
                f"{cap} declining more than typical",
            ),
            FeatureInfo(
                f"{index}_trend_per_10d",
                f"{cap} trend",
                "Vegetation",
                "crop",
                f"Stronger {x} trend than typical",
                f"Weaker {x} trend than typical",
            ),
            FeatureInfo(
                f"{index}_area_to_date",
                f"Cumulative {x}",
                "Vegetation",
                "crop",
                f"High cumulative {x}",
                f"Low cumulative {x}",
            ),
            FeatureInfo(
                f"{index}_near_silking",
                f"{cap} around silking",
                "Vegetation",
                "crop",
                f"Strong {x} around silking",
                f"Weak {x} around silking",
            ),
            FeatureInfo(
                f"{index}_vs_site_mean",
                f"{cap} vs. neighbouring plots",
                "Vegetation",
                "crop",
                f"{cap} above neighbouring plots",
                f"{cap} below neighbouring plots",
            ),
        ]
    return out


_W = "Weather"
_OTHERS = [
    FeatureInfo(
        "gdd_since_planting",
        "Growing degree days since planting",
        _W,
        "weather",
        "Ahead in heat units",
        "Behind in heat units",
    ),
    FeatureInfo(
        "rain_7d_mm", "Rainfall, last 7 days", _W, "weather", "Wet last 7 days", "Dry last 7 days"
    ),
    FeatureInfo(
        "rain_14d_mm",
        "Rainfall, last 14 days",
        _W,
        "weather",
        "Wet last 14 days",
        "Dry last 14 days",
    ),
    FeatureInfo(
        "rain_30d_mm",
        "Rainfall, last 30 days",
        _W,
        "weather",
        "Above-typical rainfall, last 30 days",
        "Rainfall deficit, last 30 days",
    ),
    FeatureInfo(
        "rain_60d_mm",
        "Rainfall, last 60 days",
        _W,
        "weather",
        "Above-typical rainfall, last 60 days",
        "Rainfall deficit, last 60 days",
    ),
    FeatureInfo(
        "rain_since_planting_mm",
        "Rainfall since planting",
        _W,
        "weather",
        "Wet season so far",
        "Dry season so far",
    ),
    FeatureInfo(
        "days_since_meaningful_rain",
        "Days since a 10 mm rain",
        _W,
        "weather",
        "Long wait since a soaking rain",
        "Recent soaking rain",
    ),
    FeatureInfo(
        "longest_dry_spell_days",
        "Longest dry spell since planting",
        _W,
        "weather",
        "Long dry spell this season",
        "No long dry spell this season",
    ),
    FeatureInfo(
        "current_dry_spell_days",
        "Current dry spell",
        _W,
        "weather",
        "In a dry spell",
        "Recent rain",
    ),
    FeatureInfo(
        "max_consecutive_wet_days",
        "Longest wet spell since planting",
        _W,
        "weather",
        "Long wet spell this season",
        "No long wet spell",
    ),
    FeatureInfo(
        "very_heavy_rain_days",
        "Days with 20 mm or more of rain",
        _W,
        "weather",
        "Several very heavy rains",
        "Few very heavy rains",
    ),
    FeatureInfo(
        "tmean_7d_f",
        "Average temperature, last 7 days",
        _W,
        "weather",
        "Warm last 7 days",
        "Cool last 7 days",
    ),
    FeatureInfo(
        "tmean_30d_f",
        "Average temperature, last 30 days",
        _W,
        "weather",
        "Warm last 30 days",
        "Cool last 30 days",
    ),
    FeatureInfo(
        "tmax_mean_7d_f",
        "Average high, last 7 days",
        _W,
        "weather",
        "Hot afternoons, last 7 days",
        "Mild afternoons, last 7 days",
    ),
    FeatureInfo(
        "tmax_max_7d_f",
        "Hottest day, last 7 days",
        _W,
        "weather",
        "Very hot day in the last week",
        "No very hot day in the last week",
    ),
    FeatureInfo(
        "tmax_max_30d_f",
        "Hottest day, last 30 days",
        _W,
        "weather",
        "Very hot day in the last month",
        "No very hot day in the last month",
    ),
    FeatureInfo(
        "heat_days_since_planting",
        "Days at 95 °F or hotter",
        _W,
        "weather",
        "Frequent heat stress (95 °F days)",
        "Few heat-stress days",
    ),
    FeatureInfo(
        "heat_days_30d",
        "Days at 95 °F or hotter, last 30 days",
        _W,
        "weather",
        "Recent heat stress",
        "No recent heat stress",
    ),
    FeatureInfo(
        "max_consecutive_heat_days",
        "Longest run of 95 °F days",
        _W,
        "weather",
        "Extended heat wave",
        "No extended heat wave",
    ),
    FeatureInfo(
        "killing_degree_days_29c",
        "Heat above 29 °C (degree days)",
        _W,
        "weather",
        "Accumulated damaging heat",
        "Little damaging heat",
    ),
    FeatureInfo(
        "warm_nights_since_planting",
        "Nights at 70 °F or warmer",
        _W,
        "weather",
        "Frequent warm nights",
        "Few warm nights",
    ),
    FeatureInfo(
        "warm_nights_30d",
        "Warm nights, last 30 days",
        _W,
        "weather",
        "Recent warm nights",
        "Cool recent nights",
    ),
    FeatureInfo(
        "crop_water_use_since_planting_mm",
        "Estimated crop water use",
        _W,
        "weather",
        "High crop water demand",
        "Low crop water demand",
    ),
    FeatureInfo(
        "water_deficit_30d_mm",
        "Water deficit, last 30 days",
        _W,
        "weather",
        "Water deficit, last 30 days",
        "Adequate water, last 30 days",
    ),
    FeatureInfo(
        "water_deficit_since_planting_mm",
        "Water deficit since planting",
        _W,
        "weather",
        "Season-long water deficit",
        "Adequate water this season",
    ),
    FeatureInfo(
        "weather_completeness",
        "Share of days with weather records",
        _W,
        "weather",
        "Complete weather record",
        "Gaps in the weather record",
    ),
    FeatureInfo(
        "rain_before_silking_mm",
        "Rainfall before silking",
        _W,
        "weather",
        "Wet vegetative period",
        "Dry vegetative period",
    ),
    FeatureInfo(
        "rain_around_silking_mm",
        "Rainfall around silking",
        _W,
        "weather",
        "Rain around pollination",
        "Rainfall deficit around pollination",
    ),
    FeatureInfo(
        "heat_days_around_silking",
        "95 °F days around silking",
        _W,
        "weather",
        "Heat stress around pollination",
        "No heat stress around pollination",
    ),
    FeatureInfo(
        "water_deficit_around_silking_mm",
        "Water deficit around silking",
        _W,
        "weather",
        "Water deficit around pollination",
        "Adequate water around pollination",
    ),
    FeatureInfo(
        "rain_grain_fill_mm",
        "Rainfall during grain fill",
        _W,
        "weather",
        "Rain during grain fill",
        "Dry grain fill",
    ),
    FeatureInfo(
        "heat_days_grain_fill",
        "95 °F days during grain fill",
        _W,
        "weather",
        "Heat stress during grain fill",
        "No heat stress during grain fill",
    ),
    FeatureInfo(
        "warm_nights_grain_fill",
        "Warm nights during grain fill",
        _W,
        "weather",
        "Warm nights during grain fill",
        "Cool nights during grain fill",
    ),
    FeatureInfo(
        "water_deficit_grain_fill_mm",
        "Water deficit during grain fill",
        _W,
        "weather",
        "Water deficit during grain fill",
        "Adequate water during grain fill",
    ),
    FeatureInfo(
        "soil_available_water_cm",
        "Soil available water capacity",
        "Soil",
        "soil",
        "High soil water-holding capacity",
        "Low soil water-holding capacity",
    ),
    FeatureInfo(
        "soil_organic_matter_pct",
        "Soil organic matter",
        "Soil",
        "soil",
        "High soil organic matter",
        "Low soil organic matter",
    ),
    FeatureInfo("soil_ph", "Soil pH", "Soil", "soil", "Higher soil pH", "Lower soil pH"),
    FeatureInfo(
        "soil_root_zone_depth_cm",
        "Root zone depth",
        "Soil",
        "soil",
        "Deep root zone",
        "Shallow root zone",
    ),
    FeatureInfo(
        "soil_drainage_rank",
        "Soil drainage (wetter is higher)",
        "Soil",
        "soil",
        "Poorly drained soil",
        "Well-drained soil",
    ),
    FeatureInfo("soil_slope_pct", "Slope", "Soil", "soil", "Sloping ground", "Level ground"),
    FeatureInfo(
        "water_deficit_30d_share_of_soil_storage",
        "30-day water deficit relative to soil storage",
        "Soil",
        "soil_weather",
        "Water deficit large for this soil",
        "Soil water reserve covering demand",
    ),
    FeatureInfo(
        "very_heavy_rain_days_on_poorly_drained_soil",
        "Very heavy rains on poorly drained soil",
        "Soil",
        "soil_weather",
        "Heavy rain on poorly drained soil",
        "No heavy rain on poorly drained soil",
    ),
    FeatureInfo(
        "county_yield_5yr_avg",
        "County 5-year average yield",
        "History",
        "history",
        "High-yielding county",
        "Lower-yielding county",
    ),
    FeatureInfo(
        "county_yield_prev_year",
        "County yield last year",
        "History",
        "history",
        "Strong county yield last year",
        "Weak county yield last year",
    ),
    FeatureInfo(
        "county_yield_trend",
        "County yield trend (bu/ac per year)",
        "History",
        "history",
        "Rising county yields",
        "Flat or falling county yields",
    ),
    FeatureInfo(
        "nitrogen_lb_ac",
        "Nitrogen rate",
        "Management",
        "management",
        "High nitrogen rate",
        "Low nitrogen rate",
    ),
    FeatureInfo("irrigated", "Irrigated", "Management", "management", "Irrigated", "Rainfed"),
    FeatureInfo(
        "genotype", "Hybrid", "Management", "management", "Hybrid", "Hybrid", dtype="category"
    ),
    FeatureInfo(
        "days_since_planting",
        "Days since planting",
        "Temporal",
        "temporal",
        "Later in the season",
        "Earlier in the season",
    ),
    FeatureInfo(
        "planting_day_of_year",
        "Planting date",
        "Temporal",
        "temporal",
        "Late planting",
        "Early planting",
    ),
]

CATALOG: dict[str, FeatureInfo] = {f.name: f for f in _vegetation() + _OTHERS}


def info(name: str) -> FeatureInfo:
    """Catalog entry, or a neutral description for a feature it doesn't know
    (e.g. a management column a new dataset adds)."""
    if name in CATALOG:
        return CATALOG[name]
    label = name.replace("_", " ").capitalize()
    return FeatureInfo(
        name, label, "Management", "management", f"High {label.lower()}", f"Low {label.lower()}"
    )
