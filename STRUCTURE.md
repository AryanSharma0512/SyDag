# SoilSignal: Project Structure & Data-Day Map

What exists, where it lives, and what to run or call once the challenge dataset
arrives. **Keep this file updated in the same PR as any structural change.**

Last updated: 2026-09-24

---

## How a request flows

```
Browser ──► sydag.aboutsharma.com (Cloudflare → Aryan's reverse proxy)
              ├── /*      → sydag_frontend  (nginx serving the Vite build)
              └── /api/*  → sydag_backend   (FastAPI, port 8000)
                              ├── forecasts  ← ForecastProvider  (mock data today)
                              ├── predictions ← ModelRegistry    (backend/artifacts/)
                              └── /api/context/* ← USDA SSURGO, NOAA NCEI, USDA NASS
                                                   (fetched by the backend, cached in backend/cache/)
```

---

## Data-day playbook

In order. **Ready** = built and tested. **Not built** = still to do.

| # | Step | What to run / call / edit | Status |
|---|------|---------------------------|--------|
| 1 | Profile the dataset | `ml/` profiler | Not built (ML starter kit) |
| 2 | Features + leak-free validation + training | `ml/` | Not built (ML starter kit) |
| 3 | Export each trained model | `save_artifact(estimator, metadata, schema, root)` in `backend/app/model/export.py`. One model per season cutoff (`as_of: "MM-DD"`). Pattern to copy: `backend/scripts/make_dummy_model.py` | Ready |
| 4 | Add any new model library to the backend | `cd backend && uv add lightgbm` (or xgboost/catboost), commit `uv.lock`, rebuild the image | Ready |
| 5 | Test the model locally | `cd backend && uv run uvicorn app.main:app --port 8000`, then `GET /api/models` and `POST /api/predict` | Ready |
| 6 | Deploy the model | Copy `backend/artifacts/<model_id>/` to the server, then `docker compose -f compose.sydag.yml restart backend`. Check `/api/health` shows `modelsLoaded > 0` | Ready |
| 7 | Get predictions | `POST /api/predict` with `features` + `asOfDate` | Ready |
| 8 | Show real forecasts in the dashboard | Model-backed `ForecastProvider` in `backend/app/providers.py`; likely contract changes (see "Contracts") | Not built (needs dataset shape) |
| 9 | Switch the live site off mock data | Build frontend with `VITE_DEMO_MODE=false` (compose build arg) | Ready (needs `/api` proxy rule live) |
| 10 | Remove the dummy models | Delete `backend/artifacts/dummy-*` locally and on the server | — |
| 11 | Public data for the real fields | Give each field its real `latitude`/`longitude`; soil, observed weather and county yields load automatically through `/api/context/all`. Regenerate the demo snapshot with `cd backend && uv run python -m scripts.snapshot_context` | Ready |
| 12 | County yield history | Locally the key is in `backend/.env` (git-ignored). On the server, put `SOILSIGNAL_NASS_API_KEY=...` in a `.env` next to `compose.sydag.yml` and restart the backend. **Never commit the key: the repo is public** | Ready (add the key on the server) |

---

## API reference

Base path `/api`. Interactive docs at `/api/docs`. JSON is camelCase.

| Method | Endpoint | Called by / when | Returns |
|--------|----------|------------------|---------|
| GET | `/api/health` | Deploy checks, Docker healthcheck | `status`, `version`, `dataSource`, `modelsLoaded` |
| GET | `/api/fields` | Frontend `getFields()` | `FieldMeta[]` |
| GET | `/api/fields/{id}` | Frontend `getFieldById()` | `FieldMeta` |
| GET | `/api/fields/{id}/forecast` | Dashboard on load and on field switch (`getForecast()`) | `FieldForecast`: all snapshots, vegetation, events, history, sources |
| GET | `/api/fields/{id}/weather?snapshotId=` | Frontend `getWeatherContext()` | `WeatherContext` (latest snapshot by default) |
| GET | `/api/fields/{id}/soil` | Frontend `getSoilContext()` | `SoilContext` |
| GET | `/api/models` | After deploying a model, to confirm it loaded | id, metrics, validation, `asOf`, feature list |
| POST | `/api/predict` | **Prediction on real data.** Body: `{"features": {...}, "asOfDate": "YYYY-MM-DD"}` or `"modelId"` | `yield`, `lowerBound`, `upperBound`, `intervalLevel`, `confidence`, `confidenceRating`, `drivers` |
| GET | `/api/context/all?lat=&lon=&date=` | Dashboard once per field (`getLocationContext()`), with `date` repeated for every forecast date | `LocationContext`: `county`, and `soil` / `weather` / `yieldHistory` parts, each with its own `status` (`ok`, `unavailable`, `not_configured`) |
| GET | `/api/context/soil?lat=&lon=` | Soil for one point | `SoilProfile` from USDA NRCS SSURGO |
| GET | `/api/context/weather?lat=&lon=&date=` | Observed weather as of a date | `ObservedWeather`: nearest NOAA station, rainfall, growing degree days, heat days, dry spells |
| GET | `/api/context/yield-history?lat=&lon=&throughYear=` | County corn yields | `YieldHistory` from USDA NASS (needs `SOILSIGNAL_NASS_API_KEY`) |

Data provenance (`getDataSources()` in `src/services/sources.ts`) has no endpoint yet: it
always returns the list in `src/mock/fieldsData.ts`, in both modes.

Context sources are cached on disk (soil forever, county yields 14 days, weather 6 hours
while recent and 30 days once settled). If a source is down, the last good copy is served.

Errors: `404` unknown field/model/snapshot, or no model valid by `asOfDate`;
`422` bad prediction input (lists every problem); `503` no model artifacts loaded
or one failed to load (forecast endpoints keep working).

---

## Repository map

### Deployment (root)

| Path | Purpose |
|------|---------|
| `compose.sydag.yml` | Runs `sydag_frontend` (host `127.0.0.1:8188`) and `sydag_backend` (`127.0.0.1:8189`) on `lostnfound_network`; mounts `backend/artifacts` read-only |
| `Dockerfile.sydag` | Frontend image: `npm ci` + Vite build → nginx. Build arg `VITE_DEMO_MODE` |
| `nginx.sydag.conf` | Frontend nginx: SPA fallback, asset caching |
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
| `app/providers.py` | `ForecastProvider` protocol + `MockForecastProvider`; `get_registry()` loads models |
| `app/config.py` | Settings (`SOILSIGNAL_*` env vars) |
| `app/model/contract.py` | Model artifact format: `ModelMetadata`, `FeatureSchema` |
| `app/model/artifact.py` | Loads and checks artifacts, validates inputs, predicts; `ModelRegistry.for_date()` picks the point-in-time model |
| `app/model/export.py` | `save_artifact()`: the only way the ML side should write models |
| `app/context_routes.py` | `/api/context/*` endpoints |
| `app/context/service.py` | Runs the public-data sources in parallel with caching; each fails independently |
| `app/context/soil.py`, `weather.py`, `yield_history.py`, `geo.py` | One module per source: USDA Soil Data Access, NOAA NCEI, USDA NASS Quick Stats, FCC county lookup |
| `app/context/cache.py` | Disk cache with per-source lifetimes; serves the last good copy when a source is down |
| `cache/` | Cached public data (git-ignored; a named Docker volume in production) |
| `artifacts/<model_id>/` | Deployed models (`model.joblib`, `metadata.json`, `feature_schema.json`); `dummy-*` is git-ignored |
| `data/mock/fields.json` | Mock forecasts, generated from `src/mock/fieldsData.ts` |
| `scripts/make_dummy_model.py` | Trains 3 synthetic cutoff models; export reference |
| `scripts/snapshot_context.py` | Fetches public data for every demo field; writes `src/mock/contextSnapshot.ts` and warms the cache |
| `tests/` | `test_api.py` (endpoints + contract), `test_model.py` (artifacts, predict, point-in-time), `test_context.py` (public data, replayed offline from `tests/fixtures/context/`) |
| `Dockerfile` | Python 3.13 + uv, frozen lockfile, non-root, healthcheck |
| `pyproject.toml` / `uv.lock` | Pinned deps. **Models must be trained with these versions** |
| `README.md` | Backend details: running, testing, artifact format |

### Frontend (`src/`)

| Path | Purpose |
|------|---------|
| `types/agricultural.ts` | Frontend data contract (`FieldForecast` and friends) |
| `services/*.ts` | The only code that fetches data: demo data in demo mode, `/api` otherwise |
| `services/sources.ts` | Data provenance list (demo data in both modes; no endpoint yet) |
| `services/context.ts` | `getLocationContext()`: public soil, weather and county yields for a field |
| `services/apiClient.ts` | `apiGet()` JSON client |
| `config/appConfig.ts` | Branding, event, team, `demoMode`, `apiBaseUrl`, defaults |
| `mock/fieldsData.ts` | 5 demo fields and `DATA_SOURCES` (source of `backend/data/mock/fields.json`). Coordinates are real farmland whose SSURGO soil matches each field; yields are scaled to each county's real NASS five-year average |
| `mock/contextSnapshot.ts` | Generated snapshot of the public data for the demo fields, used in demo mode |
| `App.tsx` | Page shell: route transitions, presentation (`?presentation=true`, `F`) and debug (`?debug=true`) flags |
| `utils/router.tsx` | Client-side routes: `/` overview, `/dashboard`, `/methodology`, `/about` |
| `components/dashboard/DashboardView.tsx` | Dashboard state: fields, selected field, active date, field-switch transition, shortcuts |
| `components/dashboard/*` | One component per dashboard section; hand-built SVG charts |
| `components/overview/`, `components/methodology/`, `components/about/` | The other three pages |
| `components/brand/` | SoilSignal mark, lockup and animated logo |
| `components/common/` | Navigation, footer, page transitions, animated numbers, shared controls |
| `components/debug/DebugPanel.tsx` | Scenario switcher and simulated loading/error states (`?debug=true`) |
| `utils/` | Chart geometry, motion timings, palette, formatting, hooks |

`public/` holds the favicon, touch icon and social preview image.

### Tooling

| Path | Purpose |
|------|---------|
| `scripts/export-mock-data.ts` | `npm run export:mock` → regenerates `backend/data/mock/fields.json` |
| `vite.config.ts` | Dev server; proxies `/api` to `localhost:8000` |

### Not built yet

| Path | Purpose |
|------|---------|
| `ml/` | ML starter kit: profiler, splits, baselines, features, experiment log |

---

## Contracts that must stay in sync

| If you change… | Also change… | Guard |
|----------------|--------------|-------|
| `src/types/agricultural.ts` | `backend/app/schemas.py` | `test_forecast_matches_frontend_mock_exactly` |
| `src/mock/fieldsData.ts` | Run `npm run export:mock` | Same test |
| A field's coordinates or dates | Run `cd backend && uv run python -m scripts.snapshot_context` | `npm run lint` type-checks the snapshot |
| Context types in `src/types/agricultural.ts` | `backend/app/schemas.py` (location context section) | `test_context.py` |
| Model artifact format | `backend/app/model/contract.py` only | `test_model.py` |
| ML library versions | `backend/uv.lock` (train with the same versions) | Artifact fails to load |
| An endpoint | `src/services/*.ts`, this file | — |

---

## Configuration

| Variable | Where | Default | Effect |
|----------|-------|---------|--------|
| `VITE_DEMO_MODE` | Frontend build (compose arg) | `true` | `false` = fetch from `/api` instead of mocks |
| `VITE_API_BASE_URL` | Frontend build | `/api` | API location |
| `API_PROXY_TARGET` | Vite dev server | `http://localhost:8000` | Where `/api` goes in local dev |
| `SOILSIGNAL_MODEL_DIR` | Backend | `backend/artifacts` | Where models are loaded from |
| `SOILSIGNAL_MOCK_DATA_PATH` | Backend | `backend/data/mock/fields.json` | Mock forecast source |
| `SOILSIGNAL_NASS_API_KEY` | Backend (compose passes it through) | unset | Enables county yields from USDA NASS |
| `SOILSIGNAL_CACHE_DIR` | Backend | `backend/cache` | Public-data cache |
| `SOILSIGNAL_CONTEXT_TIMEOUT_SECONDS` | Backend | `20` | Timeout for USDA / NOAA requests |
| `SOILSIGNAL_SEASON_START` | Backend | `05-01` | Season totals (degree days, heat days, dry spells) count from this date |

---

## Local development

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
VITE_DEMO_MODE=false npm run dev          # dashboard against the local API
cd backend && uv run pytest               # backend tests
npm run lint && npm run build             # frontend checks
```
