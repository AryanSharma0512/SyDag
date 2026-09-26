# Agent 3 handoff: progressive early-signal experiments

**Question this answers:** how early can SoilSignal produce a useful yield forecast? More
precisely: *from which satellite pass does imagery add enough over field records to support
in-season scouting decisions?* Nothing here picks a winner. The framework produces the
evidence, and the team chooses the narrative.

| | |
|---|---|
| Code | `ml/soilsignal_ml/progressive/` (entry point `ml/progressive_experiment.py`, or `python -m soilsignal_ml progressive`) |
| Config | `ml/configs/progressive.yaml` (fix it before looking at results) |
| Tests | `ml/tests/test_progressive.py` (23 tests: leakage, splits, metrics, criteria, backend contract) |
| Template outputs | `ml/experiments/progressive/_template_synthetic/` (**synthetic, not a result**) |
| Backend file | `backend/artifacts/imagery_ablation.json`, written only by `--publish` from a real run |

## 0. Status: real results on the practice data

Real practice-data runs (Shrestha et al. 2024, 2022 season), default config (CatBoost primary,
leave-one-site-out, nested intervals):

- `ml/experiments/progressive/practice_3sites/`: **the challenge's three locations** (Ames,
  Crawfordsville, Lincoln; `--sites Ames Crawfordsville Lincoln`). 30 minutes on 4 cores.
- `ml/experiments/progressive/practice_5sites/`: all five practice sites. 16 minutes.

Read `summary.md` in each. The three-site headline (CatBoost, MAE in bu/ac, lower is better):

| Information | Acquired (range over sites) | Median DAP | MAE | vs records only | Better in | 90% coverage | Recall @ 20% (within-site model) |
|---|---|---|---|---|---|---|---|
| Training mean (Baseline A) | – | – | 74.5 | – | – | 69% | – |
| Records only | – | – | 95.5 | reference | – | 69% | 24% |
| + TP1 | Jul 10–18 | 57 | 72.4 | −24% | 3/3 sites | 70% | 39% |
| + TP1–TP2 | Jul 20–Aug 6 | 70 | 52.3 | −45% | 3/3 | 71% | 35% |
| + TP1–TP3 | Aug 2–Sep 3 | 83 | **48.2** | **−49%** | 3/3 | 76% | 25% |
| + TP1–TP4 | Aug 31–Sep 13 | 112 | 63.3 | −34% | 3/3 | 80% | 38% |
| + TP1–TP6 | Sep 24–Oct 9 | 128 | 79.3 | −17% | 3/3 | 76% | 30% |

Random scouting recalls 20% at a 20% budget; a perfect ranking recalls 80%.

What the evidence says (for the team to turn into a narrative):

- **Imagery helps from the very first pass.** Every stage beats records only, at every held-out
  site and with every model. Error is lowest with TP1–TP3 (early August at Ames and
  Crawfordsville), and **late passes make cross-site error worse again** (senescence timing
  differs by site). This matches the published within-location finding that
  late-July/early-August images carry the signal.
- **Records only is worse than predicting the average** at an unseen site (95.5 vs 74.5): the
  hybrid and nitrogen effects learned at two sites transfer badly to the third (nitrogen is
  confounded with blocks). Say "imagery vs records" *and* "vs the training mean".
- **Scouting value is earliest:** with TP1 (mid-July, ~57 days after planting, ~3 months before
  harvest), the within-site model finds 39% of the eventual bottom-quartile plots when scouting
  20%, vs 24% with records only and 20% at random. The no-model "lowest NDVI" ranking is
  competitive early (34–36% at TP1–TP2) and collapses late (15% at TP6). The model's value is
  in keeping the ranking useful later in the season.
- **No stage passes all five checks, only because of calibration:** coverage is 70–81%
  against a 90% target, and one site is far worse (e.g. 14% at TP2). With three sites, the
  intervals are calibrated from 2-site folds that don't capture a whole new site's offset.
  TP1 and TP2 pass the other four checks. The honest statement is: *the ranking is useful from
  mid-July; the absolute yield level at a new site is not yet trustworthy, and the stated
  range is too narrow.*
- **Absolute accuracy is weak across sites** (R² ≤ 0.08 at best). Lincoln's 2022 drought
  (site mean ~41 bu/ac) dominates the error. The random-split contrast (MAE 14–22) shows how
  flattering a non-grouped split would be.
- **Residuals are spatially clustered** (Moran's I 0.2–0.4, p < 0.05 at every site-season, plot
  spacing ~3 m). Neighbouring plots miss together, so neighbour-relative features (in Python)
  are the most promising next feature to try. This strengthens the case for a residual map
  layer, but not for PostGIS in the model (§10).
- Five sites (`practice_5sites`): same shape, a smaller gain at TP1 (+4%, not significant under
  the checks), and TP1–TP2 through TP1–TP5 at −28% to −34%.

`imagery_ablation.json` in each folder is ready to publish (`--publish`, default stage TP6). It
was **not** copied into `backend/artifacts/`, because that changes the live dashboard. Choose the
stage first (e.g. `--ablation-stage tp3`).

The synthetic fixture (`_template_synthetic/`) is still used by the tests. It is not a result.

## 1. Where this sits in the pipeline

```
Agent 1  plots.csv (records + yield + coords)  ─┐
         acquisitions.csv (site, year, TP, date) ├─►  Agent 3  progressive_experiment.py
Agent 2  tp_features.csv (cumulative by TP)    ─┘          │
                                                           ├─ progressive_results.csv / .json
                                                           ├─ scouting_results.csv, criteria.json
                                                           ├─ figures/*.png, summary.md
                                                           ├─ predictions.csv / .geojson (map)
                                                           └─ imagery_ablation.json ─► backend/artifacts/
```

## 2. Expected inputs (the contract: `progressive/contract.py`)

CSV or Parquet. Column names are normalized, so common source spellings are accepted
(`location`, `yieldPerAcre`, `plantingDate`, `hybrid`, `poundsOfNitrogenPerAcre`, `lat`/`lon`,
`time_point`/`TP`, `acquisition_date`).

### Agent 1: `plots` (one row per plot)

| Column | Required | Notes |
|---|---|---|
| `plot_id` | yes | unique; must match Agent 2's `plot_id` |
| `site_id` | yes | location; grouped validation and scouting units use it |
| `year` | yes | season; enables leave-one-year-out and 2022 → 2023 |
| `planting_date` | yes | for days after planting (DAP); also a record feature (day of year) |
| `final_yield` | yes | bu/ac; plots without yield are dropped |
| `genotype`, `nitrogen_lb_ac`, `irrigated` | if present | **Baseline B** uses only these plus planting day of year |
| `field_id` | optional | experiment block; used for the optimistic "field" contrast |
| `latitude`, `longitude` | optional | enables the spatial residual check and the GeoJSON |
| `harvest_date` | optional | lead time to harvest; otherwise Oct 15 is assumed (`harvest_mmdd`) |

Anything else (stand count, anthesis, …) is ignored. Records are only what a grower knows at
planting.

### Agent 1: `acquisitions` (one row per satellite pass)

`site_id, year, tp, date`, from `DateofCollection.xlsx`. It can be skipped if Agent 2's table has
a `date` column per (plot, tp).

### Agent 2: imagery features (pick ONE form)

0. **`--imagery-table`, Agent 2's own output (recommended; merged from PR #12):**
   `ml/data/interim/imagery/satellite_features.parquet` from `python -m soilsignal_ml.imagery run`.
   One row per plot × cutoff (`records_only`, TP1…TP6), each TPk row built from images up to that
   site's TPk date only. The adapter (`contract.from_imagery_table`) takes the acquisition dates
   from `as_of_date`, the records and yield from the `records_only` rows (or from `--plots` if
   Agent 1's table is passed too), and uses every numeric column *except* the imagery package's
   own identifier, timing, QA, planting-known and target columns as imagery features
   (`--include-qa` adds the QA columns). `tests/test_progressive.py` runs Agent 2's synthetic
   TIFFs through both pipelines to keep this seam from breaking.
1. **`--tp-features`, cumulative long (preferred):** one row per (`plot_id`, `tp`), where the
   row for `tp = k` was computed from passes 1..k only. Numeric columns are features.
2. **`--tp-features`, cumulative wide:** one row per plot, with a TP token in each column
   (`ndvi_tp3`, `TP3_ndvi`). Stage k sees only columns whose token is ≤ k. Columns without a
   token are ignored (and listed in the notes).
3. **`--tp-observations`, per-pass:** one row per (`plot_id`, `tp`) with that pass's own values
   (bands, indices, texture). `contract.accumulate` then builds, for each value and each k:
   latest, mean, max, min, change since the previous pass, trend per 10 days, and latest and
   mean *relative to the same pass's site-season mean*. The relative ones remove site offsets
   and use no yields.

**Leakage guards:** feature names matching `yield|harvest|anthesis|stand_count|grain|moisture|…`
are refused unless allowed with `--allow-columns`. Wide columns from later TPs are masked, and
per-pass accumulation only ever sees passes ≤ k. A test tampers with TP4–TP6 and asserts that
the TP1–TP3 features don't change.

The no-model scouting baseline reads `naive_ranking_column` (default `ndvi_latest`), falling
back to `ndvi_current` (Agent 2's name).

## 3. Experiment configurations

**Stages** (`stage_mode`):
- `tp` (default): Records only → + TP1 → + TP1–TP2 → … → + TP1–TP6.
- `dap`: + every pass acquired by N days after planting, per plot (`--stages 45 60 75 90 105`).
- `calendar`: + every pass by a date each season (`--stages 07-15 07-31 08-15`).

TP labels are not dates. Lincoln's TP2 is Aug 6, and Crawfordsville's is Jul 20. Every stage
therefore reports its acquisition-date range, median DAP, passes per plot and median lead time
to harvest, overall and per site-season. The `dap` mode answers "early" on a common clock.

**Models:** `mean` (Baseline A), `ridge`, `random_forest`, `hist_gradient_boosting`,
`catboost`. `xgboost` and `lightgbm` register automatically where installed (higher-compute
machine). They reuse `ml/soilsignal_ml/models/*`, so any exported model still loads in the
backend. **The same fixed hyperparameters are used at every stage**, so a change between stages
reflects the information added, not tuning luck. Override them once in `params:`.
**Primary model** (headline table, criteria, `imagery_ablation.json`): `catboost`, chosen *before*
the run rather than by lowest test error. Change it with `--primary-model`.

**Neural or image models tomorrow:** export per-(plot, TP) embeddings, computed from passes ≤ k
only, as a cumulative long table and pass them as `--tp-features`. The whole comparison then
applies unchanged. To add a new estimator, add a `ModelSpec` in `progressive/models.py`.

## 4. Exact commands (run from `ml/`)

```bash
cd ml
PY="uv run --project ../backend --group ml python"

# 0. Smoke test (about 1 min): proves the environment works; outputs are synthetic.
$PY progressive_experiment.py --synthetic --synthetic-scale 0.3 --fast --out /tmp/smoke

# a. THE MAIN RUN, straight from Agent 2's output (after `python -m soilsignal_ml.imagery run`)
$PY progressive_experiment.py \
    --imagery-table data/interim/imagery/satellite_features.parquet \
    --name sydag26 --dataset-label "Challenge data"
#   add  --plots data/processed/sydag26/plots.csv  once Agent 1's table exists (records, yield,
#   lat/lon for the spatial check and GeoJSON; Agent 2's table has no coordinates)
#   outputs -> experiments/progressive/sydag26/  (read summary.md first)

# a2. Same, from separate Agent 1 / Agent 2 files in the generic contract
$PY progressive_experiment.py \
    --plots data/processed/sydag26/plots.csv \
    --acquisitions data/processed/sydag26/acquisitions.csv \
    --tp-features data/interim/tp_features.csv --name sydag26

# b. Same, "early" on a common clock (days after planting) instead of TP labels
$PY progressive_experiment.py --plots ... --tp-features ... --acquisitions ... \
    --name sydag26-dap --stage-mode dap --stages 50 60 70 80 90 100 110 120

# c. 2022 -> 2023: automatic. If 2023 has >= 100 labelled plots with imagery, "temporal"
#    becomes the headline; otherwise it is skipped and the reason is written to summary.md.
$PY progressive_experiment.py ... --test-year 2023

# d. Publish the dashboard comparison (refuses synthetic runs; validated with the backend's
#    own schema). --ablation-stage picks the stage (default: all passes).
$PY progressive_experiment.py ... --dataset-label "Challenge data" --ablation-stage tp3 --publish
#   then: docker compose restart backend  (or just reload; the file is read per request)

# e. Real PRACTICE data, wherever zenodo.org + NOAA are reachable (about 15 min)
$PY -m soilsignal_ml ingest && $PY progressive_experiment.py --canonical shrestha2024

# f. Faster iterations: fewer models / fewer trees
$PY progressive_experiment.py ... --models mean ridge catboost --fast

# g. Re-render figures from a finished run (no refitting)
$PY -m soilsignal_ml.progressive.figures experiments/progressive/sydag26

# Tests
uv run --project ../backend --group ml --group dev pytest tests/test_progressive.py -q
```

Runtime: the full default config on about 1,500 plots (5 models, 7 stages, nested intervals,
CQR, all schemes) takes **about 5.5 minutes** on a 4-core container (measured on the fixture).
`--fast` or fewer `--models` cuts it roughly in proportion.

## 5. Validation design (`progressive/folds.py`)

Plots at one site share weather, soil, planting and management, so a random split puts
near-copies of every test plot in training. **Random splits are never the headline.** Every
usable scheme runs, and the headline is the most demanding one available:

| Scheme | Question | Runs when |
|---|---|---|
| `temporal` | a later season (train 2022, test 2023) | test season has ≥ `min_test_plots` labelled plots and ≥ 50% of them imaged |
| `site` | a location never seen (leave-one-site-out) | ≥ 2 sites (**expected headline tomorrow**) |
| `year` | a season never seen | ≥ 2 seasons |
| `site_year` | a site-season never seen | ≥ 2 seasons |
| `field` | *optimistic contrast*: unseen block within seen sites | ≥ 2 blocks |
| `random` | *optimistic contrast*: plot 5-fold | always, shown only to expose the gap |

Every grouped fold goes through the existing overlap assertion (`validation/splits.py`).
The headline scheme runs all models. Other grouped schemes run the primary model and the mean,
and contrasts run the primary model only (a compute budget).

## 6. Metrics (all out-of-fold; `progressive/metrics.py`)

| Family | Metric |
|---|---|
| Accuracy | MAE (headline), RMSE, R², mean bias (predicted − actual), MAE per held-out site-season |
| Ranking | **Spearman within each site-season** (averaged). Pooled Spearman is kept too, but it mostly measures between-site offsets |
| Uncertainty | 90% interval coverage, worst site-season coverage, mean width (two methods, below) |
| Imagery value | **ΔMAE vs records only** (same model, folds and plots; positive = imagery helped), % reduction, 95% paired bootstrap interval, number of held-out site-seasons where MAE fell, ΔMAE vs the *best* records-only model (conservative) |
| Timing | acquisition date range, median DAP, passes per plot, lead time to harvest, per site-season |

**Intervals.** *Nested conformal*: each outer training set is split again (same grouping where
possible), and inner-fold residuals set the offsets, which are then scored on the outer test
group. Coverage is honest, and the width is constant within a fold. *CQR* (conformalized
quantile regression, Romano et al. 2019): 5th and 95th percentile boosting models,
conformalized the same way, give a per-plot width. With only 3 sites, inner leave-one-site-out
calibrates on 2-site folds, so **expect under-coverage under leave-one-site-out**. That is a
real limitation of three locations, and it is reported, not hidden.

## 7. Scouting decision layer

> If agronomists can inspect only X% of plots, how many genuinely poor plots does SoilSignal
> send them to?

- **Poor plot** = bottom quartile of final yield **within its site-season** (scouting happens
  per location). Budgets: 10%, 20%, 25% of plots per site-season.
- **Recall** = share of those poor plots in the scouted set, pooled over site-seasons. Precision,
  lift over random, and skill `(recall − random) / (perfect − random)` are also reported.
  Random recalls ≈ budget. A perfect ranking recalls `min(1, budget / 25%)`, so 80% at a 20%
  budget.
- **Rankings compared at every stage** (lowest scouted first). None is an opaque risk score:
  - `forecast`: the primary model's yield forecast
  - `lower_bound`: the CQR 90% lower bound (downside risk). With a constant-width interval this
    would be *identical* to `forecast`, which is why CQR is used.
  - `relative_forecast`: the same model family trained on *yield minus its site-season mean*.
    A ranking within a site doesn't need the unknown site level, so this model spends its
    capacity on within-site differences.
  - `records_only`: the criterion's ranking method using records only (flat reference)
  - `naive_imagery`: lowest latest NDVI, no model. **Beat this before claiming model value for
    scouting.**
- Missing scores (a plot with no image yet) rank last and still count, and ties are broken at
  random, so every ranking is judged on the same plots.

## 8. "Earliest useful forecast" criteria (`progressive/criteria.py`)

Evaluated per imagery stage on the headline scheme and primary model. Each check reports its
value, threshold and yes/no/unknown (`criteria.json`, and the table in `summary.md`):

1. **Beats records**: MAE ≥ 5% below records only, and the bootstrap interval for ΔMAE excludes 0.
2. **Consistent**: MAE falls in ≥ 67% of held-out site-seasons, and in ≥ 75% of candidate
   models (not one model's luck).
3. **Calibrated**: coverage within ±5 points of 90%, and no site-season below 75%.
4. **Scouting**: bottom-quartile recall at a 20% budget beats the same ranking method on records
   only by ≥ 5 points (`scouting_ranker`, fixed in advance: `relative_forecast`), and beats random.
5. **Early**: median lead time to harvest ≥ 30 days.

The output lists the **first stage passing all five** (or none) and, separately, the stages
passing the accuracy checks. The lowest-MAE stage is *not* automatically the answer. The
thresholds live in `configs/progressive.yaml`, so change them before the run, not after.

## 9. Outputs and where they go

`ml/experiments/progressive/<name>/`:

| File | Use |
|---|---|
| `summary.md` | the human-readable report: progression table, criteria, scouting, contrast, spatial, timing, notes |
| `progressive_results.csv` / `.json` | every stage × model × scheme row (the JSON also holds config, timing, features, criteria) |
| `progression_table.md` | the headline table for slides |
| `scouting_results.csv` | recall / precision / lift / skill by stage, ranking and budget |
| `criteria.json` | the five checks, value by value |
| `spatial_autocorrelation.csv` | Moran's I of residuals per stage and site-season |
| `predictions.csv`, `predictions.geojson` | out-of-fold forecast, interval and residual per plot and stage (map layer; git-ignored in the template) |
| `imagery_ablation.json` | the **backend contract**: records only vs + imagery at one stage |
| `imagery_ablation_by_stage.json` | the same comparison at every stage, with timing, intervals and recall |
| `figures/` | `mae_vs_stage`, `delta_mae_vs_stage`, `interval_vs_stage`, `scouting_recall_vs_stage`, `validation_contrast` |

**Backend:** `--publish` writes `backend/artifacts/imagery_ablation.json` (and the by-stage file
next to it). The API (`GET /api/evaluation/imagery`) and the dashboard's "What did the satellite
imagery add?" card read it with no code change. It is validated with the backend's own
pydantic model before it is written. The registry only scans directories, so the extra JSON is
safe. The by-stage file is *not read by the API yet*. To show the comparison by stage on the
dashboard, the backend/frontend owner would add `GET /api/evaluation/imagery/stages` returning
`imagery_ablation_by_stage.json` (its shape is stable). The current card already renders more
than two variants, but it prints a single `as_of` date, so keep the published file to two
variants and choose the stage with `--ablation-stage`.

## 10. PostGIS: **DO NOT PRIORITIZE POSTGIS** (for prediction or validation)

- **Scale:** about 1,500 plots × 6 passes. Every spatial operation the ML needs (nearest
  neighbours, Moran's I, buffers, plot-to-plot distances) runs in memory with scipy in
  milliseconds (`progressive/spatial.py`). The ML pipeline and the API are file-based
  (CSV/Parquet → joblib + JSON), and compose has no DB service. A database would add a
  deployment dependency with no accuracy gain.
- **The one spatial question that matters for accuracy is answered without it.**
  `spatial_autocorrelation.csv` reports Moran's I of out-of-fold residuals per site-season. If
  the real residuals are clearly clustered (median I ≳ 0.2 with p < 0.05 in most site-seasons),
  the fix is **neighbour features in Python** (e.g. neighbours' mean relative NDVI, or
  range/row trend), not a database. The synthetic fixture includes a spatial field, and the
  check detects it.
- **Where PostGIS is legitimate** (the map-focused teammate's call): plot polygons, vector tiles
  or dynamic spatial queries in the API, and scouting route layers. `predictions.geojson` is
  already a drop-in layer (points with forecast and residual per stage). It loads into the
  existing Postgres with `ogr2ogr -f PostgreSQL PG:"…" predictions.geojson -nln plot_predictions`
  if they want it there. Keep credentials out of the repo.

## 11. What the synthetic template does and does not show

It shows the **format** and that every path runs. Its numbers are not evidence. Structural
behaviours worth watching for in the real data (they come from the practice data's real
structure, which the fixture copies):
- **Records-only can rank plots *worse than random* within a new site.** Nitrogen rates sit in
  separate blocks with site-specific patterns (see `dataset_profile.md`), so nitrogen effects
  learned at other sites transfer backwards. The existing sensitivity checks flag the same
  thing ("investigate").
- **Imagery can cut cross-site MAE a lot and still barely improve within-site ranking**: the
  gain comes from getting the site level right. That is why ranking is scored within
  site-seasons and why `naive_imagery` and `relative_forecast` exist.
- **Late passes can hurt at an unseen site**: senescence timing differs by site, and Lincoln's
  NDVI-yield correlation flips sign after the drought.
- Ridge extrapolates badly on site-identifying features with 2 training sites (MAE in the
  hundreds). The existing practice report shows the same (Ridge 150 ± 160 in May). The figures
  mark off-scale points.

## 12. Unresolved questions for tomorrow

1. **2023 labels?** If fewer than 100 labelled, imaged 2023 plots exist, the temporal test is
   skipped automatically, and the limitation is stated in `summary.md` (brief: don't force it).
2. **Three sites:** leave-one-site-out gives 3 folds. The consistency check (≥ 2 of 3) is coarse,
   and interval calibration inside 2-site folds is fragile. Report coverage honestly, or decide
   on a documented widening.
3. **Harvest dates** aren't in the ground truth, so lead time assumes Oct 15. Agent 1: add
   `harvest_date` if the organizers provide it.
4. **Definition of "poor plot":** bottom quartile within site-season is our reading. If the
   organizers define it differently (e.g. relative to a check hybrid), change `poor_quantile` /
   `scouting_unit` or add a column.
5. **Primary model** is CatBoost by default. Keep or change it *before* the real run.
6. **Records + public context** (NOAA weather, SSURGO soil) is deliberately *not* in Baseline B,
   which per the brief is records only. It could be a separate stage if the team wants it.
7. **Agent 2's table has no coordinates** (only per-image centroids in EPSG 32615 in
   `satellite_image_features.parquet`), so the spatial residual check and the GeoJSON need
   Agent 1's `--plots` with latitude/longitude.
8. **Calibration at a new site** fails everywhere on the practice data (coverage 70–81%). The
   options are to widen by a documented factor, to calibrate per site-season (Mondrian), or to
   report ranges as indicative. This is a team decision.

## 13. Coordination-doc briefing (paste as-is)

> **[Agent 3]** Progressive early-signal framework is in the PR (see the PR link) at
> `ml/soilsignal_ml/progressive/` (run `ml/progressive_experiment.py`; full guide in
> `AGENT3_HANDOFF.md`).
> **Needs from Agent 1:** `plots` (plot_id, site_id, year, planting_date, final_yield +
> genotype, nitrogen_lb_ac, irrigated; optional field_id, lat/lon, harvest_date) and
> `acquisitions` (site_id, year, tp, date from DateofCollection).
> **Needs from Agent 2:** ONE of: cumulative long `tp_features` (plot_id, tp, features where the
> tp=k row uses passes 1..k only), wide (`ndvi_tp3` style), or per-pass `tp_observations`
> (I accumulate). The NDVI baseline expects `ndvi_latest`; tell me if named differently.
> **Validation:** grouped only (auto headline: 2022→2023 if ≥ 100 labelled imaged 2023 plots,
> else leave-one-site-out); random split is shown only as a contrast.
> **Outputs:** progression table (records → TP1…TP6 with dates/DAP), ΔMAE + bootstrap CI,
> 90% coverage/width (nested conformal + CQR), scouting recall @10/20/25%, 5 transparent
> "earliest useful" checks, `imagery_ablation.json` for the backend (`--publish`).
> **Real practice results (3 challenge sites, leave-one-site-out):** imagery beats records at
> every TP and every site; lowest error with TP1–TP3 (MAE 48 vs 95.5 records only); within-site
> scouting from TP1 (mid-July) finds 39% of bottom-quartile plots at a 20% budget vs 24% records,
> 20% random. The 90% ranges under-cover at a new site (70–81%). See
> `ml/experiments/progressive/practice_3sites/summary.md`.
> **PostGIS:** DO NOT PRIORITIZE for ML (scipy does the spatial checks); `predictions.geojson`
> is ready for the map layer.
