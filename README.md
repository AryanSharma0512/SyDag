# SoilSignal

**Know the season before harvest.**

SoilSignal uses satellite imagery, field records and weather history to estimate final maize yield during the growing season. It is being built for the SyDAg26 IoT4Ag Hackathon at Purdue University.

## What it answers

The product is one number: **the final yield forecast** for a maize plot, in bu/ac, with a prediction range, updated through the season. Four questions support it:

- **How early can we know?** Validation error (MAE in bu/ac, with R² alongside) by days after planting, and the earliest point where the forecast is useful.
- **When will the crop likely mature?** Growing degree days since planting and an estimated physiological-maturity window.
- **What weather outcomes are plausible?** A historical weather outlook: what the next 30, 60 or 90 days (or the rest of the season) brought in past seasons at the same station. It is not a weather forecast, and it is kept separate from the yield forecast until the yield model uses future-weather features.
- **Is an extra UAV pass worth it?** Satellite-only vs satellite + UAV validation error from a matched experiment. Satellite is the base layer; UAV is optional.

Each forecast uses only the data that would have been available on its date. There is no "confidence %": error is reported as validation MAE in bu/ac, and R² is never presented as accuracy.

## Current prototype

This repository holds the front end and the backend API (`backend/`). By default the front end runs entirely on local demo data and needs no API keys or external services.

| Route | What it shows |
| --- | --- |
| `/` | Overview: the headline, the U.S. trial-site map (each site's data, from `/api/sites`), what SoilSignal answers, and a preview of one plot's season |
| `/dashboard` | Location → season → plot, then in order: **final yield forecast** (bu/ac, prediction range, days after planting, typical validation error); how the forecast developed; how early can we know; historical weather outlook (`/api/weather-outlook`, 30d / 60d / 90d / season); crop development (GDD, maturity window); satellite vs UAV. Everything else (model drivers, crop observations, every plot at this date, hybrid table, deployed-model validation, NOAA and USDA context, provenance) is under **More detail** |
| `/methodology` | The pipeline (TIFFs → plot mask → features → + records and weather → model → yield), satellite processing, validation by days after planting, what R² and MAE mean, prediction ranges, the weather outlook method, GDD and maturity, satellite vs UAV, leakage safeguards, data sources |
| `/data` | The trial data by location (satellite, weather, field records, UAV) and the public context for one plot (NOAA weather, NASS county yields, SSURGO soil) with live source status, tables and CSV downloads |
| `/about` | The team |

Useful flags and shortcuts:

- `?presentation=true` (or press `F`) is for a TV during the pitch: large type, no debug controls, tables or "More detail"; the forecast, timeline, weather outlook, maturity and UAV comparison stay.
- `?debug=true` adds a small diagnostics button with a location switcher and loading, missing-satellite and weather-error states.
- `?site=Ames&plot=...` opens the dashboard on a location and plot (the dashboard keeps the URL in step).
- On the dashboard, `←` / `→` move through forecast dates. In presentation or debug mode, `1`–`9` switch location and `R` resets.

Motion respects `prefers-reduced-motion`: entrance sequences render their final state immediately and route transitions drop their movement.

## Architecture

```
Frontend (React + Vite)
   ↓  normalized responses
Backend API (backend/, FastAPI): trial sites, final results, live forecasts, weather outlook, model evaluation, public context
   ↓
Model artifacts (backend/artifacts/, exported by ml/) and NOAA / USDA services
```

Components never fetch weather, soil, satellite or model data directly. They call the functions in `src/services/`, which return the typed shapes in `src/types/`. In demo mode (the default) those services resolve demo data from `src/mock/`; built with `VITE_DEMO_MODE=false`, they call the backend API instead, with no component changes. The backend's response models (`backend/app/schemas.py`) mirror `src/types/agricultural.ts`, and a backend test fails if the two drift apart.

Stack: React 19, TypeScript, Vite, Tailwind CSS 4, and Motion. Charts, the logo and all illustrations are hand-built SVG. Inter and Geist Mono are self-hosted through Fontsource, so the site makes no third-party requests.

## Local development

Requires Node.js 20.19+ or 22.12+ (the Docker build uses Node 22).

```bash
npm install
npm run dev      # http://localhost:3000
npm run lint     # type-check with tsc
```

npm is the package manager for production: the Docker build runs `npm ci` against `package-lock.json`. After changing `src/mock/fieldsData.ts`, run `npm run export:mock` to refresh the backend's copy of the demo data.

To run the dashboard against the local API (needs [uv](https://docs.astral.sh/uv/)):

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
VITE_DEMO_MODE=false npm run dev    # Vite forwards /api to localhost:8000
```

See `backend/README.md` for the API, tests and model artifacts, and `STRUCTURE.md` for the full repository map.

## Production build

```bash
npm run build    # outputs static files to dist/
npm run preview  # serve the production build locally
```

Production runs at [sydag.aboutsharma.com](https://sydag.aboutsharma.com) as two containers from `compose.sydag.yml`: the front end as static files behind Nginx (`Dockerfile.sydag`, `nginx.sydag.conf`) and the API (`backend/Dockerfile`), with the reverse proxy sending `/api/*` to the API. Nginx falls back to `index.html`, so `/`, `/dashboard`, `/data`, `/methodology` and `/about` all load directly.

```bash
docker compose -f compose.sydag.yml up -d --build
```

## Project structure

```
src/
├── components/
│   ├── brand/          SoilSignal mark, static lockup, animated logo
│   ├── common/         Navigation, footer, page transitions, badges, shared controls
│   ├── overview/       Overview page, hero animation, trial-site map (usMap.ts: generated state outlines), forecast preview, what it answers
│   ├── dashboard/      Farmer view (location bar, yield forecast, timeline, how early, weather outlook, crop development, satellite vs UAV) and the "More detail" sections (drivers, crop observations, scouting queue, hybrids, reliability, imagery comparison, context, provenance)
│   ├── results/        Validation-by-DAP chart and table, shared by the dashboard and Methodology
│   ├── data/           Data page: trial data by location; public context panels, tables, CSV downloads
│   ├── methodology/    Methodology page, pipeline diagram, uncertainty demo
│   ├── about/          About page and team
│   └── debug/          Diagnostics panel (only with ?debug=true)
├── config/             App configuration and team
├── mock/               Demo data for five fields
├── services/           Data access boundary (sites, final results, plot forecasts, weather outlook, fields, forecasts, decisions, evaluation, context, sources)
├── types/              Front-end data contract
├── utils/              Chart geometry, motion constants, formatting, hooks, routing
└── App.tsx             Routes, presentation and debug flags
public/                 Favicon, touch icon and social preview image
backend/                FastAPI service: forecasts, model predictions, tests
scripts/                export-mock-data.ts (npm run export:mock), build-us-map.mjs (regenerates the map outlines)
```

## Data strategy

The trial data is the primary input: six-band satellite imagery per plot plus the field record (planting date, nitrogen rate, irrigation, hybrid, site and season). Satellite plot images exist at Ames, Crawfordsville and Lincoln; UAV images at Ames only; Missouri Valley and Scottsbluff have field records but no plot imagery (`backend/data/trial_sites.json`, from the challenge inventory). Weather history for the outlook is 27–31 quality-checked seasons per site from NOAA GHCN-Daily.

| Source | Purpose | Status |
| --- | --- | --- |
| Shrestha et al. (2024) multistate maize trials | Satellite imagery, field records and yields for the deployed practice models | Deployed ("Practice data") |
| IoT4Ag challenge data | Satellite and UAV imagery and field records for the final models | Final results arrive as `backend/artifacts/final_results.json` |
| NOAA GHCN-Daily (long record per site) | Historical weather outlook | Deployed (`backend/data/weather_history/`) |
| NOAA NCEI (daily station observations) | Weather context | Connected |
| USDA NRCS SSURGO | Soil context | Connected |
| USDA NASS Quick Stats | County yield history | Connected |

The navigation badge shows the backend's own label for the data behind the forecasts: the published final results' `dataset_label` once they exist, otherwise `datasetLabel` from `/api/health` ("Practice data" today). The frontend never hardcodes it.

### Handing results to the website (ML team)

The website reads a **frozen, versioned results file** instead of re-running training: `backend/artifacts/final_results.json`, built from the ML team's 2022 temporal run by `cd backend && uv run python -m scripts.build_final_results` (inputs in `ml/experiments/temporal_final_2022/`) (contract and example in `backend/app/results.py`, walkthrough in `docs/FINAL_RESULTS_CONTRACT.md`). It carries the model and validation strategy, R² / MAE / RMSE by days after planting, the earliest useful DAP, per-site and per-plot forecasts, GDD / maturity estimates, and the matched satellite-only vs satellite + UAV comparison. Check it with `cd backend && uv run python -m app.results path/to/final_results.json`, copy it into `backend/artifacts/` and it is served on the next request. Until it exists, every section it feeds says it is waiting; nothing is estimated in its place.

Also picked up with no frontend change: new model artifacts (the live forecasts and the deployed-model validation), a new showcase bundle, and `backend/artifacts/imagery_ablation.json`. To draw an agreed error threshold on the deployed-model chart, set `acceptableMaeBuAc` in `src/config/appConfig.ts`.

## Team

- **Aryan Sharma**, B.S. Agriculture
- **Sahil Jain**, B.S. Computer Science
- **Shashwat Goel**, B.S. Computer Science
- **Sri Madur**
- **Sidney Millen**
