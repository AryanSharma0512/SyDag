# Agronomy thresholds for SoilSignal features (maize)

Last updated: 2026-09-24. Machine-readable copy: [`agronomy_thresholds.yaml`](agronomy_thresholds.yaml).
The values are used in `backend/app/features/thresholds.py`. A test keeps the code, this file's
YAML twin, and the sources in step.

## The rule this document serves

The literature supplies **structure**; the data supplies **weights**.

Every threshold below defines a *feature*: a count, a sum, or a window, such as "days at 95 °F or
hotter within 14 days of silking". None of them subtracts bushels from a forecast. There is no
`if rainfall > 100: yield -= 10` anywhere in SoilSignal. The trained model decides how much
each feature matters. The sensitivity checks then compare the model's behavior with the
qualitative expectations at the end of this file.

## Thresholds

| Variable | Threshold / window | Units | Stage | Expected relationship | Applicability | Source (year) | Confidence |
|---|---|---|---|---|---|---|---|
| GDD base | 50 | °F | Planting–R6 | Development ≈ 0 below | US Corn Belt standard | Nielsen, Purdue [1]; Gilmore & Rogers 1958; Barger 1969 | High |
| GDD cap | 86 | °F | Planting–R6 | No faster development above | US Corn Belt standard | Nielsen, Purdue [1] | High |
| Emergence | 120 | GDD °F | VE | Stage marker | 100–120 typical; soil temp governs until ~V6 | Nielsen, Purdue [2]; ISU PMR 1009 [3] | Medium |
| Silking (VT/R1) | 1,300 | GDD °F | R1 | Anchors pollination window | Hybrid-specific, ~1,200–1,450 | ISU PMR 1009 [3] (2011) | Medium |
| Black layer (R6) | 2,700 | GDD °F | R6 | End of grain fill | 105–115-day hybrids: 2,400–2,800 | ISU PMR 1009 [3]; Nielsen [1] | Medium |
| Pollination window | ±14 | days around silking | VT–R2 | Kernel number set; most stress-sensitive | General | ISU ICM [4]; Nielsen [5] | Medium |
| Heat-stress day | ≥ 95 | °F max | VT–R1, grain fill | Pollen viability ↓, silk desiccation; severe mainly with short soil moisture | Moisture-dependent | ISU ICM [4] | High |
| Damaging heat | > 29 | °C, degree days | Season | Yield ↑ to 29 °C, steep ↓ above | US counties 1950–2005 | Schlenker & Roberts 2009 [6] | High |
| Warm night | ≥ 70 | °F min | Grain fill | Respiration ↑, shorter grain fill | Corn Belt; fewer controlled studies | OSU [7]; Pioneer | Medium |
| Dry / wet day | < 1 / ≥ 1 | mm/day | Season | Dry spells (CDD), wet spells (CWD) | Climatology convention | ETCCDI [8] | Medium |
| Soaking rain | ≥ 10 | mm/day | Season | Showers largely intercepted/evaporated | Convention | ETCCDI R10mm [8] | Low |
| Very heavy rain | ≥ 20 | mm/day | Season; worst before V6 | Saturation → O₂ gone in ~48 h; young corn survives 2–4 days of ponding (less above 77 °F) | Depends on drainage, prior moisture | ETCCDI R20mm [8]; Nielsen [9] | Low |
| Crop coefficient, initial | 0.3 | × ET₀ | Planting–~V5 | Water demand = Kc × ET₀ | FAO-56 cereals | FAO-56 Table 12 [10] (1998) | High |
| Crop coefficient, mid | 1.20 | × ET₀ | Silking–dough | Peak demand; ISU puts it at ~0.3 in/day at tasseling | Field maize | FAO-56 [10]; ISU [11] | High |
| Crop coefficient, end | 0.60 (0.60–0.35) | × ET₀ | R6 | Demand falls through senescence | Field maize | FAO-56 [10] | High |
| Kc rise starts | 350 | GDD °F | ~V4–V5 | Schedule point for the Kc curve | Approximation | ISU PMR 1009 leaf interval [3]; FAO-56 [10] | Low |
| Allowed depletion p | 0.55 | share of root-zone available water | Season | Transpiration falls once depletion exceeds p × available water | Field maize; **weather outlook scorer only** | FAO-56 Table 22 [10] (1998) | Medium |
| Yield response Ky | 0.4 / 1.5 / 0.5 / 0.2 | relative yield loss ÷ relative ET deficit | Vegetative / flowering (silking ±14 d) / yield formation / ripening | 1 − Ya/Ym = Ky (1 − ETa/ETm) | Maize; **weather outlook scorer only** | Doorenbos & Kassam 1979, FAO-33; FAO maize crop information (1979) | Medium |

Reference ET uses the **Hargreaves equation (FAO-56 eq. 52)**, because it needs only daily
maximum and minimum temperature, which is exactly what NOAA GHCN-Daily provides. It is less
accurate than Penman-Monteith, which needs humidity, wind and radiation.

## The questions the brief asked

### Heat: at what stage, how long, under what moisture?

- **Stage.** Pollination is the sensitive window. ISU: above about 95 °F, pollen stops being viable
  and exposed silks desiccate [4]. After silking, heat mostly shortens grain fill.
- **Moisture decides severity.** ISU: "high temperatures will not severely stress corn
  pollination if soil moisture is adequate" [4]. Lobell et al. (2013) find that most of extreme
  heat's damage in the US runs through **vapor-pressure deficit and water stress**, not through
  direct injury to reproductive organs [12].
- **Dose.** Schlenker & Roberts (2009): US corn yield rises with temperature up to 29 °C, then
  falls steeply [6]. Lobell et al. (2011): each degree day above 30 °C cut yield about 1% under
  good rainfed conditions and 1.7% under drought, in >20,000 African trials [13].
- **Nights.** Minimums at or above 70 °F during grain fill raise respiration. Extension estimates
  are around 2% per °F of July night-time warming [7]. Confidence is lower here.
- **Features built:** `heat_days_since_planting`, `heat_days_30d`, `max_consecutive_heat_days`,
  `heat_days_around_silking`, `heat_days_grain_fill`, `killing_degree_days_29c` (single-sine),
  `warm_nights_*`. The heat × water interaction is left to the trees, which also see the
  water-deficit features.

### Drought and rainfall deficit

- **Demand is stage-dependent.** Peak water use at tasseling/silking is roughly 0.28–0.40 in/day
  [11]. ISU work summarizes severe stress at pollination as costing about 3–8% of yield per day
  (Claassen & Shaw) [11].
- **Rain alone is not enough.** 40 mm means different things at 0.3 in/day demand than at
  0.1 in/day, and on a silt loam versus a sand.
- **Features built:** `water_deficit_30d_mm`, `water_deficit_since_planting_mm`,
  `water_deficit_around_silking_mm` and `water_deficit_grain_fill_mm`, each computed as crop
  demand (Kc × Hargreaves ET₀) minus rain. Also rain windows (7/14/30/60 days, since planting,
  before and around silking, grain fill), `longest_dry_spell_days`, `current_dry_spell_days` and
  `days_since_meaningful_rain`.

### Excess water and flooding

- Saturated soil runs out of oxygen within about **48 hours**. Before V6 (growing point at or
  below the surface), corn survives **2–4 days** of ponding, and less when temperatures exceed
  about 77 °F [9]. Losses are small if flooding lasts under 48 hours.
- Risk depends on drainage, prior wetness, intensity and temperature, so there is **no
  "more rain = less yield" rule**.
- **Features built:** `very_heavy_rain_days` (ETCCDI R20mm), `max_consecutive_wet_days` (CWD),
  and the interaction `very_heavy_rain_days_on_poorly_drained_soil`.

### Growing degree days

The modified 86/50 °F method is the US standard (Gilmore & Rogers 1958; Barger 1969; NOAA).
The daily maximum is capped at 86 °F and the daily minimum is raised to 50 °F, then
GDD = (max + min) / 2 − 50 [1]. `test_features.py` reproduces Nielsen's three worked examples.
Silking and black-layer GDD are hybrid-specific. The practice dataset records GDD to anthesis
at Lincoln and Scottsbluff, which the dataset profile compares with the 1,300 used here.

### Soil

Soil properties enter as **features and interaction context, never as yield penalties**:

| Property | Typical range | Expected role | Source |
|---|---|---|---|
| Available water storage (top 100 cm) | Silt loam ~2.0–2.5 in/ft; sandy loam ~1.3 in/ft; sand 0.25–0.75 in/ft | Buffers dry spells; matters most under deficit | UNL G1850 [14] |
| pH (1:1 water) | Corn optimum 6.0–6.8; Iowa targets 6.5 (6.0 over calcareous subsoil) | Weak effect inside the normal range | ISU ICM 2013 [15]; Purdue field guide |
| Drainage class | 7 NRCS classes | Poorly drained: heavy-rain risk, drought buffer | NRCS; Nielsen [9] |
| Organic matter, root-zone depth, slope | — | Context | SSURGO |

Interactions built, each with a stated reason:

- `water_deficit_30d_share_of_soil_storage`: the 30-day deficit divided by the soil's
  plant-available water. This measures how much of the soil's reserve recent demand has used.
- `very_heavy_rain_days_on_poorly_drained_soil`: heavy rain matters most where water can't
  drain away.

Trees learn other interactions on their own, so no further products are added.

### Growth-stage awareness

Stages come from GDD accumulated since planting up to the forecast date. A window that hasn't
started yet produces **no feature, not a guess**. For example, `rain_around_silking_mm` does
not exist in a June forecast.

## Expected qualitative behavior (for sensitivity checks)

| Feature | Expected | Why |
|---|---|---|
| `water_deficit_30d_mm`, `water_deficit_around_silking_mm` | ↓ yield | Water stress, worst at pollination [4][11][12] |
| `heat_days_since_planting`, `killing_degree_days_29c` | ↓ | Heat above 29 °C / 95 °F [4][6] |
| `longest_dry_spell_days` | ↓ | Soil water depletion |
| `warm_nights_since_planting` | ↓ | Respiration during grain fill [7] |
| `rain_30d_mm` | Context | Helps under deficit, can hurt on poorly drained soil [9] |
| `ndvi_current`, `ndre_current` | ↑ | Canopy vigor / chlorophyll. NDVI saturates over dense canopy; NDRE less so [16] |
| `soil_available_water_cm` | ↑ | Stored water buffers dry spells [14] |
| `nitrogen_lb_ac` | ↑, toward a plateau | N response curve (ISU MRTN) [17] |

A model that disagrees gets investigated, not overruled.

## Sources

1. Nielsen, R.L. *Heat Unit Concepts Related to Corn Development.* Purdue Univ., updated 2020. https://www.agry.purdue.edu/ext/corn/news/timeless/heatunits.html
2. Nielsen, R.L. *Use Thermal Time to Predict Leaf Stage Development in Corn.* Purdue Univ., 2019. http://www.kingcorn.org/news/timeless/VStagePrediction.html
3. Abendroth, L.J., Elmore, R.W., Boyer, M.J., Marlay, S.K. *Corn Growth and Development.* Iowa State Univ. Extension PMR 1009, 2011. https://shop.iastate.edu/extension/farm-environment/crops-and-soils/agronomic-crops/pmr1009pdf.html
4. Iowa State Univ. ICM Encyclopedia. *Corn pollination: effect of high temperature and stress* (text by R. Elmore). https://crops.extension.iastate.edu/encyclopedia/corn-pollination-effect-high-temperature-and-stress
5. Nielsen, R.L. *Drought & Heat Stress Effects on Corn Pollination.* Purdue Univ. https://www.agry.purdue.edu/ext/corn/news/articles.95/p&c9522.htm
6. Schlenker, W., Roberts, M.J. (2009). Nonlinear temperature effects indicate severe damages to U.S. crop yields under climate change. *PNAS* 106:15594–15598. https://www.pnas.org/doi/10.1073/pnas.0906865106
7. Ohio State Univ. Agronomic Crops Network (2019). *Hot night temperatures can decrease corn yield.* https://agcrops.osu.edu/newsletter/corn-newsletter/2019-27/hot-night-temperatures-can-decrease-corn-yield
8. ETCCDI. *List of 27 core climate-extremes indices* (WMO CCl/CLIVAR/JCOMM). https://etccdi.pacificclimate.org/list_27_indices.shtml
9. Nielsen, R.L. *Effects of Flooding or Ponding on Corn Prior to Tasseling.* Purdue Univ. https://www.agry.purdue.edu/ext/corn/news/timeless/pondingyoungcorn.html
10. Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). *Crop evapotranspiration.* FAO Irrigation and Drainage Paper 56 (Hargreaves eq. 52; Table 12). https://www.fao.org/4/x0490e/x0490e0b.htm
11. Iowa State Univ. ICM (2017). *Influence of Drought on Corn and Soybean*, and *Corn and "a Big Long Heat Wave on the Way"* (2011). https://crops.extension.iastate.edu/cropnews/2017/07/influence-drought-corn-and-soybean
12. Lobell, D.B., Hammer, G.L., McLean, G., Messina, C., Roberts, M.J., Schlenker, W. (2013). The critical role of extreme heat for maize production in the United States. *Nature Climate Change* 3:497–501. https://www.nature.com/articles/nclimate1832
13. Lobell, D.B., Bänziger, M., Magorokosho, C., Vivek, B. (2011). Nonlinear heat effects on African maize as evidenced by historical yield trials. *Nature Climate Change* 1:42–45. https://www.nature.com/articles/nclimate1043
14. Univ. of Nebraska–Lincoln Extension. *Irrigation Management for Corn* (G1850). https://extensionpubs.unl.edu/publication/g1850/2008/html/view
15. Iowa State Univ. ICM (2013). *Update to Iowa Phosphorus, Potassium and Lime Recommendations.* https://crops.extension.iastate.edu/cropnews/2013/09/update-iowa-phosphorus-potassium-and-lime-recommendations
16. Sharma, L.K., Bu, H., Denton, A., Franzen, D.W. (2015). Active-optical sensors using red NDVI compared to red edge NDVI for prediction of corn grain yield in North Dakota. *Sensors* 15:27832. https://www.mdpi.com/1424-8220/15/11/27832
17. Sawyer, J. et al. (2006). *Concepts and Rationale for Regional Nitrogen Rate Guidelines for Corn.* Iowa State Univ. PM 2015. https://publications.iowa.gov/3847/1/PM2015.pdf
