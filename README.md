# SoilSignal

**See the season before harvest.**

SoilSignal estimates end-of-season maize yield for each trial plot from satellite imagery and field records, early enough for an agronomy team to decide where to send limited scouting crews. It is being built for the SyDAg26 IoT4Ag Hackathon at Purdue University.

## What it answers

- **Which plots deserve a scouting visit?** The dashboard's "Plots to review" table sorts every plot by forecast range, predicted yield or change since the previous forecast. There is no composite risk score.
- **Which hybrids are on track?** Mean forecast, plot spread and range per hybrid, shown once enough hybrids have enough plots to compare.
- **How much did satellite imagery improve the prediction?** Validation error with and without imagery, once the ML team publishes the comparison.
- **How early does the model become useful?** Validation error of the model behind each forecast date, from `GET /api/models`.

Every forecast carries a 90% range, and each one uses only the imagery and records available by its date. NOAA weather and USDA soil and county yields are shown as context.

## Current prototype

This repository holds the front end and the backend API (`backend/`). By default the front end runs entirely on local demo data and needs no API keys or external services.

| Route | What it shows |
| --- | --- |
| `/` | Overview: what SoilSignal answers, the challenge scope, and a preview of one plot's season |
| `/dashboard` | In order: the plot's trial record (hybrid, N rate, site); its forecast, 90% range, confidence and change since the previous forecast; **Plots to review** (every plot at the selected date); the forecast through the satellite passes with the acquisition strip; crop development and the neighbouring-plot map; the drivers of this forecast; hybrid performance; model reliability (validation error by forecast date, and what imagery adds); NOAA and USDA context; data provenance |
| `/data` | Data Explorer: the NOAA and USDA data behind each plot (NCEI weather, SSURGO soil, NASS county yields) with live source status, observed vs. derived values, retrieval times, tables and CSV downloads |
| `/methodology` | How the forecasts are built: pipeline, accuracy by imagery stage, an interactive range example, and data sources |
| `/about` | The team |

Useful flags and shortcuts:

- `?presentation=true` (or press `F`) enlarges the key metrics and chart and reduces navigation for demos.
- `?debug=true` adds a small diagnostics button with a scenario switcher and loading, missing-satellite and weather-error states.
- On the dashboard, `←` / `→` move through forecast dates; the scouting queue follows. In presentation or debug mode, `1`–`5` switch between the featured plots and `R` resets.

Motion respects `prefers-reduced-motion`: entrance sequences render their final state immediately and route transitions drop their movement.

## Architecture

```
Frontend (React + Vite)
   ↓  normalized responses
Backend API (backend/, FastAPI): forecasts, the scouting queue, model evaluation, public context
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
│   ├── overview/       Overview page, hero animation, forecast preview, the challenge questions
│   ├── dashboard/      Dashboard sections (summary, scouting queue, timeline and pass strip, crop, spatial, drivers, hybrids, reliability, imagery comparison, context, provenance)
│   ├── data/           Data Explorer: source status, weather / soil / yield panels, tables, CSV downloads
│   ├── methodology/    Methodology page, pipeline animation, uncertainty demo
│   ├── about/          About page and team
│   └── debug/          Diagnostics panel (only with ?debug=true)
├── config/             App configuration and team
├── mock/               Demo data for five fields
├── services/           Data access boundary (fields, forecasts, decisions, evaluation, weather, soil, sources)
├── types/              Front-end data contract
├── utils/              Chart geometry, motion constants, formatting, hooks, routing
└── App.tsx             Routes, presentation and debug flags
public/                 Favicon, touch icon and social preview image
backend/                FastAPI service: forecasts, model predictions, tests
scripts/                export-mock-data.ts (npm run export:mock)
```

## Data strategy

The trial data is the primary input: six-band satellite imagery per plot plus the field record (planting date, nitrogen rate, irrigation, hybrid, site and season). Around it, the backend looks up public data for each plot's coordinates, and the dashboard shows it with its source and retrieval date.

| Source | Purpose | Status |
| --- | --- | --- |
| Shrestha et al. (2024) multistate maize trials | Satellite imagery, field records and yields for training and the deployed forecasts | Deployed ("Practice data") |
| IoT4Ag challenge data | Satellite imagery and field records for the challenge models | Adapter and models in progress (`ml/`) |
| NOAA NCEI (daily station observations) | Weather | Connected |
| USDA NRCS SSURGO | Soil | Connected |
| USDA NASS Quick Stats | County yield history | Connected |

The navigation badge shows the backend's own label for the data behind the forecasts (`datasetLabel` from `/api/health`): "Practice data" today. It changes when the ML team deploys models and bundles for the challenge data; the frontend never hardcodes it.

For the ML team, three things update the dashboard with no frontend change: new model artifacts (the reliability chart and every forecast), a new showcase bundle (the plots in the scouting queue and hybrid table), and `backend/artifacts/imagery_ablation.json` (the imagery comparison; format in `backend/app/forecast/evaluation.py`). To draw an agreed error threshold on the reliability chart, set `acceptableMaeBuAc` in `src/config/appConfig.ts`.

## Team

- **Aryan Sharma**, B.S. Agriculture
- **Sahil Jain**, B.S. Computer Science
- **Shashwat Goel**, B.S. Computer Science
- **Sri Madur**
- **Sidney Millen**
