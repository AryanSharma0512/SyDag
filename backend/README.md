# SoilSignal API

FastAPI service that serves field forecasts to the dashboard and predictions from
trained models. Forecast responses mirror `src/types/agricultural.ts` exactly
(`app/schemas.py`). Forecasts currently come from the frontend's mock dataset;
predictions come from whatever model artifacts are in `artifacts/`.

## Run locally

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/api/docs

To point the dashboard at it, run the frontend with `VITE_DEMO_MODE=false npm run dev`;
Vite forwards `/api` to `localhost:8000`.

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/health` | `{status, version, dataSource}` |
| GET | `/api/fields` | `FieldMeta[]` |
| GET | `/api/fields/{id}` | `FieldMeta` |
| GET | `/api/fields/{id}/forecast` | `FieldForecast` |
| GET | `/api/fields/{id}/weather?snapshotId=` | `WeatherContext` (latest snapshot by default) |
| GET | `/api/fields/{id}/soil` | `SoilContext` |
| GET | `/api/models` | loaded models: id, metrics, validation, `asOf`, features |
| POST | `/api/predict` | yield, 90% interval, confidence, drivers |

Unknown ids return `404 {"detail": "..."}`. Model endpoints return `503` when no
artifacts are loaded or one fails to load; the forecast endpoints keep working.

`POST /api/predict` body:

```json
{
  "features": {"ndvi_mid_mean": 0.82, "rain_30d_mm": 42, "...": "..."},
  "asOfDate": "2026-07-20",
  "modelId": null
}
```

Give `modelId` to pick a model, or `asOfDate` to use the model with the latest
season cutoff on or before that date (never a later one, so no future data leaks
in). With neither, the latest model is used. Bad or missing features return `422`
listing every problem.

## Model artifacts

Each trained model is a directory `artifacts/<model_id>/`:

| File | Contents |
| --- | --- |
| `model.joblib` | fitted estimator with `.predict(DataFrame)` (sklearn API; pipelines are fine) |
| `metadata.json` | `ModelMetadata`: id, algorithm, target, unit, CV metrics, validation, `as_of` cutoff (`"MM-DD"`), interval offsets, optional `dataset` and `holdout` (accuracy on data never used in training) |
| `feature_schema.json` | `FeatureSchema`: ordered features with dtype, nullable, label, category, importance, direction, and optionally `typical`, `train_low`/`train_high`, `high_label`/`low_label` |

The contract is defined in `app/model/contract.py`. Export with
`app.model.export.save_artifact(estimator, metadata, schema, root)`: it refuses to
write an artifact the API couldn't load (for example, feature count or column
order not matching what the estimator was fitted on).

- **Intervals:** `interval.lower_offset`/`upper_offset` are added to the point
  prediction. The ML pipeline sets them from out-of-fold residual quantiles on
  unseen sites (5th/95th percentile for 90%).
- **Confidence** = interval precision × in-domain share, as a 0–100 display score
  (not a probability). Interval precision is `1 - (upper - lower) / yield`. In-domain
  share is the fraction of numeric inputs inside `[train_low, train_high]`, the
  central 98% of training values; an input outside that range means the model is
  extrapolating. HIGH ≥ 80, MODERATE ≥ 60, otherwise LOW.
- **Drivers:** when the schema has `typical` values, each prediction gets its own
  drivers (`app/model/explain.py`). A feature's contribution is how far the forecast
  moves if that feature alone were typical. It is shown with `high_label` or
  `low_label` depending on the field's value, e.g. "Rainfall deficit, last 30 days",
  and ranked by share. These are associations the model learned, not causes. Without
  `typical`, drivers fall back to global `importance` (or `feature_importances_`).
- **Progressive forecasts:** export one model per season cutoff (`as_of`), each
  trained only on features observable by that date.
- **Features:** `app/features/` turns raw field inputs (images, daily weather, soil,
  management, county history) into model features as of a date. The ML pipeline in
  `ml/` trains on exactly this code. See `ml/README.md`.

`scripts/make_dummy_model.py` is a minimal worked example on synthetic data;
`ml/soilsignal_ml/export/export_to_backend.py` is the real one.

```bash
uv run python -m scripts.make_dummy_model   # writes artifacts/dummy-06-15 etc.
```

**Versions matter.** A joblib file only loads reliably with the same library
versions it was trained with. Train with the versions pinned in `uv.lock`
(scikit-learn, numpy, pandas), and add any new model library (LightGBM, XGBoost,
CatBoost) to this project before exporting with it. Training-only libraries live in
the `ml` dependency group (`uv sync --group ml`), which Docker does not install.

**Only load artifacts the team produced.** joblib files are pickles and run code
when loaded.

## Tests and lint

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

`tests/test_api.py` asserts each forecast response equals the mock JSON exactly,
so the contract can't silently drift from the frontend types.

## Location context (public data)

`/api/context/*` looks up public agronomic data for a coordinate. The frontend never
calls USDA or NOAA itself; the backend fetches, normalizes and caches everything.

| Endpoint | Source | Key needed |
| --- | --- | --- |
| `GET /api/context/soil?lat=&lon=` | USDA NRCS SSURGO via Soil Data Access: series, texture, drainage, hydrologic group, available water (top 100 cm), organic matter, pH, root zone | No |
| `GET /api/context/weather?lat=&lon=&date=` | NOAA NCEI daily summaries (GHCN-Daily) from the nearest station with rain and temperature records | No |
| `GET /api/context/yield-history?lat=&lon=&throughYear=` | USDA NASS Quick Stats: county corn yields by year and the 5-year average | Yes |
| `GET /api/context/all?lat=&lon=&date=&date=...` | All of the above in one response; each part reports `ok`, `unavailable` or `not_configured` | — |

- **Derived here, not fetched:** rainfall over 7 and 30 days, 30-day mean temperature,
  growing degree days (base 50 °F, cap 86 °F), days at 95 °F or hotter, and the longest
  run of days under 1 mm of rain. Season totals count from `SOILSIGNAL_SEASON_START`
  (default May 1).
- **Soil:** the dominant soil component of the mapped unit; land cover such as
  "Urban land" or "Water" is skipped.
- **County yields:** need a free key from https://quickstats.nass.usda.gov/api in
  `SOILSIGNAL_NASS_API_KEY`. Locally, put it in `backend/.env`; in Docker, compose passes
  it through from the environment or a `.env` next to `compose.sydag.yml`. Both files are
  git-ignored; never commit the key (the repository is public). Without a key the
  dashboard keeps its demo history.
- **Caching:** `cache/` (a named volume in Docker). Soil and counties never expire, county
  yields last 14 days, weather 6 hours while recent and 30 days once settled. If a source
  is down, the last good copy is served and flagged.
- **Demo snapshot:** `uv run python -m scripts.snapshot_context` fetches public data for
  every demo field, writes `src/mock/contextSnapshot.ts` (shown in demo mode) and warms
  the cache. Rerun it after changing field coordinates or dates.
- **Tests** replay responses recorded from the real services
  (`tests/fixtures/context/`), so they never touch the network. The NASS fixture is a
  synthetic example in the documented response shape.

## Mock data

`data/mock/fields.json` is generated from `src/mock/fieldsData.ts`. After changing
the frontend mocks, regenerate it from the repo root with `npm run export:mock`.

## Deployment

`compose.sydag.yml` runs this as `sydag_backend` (port 8000 inside the container,
`127.0.0.1:8189` on the host) on `lostnfound_network`. The reverse proxy must
forward `/api/*` to it with the `/api` prefix preserved.

`backend/artifacts/` is mounted read-only into the container, so deploying a model
needs no rebuild: copy `artifacts/<model_id>/` onto the server and run
`docker compose -f compose.sydag.yml restart backend`. Check `/api/health`
(`modelsLoaded`) and `/api/models` afterwards.

Settings are environment variables prefixed `SOILSIGNAL_` (see `app/config.py`).
