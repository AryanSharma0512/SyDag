# SoilSignal ML

Trains the progressive (as-of-date) yield models that the SoilSignal API serves. On data day,
responding to a new dataset should mean **write an adapter → inspect → adjust config → retrain →
validate → export → deploy**, never a rewrite.

```
python -m soilsignal_ml ingest     canonical dataset: plots, images, weather, soil, county yields
python -m soilsignal_ml validate   data checks (units, ranges, duplicates, coverage)
python -m soilsignal_ml profile    experiments/reports/dataset_profile.md
python -m soilsignal_ml train      screen feature sets, tune and validate every model, every cutoff
python -m soilsignal_ml report     experiments/reports/model_report.md
python -m soilsignal_ml export     backend/artifacts/soilsignal-maize-MMDD/ via save_artifact()
python progressive_experiment.py   early signal: records only vs + TP1..TP6, scouting, imagery_ablation.json
```

Run every command from `ml/` with the backend's environment and the `ml` dependency group:

```bash
cd ml
uv run --project ../backend --group ml python -m soilsignal_ml train
uv run --project ../backend --group ml pytest
```

## Why the environment is the backend's

A model has to be trained with the same scikit-learn, numpy and pandas versions the API loads it
with. Training libraries (CatBoost, Optuna, tifffile, pyproj, …) are therefore a dependency
**group** in `backend/pyproject.toml`: one lockfile for both. Docker installs only the runtime
dependencies, plus whichever model library a deployed model needs.

LightGBM and XGBoost need the OpenMP runtime (`libomp`), which the training Mac lacks.
scikit-learn's `HistGradientBoostingRegressor` implements LightGBM's histogram algorithm, and
CatBoost covers ordered boosting.

## Where things live

| Path | What |
|---|---|
| `soilsignal_ml/ingest/dataset_adapter.py` | `PublicDatasetAdapter` (Shrestha et al. 2024) and the `HackathonDatasetAdapter` stub |
| `soilsignal_ml/ingest/canonical.py` | The canonical tables every adapter produces, and `field_inputs(plot)` |
| `soilsignal_ml/ingest/remote_zip.py` | Reads members of a remote zip over HTTP byte ranges: the 3.2 GB archive is never downloaded, only ~120 MB streamed through memory |
| `soilsignal_ml/ingest/context.py` | NOAA weather (gap-filled from nearby stations), SSURGO soil per plot, NASS county yields, all through the backend's own fetchers |
| `soilsignal_ml/ingest/validate.py`, `profile.py` | Data checks and the dataset profile |
| `soilsignal_ml/features/build.py` | Training tables from `backend/app/features` (the same code serving uses) |
| `soilsignal_ml/validation/splits.py` | Grouped splits (plot, field, site, year) and the held-out site, with overlap assertions |
| `soilsignal_ml/models/` | The model ladder (mean, Ridge, Random Forest, HistGradientBoosting, CatBoost) and `train.py` |
| `soilsignal_ml/evaluation/` | Metrics, conformal-style intervals, permutation importance and direction, sensitivity checks, report |
| `soilsignal_ml/progressive/` | Early-signal experiments (records only vs + imagery through TP1…TP6): input contract for the ingestion and feature agents, grouped validation incl. 2022 → 2023, nested conformal and CQR intervals, scouting recall, "earliest useful" checks, `imagery_ablation.json`. See `AGENT3_HANDOFF.md` |
| `progressive_experiment.py`, `configs/progressive.yaml` | Its entry point and settings (fixed before a run) |
| `soilsignal_ml/export/export_to_backend.py` | Writes artifacts with `app.model.export.save_artifact` |
| `configs/project.yaml` | Held-out site, seed, interval level, trials, simplicity margin |
| `configs/{may,june,july,august,full}.yaml` | One file per season cutoff (`as_of`, `model_id`) |
| `research/` | Agronomy thresholds (with sources) and published benchmarks |
| `experiments/results.csv`, `experiments/runs/` | One row per evaluated model; full detail per run |
| `experiments/reports/` | Dataset profile and model report |
| `experiments/rehearsal/` | The superseded first run (mean-only selection) and why it was replaced |
| `notebooks/explore_dataset.ipynb` | Exploration of the canonical dataset |
| `data/` | Git-ignored. `processed/<dataset>/` holds the canonical tables, `interim/` the feature tables |

Feature engineering itself lives in **`backend/app/features/`** (`build_features(inputs, as_of)`).
The API computes the same features when it serves a forecast, and the backend's Docker image
only contains `backend/`.

## The method, in order

1. **Point-in-time features.** `build_features()` drops every input dated after the forecast
   date, then asserts nothing later got through. `ml/tests/test_leakage.py` appends extreme future
   weather, imagery and county yields to real plots and checks that no feature changes.
2. **Held-out site.** Chosen in `configs/project.yaml` before any training. It is never used for
   screening, tuning, selection or intervals. The dashboard shows its plots, so every live number
   is out-of-sample.
3. **Feature-set screening.** Each ablation (management, crop signals, +timing, +weather, +soil,
   all) is scored by leave-one-site-out CV with default parameters. With few sites, site-level
   features can act as site identifiers, so whether they help a new site is measured, not assumed.
   A feature is used only if it is observable at every training site by the cutoff.
4. **Tuning.** Optuna minimizes mean leave-one-site-out MAE.
5. **Selection.** Lowest **mean + 1 SD** of fold MAE: a model that is consistent across sites
   beats one that is sometimes excellent and sometimes far off (brief §45). A more complex model
   has to win by more than `simpler_model_margin`. The first full run used the mean alone. That
   run is kept in `experiments/rehearsal/`, with the reason it was replaced.
6. **Intervals.** Quantiles of out-of-fold residuals from unseen sites, with a finite-sample
   conformal correction. Coverage is reported on the held-out site.
7. **Drivers.** Permutation importance on held-out-site folds, and direction from per-plot
   contributions (see `backend/app/model/explain.py`). Serving computes per-forecast drivers
   the same way.
8. **Sensitivity.** Sweep one feature for a typical plot and compare the response with the
   literature (`research/agronomy_thresholds.yaml`). A mismatch means investigate, not override.

## Challenge dataset (SyDAg26)

`python -m soilsignal_ml challenge` reads the organizers' shared folder (a local copy at
`ml/data/raw/challenge/`: `Groundtruth/` (any case), `Satellite/<Location>/TP1..6/`,
`UAV/<Location>/TP1..3/`) and writes compact tables to `ml/data/challenge/` (committed; no
imagery). `time_point` is an int per site and modality, and dates are datetime64:

| File | One row per | Read by |
|---|---|---|
| `plots.parquet` | ground-truth plot: `plot_id` = `{year}-{site}-{experiment}-{range}-{row}`, records, target, coordinates | imagery `--plots`, progressive `--plots` |
| `images.parquet` | usable image: `path, modality, site_id, time_point, plot_id, date` | imagery `--manifest` |
| `acquisition_dates.parquet` | site × modality × pass → date (`DateofCollection.xlsx`) | imagery `--acquisitions` |
| `satellite_acquisitions.parquet` | satellite pass: `site_id, year, tp, date` | progressive `--acquisitions` |
| `satellite_manifest.parquet`, `uav_manifest.parquet` | every file, incl. unmatched and duplicates, with raster metadata | audit |
| `observations.parquet`, `sites.parquet`, `drive_inventory.parquet`, `challenge_manifest.json` | usable image; site; Drive file; counts, anomalies, schemas | reference |

```bash
PY="uv run --project ../backend --group ml python"
$PY -m soilsignal_ml challenge --inventory data/challenge/drive_inventory.parquet  # restartable
$PY -m soilsignal_ml --dataset sydag26 ingest     # canonical tables (--dataset before the command)
$PY -m soilsignal_ml challenge-sql                # optional Postgres/PostGIS load
```

`HackathonDatasetAdapter` (`ingest/dataset_adapter.py`, dataset `sydag26`) turns these into the
canonical tables. It takes indices from the imagery stage's
`data/interim/imagery/canonical_observations.csv` when present, else from the GeoTIFFs.
Weather, soil and county yields stay separate context tables; `plots` holds records only.
Details, statistics and anomalies: `AGENT1_HANDOFF.md` at the repository root.

## Data day: switching to the challenge dataset

1. `challenge` (above), then `--dataset sydag26 ingest` and `validate`
   (`HackathonDatasetAdapter` is implemented). Read `experiments/reports/sydag26_dataset_profile.md`
   before changing anything.
2. The early-signal benchmark (records only, then + TP1, + TP1–TP2, …) runs in
   `progressive_experiment.py` (`AGENT3_HANDOFF.md`).
3. Revisit `configs/`: the held-out group (site? year?), the cutoff dates for that season,
   and `primary_validation` in `splits.py` terms (with several years, `year` is the honest split).
4. `train`, `report`, `export`. Add the winning library to the backend if it isn't there
   (`cd backend && uv add catboost`).
5. `cd backend && uv run pytest`, then deploy (see `STRUCTURE.md`).
