# Maize yield-prediction benchmarks: what "good" looks like

Last updated: 2026-09-24. This file puts SoilSignal's numbers in context. Headline accuracy figures
are only comparable when the **scale** (plot, field, county), the **prediction date**, and above
all the **validation split** match. A full-season model tested on a random split is not
comparable to a July model tested on a site it has never seen.

Unit note: 1 t/ha of maize grain ≈ 15.9 bu/ac (56 lb/bu).

## Studies

| Study | Scale & data | Locations / years | Inputs | Prediction date | Model | Validation | Reported accuracy |
|---|---|---|---|---|---|---|---|
| **Shrestha et al. 2025** [1] (the practice dataset's paper) | Plot; ~2,100 plots, 84 hybrids | 5–6 sites, US Corn Belt, 2022 | Pléiades Neo satellite (30 cm) or UAV RGB, one time point per model | Each of 6 (satellite) / 3 (UAV) dates | 6 baselines (incl. LASSO, RF) | (a) unseen genotypes in a seen location; (b) train one location, test others | Within location: satellite ≈ UAV, best from late-July/early-August images. **Out of location: prediction accuracy (correlation) ≤ 0.31** |
| **Powadi et al. 2025** [2] (same dataset) | Plot; ~4,000 satellite images | 5 sites, 2022 (+ Ames 2023) | Compositional-autoencoder features or vegetation indices | Time points 1–4 | XGBoost on latent features | 5-fold grouped by **genotype** (seen locations) | **R² 0.75–0.80, RMSE 1.30–1.48 t/ha (≈ 21–24 bu/ac)**. Leave-one-location-out reported only as top-hybrid ranking overlap (27–56% of the top 25%), no absolute error |
| Deines et al. 2021 [3] | Field; >1 million yield-monitor fields | US Corn Belt, 2008–2018 | Landsat + weather (SCYM, crop-model-trained) | End of season | Scalable Crop Yield Mapper | Independent ground truth | **Field-level r² = 0.45** (30 m pixel r² 0.31–0.40) |
| Schwalbert et al. 2020 [4] | County | US Corn Belt, multi-year | Satellite imagery + weather | Mid-season | Not verified here | Not verified here | County-level satellite models reach **RMSE ≈ 1 t/ha (≈ 15 bu/ac)**, as summarized by [1] for this study and Jin et al. 2017 |
| Schwalbert et al. 2018 (cited in [1]) | Field; 19 fields | Multi-location | 10–60 m satellite + yield | In-season | Regression | Multi-location train/test | **R² = 0.32** |
| Khaki & Wang 2019 [5] | Hybrid × location; 2,267 hybrids | 2,247 locations, 2008–2016 | Genotype + weather + soil | Pre-season (predicted weather) | Deep neural network | Held-out 2017 season | **RMSE = 12% of mean yield** (≈ 50% of the SD) |
| Barzin et al. 2020 [6] | Sub-field blocks | 1 field, Mississippi State, 4 N rates (0–270 kg/ha) | UAV multispectral (red edge), 26 indices | V3 through VT | Multiple linear regression, gradient boosting | Within one field | **R² 0.90 at V10 and 0.93 at VT**; accuracy rose as the crop developed |

## What this means for SoilSignal

1. **The closest comparison is [1] and [2]: same plots, same imagery.** Within a known location,
   unseen hybrids are predictable (R² ≈ 0.8, RMSE ≈ 21–24 bu/ac in [2]). Across locations, the
   authors report correlations up to ~0.31 [1], or only top-hybrid rankings [2]. Neither reports
   absolute cross-site error, the quantity SoilSignal's leave-one-site-out MAE measures.
2. **Grouped-by-plot results look much better than cross-site ones**, on this dataset and in
   general. The shared site, weather and management make a random or plot split optimistic, and
   Shrestha et al. make the same point (citing Di Paola et al. 2016). SoilSignal reports all three
   splits side by side in `ml/experiments/reports/model_report.md`.
3. **Imagery around silking carries most of the signal.** Late July / early August images predict
   best in [1], and [6] finds accuracy rising through V10 to tasseling, with red-edge indices
   among the strongest. [6]'s R² above 0.9 comes from one field whose variation is mostly
   nitrogen rate, which is the easiest setting of all. SoilSignal's progressive table
   should show the largest drop in error once July imagery arrives.
4. **Scale matters.** County or field models (RMSE ≈ 15 bu/ac [4]; r² ≈ 0.45 [3]) average out
   plot noise and hybrid differences. A plot-level forecast for an unseen site should not be held
   to those numbers.

## SoilSignal on the practice data

Full tables: `ml/experiments/reports/model_report.md`. Leave-one-site-out CV used Ames, Lincoln,
Missouri Valley and Scottsbluff; Crawfordsville was scored once, after selection.

| Forecast date | SoilSignal model | Held-out site MAE (bu/ac) | Mean-yield baseline | Grouped-by-plot CV MAE |
|---|---|---|---|---|
| May 31 | CatBoost, crop + weather | 72.0 | 56.5 | 21.1 |
| June 30 | CatBoost, crop + weather + soil | 44.0 | 56.5 | 20.2 |
| **July 31** | HistGradientBoosting, crop signals | **18.0** (RMSE 23.0) | 56.5 | 17.2 |
| August 31 | HistGradientBoosting, crop signals | 28.4 | 56.5 | 16.0 |
| Full season | CatBoost, crop + timing | 34.7 | 56.5 | 15.8 |

- **Within a known site**, SoilSignal's grouped-by-plot error (~16–21 bu/ac) is in the range [2]
  reports for unseen hybrids at seen locations (RMSE ≈ 21–24 bu/ac). This is the easy question.
- **At an unseen site**, the published work on these plots reports correlations up to ~0.31 [1]
  and no absolute error [2]. SoilSignal's July forecast for the held-out site is off by 18 bu/ac on
  average (11% of its mean yield) with almost no bias. Pre-season forecasts are no better, and in
  May worse, than the average, which matches [1]'s finding that late-July/early-August imagery
  carries the signal.
- **The held-out result is one site.** With four development sites, CV spreads of ±8–26 bu/ac
  between folds are the more honest measure of how much a new site's error can vary.

## Sources

1. Shrestha, N., Powadi, A., Davis, J., et al. (2025). Plot-level satellite imagery can substitute for UAVs in assessing maize phenotypes across multistate field trials. *Plants, People, Planet*. https://doi.org/10.1002/ppp3.10613. Data: https://doi.org/10.5061/dryad.905qftttm
2. Powadi, A.A., Jubery, T.Z., Tross, M., Shrestha, N., Coffey, L., Schnable, J.C., Schnable, P.S., Ganapathysubramanian, B. (2025). Enhancing yield prediction from plot-level satellite imagery through genotype and environment feature disentanglement. *Frontiers in Plant Science* 16:1617831. https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2025.1617831/full
3. Deines, J.M., Patel, R., Liang, S.Z., Dado, W., Lobell, D.B. (2021). A million kernels of truth: insights into scalable satellite maize yield mapping and yield gap analysis from an extensive ground dataset in the US Corn Belt. *Remote Sensing of Environment* 253:112174. https://www.sciencedirect.com/science/article/pii/S0034425720305472
4. Schwalbert, R., et al. (2020). Mid-season county-level corn yield forecast for US Corn Belt integrating satellite imagery and weather variables. *Crop Science* 60:739–750. https://acsess.onlinelibrary.wiley.com/doi/abs/10.1002/csc2.20053
5. Khaki, S., Wang, L. (2019). Crop yield prediction using deep neural networks. *Frontiers in Plant Science* 10:621. https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2019.00621/full
6. Barzin, R., Pathak, A., Lotfi, H., Varco, J., Bora, G.C. (2020). Use of UAS multispectral imagery at different physiological stages for yield prediction and input resource optimization in corn. *Remote Sensing* 12:2392. https://www.mdpi.com/2072-4292/12/15/2392
