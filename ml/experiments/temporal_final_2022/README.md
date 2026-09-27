# Temporal yield models, 2022: the website's final results

The ML team's final run: site-specific cumulative yield models for 2,131 maize plots at five
2022 SyDAg trial sites, six satellite stages per plot (TP1–TP6), validated by nested
cross-validation within each site, with 90% CV+ conformal prediction ranges.

| File | What it is |
|---|---|
| `temporal_plot_predictions.csv` | Out-of-fold forecast per plot and stage, by series. The website uses only `series == "deployed"` (the best inner-validated model available so far); `preseason` is the field-records-only baseline. The `raw_*` series are research history. |
| `temporal_model_coordinates.csv` | Validation metrics per site and stage for the raw, deployed, satellite-only and pre-season models. The website shows the `deployed_*` and `preseason_agronomic_*` columns. |
| `uav_matched_comparison.json` | The separate matched satellite vs satellite + UAV experiment (975 plots, Ames and Crawfordsville, about 125 DAP), as the ML team reported it. Not part of the temporal CSVs. |

The website does not read these files directly. They become `backend/artifacts/final_results.json`:

```bash
cd backend
uv run python -m scripts.build_final_results        # writes and checks the artifact
uv run python -m app.results artifacts/final_results.json
```

The script cross-checks every site metric against the plot rows and stops if they disagree.
Options: `--featured PLOT_ID` to open a site on a different plot than the median-yield one,
`--earliest-useful-mae 15` to publish an agreed "useful from" rule (unset by default).
