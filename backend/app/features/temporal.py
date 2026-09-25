"""Season timing: days and heat units since planting, and the inferred growth stage."""

from datetime import date

from app.features import thresholds as t

# Stage names match the dashboard's GrowthStage type.
STAGES = ("Emergence", "Vegetative", "Reproductive", "Grain Fill", "Maturity")


def growth_stage(gdd_since_planting: float) -> str:
    """Stage from heat units since planting (ISU PMR 1009 milestones). 'Reproductive'
    spans silking through early kernel development (R1-R2, ~500 GDD)."""
    if gdd_since_planting < t.GDD_EMERGENCE:
        return "Emergence"
    if gdd_since_planting < t.GDD_SILKING:
        return "Vegetative"
    if gdd_since_planting < t.GDD_SILKING + 500:
        return "Reproductive"
    if gdd_since_planting < t.GDD_BLACK_LAYER:
        return "Grain Fill"
    return "Maturity"


def temporal_features(planting: date, as_of: date) -> dict[str, float]:
    return {
        "days_since_planting": float((as_of - planting).days),
        "planting_day_of_year": float(planting.timetuple().tm_yday),
    }
