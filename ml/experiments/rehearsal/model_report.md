# Rehearsal run (superseded): experiment report

> **Kept for the record, not used.** The first full run selected models and feature sets by
> *mean* leave-one-site-out MAE alone. Brief §45 asks to weigh consistency across folds
> as well. Under the mean-only rule the August model was Ridge (CV MAE 32.3 ± 16.7), which
> overshot the held-out site by ~52 bu/ac. The rule was corrected to mean + 1 SD before the
> final run. This run printed held-out scores, so the held-out site informed that correction
> and is a lightly used test rather than a pristine one. The final report is
> `../reports/model_report.md`. Per-run JSON detail for this rehearsal was not kept;
> `results.csv` here has every evaluation's metrics and parameters.


Generated 2026-09-24 from `ml/experiments/candidates/*/summary.json` (code `3307d14-dirty`, dataset version `8b8159f6db44`).

## Setup

- **Data:** 1643 development plots at 4 sites (Ames, Lincoln, MOValley, Scottsbluff) plus the held-out site **Crawfordsville**. Public practice data (Shrestha et al. 2024), 2022 season, 84 hybrids, 0–250 lb N/ac, six Pléiades Neo images per plot.
- **Validation:** leave-one-site-out CV on the development sites for feature-set screening, tuning (30 Optuna trials per model), model selection and interval calibration. Crawfordsville is scored once, after selection, with nothing fitted to it.
- **Point-in-time:** each cutoff's features come from `build_features(inputs, as_of)`, which drops and then asserts against anything dated after the cutoff.
- **Intervals:** 90% intervals from out-of-fold residual quantiles (conformal-style finite-sample correction). Coverage below is on data that played no part in setting them.

## Progressive performance: how early does SoilSignal become useful?

Selected model per cutoff. *CV* = mean over leave-one-site-out folds (± spread between sites). *Held-out* = Crawfordsville, never seen during development.

| Information available | Model | Feature set | Features | CV MAE | Held-out MAE | Held-out RMSE | Held-out R² | Held-out MAE / mean yield | 90% interval (bu/ac) | Held-out coverage |
|---|---|---|---|---|---|---|---|---|---|---|
| Through May | CatBoost | Crop + soil | 9 | 51.0 ± 31.1 | 42.6 | 48.9 | -2.92 | 26% | -133 / +77 | 91% |
| Through June | CatBoost | Crop + soil | 9 | 51.0 ± 31.1 | 42.6 | 48.9 | -2.92 | 26% | -133 / +77 | 91% |
| Through July | HistGradientBoosting | Crop signals | 27 | 44.9 ± 23.8 | 18.0 | 23.0 | 0.13 | 11% | -106 / +79 | 100% |
| Through August | Ridge | Crop signals | 39 | 32.3 ± 16.7 | 51.9 | 56.1 | -4.16 | 31% | -27 / +101 | 11% |
| Full season | CatBoost | Crop + timing | 40 | 39.6 ± 5.2 | 34.7 | 40.5 | -1.70 | 21% | -66 / +91 | 99% |

## Model comparison (leave-one-site-out CV MAE, bu/ac; tuned on the selected feature set)

| Model | Through May | Through June | Through July | Through August | Full season |
|---|---|---|---|---|---|
| Mean baseline | 58.8 ± 23.2 | 58.8 ± 23.2 | 58.8 ± 23.2 | 58.8 ± 23.2 | 58.8 ± 23.2 |
| Ridge | 60.4 ± 27.0 | 60.4 ± 27.0 | 83.5 ± 49.2 | 32.3 ± 16.7 | 53.5 ± 14.2 |
| Random Forest | 54.1 ± 27.9 | 54.1 ± 27.9 | 53.0 ± 29.1 | 43.8 ± 11.6 | 58.0 ± 11.2 |
| HistGradientBoosting | 55.9 ± 27.4 | 55.9 ± 27.4 | 44.9 ± 23.8 | 36.7 ± 7.7 | 51.1 ± 9.4 |
| CatBoost | 51.0 ± 31.1 | 51.0 ± 31.1 | 45.3 ± 25.7 | 39.7 ± 15.5 | 39.6 ± 5.2 |

Same models, fitted on all development sites and scored once on Crawfordsville (MAE, bu/ac). Shown for context: selection above used CV only.

| Model | Through May | Through June | Through July | Through August | Full season |
|---|---|---|---|---|---|
| Mean baseline | 56.5 | 56.5 | 56.5 | 56.5 | 56.5 |
| Ridge | 47.4 | 47.4 | 52.3 | 51.9 | 81.2 |
| Random Forest | 34.5 | 34.5 | 16.7 | 18.9 | 61.0 |
| HistGradientBoosting | 30.7 | 30.7 | 18.0 | 28.4 | 79.8 |
| CatBoost | 42.6 | 42.6 | 23.1 | 22.4 | 34.7 |

## Why grouped validation matters

MAE of each cutoff's selected model under three splits of the development sites. Random-like splits (grouped by plot) share a site's weather, soil and management between train and test, so they look far better than what a new location will see.

| Cutoff | Model | Grouped by plot (5-fold) | Grouped by field (4-fold) | Leave-one-site-out |
|---|---|---|---|---|
| Through May | CatBoost | 21.1 | 49.4 | 51.0 |
| Through June | CatBoost | 21.1 | 49.4 | 51.0 |
| Through July | HistGradientBoosting | 17.2 | 44.1 | 44.9 |
| Through August | Ridge | 17.7 | 26.8 | 32.3 |
| Full season | CatBoost | 15.8 | 31.7 | 39.6 |

### Leave-one-site-out, fold by fold (selected model, MAE bu/ac)

| Cutoff | Test site: Ames | Test site: Lincoln | Test site: MOValley | Test site: Scottsbluff |
|---|---|---|---|---|
| Through May | 27.5 | 103.9 | 29.5 | 43.0 |
| Through June | 27.5 | 103.9 | 29.5 | 43.0 |
| Through July | 26.8 | 83.4 | 23.8 | 45.6 |
| Through August | 41.8 | 18.0 | 14.7 | 54.8 |
| Full season | 33.9 | 39.5 | 37.1 | 47.9 |

## Feature ablation

Each group combination is cross-validated (leave-one-site-out, default parameters, best of Ridge / Random Forest / HistGradientBoosting / CatBoost). The lowest CV MAE picks the feature set; held-out MAE on Crawfordsville is shown for context only.

| Feature set: CV MAE (held-out MAE) | Through May | Through June | Through July | Through August | Full season |
|---|---|---|---|---|---|
| Management only | 69.2 (71.2) | 69.2 (71.2) | 69.2 (71.2) | 69.2 (71.2) | 69.2 (71.2) |
| Crop + timing | 71.2 (29.1) | 71.2 (29.1) | 55.4 (25.1) | 45.5 (23.3) | 43.5 (61.4) **←** |
| Crop + weather | 57.8 (60.6) | 59.5 (51.7) | 61.6 (43.5) | 45.7 (21.1) | 45.1 (31.7) |
| Crop + soil | 56.3 (34.9) **←** | 56.3 (34.9) **←** | 48.1 (27.8) | 37.8 (53.5) | 47.2 (42.3) |
| Crop + weather + soil | 61.7 (56.1) | 58.2 (63.5) | 63.3 (34.4) | 46.3 (21.4) | 50.8 (31.6) |
| All (+ timing, county history) | 59.0 (47.6) | 60.0 (59.4) | 59.2 (41.9) | 45.8 (20.5) | 53.5 (36.0) |
| Crop signals | – | – | 46.3 (17.5) **←** | 33.0 (52.8) **←** | 45.7 (54.8) |

A dash means the set adds no columns at that cutoff: before the first satellite image, "Crop signals" is the same as "Management only". Sets that produce identical columns are evaluated once.

## Seasonal ablation: what another month of data buys

| Cutoff | CV MAE | Held-out MAE | Change vs previous cutoff |
|---|---|---|---|
| Through May | 51.0 | 42.6 | – |
| Through June | 51.0 | 42.6 | 0.0 |
| Through July | 44.9 | 18.0 | -24.6 |
| Through August | 32.3 | 51.9 | 34.0 |
| Full season | 39.6 | 34.7 | -17.3 |

## Top model drivers (permutation importance on held-out-site folds)

- **Through May** (CatBoost): `soil_ph` 28% (positive), `genotype` 26% (neutral), `nitrogen_lb_ac` 16% (neutral), `soil_slope_pct` 15% (negative), `soil_available_water_cm` 10% (positive), `soil_drainage_rank` 5% (negative)
- **Through June** (CatBoost): `soil_ph` 28% (positive), `genotype` 26% (neutral), `nitrogen_lb_ac` 16% (neutral), `soil_slope_pct` 15% (negative), `soil_available_water_cm` 10% (positive), `soil_drainage_rank` 5% (negative)
- **Through July** (HistGradientBoosting): `genotype` 46% (neutral), `ndre_current` 15% (positive), `gndvi_current` 10% (positive), `nitrogen_lb_ac` 5% (negative), `ndvi_vs_site_mean` 4% (positive), `evi_min_to_date` 4% (negative)
- **Through August** (Ridge): `gndvi_current` 11% (positive), `ndvi_max_to_date` 10% (positive), `evi_current` 7% (positive), `ndre_current` 6% (positive), `ndvi_near_silking` 6% (positive), `ndvi_change_from_previous` 5% (negative)
- **Full season** (CatBoost): `genotype` 15% (neutral), `ndre_area_to_date` 14% (positive), `ndvi_change_from_previous` 11% (negative), `evi_area_to_date` 10% (positive), `gndvi_min_to_date` 7% (positive), `evi_change_from_previous` 6% (positive)

## Agronomic sensitivity checks

For the plot whose forecast is closest to the median, one feature is swept from its 5th to 95th percentile with everything else fixed. *Investigate* marks a response opposite to the literature (see `ml/research/agronomy_thresholds.md`). A flat response means the feature isn't in the selected set, or the model doesn't use it for this plot.

| Cutoff | Feature | Swept range | Forecast change (bu/ac) | Model | Literature | Status |
|---|---|---|---|---|---|---|
| Through May | `soil_available_water_cm` | 15.3 → 21.4 | -1.2 | mixed | increase | consistent |
| Through May | `nitrogen_lb_ac` | 75.0 → 250.0 | -33.3 | decrease | increase | investigate |
| Through June | `soil_available_water_cm` | 15.3 → 21.4 | -1.2 | mixed | increase | consistent |
| Through June | `nitrogen_lb_ac` | 75.0 → 250.0 | -33.3 | decrease | increase | investigate |
| Through July | `ndvi_current` | 0.496 → 0.832 | +5.2 | increase | increase | consistent |
| Through July | `ndre_current` | 0.187 → 0.371 | +5.6 | increase | increase | consistent |
| Through July | `nitrogen_lb_ac` | 75.0 → 250.0 | +14.5 | increase | increase | consistent |
| Through August | `ndvi_current` | 0.58 → 0.82 | +48.4 | increase | increase | consistent |
| Through August | `ndre_current` | 0.238 → 0.35 | +21.3 | increase | increase | consistent |
| Through August | `nitrogen_lb_ac` | 75.0 → 250.0 | -11.1 | decrease | increase | investigate |
| Full season | `ndvi_current` | 0.287 → 0.742 | -1.9 | mixed | increase | consistent |
| Full season | `ndre_current` | 0.104 → 0.29 | -6.2 | mixed | increase | consistent |
| Full season | `nitrogen_lb_ac` | 75.0 → 250.0 | -15.4 | decrease | increase | investigate |

## Reading these numbers honestly

- **Four development sites are very few.** Site means range from about 41 bu/ac (Lincoln, 2022 drought, rainfed) to about 165 bu/ac. Leave-one-site-out CV asks each model to forecast a site unlike any it trained on, and the Lincoln fold dominates the CV average. Grouped-by-plot numbers are several times better only because they don't ask that question.
- **Site-level context rarely transfers from so few sites.** Weather, soil, county history and planting date take four or five distinct values in training, so a model can use them as site identifiers. The ablation measures whether they help a new site rather than assuming it; they remain on the dashboard as context either way.
- **One season.** Leave-one-year-out validation is impossible with 2022 only.
- **Intervals are wide by design.** They come from errors on unseen sites. More sites and years (the challenge data) should narrow them.
- Comparable published work is summarized in `ml/research/model_benchmarks.md`. Its numbers are only comparable when the prediction date and validation split match.
