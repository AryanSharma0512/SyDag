# SoilSignal: Project Structure & Data-Day Map

What exists, where it lives, and what to run or call to move the site from the
practice data to the challenge data. **Keep this file updated in the same PR as any structural change.**

Last updated: 2026-09-27

---

## How a request flows

```
Browser ──► sydag.aboutsharma.com (Cloudflare → Aryan's reverse proxy)
              ├── /*      → sydag_frontend  (nginx serving the Vite build)
              └── /api/*  → sydag_backend   (FastAPI, port 8000)
                              ├── forecasts  ← ModelForecastProvider: backend/data/practice + backend/artifacts
                              │                 (SOILSIGNAL_DATA_SOURCE=mock serves the demo data instead)
                              ├── predictions ← ModelRegistry    (backend/artifacts/)
                              │                   features ← backend/app/features (build_features)
                              └── /api/context/* ← USDA SSURGO, NOAA NCEI, USDA NASS
                                                   (fetched by the backend, cached in backend/cache/)

ml/ (offline) ── dataset adapter ─► canonical tables ─► build_features (same backend code)
                 ─► leave-one-site-out screening/tuning ─► held-out site ─► save_artifact()
                 ─► backend/artifacts/soilsignal-maize-MMDD/
```

---

## Data-day playbook

In order. **Ready** = built and tested. **Not built** = still to do.

| # | Step | What to run / call / edit | Status |
|---|------|---------------------------|--------|
| 0 | Map the challenge files to the canonical tables | `cd ml && uv run --project ../backend --group ml python -m soilsignal_ml challenge` (inventory + joins → `ml/data/challenge/`), then `python -m soilsignal_ml --dataset sydag26 ingest` (`HackathonDatasetAdapter`). The downstream stages read `ml/data/challenge/{plots,images,acquisition_dates,satellite_acquisitions}.parquet`. See `AGENT1_HANDOFF.md`. Still to set: the held-out group and cutoffs in `ml/configs/` | Ready |
| 1 | Ingest, check and profile the dataset | `cd ml && uv run --project ../backend --group ml python -m soilsignal_ml ingest`, then `validate`, `profile` (→ `ml/experiments/reports/dataset_profile.md`) | Ready |
| 2 | Features + leak-free validation + training | `... -m soilsignal_ml train` (feature-set screening, Optuna tuning, leave-one-site-out, held-out site), then `report` (→ `ml/experiments/reports/model_report.md`) | Ready |
| 2b | Early signal: records only vs + imagery through TP1…TP6, scouting recall, `imagery_ablation.json` | `... python progressive_experiment.py --imagery-table data/interim/imagery/satellite_features.parquet` (after `python -m soilsignal_ml.imagery run`; or `--plots … --tp-features … --acquisitions …`) (→ `ml/experiments/progressive/<name>/summary.md`; `--publish` writes `backend/artifacts/imagery_ablation.json`). Guide: `AGENT3_HANDOFF.md` | Ready (synthetic template only; no real run yet) |
| 3 | Export each trained model | `... -m soilsignal_ml export` (calls `save_artifact()` in `backend/app/model/export.py` for every cutoff config) | Ready |
| 4 | Add any new model library to the backend | `cd backend && uv add catboost` (or lightgbm/xgboost), commit `uv.lock`, rebuild the image. Training-only libraries go in the `ml` group: `uv add --group ml ...` | Ready |
| 5 | Test the model locally | `cd backend && uv run uvicorn app.main:app --port 8000`, then `GET /api/models` and `POST /api/predict` | Ready |
| 6 | Deploy the model | Copy `backend/artifacts/<model_id>/` to the server, then `docker compose -f compose.sydag.yml restart backend`. Check `/api/health` shows `modelsLoaded > 0` | Ready |
| 7 | Get predictions | `POST /api/predict` with `features` + `asOfDate` | Ready |
| 8 | Give the API the fields to show | `... -m soilsignal_ml showcase` writes raw inputs for the held-out plots to `backend/data/practice/<dataset>.json` (inputs only; the API computes every forecast). For challenge data, point `showcase.py` at the plots the dashboard should show | Ready |
| 9 | Real forecasts on the live site | Default already: compose builds the frontend with `VITE_DEMO_MODE=false` and runs the backend with `SOILSIGNAL_DATA_SOURCE=model`. `deploy.sh` rebuilds both and fails unless `/api/health` reports `"dataSource":"model"` with models loaded | Ready |
| 10 | Remove the dummy models | Delete `backend/artifacts/dummy-*` locally and on the server (the registry would mix them with real cutoffs) | — |
| 11 | Public data for the real fields | Give each field its real `latitude`/`longitude`; soil, observed weather and county yields load automatically through `/api/context/all`. Regenerate the demo snapshot with `cd backend && uv run python -m scripts.snapshot_context` | Ready |
| 11b | Publish the imagery comparison | Write `backend/artifacts/imagery_ablation.json` (validation MAE with and without imagery; format in `backend/app/forecast/evaluation.py`) and deploy it with the models. The dashboard shows "Waiting for the current training run." until it exists | Ready (file to write) |
| 11c | Historical weather outlook | Put the challenge weather file in `ml/data/raw/weather/`, then `cd ml && uv run --project ../backend --group ml python -m soilsignal_ml.weather_outlook history` (NOAA/IEM download, season QC, publishes `backend/data/weather_history/{supplied,long}/`) and `... backtest --library long`. Serve with `GET /api/weather-outlook`. Method and results: `ml/research/weather_outlook.md` | Ready (dashboard "Historical weather outlook") |
| 11d | **Publish the frozen final results** | Write `final_results.json` (contract in `backend/app/results.py`, walkthrough in `docs/FINAL_RESULTS_CONTRACT.md`), check it with `cd backend && uv run python -m app.results <file>`, copy it to `backend/artifacts/` locally and on the server (the folder is mounted; no restart or rebuild). Feeds "How early can we know?", the typical validation error, per-plot forecasts by location, maturity, and satellite vs UAV | Ready (file to write) |
| 11e | Trial-site registry | After the challenge inventory changes: `cd backend && uv run --group ml python -m scripts.export_trial_sites` (writes `backend/data/trial_sites.json` and `src/mock/trialSites.ts`); served by `GET /api/sites` | Ready |
| 12 | County yield history | Locally the key is in `backend/.env` (git-ignored). On the server, put `SOILSIGNAL_NASS_API_KEY=...` in a `.env` next to `compose.sydag.yml` and restart the backend. **Never commit the key: the repo is public** | Ready (add the key on the server) |

---

## API reference

Base path `/api`. Interactive docs at `/api/docs`. JSON is camelCase.

| Method | Endpoint | Called by / when | Returns |
|--------|----------|------------------|---------|
| GET | `/api/health` | Deploy checks, Docker healthcheck, navigation badge | `status`, `version`, `dataSource` (`model`, `mock`, or `unavailable`), `modelsLoaded`, `datasetLabel` ("Practice data") |
| GET | `/api/fields?site=` | Frontend `getFields()`; with `site`, the dashboard's plot picker (`getSitePlots()`) | `FieldMeta[]`: the featured plots, with `plotId`, `site`, `hybrid`, `nitrogenLbAc`, `plantingDate` when the bundle has them. With `site`, every plot with a forecast at that trial site |
| GET | `/api/sites` | Overview map, dashboard location bar, Data and Methodology pages (`getTrialSites()`) | `TrialSite[]` (`backend/app/sites.py`): the five trial sites from `data/trial_sites.json` (state, coordinates, irrigation, plots, satellite and UAV acquisitions and usable plot images per season), plus what this deployment can show: `weather` (weather-library key, seasons, station, whether similar seasons are weighted) and `forecasts` (live-model plots, final-result plots, seasons) |
| GET | `/api/results` | Dashboard and Methodology (`getFinalResults()`) | `FinalResults` (`backend/app/results.py`): `status` `pending` until `artifacts/final_results.json` exists, then model, validation, performance by days after planting (R², MAE, RMSE), earliest useful DAP, site forecasts, plot counts, maturity, satellite vs UAV. `503` naming the problem if the file is malformed |
| GET | `/api/results/plots?site=&season=` | Dashboard plot picker and forecast when the final results cover a site (`getResultPlots()`) | Per-plot forecasts (`date`, `dap`, `yield`, `lower`, `upper`) and optional per-plot UAV predictions; empty while pending |
| GET | `/api/fields/{id}` | Frontend `getFieldById()` | `FieldMeta`. Every plot in `/api/decisions` resolves here and in `/forecast`, not only the featured ones |
| GET | `/api/fields/{id}/forecast` | Dashboard on load and on field switch (`getForecast()`) | `FieldForecast`: one snapshot per model cutoff (point-in-time features + model), vegetation, events, history, sources. `503` if the model data source can't serve |
| GET | `/api/fields/{id}/weather?snapshotId=` | Frontend `getWeatherContext()` | `WeatherContext` (latest snapshot by default) |
| GET | `/api/fields/{id}/soil` | Frontend `getSoilContext()` | `SoilContext` |
| GET | `/api/decisions?asOfDate=` | Dashboard scouting queue and hybrid table, on every change of forecast date (`getDecisions()`) | `DecisionSet`: every plot in that season at its latest forecast on or before the date (same features and model as the dashboard snapshot), previous forecast and change, top negative driver. `404` for an unknown season or a date before the first forecast |
| GET | `/api/models` | Dashboard "When does the forecast become useful?" (`getModels()`); after deploying a model, to confirm it loaded | id, metrics, validation, `asOf`, feature list, `dataset`, `holdout` (held-out site accuracy) |
| GET | `/api/evaluation/imagery` | Dashboard "What did the satellite imagery add?" (`getImageryAblation()`) | `ImageryAblation`: `status` `pending` until `artifacts/imagery_ablation.json` exists, then the variants' validation MAE. `503` if the file is malformed |
| GET | `/api/weather-outlook?site=&asOfDate=&horizonDays=&plantingDate=&library=` | Dashboard "Historical weather outlook" on every change of site, forecast date or horizon (`src/services/weatherOutlook.ts`, which maps it to the website's own `WeatherOutlook` type; `site` is the weather-library key from `/api/sites`, e.g. `MOValley`) | Historical analog outlook (contract in `backend/app/weather_outlook/contract.py`, `contractVersion`): favorable / typical / adverse probabilities with bootstrap intervals, historical and effective seasons, weather outcome percentiles, representative seasons, analog weights. `horizonDays` is days or `season`. `404` unknown site or library name, `422` a date/horizon the library cannot answer, `503` library missing |
| POST | `/api/predict` | **Prediction on real data.** Body: `{"features": {...}, "asOfDate": "YYYY-MM-DD"}` or `"modelId"` | `yield`, `lowerBound`, `upperBound`, `intervalLevel`, `confidence` (interval precision × share of inputs inside the training range), `confidenceRating`, `drivers` (this forecast's own drivers when the schema has typical values) |
| GET | `/api/context/all?lat=&lon=&date=` | Dashboard once per field (`getLocationContext()`), with `date` repeated for every forecast date | `LocationContext`: `county`, and `soil` / `weather` / `yieldHistory` parts, each with its own `status` (`ok`, `unavailable`, `not_configured`) |
| GET | `/api/context/soil?lat=&lon=` | Soil for one point | `SoilProfile` from USDA NRCS SSURGO |
| GET | `/api/context/weather?lat=&lon=&date=` | Observed weather as of a date | `ObservedWeather`: nearest NOAA station, rainfall, growing degree days, heat days, dry spells |
| GET | `/api/context/yield-history?lat=&lon=&throughYear=` | County corn yields | `YieldHistory` from USDA NASS (needs `SOILSIGNAL_NASS_API_KEY`) |
| GET | `/api/context/export?lat=&lon=&type=&date=` | Data Explorer downloads (`getLocationContextCsv()`); `type` is `weather`, `soil`, `yield-history` or `all` | CSV of the normalized values (never raw upstream responses); `all` is a long table that includes each source's status |

Data provenance (`getDataSources()` in `src/services/sources.ts`): in API mode it is the
forecast's own `sources` (practice/challenge data, connected public data, model output); in
demo mode, the list in `src/mock/fieldsData.ts`. It describes the sources; it is not live
connectivity. The Data Explorer's "Connected" means the latest `/api/context/all` response
reported `status: ok` for that source.

Context sources are cached on disk (soil forever, county yields 14 days, weather 6 hours
while recent and 30 days once settled). If a source is down, the last good copy is served.

Errors: `404` unknown field/model/snapshot, or no model valid by `asOfDate`;
`422` bad prediction input (lists every problem); `503` no model artifacts loaded
or one failed to load, and for forecast endpoints when `SOILSIGNAL_DATA_SOURCE=model` has
no bundles or models. There is no fallback to demo data; the dashboard shows an error.

---

## Repository map

### Deployment (root)

| Path | Purpose |
|------|---------|
| `compose.sydag.yml` | Runs `sydag_frontend` (host `127.0.0.1:8188`) and `sydag_backend` (`127.0.0.1:8189`) on `lostnfound_network`; mounts `backend/artifacts` read-only |
| `Dockerfile.sydag` | Frontend image: `npm ci` + Vite build → nginx. Build arg `VITE_DEMO_MODE` |
| `nginx.sydag.conf` | Frontend nginx: SPA fallback, asset caching, `/api/` proxied to the backend container |
| `deploy.sh` | Production deploy, run on the server by `.github/workflows/` on every push to `main`: pull, rebuild frontend **and** backend, wait for the page and for `/api/health` to report model forecasts |
| `.dockerignore` | Keeps `node_modules`, `dist`, env files, `backend/` out of the frontend image |
| `.env.example` | Frontend env vars (see "Configuration") |
| `package.json` / `package-lock.json` | Frontend deps. npm is the production package manager (Docker runs `npm ci`) |
| `bun.lock` | Also committed for Bun users; refresh with `bun install` after dependency changes |
| `README.md` | Product overview, routes, local development |

### Backend (`backend/`)

| Path | Purpose |
|------|---------|
| `app/main.py` | FastAPI app; docs at `/api/docs` |
| `app/routes.py` | All `/api` endpoints |
| `app/schemas.py` | API response models; **mirror of `src/types/agricultural.ts`** |
| `app/providers.py` | `ForecastProvider` protocol, `ModelForecastProvider` (production), `MockForecastProvider`; `get_provider()` picks by `SOILSIGNAL_DATA_SOURCE`, no fallback; `get_registry()` loads models |
| `app/forecast/bundle.py` | Loads a showcase bundle (raw inputs for the dashboard's fields) into `FieldInputs` |
| `app/forecast/builder.py` | `FieldForecast` from inputs + models: per-cutoff snapshots, weather vs normals, soil, drivers as plain-language explanations, neighbouring-plot map, events, history, provenance; the trial record on `FieldMeta`; `decisions()` scores every bundled plot per forecast date for `/api/decisions` |
| `app/forecast/evaluation.py` | Reads `artifacts/imagery_ablation.json` (the ML team's with/without imagery comparison) for `/api/evaluation/imagery` |
| `app/results.py` | The frozen final-results contract: parses `artifacts/final_results.json` (re-read when it changes), serves `/api/results` and `/api/results/plots`; `python -m app.results <file>` checks a file |
| `app/sites.py` | Trial-site models for `/api/sites`; loads `data/trial_sites.json` |
| `data/trial_sites.json` | The five trial sites from the challenge inventory (written by `scripts/export_trial_sites.py`) |
| `app/weather_outlook/` | Historical weather outlook: `history.py` (library loader), `features.py` (season-to-date descriptors and horizon outcomes from `app/features/weather.py`), `analogs.py` (robust standardization, kernel weights, effective sample size, terciles), `stress.py` (provisional FAO water/heat stress scorer), `scenarios.py` (`WeatherOutlook.generate`, trajectories, bootstrap, `couple_yield`), `coupling.py` (`artifact_predictor`: a yield model scores each trajectory), `contract.py` (JSON + trajectory table), `service.py` (API) |
| `app/config.py` | Settings (`SOILSIGNAL_*` env vars) |
| `app/model/contract.py` | Model artifact format: `ModelMetadata` (incl. held-out evaluation), `FeatureSchema` (incl. typical values, training ranges, driver phrases) |
| `app/model/artifact.py` | Loads and checks artifacts, validates inputs, predicts, confidence; `ModelRegistry.for_date()` picks the point-in-time model |
| `app/model/explain.py` | Per-forecast drivers: how far the forecast moves if one feature were typical |
| `app/model/export.py` | `save_artifact()`: the only way the ML side should write models |
| `app/features/build.py` | `build_features(FieldInputs, as_of)`: the one feature pipeline for training and serving; drops and asserts against anything dated after `as_of` |
| `app/features/inputs.py` | `FieldInputs`: raw per-field inputs (images, daily weather, soil, management, county yields) |
| `app/features/vegetation.py`, `weather.py`, `soil.py`, `temporal.py` | Index formulas and in-season summaries; GDD, heat, dry spells, Hargreaves water deficit, stage windows; soil; growth stage |
| `app/features/thresholds.py` | Agronomic thresholds, each sourced in `ml/research/agronomy_thresholds.md` |
| `app/features/catalog.py` | Every feature's label, category, ablation group and driver phrases |
| `app/context_routes.py` | `/api/context/*` endpoints |
| `app/context/service.py` | Runs the public-data sources in parallel with caching; each fails independently |
| `app/context/soil.py`, `weather.py`, `yield_history.py`, `geo.py` | One module per source: USDA Soil Data Access, NOAA NCEI, USDA NASS Quick Stats, FCC county lookup |
| `app/context/cache.py` | Disk cache with per-source lifetimes; serves the last good copy when a source is down |
| `cache/` | Cached public data (git-ignored; a named Docker volume in production) |
| `artifacts/<model_id>/` | Deployed models (`model.joblib`, `metadata.json`, `feature_schema.json`). `soilsignal-maize-0531` … `-1015` are the practice-data models, committed so a pull deploys them; `dummy-*` is git-ignored |
| `data/mock/fields.json` | Mock forecasts, generated from `src/mock/fieldsData.ts` |
| `data/practice/<dataset>.json` | Showcase bundle: raw inputs (images, weather, soil, management, county history, climate normals) for the held-out plots the dashboard shows. Written by `ml ... showcase`; holds no yields |
| `data/weather_history/<library>/` | Weather libraries for the outlook: `daily.csv.gz` (one station per site) and `manifest.json` (station, seasons kept and left out with reasons, site parameters, outlook settings). `supplied` = challenge file 2018-2023; `long` = NOAA GHCN-Daily 1994-2025. Written by `ml ... weather_outlook history` |
| `scripts/make_dummy_model.py` | Trains 3 synthetic cutoff models; export reference |
| `scripts/export_trial_sites.py` | `ml/data/challenge/` inventory → `data/trial_sites.json` and `src/mock/trialSites.ts` |
| `scripts/snapshot_context.py` | Fetches public data for every demo field; writes `src/mock/contextSnapshot.ts` and warms the cache |
| `tests/` | `test_results_sites.py` (final-results contract, trial sites, `/api/fields?site=`), `test_api.py` (endpoints + contract, no-fallback), `test_model.py` (artifacts, predict, point-in-time), `test_features.py` (formulas, leakage), `test_forecast.py` (model-backed forecasts recomputed from raw inputs), `test_context.py` (public data, replayed offline from `tests/fixtures/context/`) |
| `Dockerfile` | Python 3.13 + uv, frozen lockfile, non-root, healthcheck |
| `pyproject.toml` / `uv.lock` | Pinned deps. **Models must be trained with these versions**. Training-only libraries are the `ml` dependency group (not installed in Docker) |
| `README.md` | Backend details: running, testing, artifact format |

### Frontend (`src/`)

| Path | Purpose |
|------|---------|
| `types/agricultural.ts` | Frontend data contract (`FieldForecast` and friends) |
| `types/results.ts`, `types/sites.ts` | Mirrors of `backend/app/results.py` and `backend/app/sites.py` |
| `types/weatherOutlook.ts` | The website's own weather-outlook shape (not the raw API) |
| `services/sites.ts` | `getTrialSites()`: `/api/sites`; demo mode: `mock/trialSites.ts` plus a "Demo fields" location for the demo data |
| `services/results.ts` | `getFinalResults()`, `getResultPlots()`, `stageForDap()`, `maturityFor()`; demo mode: pending. Swap the source here to move from the frozen file to live inference |
| `services/plotForecasts.ts` | One `PlotSeries` per plot whichever source serves it (final results where they cover a site, else the live models); plot lists per site; typical validation error; the default forecast date |
| `services/weatherOutlook.ts` | Wraps `/api/weather-outlook`: fractions → whole percentages, mm → inches, loading / success / unavailable; no fallback numbers |
| `services/*.ts` | The only code that fetches data: demo data in demo mode, `/api` otherwise |
| `services/sources.ts` | Data provenance: the forecast's `sources` in API mode, the demo list in demo mode |
| `services/dataset.ts` | Dataset labels: `getDatasetLabel()` for live-model views (`/api/health`), `getSiteDatasetLabel()` for the navigation badge (the final results' label once published) |
| `services/context.ts` | `getLocationContext()`: public soil, weather and county yields for a field; `getLocationContextCsv()` for downloads |
| `services/decisions.ts` | `getDecisions(asOfDate)`: every plot at a date for the scouting queue (demo mode assembles it from the demo fields) |
| `services/evaluation.ts` | `getModels()` and `getImageryAblation()` for the model reliability section (demo mode: none / pending) |
| `utils/imagery.ts` | Satellite passes from the vegetation series: pass counts, "Before imagery" / "After pass N" labels, planting date |
| `services/contextCsv.ts` | Demo-build CSV from the snapshot, mirroring `backend/app/context/export.py` |
| `utils/useLocationContext.ts` | Hook that loads a field's location context once for all its forecast dates (dashboard and Data Explorer) |
| `services/apiClient.ts` | `apiGet()` JSON client |
| `config/appConfig.ts` | Branding, event, team, `demoMode`, `apiBaseUrl`, defaults |
| `mock/fieldsData.ts` | 5 demo fields and `DATA_SOURCES` (source of `backend/data/mock/fields.json`). Coordinates are real farmland whose SSURGO soil matches each field; yields are scaled to each county's real NASS five-year average |
| `mock/contextSnapshot.ts` | Generated snapshot of the public data for the demo fields, used in demo mode |
| `mock/trialSites.ts` | Generated trial-site list for the demo build |
| `App.tsx` | Page shell: route transitions, presentation (`?presentation=true`, `F`) and debug (`?debug=true`) flags |
| `utils/router.tsx` | Client-side routes: `/` overview, `/dashboard`, `/data`, `/methodology`, `/about` |
| `components/dashboard/DashboardView.tsx` | Farmer view: location → season → plot (URL `?site=&plot=`), then yield forecast, timeline, how early, weather outlook, crop development, satellite vs UAV, and a collapsed "More detail"; shortcuts; presentation mode |
| `components/dashboard/LocationBar.tsx` | Location tabs, season picker (hidden with one season), per-site plot picker with a filter |
| `components/dashboard/ForecastSummary.tsx` | Final yield forecast, prediction range, days after planting, typical validation error. No confidence % |
| `components/dashboard/HowEarly.tsx`, `WeatherOutlookCard.tsx`, `MaturityCard.tsx`, `SatelliteVsUav.tsx` | The four supporting modules; each waits honestly for its data |
| `components/dashboard/DashboardDetail.tsx` | "More detail": drivers, crop observations, neighbouring plots, every plot at this date, hybrids, deployed-model validation, location context, provenance (loaded when opened) |
| `components/results/PerformanceByDap.tsx` | MAE (or R²) by days after planting with R² in an aligned row, and its table |
| `components/overview/TrialSiteMap.tsx`, `usMap.ts` | U.S. map of the trial sites; `usMap.ts` is generated by `scripts/build-us-map.mjs` (no map library at runtime) |
| `components/dashboard/ScoutingQueue.tsx` | "Plots to review": transparent sorts (most uncertain, lowest, highest, largest change), table on tablet/desktop, stacked rows on phones, top 10 with "View all" |
| `components/dashboard/HybridPerformance.tsx` | Hybrid table from the same decisions; hidden unless at least 3 hybrids have 3+ plots |
| `components/dashboard/ModelReliability.tsx`, `ImageryValue.tsx` | Validation error by forecast date (optional threshold line: `acceptableMaeBuAc` in `appConfig.ts`); the imagery comparison or "Waiting for the current training run." |
| `components/dashboard/*` | One component per dashboard section; hand-built SVG charts |
| `components/data/*` | Data page (`/data`): trial data by location (`TrialDataSection.tsx`), then public context: source status, weather, county-yield and soil panels, Visual/Data views, CSV menu |
| `components/overview/`, `components/methodology/`, `components/about/` | The other three pages |
| `components/brand/` | SoilSignal mark, lockup and animated logo |
| `components/common/` | Navigation, footer, page transitions, animated numbers, shared controls |
| `components/debug/DebugPanel.tsx` | Location switcher and simulated loading/error states (`?debug=true`) |
| `utils/` | Chart geometry, motion timings, palette, formatting, hooks |

`public/` holds the favicon, touch icon and social preview image.

### Tooling

| Path | Purpose |
|------|---------|
| `scripts/export-mock-data.ts` | `npm run export:mock` → regenerates `backend/data/mock/fields.json` |
| `scripts/build-us-map.mjs` | Regenerates `src/components/overview/usMap.ts` from us-atlas (install the listed packages with `--no-save` first) |
| `vite.config.ts` | Dev server; proxies `/api` to `localhost:8000` |

### ML pipeline (`ml/`)

Run from `ml/` with `uv run --project ../backend --group ml python -m soilsignal_ml <command>`.
Details in `ml/README.md`.

| Path | Purpose |
|------|---------|
| `soilsignal_ml/__main__.py` | CLI: `ingest`, `context`, `validate`, `profile`, `train`, `report`, `export`, `showcase`, `progressive`, `challenge`, `challenge-sql` (`--dataset NAME` goes before the command) |
| `soilsignal_ml/ingest/` | Dataset adapters (`PublicDatasetAdapter` = Shrestha et al. 2024, `shrestha2024`; `HackathonDatasetAdapter` = the challenge data, `sydag26`), canonical tables, remote-zip streaming, public context, data checks, profiler |
| `soilsignal_ml/ingest/challenge*.py`, `imagery.py` | Challenge dataset: ground truth + acquisition dates + image manifests on one plot key (`challenge.py`), GeoTIFF/PNG metadata (`imagery.py`), outputs and `challenge_manifest.json` (`challenge_report.py`), Postgres/PostGIS export (`challenge_postgres.py`). The canonical adapter is `HackathonDatasetAdapter` in `dataset_adapter.py` |
| `soilsignal_ml/features/build.py` | Training tables from `backend/app/features` |
| `soilsignal_ml/validation/splits.py` | Grouped splits (plot, field, site, year) and the held-out site, with overlap checks |
| `soilsignal_ml/models/` | Mean, Ridge, Random Forest, HistGradientBoosting, CatBoost; `train.py` runs screening, tuning, selection, held-out scoring |
| `soilsignal_ml/evaluation/` | Metrics, intervals, drivers, sensitivity checks, report |
| `soilsignal_ml/progressive/` | Early-signal experiments: stages (TP / days after planting / date), grouped validation incl. 2022 → 2023, nested conformal + CQR intervals, scouting recall, "earliest useful" checks, `imagery_ablation.json`. Entry point `progressive_experiment.py`; config `configs/progressive.yaml` |
| `soilsignal_ml/export/export_to_backend.py` | Writes `backend/artifacts/` with `save_artifact()` |
| `soilsignal_ml/export/showcase.py` | Writes the showcase bundle for the held-out plots, with 1991–2020 rain normals and a 10-year GDD pace from NOAA |
| `soilsignal_ml/imagery/` | Challenge imagery -> progressive features: TIFF masking and band/index statistics, records_only/TP1..TP6 table with temporal and site-relative features, UAV RGB features by flight date, quality flags and report, visual QA. CLI: `python -m soilsignal_ml.imagery` (`run`, `benchmark`, `dictionary`, `synthetic`). Handoff: `ml/AGENT2_HANDOFF.md` |
| `configs/` | `project.yaml` (held-out site, seed, trials) and one file per cutoff (`may` … `full`) |
| `research/` | `agronomy_thresholds.md`/`.yaml` (sourced thresholds), `model_benchmarks.md` (published results), `weather_outlook.md` (weather outlook method, data, backtest, limitations) |
| `experiments/` | `results.csv` + `runs/` (every evaluated model), `reports/` (dataset profile, model report), `progressive/` (early-signal runs; `_template_synthetic/` shows the format and is not a result) |
| `soilsignal_ml/weather_outlook/`, `weather_outlook.py` | Weather outlook research: `history.py` (NOAA/IEM download, observation-time alignment, gap handling, neighbour QC, publish), `backtest.py` + `report.py` (leave-one-season-out), `cli.py`. Config `configs/weather_outlook.yaml`; outputs `experiments/weather_outlook/` (`data_qc.md`, `<library>/backtest.md`, `summary.csv`, `cases.csv`, `figures/`, `examples/`) |
| `notebooks/explore_dataset.ipynb` | Exploration of the canonical dataset |
| `tests/` | Data checks, leakage, splits, models + artifact round trip, research ↔ code |
| `data/` | Git-ignored datasets (`processed/` canonical tables, `interim/` feature tables, `raw/challenge/` the organizers' folder), except `data/challenge/*.parquet` + `challenge_manifest.json` (compact challenge tables, committed) |



---

## Contracts that must stay in sync

| If you change… | Also change… | Guard |
|----------------|--------------|-------|
| `src/types/agricultural.ts` | `backend/app/schemas.py` | `test_forecast_matches_frontend_mock_exactly` |
| Decision / evaluation types (`PlotDecision`, `DecisionSet`, `ModelInfo`, `ImageryAblation`) | `backend/app/schemas.py`, `src/services/decisions.ts` (demo assembly mirrors `MockForecastProvider.get_decisions`) | `test_decisions_*`, `test_imagery_comparison_*` |
| `src/mock/fieldsData.ts` | Run `npm run export:mock` | Same test |
| A field's coordinates or dates | Run `cd backend && uv run python -m scripts.snapshot_context` | `npm run lint` type-checks the snapshot |
| Context types in `src/types/agricultural.ts` | `backend/app/schemas.py` (location context section) | `test_context.py` |
| Model artifact format | `backend/app/model/contract.py` only | `test_model.py`, `ml/tests/test_models.py` |
| ML library versions | `backend/uv.lock` (train with the same versions; the ML pipeline runs in the backend's environment) | Artifact fails to load |
| A threshold in `backend/app/features/thresholds.py` | `ml/research/agronomy_thresholds.yaml` and `.md` | `ml/tests/test_research.py` |
| A new feature in `backend/app/features/` | Its entry in `app/features/catalog.py`; retrain and re-export | `test_every_built_feature_is_described_in_the_catalog` |
| Driver categories (`FeatureImportanceItem.category`) | `src/types/agricultural.ts`, `backend/app/schemas.py`, `app/model/contract.py` | — |
| Source roles, `SpatialContext.description`/`provenance`, optional `ForecastSnapshot.spatial` | `src/types/agricultural.ts` ↔ `backend/app/schemas.py`; `DataSources.tsx`, `DataBadge.tsx` | `test_forecast.py` |
| Forecast cutoffs (`ml/configs/*.yaml`) | Re-export models and re-run `showcase` (the bundle's dates) | `ml/tests/test_end_to_end.py` |
| Weather outlook contract (`app/weather_outlook/contract.py`) | bump `CONTRACT_VERSION`; this file | `backend/tests/test_weather_outlook.py` |
| `ml/configs/weather_outlook.yaml` (stations, QC, per-site weighting) | Re-run `weather_outlook history` (republishes the libraries) and the backtest | `ml/tests/test_weather_outlook.py` |
| Final-results contract (`backend/app/results.py`) | `src/types/results.ts`, `docs/FINAL_RESULTS_CONTRACT.md` | `test_results_sites.py` |
| Trial-site models (`backend/app/sites.py`) or the challenge inventory | `src/types/sites.ts`; rerun `scripts/export_trial_sites.py` | `test_sites_come_from_the_inventory_with_honest_imagery_flags` |
| Weather outlook JSON shape | `src/services/weatherOutlook.ts` (the only reader of the raw shape) | — |
| An endpoint | `src/services/*.ts`, this file | — |

---

## Configuration

| Variable | Where | Default | Effect |
|----------|-------|---------|--------|
| `VITE_DEMO_MODE` | Frontend build (compose arg) | `false` in compose/Docker; unset (`npm run dev`) means demo | `false` = fetch from `/api` instead of mocks |
| `VITE_API_BASE_URL` | Frontend build | `/api` | API location |
| `API_PROXY_TARGET` | Vite dev server | `http://localhost:8000` | Where `/api` goes in local dev |
| `SOILSIGNAL_MODEL_DIR` | Backend | `backend/artifacts` | Where models are loaded from |
| `SOILSIGNAL_DATA_SOURCE` | Backend (compose passes it) | `model` | `model` = forecasts from models + practice bundles; `mock` = demo data. No fallback between them |
| `SOILSIGNAL_PRACTICE_DATA_DIR` | Backend | `backend/data/practice` | Showcase bundles (`*.json`) |
| `SOILSIGNAL_MOCK_DATA_PATH` | Backend | `backend/data/mock/fields.json` | Mock forecast source (`SOILSIGNAL_DATA_SOURCE=mock`) |
| `SOILSIGNAL_NASS_API_KEY` | Backend (compose passes it through) | unset | Enables county yields from USDA NASS |
| `SOILSIGNAL_CACHE_DIR` | Backend | `backend/cache` | Public-data cache |
| `SOILSIGNAL_CONTEXT_TIMEOUT_SECONDS` | Backend | `20` | Timeout for USDA / NOAA requests |
| `SOILSIGNAL_SEASON_START` | Backend | `05-01` | Season totals (degree days, heat days, dry spells) count from this date |
| `SOILSIGNAL_WEATHER_HISTORY_DIR` | Backend | `backend/data/weather_history` | Weather outlook libraries |
| `SOILSIGNAL_WEATHER_OUTLOOK_LIBRARY` | Backend | `long` | Library `/api/weather-outlook` uses when the request names none |
| `SOILSIGNAL_SITES_FILE` | Backend | `backend/data/trial_sites.json` | Trial-site registry for `/api/sites` |

---

## Local development

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000   # model-backed
VITE_DEMO_MODE=false npm run dev          # dashboard against the local API
SOILSIGNAL_DATA_SOURCE=mock uv run uvicorn app.main:app --port 8000        # API on demo data
cd backend && uv run pytest               # backend tests
cd ml && uv run --project ../backend --group ml pytest   # ML tests
npm run lint && npm run build             # frontend checks
```
