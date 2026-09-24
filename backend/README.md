# YieldLens API

FastAPI service that serves field forecasts to the dashboard. Responses mirror
`src/types/agricultural.ts` exactly (`app/schemas.py`). Today it serves the
frontend's mock dataset; the challenge model plugs in later as another
`ForecastProvider` (`app/providers.py`) without changing routes.

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

Unknown ids return `404 {"detail": "..."}`.

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

Settings are environment variables prefixed `YIELDLENS_` (see `app/config.py`).
