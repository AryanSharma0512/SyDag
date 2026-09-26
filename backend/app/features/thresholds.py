"""
Agronomic thresholds used to build features. Each value is documented, with its
source and confidence, in ml/research/agronomy_thresholds.md; the machine-readable
copy is ml/research/agronomy_thresholds.yaml and a test keeps the two in step.

These values define *features* (counts, sums, windows). They never adjust a yield
directly: the trained model learns how much each one matters.
"""

# Growing degree days: modified 86/50 method (Gilmore & Rogers 1958; Barger 1969;
# Nielsen, Purdue). Daily max capped at 86 °F, daily min raised to 50 °F.
GDD_BASE_F = 50.0
GDD_CAP_F = 86.0

# Development milestones in GDD (°F) after planting (Abendroth et al. 2011, ISU PMR 1009).
GDD_EMERGENCE = 120.0
GDD_SILKING = 1300.0  # VT/R1
GDD_BLACK_LAYER = 2700.0  # R6, physiological maturity
# Window around silking in which kernel number is set (Purdue, ISU: the weeks around silking).
SILKING_WINDOW_DAYS = 14  # days either side of the estimated silking date

# Heat. Pollen viability and silk desiccation above 95 °F (ISU ICM; Nielsen, Purdue).
HEAT_STRESS_F = 95.0
# Yield declines steeply above 29 °C (84.2 °F) (Schlenker & Roberts 2009, PNAS).
KILLING_DEGREE_BASE_C = 29.0
# Warm nights increase respiration during grain fill (Purdue; Ohio State; Pioneer).
WARM_NIGHT_F = 70.0

# Precipitation day definitions (ETCCDI climate-extremes indices, WMO/CLIVAR).
DRY_DAY_MM = 1.0  # CDD / CWD: a wet day has at least 1 mm
MEANINGFUL_RAIN_MM = 10.0  # R10mm: heavy precipitation day
VERY_HEAVY_RAIN_MM = 20.0  # R20mm: very heavy precipitation day

# Crop water demand: FAO-56 Hargreaves reference ET (eq. 52) times single crop
# coefficients for field maize (FAO-56 Table 12: Kc mid 1.20, Kc end 0.60-0.35;
# cereals Kc ini 0.3).
KC_INITIAL = 0.3
KC_MID = 1.2
KC_END = 0.6
GDD_KC_RISE_START = 350.0  # end of the initial stage, roughly V4-V5 at ~84 GDD per leaf

# Water stress, used only by the weather outlook's provisional scenario scorer
# (app/weather_outlook/stress.py), never as a model feature. FAO-56 Table 22: field maize
# tolerates depletion of this share of root-zone available water before transpiration
# drops. FAO-33 (Doorenbos & Kassam 1979) yield response factors for maize by growth period:
# relative yield loss = Ky x relative evapotranspiration deficit.
DEPLETION_FRACTION_P = 0.55
KY_VEGETATIVE = 0.4
KY_FLOWERING = 1.5
KY_YIELD_FORMATION = 0.5
KY_RIPENING = 0.2

# Soil drainage classes (USDA NRCS), ordered from driest to wettest.
DRAINAGE_ORDER = (
    "Excessively drained",
    "Somewhat excessively drained",
    "Well drained",
    "Moderately well drained",
    "Somewhat poorly drained",
    "Poorly drained",
    "Very poorly drained",
)
POORLY_DRAINED_FROM = "Somewhat poorly drained"  # ponding and saturation risk (Purdue)
