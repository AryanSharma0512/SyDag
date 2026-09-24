# SoilSignal

**See the season before harvest.**

SoilSignal is a progressive crop yield forecasting interface. It turns crop observations and environmental context into yield forecasts that update through the growing season, with a prediction range that says how certain each forecast is and plain-language drivers that say what is shaping it.

It is being developed for the SyDAg26 IoT4Ag Hackathon at Purdue University.

## What it is

- **Progressive.** Forecasts evolve as the season develops, from emergence to maturity.
- **Uncertain, not opaque.** Every forecast carries a 90% prediction range that is wide early in the season and narrows as evidence accumulates.
- **Context-aware.** Crop observations are read alongside weather, soil, and historical context.

## Current prototype

This repository is the front end. It runs entirely on local demo data and needs no API keys or external services.

| Route | What it shows |
| --- | --- |
| `/` | Overview with the animated field-to-forecast story |
| `/dashboard` | Forecast dashboard: predicted yield, range and confidence, a scrubbable season timeline, growth stages, crop development (NDVI / NDRE), weather and soil context, an illustrative spatial layer, forecast drivers, historical context and data provenance |
| `/methodology` | How SoilSignal works: pipeline, seasonal forecasting, an interactive uncertainty example, and data sources |
| `/about` | The team |

Useful flags and shortcuts:

- `?presentation=true` (or press `F`) enlarges the key metrics and chart and reduces navigation for demos.
- `?debug=true` adds a small diagnostics button with a scenario switcher and loading, missing-satellite and weather-error states.
- On the dashboard, `←` / `→` move through forecast dates. In presentation or debug mode, `1`–`5` switch fields and `R` resets.

Motion respects `prefers-reduced-motion`: entrance sequences render their final state immediately and route transitions drop their movement.

## Architecture

```
Frontend (this repo, React + Vite)
   ↓  normalized responses
Backend API (planned)
   ↓
ML and context services (planned)
```

Components never fetch weather, soil, satellite or model data directly. They call the functions in `src/services/`, which return the typed shapes in `src/types/`. Today those services resolve demo data from `src/mock/`; later they will call the backend API without any component changes.

Stack: React 19, TypeScript, Vite, Tailwind CSS 4, and Motion. Charts, the logo and all illustrations are hand-built SVG. Inter and Geist Mono are self-hosted through Fontsource, so the site makes no third-party requests.

## Local development

Requires Node.js 20.19+ or 22.12+ (the Docker build uses Node 22).

```bash
npm install
npm run dev      # http://localhost:3000
npm run lint     # type-check with tsc
```

## Production build

```bash
npm run build    # outputs static files to dist/
npm run preview  # serve the production build locally
```

Production runs as static files behind Nginx (`Dockerfile.sydag`, `nginx.sydag.conf`, `compose.sydag.yml`) at [sydag.aboutsharma.com](https://sydag.aboutsharma.com). Nginx falls back to `index.html`, so `/`, `/dashboard`, `/methodology` and `/about` all load directly.

```bash
docker compose -f compose.sydag.yml up -d --build
```

## Project structure

```
src/
├── components/
│   ├── brand/          SoilSignal mark, static lockup, animated logo
│   ├── common/         Navigation, footer, page transitions, badges, shared controls
│   ├── overview/       Overview page, hero system animation, forecast preview, principles
│   ├── dashboard/      Dashboard sections (summary, timeline, stages, crop, environment, spatial, drivers, history, provenance)
│   ├── methodology/    Methodology page, pipeline animation, uncertainty demo
│   ├── about/          About page and team
│   └── debug/          Diagnostics panel (only with ?debug=true)
├── config/             App configuration and team
├── mock/               Demo data for five fields
├── services/           Data access boundary (fields, forecasts, weather, soil, sources)
├── types/              Front-end data contract
├── utils/              Chart geometry, motion constants, formatting, hooks, routing
└── App.tsx             Routes, presentation and debug flags
public/                 Favicon, touch icon and social preview image
```

## Data strategy

The competition dataset is the primary input. External sources are listed as candidates only. None are connected yet, and the challenge rules and the actual dataset will determine the final integrations.

| Source | Purpose | Status |
| --- | --- | --- |
| Hackathon data | Crop observations | Challenge-provided |
| PRISM / NOAA | Weather | Candidate |
| USDA SSURGO | Soil | Candidate |
| USDA NASS | Historical yield | Candidate |
| Sentinel-2 | Spatial context | Candidate |

All values in the interface are demo values until the challenge dataset and backend are connected. The spatial view is labeled as an illustrative demo layer.

## Team

- **Aryan Sharma**, B.S. Agriculture
- **Sahil Jain**, B.S. Computer Science
- **Shashwat Goel**, B.S. Computer Science
