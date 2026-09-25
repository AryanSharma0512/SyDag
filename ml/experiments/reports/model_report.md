# SoilSignal progressive yield model: experiment report

Generated 2026-09-24 from `ml/experiments/candidates/*/summary.json` (code `b890d82-dirty`, dataset version `7ec6bfeebcbe`).

## Setup

- **Data:** 1643 development plots at 4 sites (Ames, Lincoln, MOValley, Scottsbluff) plus the held-out site **Crawfordsville**. Public practice data (Shrestha et al. 2024), 2022 season, 84 hybrids, 0–250 lb N/ac, six Pléiades Neo images per plot.
- **Validation:** leave-one-site-out CV on the development sites for feature-set screening, tuning (30 Optuna trials per model, minimizing mean fold MAE), model selection and interval calibration. Crawfordsville is scored once, after selection, with nothing fitted to it.
- **Selection rule:** feature sets and models are ranked by **mean + 1 SD of fold MAE** (brief §45: consistency across sites matters, not only the average), and a more complex model must win by more than 3%. A rehearsal run used the mean alone and picked Ridge for August, which extrapolated badly on the held-out site. The rule was corrected before this run, so the held-out site informed it and is a lightly used test rather than a pristine one (`experiments/rehearsal/model_report.md`).
- **Point-in-time:** each cutoff's features come from `build_features(inputs, as_of)`, which drops and then asserts against anything dated after the cutoff.
- **Intervals:** 90% intervals from out-of-fold residual quantiles (conformal-style finite-sample correction). Coverage below is on data that played no part in setting them.

## Progressive performance: how early does SoilSignal become useful?

Selected model per cutoff. *CV* = mean over leave-one-site-out folds (± spread between sites). *Held-out* = Crawfordsville, never seen during development.

| Information available | Model | Feature set | Features | CV MAE | Held-out MAE | Held-out RMSE | Held-out R² | Held-out MAE / mean yield | 90% interval (bu/ac) | Held-out coverage |
|---|---|---|---|---|---|---|---|---|---|---|
| Through May | CatBoost | Crop + weather | 28 | 45.8 ± 25.8 | 72.0 | 77.0 | -8.73 | 44% | -115 / +78 | 59% |
| Through June | CatBoost | Crop + weather + soil | 36 | 49.7 ± 22.9 | 44.0 | 48.8 | -2.90 | 27% | -115 / +80 | 94% |
| Through July | HistGradientBoosting | Crop signals | 27 | 44.9 ± 23.8 | 18.0 | 23.0 | 0.13 | 11% | -106 / +79 | 100% |
| Through August | HistGradientBoosting | Crop signals | 39 | 36.7 ± 7.7 | 28.4 | 34.3 | -0.93 | 17% | -82 / +60 | 93% |
| Full season | CatBoost | Crop + timing | 40 | 39.6 ± 5.2 | 34.7 | 40.5 | -1.70 | 21% | -66 / +91 | 99% |

## Model comparison (leave-one-site-out CV MAE, bu/ac; tuned on the selected feature set)

| Model | Through May | Through June | Through July | Through August | Full season |
|---|---|---|---|---|---|
| Mean baseline | 58.8 ± 23.2 | 58.8 ± 23.2 | 58.8 ± 23.2 | 58.8 ± 23.2 | 58.8 ± 23.2 |
| Ridge | 149.8 ± 159.9 | 107.0 ± 66.1 | 83.5 ± 49.2 | 32.3 ± 16.7 | 53.5 ± 14.2 |
| Random Forest | 62.4 ± 17.2 | 62.5 ± 23.4 | 53.0 ± 29.1 | 43.8 ± 11.6 | 58.0 ± 11.2 |
| HistGradientBoosting | 69.4 ± 19.8 | 58.1 ± 24.3 | 44.9 ± 23.8 | 36.7 ± 7.7 | 51.1 ± 9.4 |
| CatBoost | 45.8 ± 25.8 | 49.7 ± 22.9 | 45.3 ± 25.7 | 39.7 ± 15.5 | 39.6 ± 5.2 |

Same models, fitted on all development sites and scored once on Crawfordsville (MAE, bu/ac). Shown for context: selection above used CV only.

| Model | Through May | Through June | Through July | Through August | Full season |
|---|---|---|---|---|---|
| Mean baseline | 56.5 | 56.5 | 56.5 | 56.5 | 56.5 |
| Ridge | 71.3 | 43.6 | 52.3 | 51.9 | 81.2 |
| Random Forest | 64.4 | 64.9 | 16.7 | 18.9 | 61.0 |
| HistGradientBoosting | 102.4 | 59.8 | 18.0 | 28.4 | 79.8 |
| CatBoost | 72.0 | 44.0 | 23.1 | 22.4 | 34.7 |

## Why grouped validation matters

MAE of each cutoff's selected model under three splits of the development sites. Random-like splits (grouped by plot) share a site's weather, soil and management between train and test, so they look far better than what a new location will see.

| Cutoff | Model | Grouped by plot (5-fold) | Grouped by field (4-fold) | Leave-one-site-out |
|---|---|---|---|---|
| Through May | CatBoost | 21.1 | 44.4 | 45.8 |
| Through June | CatBoost | 20.2 | 47.9 | 49.7 |
| Through July | HistGradientBoosting | 17.2 | 44.1 | 44.9 |
| Through August | HistGradientBoosting | 16.0 | 33.9 | 36.7 |
| Full season | CatBoost | 15.8 | 31.7 | 39.6 |

### Leave-one-site-out, fold by fold (selected model, MAE bu/ac)

| Cutoff | Test site: Ames | Test site: Lincoln | Test site: MOValley | Test site: Scottsbluff |
|---|---|---|---|---|
| Through May | 40.0 | 89.5 | 27.7 | 26.0 |
| Through June | 46.8 | 88.0 | 33.9 | 30.2 |
| Through July | 26.8 | 83.4 | 23.8 | 45.6 |
| Through August | 28.3 | 49.2 | 35.0 | 34.3 |
| Full season | 33.9 | 39.5 | 37.1 | 47.9 |

## Feature ablation

Each group combination is cross-validated (leave-one-site-out, default parameters, best of Ridge / Random Forest / HistGradientBoosting / CatBoost). The lowest mean + 1 SD picks the feature set; held-out MAE on Crawfordsville is shown for context only. Cells: CV MAE ± SD (held-out MAE).

| Feature set: CV MAE (held-out MAE) | Through May | Through June | Through July | Through August | Full season |
|---|---|---|---|---|---|
| Management only | 69.2 ± 15.8 (71.2) | 69.2 ± 15.8 (71.2) | 69.2 ± 15.8 (71.2) | 69.2 ± 15.8 (71.2) | 69.2 ± 15.8 (71.2) |
| Crop + timing | 71.2 ± 29.3 (29.1) | 71.2 ± 29.3 (29.1) | 55.6 ± 22.7 (17.1) | 45.9 ± 12.3 (17.6) | 43.5 ± 6.3 (61.4) **←** |
| Crop + weather | 57.8 ± 19.8 (60.6) **←** | 59.5 ± 24.4 (51.7) | 61.6 ± 28.4 (43.5) | 45.7 ± 16.6 (21.1) | 45.1 ± 15.1 (31.7) |
| Crop + soil | 56.3 ± 26.4 (34.9) | 56.3 ± 26.4 (34.9) | 49.9 ± 19.6 (17.8) | 37.8 ± 15.4 (53.5) | 47.2 ± 12.3 (42.3) |
| Crop + weather + soil | 61.7 ± 22.2 (56.1) | 58.2 ± 20.5 (63.5) **←** | 63.3 ± 23.5 (34.4) | 46.3 ± 17.2 (21.4) | 50.8 ± 20.3 (31.6) |
| All (+ timing, county history) | 59.0 ± 20.9 (47.6) | 60.0 ± 18.8 (59.4) | 59.2 ± 23.8 (41.9) | 45.8 ± 17.2 (20.5) | 53.5 ± 19.2 (36.0) |
| Crop signals | – | – | 46.3 ± 22.7 (17.5) **←** | 33.0 ± 14.0 (52.8) **←** | 45.7 ± 14.3 (54.8) |

A dash means the set adds no columns at that cutoff: before the first satellite image, "Crop signals" is the same as "Management only". Sets that produce identical columns are evaluated once.

## Seasonal ablation: what another month of data buys

| Cutoff | CV MAE | Held-out MAE | Change vs previous cutoff |
|---|---|---|---|
| Through May | 45.8 | 72.0 | – |
| Through June | 49.7 | 44.0 | -28.0 |
| Through July | 44.9 | 18.0 | -26.0 |
| Through August | 36.7 | 28.4 | 10.4 |
| Full season | 39.6 | 34.7 | 6.3 |

## Top model drivers (permutation importance on held-out-site folds)

- **Through May** (CatBoost): `genotype` 63% (neutral), `nitrogen_lb_ac` 37% (neutral)
- **Through June** (CatBoost): `genotype` 49% (neutral), `nitrogen_lb_ac` 36% (neutral), `soil_slope_pct` 9% (neutral), `soil_available_water_cm` 5% (positive), `soil_organic_matter_pct` 1% (negative), `very_heavy_rain_days_on_poorly_drained_soil` 0% (neutral)
- **Through July** (HistGradientBoosting): `genotype` 46% (neutral), `ndre_current` 15% (positive), `gndvi_current` 10% (positive), `nitrogen_lb_ac` 5% (negative), `ndvi_vs_site_mean` 4% (positive), `evi_min_to_date` 4% (negative)
- **Through August** (HistGradientBoosting): `genotype` 34% (neutral), `evi_current` 10% (positive), `evi_change_from_previous` 8% (positive), `ndre_max_to_date` 7% (negative), `nitrogen_lb_ac` 5% (negative), `gndvi_current` 5% (positive)
- **Full season** (CatBoost): `genotype` 15% (neutral), `ndre_area_to_date` 14% (positive), `ndvi_change_from_previous` 11% (negative), `evi_area_to_date` 10% (positive), `gndvi_min_to_date` 7% (positive), `evi_change_from_previous` 6% (positive)

## Agronomic sensitivity checks

For the plot whose forecast is closest to the median, one feature is swept from its 5th to 95th percentile with everything else fixed. *Investigate* marks a response opposite to the literature (see `ml/research/agronomy_thresholds.md`). A flat response means the feature isn't in the selected set, or the model doesn't use it for this plot.

| Cutoff | Feature | Swept range | Forecast change (bu/ac) | Model | Literature | Status |
|---|---|---|---|---|---|---|
| Through May | `water_deficit_30d_mm` | -116.068 → -19.075 | +2.8 | increase | decrease | investigate |
| Through May | `killing_degree_days_29c` | 1.057 → 8.272 | +1.3 | decrease | decrease | consistent |
| Through May | `longest_dry_spell_days` | 2.0 → 9.0 | -0.5 | decrease | decrease | consistent |
| Through May | `rain_30d_mm` | 37.6 → 158.2 | +1.4 | increase | context | consistent |
| Through May | `nitrogen_lb_ac` | 75.0 → 250.0 | -8.3 | decrease | increase | investigate |
| Through June | `water_deficit_30d_mm` | -151.081 → 68.459 | +1.0 | increase | decrease | investigate |
| Through June | `heat_days_since_planting` | 2.0 → 5.0 | +1.0 | increase | decrease | investigate |
| Through June | `killing_degree_days_29c` | 16.732 → 21.631 | -1.9 | decrease | decrease | consistent |
| Through June | `longest_dry_spell_days` | 7.0 → 20.0 | -2.1 | decrease | decrease | consistent |
| Through June | `warm_nights_since_planting` | 1.0 → 6.0 | -4.7 | decrease | decrease | consistent |
| Through June | `rain_30d_mm` | 6.4 → 228.0 | -5.3 | mixed | context | consistent |
| Through June | `soil_available_water_cm` | 15.3 → 21.4 | +1.3 | increase | increase | consistent |
| Through June | `nitrogen_lb_ac` | 75.0 → 250.0 | -3.5 | decrease | increase | investigate |
| Through July | `ndvi_current` | 0.496 → 0.832 | +5.2 | increase | increase | consistent |
| Through July | `ndre_current` | 0.187 → 0.371 | +5.6 | increase | increase | consistent |
| Through July | `nitrogen_lb_ac` | 75.0 → 250.0 | +14.5 | increase | increase | consistent |
| Through August | `ndvi_current` | 0.58 → 0.82 | +28.4 | increase | increase | consistent |
| Through August | `ndre_current` | 0.238 → 0.35 | +5.3 | increase | increase | consistent |
| Through August | `nitrogen_lb_ac` | 75.0 → 250.0 | -38.5 | decrease | increase | investigate |
| Full season | `ndvi_current` | 0.287 → 0.742 | -1.9 | mixed | increase | consistent |
| Full season | `ndre_current` | 0.104 → 0.29 | -6.2 | mixed | increase | consistent |
| Full season | `nitrogen_lb_ac` | 75.0 → 250.0 | -15.4 | decrease | increase | investigate |

## Findings

- **Through May:** held-out MAE 72.0 vs 56.5 for predicting the training mean, **worse than** the baseline (bias -72 bu/ac).
- **Through June:** held-out MAE 44.0 vs 56.5 for predicting the training mean, better than the baseline (bias -43 bu/ac).
- **Through July:** held-out MAE 18.0 vs 56.5 for predicting the training mean, better than the baseline (bias +2 bu/ac).
- **Through August:** held-out MAE 28.4 vs 56.5 for predicting the training mean, better than the baseline (bias -25 bu/ac).
- **Full season:** held-out MAE 34.7 vs 56.5 for predicting the training mean, better than the baseline (bias -32 bu/ac).
- **Sensitivity checks flag:** Through May `water_deficit_30d_mm` (increase, literature: decrease); Through May `nitrogen_lb_ac` (decrease, literature: increase); Through June `water_deficit_30d_mm` (increase, literature: decrease); Through June `heat_days_since_planting` (increase, literature: decrease); Through June `nitrogen_lb_ac` (decrease, literature: increase); Through August `nitrogen_lb_ac` (decrease, literature: increase); Full season `nitrogen_lb_ac` (decrease, literature: increase). With four development sites these responses are most likely site confounding: Scottsbluff is the hottest and driest site and the highest yielding because it is irrigated, and nitrogen rates were applied in separate experiment blocks (fields). They are reported, not overridden.

## Reading these numbers honestly

- **Four development sites are very few.** Site means range from about 41 bu/ac (Lincoln, 2022 drought, rainfed) to about 165 bu/ac. Leave-one-site-out CV asks each model to forecast a site unlike any it trained on, and the Lincoln fold dominates the CV average. Grouped-by-plot numbers are several times better only because they don't ask that question.
- **Site-level context rarely transfers from so few sites.** Weather, soil, county history and planting date take four or five distinct values in training, so a model can use them as site identifiers. The ablation measures whether they help a new site rather than assuming it; they remain on the dashboard as context either way.
- **One season.** Leave-one-year-out validation is impossible with 2022 only.
- **Intervals are wide by design.** They come from errors on unseen sites. More sites and years (the challenge data) should narrow them.
- Comparable published work is summarized in `ml/research/model_benchmarks.md`. Its numbers are only comparable when the prediction date and validation split match.
