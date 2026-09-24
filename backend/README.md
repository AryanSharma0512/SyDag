# YieldLens API

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
| `metadata.json` | `ModelMetadata`: id, algorithm, target, unit, metrics, validation, `as_of` cutoff (`"MM-DD"`), interval offsets |
| `feature_schema.json` | `FeatureSchema`: ordered features with dtype, nullable, label, category, optional importance and direction |

The contract is defined in `app/model/contract.py`. Export with
`app.model.export.save_artifact(estimator, metadata, schema, root)`: it refuses to
write an artifact the API couldn't load (for example, feature count or column
order not matching what the estimator was fitted on).

- **Intervals:** `interval.lower_offset`/`upper_offset` are added to the point
  prediction. Use validation residual quantiles (5th/95th percentile for 90%).
- **Confidence** is derived from relative interval width: `1 - (upper - lower) / yield`.
- **Progressive forecasts:** export one model per season cutoff (`as_of`), each
  trained only on features observable by that date.
- **Drivers** come from `importance` in the schema if every feature has one,
  otherwise the estimator's `feature_importances_`.

`scripts/make_dummy_model.py` is a worked example: it trains three
cutoff models on synthetic data and exports them.

```bash
uv run python -m scripts.make_dummy_model   # writes artifacts/dummy-06-15 etc.
```

**Versions matter.** A joblib file only loads reliably with the same library
versions it was trained with. Train with the versions pinned in `uv.lock`
(scikit-learn, numpy, pandas), and add any new model library (LightGBM, XGBoost,
CatBoost) to this project before exporting with it.

**Only load artifacts the team produced.** joblib files are pickles and run code
when loaded.

## Tests and lint

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

`tests/test_api.py` asserts each forecast response equals the mock JSON exactly,
so the contract can't silently drift from the frontend types.

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

Settings are environment variables prefixed `YIELDLENS_` (see `app/config.py`).
