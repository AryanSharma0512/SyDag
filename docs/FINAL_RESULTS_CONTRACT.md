# Final results: what the website needs from the ML team

The website does not train or re-run models. It reads **one frozen, versioned file** that the
final run writes:

```
backend/artifacts/final_results.json
```

The authoritative contract is `backend/app/results.py` (pydantic, with an example in its
docstring). This page is the walkthrough. Snake_case keys, as in `metadata.json`; camelCase
is accepted too.

## Deliver it

```bash
cd backend
uv run python -m app.results /path/to/final_results.json   # prints OK + a summary, or what is wrong
cp /path/to/final_results.json artifacts/                   # locally; the same folder on the server
```

`backend/artifacts/` is mounted into the API container, so copying the file on the server is
enough: the API re-reads it when it changes (no restart, no rebuild). A malformed file makes
`/api/results` return `503` with the reason, and the website says the results did not load.
Until the file exists, every section it feeds says it is waiting. Nothing is estimated in its place.

## What each field drives

| Field | Required | Shown on the website as |
|---|---|---|
| `contract_version` | yes, `1` | — |
| `results_version` | yes | Methodology ("Results version …") |
| `dataset_label` | recommended | Navigation badge, e.g. "Challenge data (SyDAg26)" |
| `model.name`, `model.validation` | yes | Methodology pipeline box and validation text, e.g. "Random Forest", "leave-one-site-out, 3 sites" |
| `performance[]`: `dap`, `mae`, `rmse`, `r2`, `n`, `label` | yes (≥ 1 row, `mae` or `r2` each) | "How early can we know?" chart (MAE primary, R² in an aligned row), Methodology table, and the dashboard's **Typical validation error** (the MAE of the latest stage at or before the forecast's DAP) |
| `earliest_useful_dap`, `earliest_useful_rule` | recommended | The "Useful from day N" band; the dashboard opens each plot on that stage. Never hardcoded: if the frozen run says 78, the site says 78 |
| `interval`: `level`, `coverage`, `method` | recommended | Methodology "Prediction ranges": the site quotes the observed `coverage`, and the nominal level only next to it |
| `plots[]`: `plot_id`, `site`, `season`, `hybrid`, `nitrogen_lb_ac`, `planting_date`, `irrigated`, `forecasts[]` | recommended | Dashboard location → plot picker and forecast. `forecasts[]` is one row per date: `date`, `dap`, `yield`, `lower`, `upper` (range optional; both or neither; `lower ≤ yield ≤ upper`) |
| `plots[].uav`: `dap`, `satellite_only`, `satellite_plus_uav` | optional | The plot's predicted yield in the two Satellite vs UAV panels |
| `sites[]`: `site`, `season`, `plots`, `forecasts[]` | optional | A site-average forecast for a location with no per-plot rows |
| `maturity[]`: `site`, `season`, `plot_id` (null = whole site), `as_of`, `gdd_since_planting`, `gdd_to_maturity`, `window_start`, `window_end`, `method` | optional | Crop development: accumulated GDD, the **estimated maturity window**, and `method` in Methodology. No date is shown without it |
| `uav`: `matched`, `sites`, `plots`, `dap`, `validation`, `framework`, `satellite_only{mae,rmse,r2}`, `satellite_plus_uav{…}`, `note` | optional | Satellite vs UAV: validation error of each and the change in bu/ac. Shown **only when `matched` is true** (same plots, dates, validation split and model framework) |

`site` uses the data's spelling (`Ames`, `Crawfordsville`, `Lincoln`, `MOValley`, `Scottsbluff`);
the website shows "Missouri Valley". `plot_id` is the id within the site (e.g. `4231-17-3`).

## What the website deliberately does not do

- It never shows R² as "accuracy" or "confidence". Farmer-facing error is MAE in bu/ac.
- It never shows a coverage level (e.g. "90%") that `interval.coverage` does not support.
- It never shows yield per weather scenario: the weather outlook and the yield forecast stay
  separate until the yield model uses future-weather features and the coupled output is
  validated. If that arrives, it needs its own contract field, not a reuse of this one.
- It never shows a UAV improvement, a narrower range or a dollar value that the matched
  comparison does not supply.

## Where the website reads it

`src/services/results.ts` is the only frontend code that reads the file's shape
(`src/types/results.ts` mirrors `backend/app/results.py`). To move from the frozen file to
live inference later, change that service; the components stay as they are.
