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

The 2022 temporal run is converted by a script, so no number is typed in by hand:

```bash
cd backend
uv run python -m scripts.build_final_results               # ml/experiments/temporal_final_2022/ → artifacts/final_results.json
uv run python -m app.results artifacts/final_results.json  # prints OK + a summary, or what is wrong
```

It reads the `deployed` series of `temporal_plot_predictions.csv`, the site metrics in
`temporal_model_coordinates.csv` (cross-checked against the plot rows) and
`uav_matched_comparison.json`; see `ml/experiments/temporal_final_2022/README.md`. Any
other file that passes the checker works the same way:

```bash
uv run python -m app.results /path/to/final_results.json
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
| `performance[]`: `dap`, `stage`, `mae`, `rmse`, `r2`, `n`, `label` | yes (≥ 1 row, `mae` or `r2` each) | Methodology's all-sites chart and table (MAE primary, R² in an aligned row when given), and the dashboard's **Typical validation error** when a site has no `site_performance`. Matched to a forecast by `stage` (e.g. `TP3`), else the latest stage at or before its DAP. Leave `r2` null for rows pooled across site-specific models |
| `site_performance[]`: `site`, `season`, `plots`, `folds`, `preseason{r2,mae,rmse,coverage,median_interval_width,n}`, `stages[]{stage,dap,dap_min,dap_max,…same metrics}` | optional | Per-site validation: the dashboard's "How early can we know?" for the selected site (pre-season as a reference line), its **Typical validation error (MAE)** at the forecast's stage, the site table under "More detail", and Methodology's per-site R² and range-width panels |
| `earliest_useful_dap`, `earliest_useful_rule` | recommended | The "Useful from day N" band; the dashboard opens each plot on that stage. Never hardcoded: if the frozen run says 78, the site says 78 |
| `interval`: `level`, `coverage`, `method` | recommended | Methodology "Prediction ranges": the site quotes the observed `coverage`, and the nominal level only next to it |
| `plots[]`: `plot_id`, `site`, `season`, `hybrid`, `nitrogen_lb_ac`, `planting_date`, `irrigated`, `featured`, `forecasts[]` | recommended | Dashboard location → plot picker and forecast; each site opens on its `featured` plot. `forecasts[]` is one row per date: `date`, `dap`, `stage`, `yield`, `lower`, `upper` (range optional; both or neither; `lower ≤ yield ≤ upper`). Yields and bounds are shown floored at 0 bu/ac |
| `plots[].uav`: `dap`, `satellite_only`, `satellite_plus_uav` | optional | The plot's predicted yield in the two Satellite vs UAV panels |
| `sites[]`: `site`, `season`, `plots`, `forecasts[]` | optional | A site-average forecast for a location with no per-plot rows |
| `maturity[]`: `site`, `season`, `plot_id` (null = whole site), `as_of`, `gdd_since_planting`, `gdd_to_maturity`, `window_start`, `window_end`, `method` | optional | Crop development: accumulated GDD, the **estimated maturity window**, and `method` in Methodology. No date is shown without it |
| `uav`: `matched`, `sites`, `plots`, `dap`, `validation`, `framework`, `satellite_only{mae,rmse,r2}`, `satellite_plus_uav{…}`, `note` | optional | Satellite vs UAV: validation error of each and the change in bu/ac. Shown **only when `matched` is true** (same plots, dates, validation split and model framework) |

`site` uses the data's spelling (`Ames`, `Crawfordsville`, `Lincoln`, `MOValley`, `Scottsbluff`);
the website shows "Missouri Valley". `plot_id` is the data's canonical id (e.g.
`2022_Ames_4233_18_10`); the website shows a short form (`Plot 4233-18-10`, `Plot 10-10` at a
site whose plots share one trial name) and keeps the canonical id in URLs.

`GET /api/results` adds `plot_counts[]` (`site`, `season`, `plots`, `observations`), counted from
`plots[]`, for the modeling facts on the Data page.

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
