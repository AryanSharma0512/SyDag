# Agent 2 handoff: satellite + UAV features, progressive TP1-TP6

Code: `ml/soilsignal_ml/imagery/`. Tests: `ml/tests/test_imagery.py`, `ml/tests/test_imagery_leakage.py`.
Docs: `ml/experiments/reports/imagery/` (feature dictionary, quality report, benchmark report).

## Where things stand

- The pipeline is complete and tested: discovery, TIFF masking and statistics, vegetation
  indices, the progressive records_only/TP1..TP6 table, temporal and site-relative features,
  QA flags and report, visual-QA contact sheets, UAV RGB features joined by flight date, and
  the feature dictionary.
- **It has not been run on the challenge imagery.** From the cloud container the Drive folder is
  readable only one file at a time through the Drive connector, and the network policy blocks
  bulk download. I used the connector to list the folder, read the Readme and the date sheet,
  and inspect one real TIFF. That settled the file format and band order (below). Everything
  else was validated on a synthetic dataset with the same layout and file format.
- First job tomorrow: run the command below on the mini PC (a few minutes), read the quality
  report, and copy the three reports into `ml/experiments/reports/imagery/`.

## Commands for tomorrow (mini PC)

```bash
cd SyDag/ml
uv sync --project ../backend --group ml --group dev      # pyarrow was added to the ml group

# 1. Download "Sample data/Sydag Data" from Drive, e.g. to ~/data/sydag
#    (it must contain Satellite/, UAV/ and Groundtruth/)

# 2. Tests (no data needed, ~30 s)
uv run --project ../backend --group ml --group dev pytest tests/test_imagery.py tests/test_imagery_leakage.py

# 3. Optional quick check on ~60 images spread over every site and TP
uv run --project ../backend --group ml python -m soilsignal_ml.imagery run \
    --data-root ~/data/sydag --out /tmp/imagery_check --limit 60

# 4. Benchmark, then the full run (resumable: rerun the same command after an interruption)
uv run --project ../backend --group ml python -m soilsignal_ml.imagery benchmark --data-root ~/data/sydag
uv run --project ../backend --group ml python -m soilsignal_ml.imagery run --data-root ~/data/sydag

# 5. Keep the real reports in git (the data folder is git-ignored)
cp data/interim/imagery/reports/*.md experiments/reports/imagery/
```

Once Agent 1's canonical tables exist, point the run at them instead of the raw ground truth:

```bash
... run --data-root ~/data/sydag \
    --plots data/processed/sydag26/plots.csv \
    --acquisitions <acquisitions.csv: site_id, modality, time_point, date> \
    --manifest <images.csv: path (+ optional site_id, time_point, plot_id, date, modality)>
```

A manifest's `plot_id`, `site_id`, `time_point` and `date` override what the file names say.
Without a manifest, plot ids follow the practice pipeline's convention,
`<site>-<experiment lowercased>-<range>-<row>` (e.g. `Ames-4231-11-3`, from
`dataset_adapter.plot_id`).

## Output locations (default `ml/data/interim/imagery/`, git-ignored)

| File | What |
|---|---|
| `satellite_features.parquet` | **The main output.** Long table, one row per plot x cutoff: `plot_id, site_id, cutoff, cutoff_tp, as_of_date`, planting-known columns, timing, temporal and current-image features, QA, `final_yield` last |
| `progressive/{records_only,TP1..TP6}.parquet` | The same rows, one file per cutoff |
| `satellite_uav_features.parquet` | The main table plus 20 UAV columns |
| `satellite_image_features.parquet` | One row per TIFF: every statistic plus masking and format metadata (centroid, EPSG, pixel size, band names) |
| `uav_image_features.parquet` | One row per UAV PNG |
| `canonical_observations.csv` | Plot x date index means in the canonical `observations` layout, so the dataset adapter needn't decode the TIFFs again |
| `quality_flags.csv` | Every flag (path, site, TP, plot, flag, detail) |
| `reports/` | `feature_quality_report.md`, `feature_dictionary.md`, `benchmark_report.md` |
| `visual_qa/` | Contact sheets and `sample.csv` |
| `cache/` | Per-image results keyed by content hash |

## Bands

In file order: **red, green, blue, NIR, red edge, deep blue** (Pléiades Neo; 0.618-0.689,
0.533-0.590, 0.446-0.520, 0.768-0.888, 0.696-0.749, 0.416-0.456 µm). 16-bit surface reflectance
x 10,000, 0.3 m pixels.

The official Readme says NIR comes first. It's wrong for these files: their GDAL band
descriptions and band means both show NIR as the fourth band. The extractor doesn't rely on
either document. It reads each file's band descriptions (`band_order_source = gdal_metadata`),
falls back to the configured order only for a file without descriptions and with exactly six
bands, and otherwise computes no statistics. As an independent check, the report shows how often
NIR is the brightest band in vegetated images.

## Index formulas (per pixel, then summarised)

| Index | Formula | Source |
|---|---|---|
| NDVI | (NIR - Red) / (NIR + Red) | backend `compute_indices` |
| NDRE | (NIR - RedEdge) / (NIR + RedEdge) | backend |
| GNDVI | (NIR - Green) / (NIR + Green) | backend |
| EVI | 2.5 (NIR - Red) / (NIR + 6 Red - 7.5 Blue + 1) | backend (Huete et al. 2002) |
| SAVI | 1.5 (NIR - Red) / (NIR + Red + 0.5) | added here (L = 0.5) |

The backend's `compute_indices()` sets per-pixel values outside [-1, 1] to NaN. That matters
only for EVI, when its denominator approaches 0; those pixels are counted (`evi_n_out_of_range`)
and flagged. Blue (not deep blue) is used in EVI. Statistics per band and per index: mean,
median, std, p10, p25, p75, p90. There are also `ndvi_cover_frac` (share of pixels with
NDVI > 0.5) and `ndvi_core_mean` / `ndre_core_mean` over the plot eroded by one pixel, which
drops the edge pixels that mix with alleys and neighbouring plots.

## Masking rules

1. **Padding**: every band is 0 (or every band equals the GDAL nodata value, which is 0 in the
   real files). The plot images are minimum bounding boxes zero-filled outside the plot.
2. **In plot**: not padding.
3. **Invalid**: in plot, but some band is <= 0, non-finite, or > 1.0 after dividing by 10,000.
   A single zero band inside the plot is an edge artefact; > 1 is saturation.
4. **Valid**: in plot and not invalid. Every statistic uses valid pixels only.

Counts per image: `n_pixels_total`, `n_padding`, `n_in_plot`, `n_valid`, `n_invalid`,
`n_saturated`, `n_nonpositive`, `n_near_zero` (valid pixels with a band < 0.001, e.g. DN 1,
which the real file has), `n_core`.

## Point-in-time design

- A **TPk row** has `as_of_date` = that site's TPk acquisition date. It's built from a table
  already cut down to images with `time_point <= k` **and** `date <= as_of_date`. The plot's
  history, the same-date site means and every flag used as a feature are computed after that
  cut. `cutoff_rows()` raises `LeakageError` if anything later reaches it.
- **records_only** rows hold planting-known columns only; `as_of_date` is the planting date.
- **Population**: every cutoff has the same plots, those with at least one satellite image
  file. That keeps cutoffs comparable. Ground-truth plots that were never imaged are counted in
  the report and left out.
- **Planting-known columns** are an allow-list (`field_id, experiment, genotype, nitrogen_lb_ac,
  irrigated, planting_date`). Stand count, days/GDD to anthesis and anything else in the ground
  truth never enter the tables.
- A plot with no image at TPk keeps its latest earlier image, with `days_since_latest_image` > 0.
- UAV flights join a row only if the flight date is <= `as_of_date`.
- Tests (all passing): deleting TP3-TP6 folders, or altering TP3-TP6 pixels, moving their dates
  90 days *earlier*, altering later UAV flights and changing every yield, leaves every
  records_only/TP1/TP2 row identical, compared with `assert_frame_equal`. A control test shows
  that altering TP2 imagery does change TP2 rows, so the comparison isn't vacuous. Another test
  rebuilds each cutoff from imagery truncated at that TP and gets the same rows.

## Feature counts (satellite table)

143 columns: 5 identifiers, 7 known at planting, 4 timing, 86 observed at the cutoff image,
35 cumulative to the cutoff, 5 QA, 1 target. 131 are numeric candidate inputs. The UAV table
adds 20 columns. Per index (NDVI, NDRE, GNDVI, EVI): `current, previous, change_from_previous,
change_per_10d, mean_to_date, min_to_date, max_to_date, trend (per 10 days), area_to_date,
vs_site_same_date_mean`, plus `vs_site_mean_avg_to_date` for NDVI and NDRE. The full list with
availability classes is in `experiments/reports/imagery/feature_dictionary.md`.

## Processing performance and caching

On synthetic data at the real scale (2,339 TIFFs, 4 vCPUs): about 1.8 ms of CPU per TIFF and
~1,400 TIFFs/s with 4 workers. A complete cold run including UAV, QA and reports takes ~33 s;
with a warm cache ~16 s. Speed isn't a constraint, so process everything.

The cache is keyed by SHA-1 of the file bytes plus `EXTRACTOR_VERSION`, in append-only JSON
lines flushed after each image. It's resumable, changed files are re-extracted automatically,
and renames cost nothing. Bump the version constant after changing masking or statistics.

## Quality issues known so far

- The Readme's band order contradicts the files (see Bands). Handled per file.
- Only `UAV/Ames` was in the Drive folder when I listed it. If that holds, Satellite + UAV can be
  compared at Ames only.
- The first satellite image at each site is mid-July (Ames 07-15, Crawfordsville 07-10,
  Lincoln 07-18). Lincoln TP4-TP6 are 8 days apart. Crawfordsville TP5-TP6 are 10-01 and 10-09,
  probably after maturity.
- Near-black plot pixels (DN 1 in red/blue) exist in the one real file checked. They're valid
  under the rules and counted; the real report shows how common they are.
- The date sheet's second tab is scratch work (and misspells Crawfordsville). Only sheet 1 is read.

## Recommended features for the first ML experiments

Start small and site-robust. With three sites and leave-one-site-out validation, absolute index
levels partly encode site and date (phenology, illumination, atmosphere), so they may not transfer.

1. **Relative vigour**: `ndvi_vs_site_same_date_mean`, `ndre_vs_site_same_date_mean`,
   `gndvi_vs_site_same_date_mean`, `ndvi_vs_site_mean_avg_to_date`,
   `ndre_vs_site_mean_avg_to_date`. They compare a plot with its neighbours on the same day,
   which is legitimate at the cutoff and cancels most site/date effects.
2. **Current level**: `ndvi_current`, `ndre_current`, `evi_current`, `cur_ndre_core_mean`.
   NDRE and EVI saturate less than NDVI over closed canopy, which matters because TP1 is
   already mid-season. `cur_ndvi_cover_frac` may sit near 1.0 for most plots once the canopy
   has closed, so check its spread at TP1 before using it.
3. **Trajectory, from TP2 on**: `ndvi_max_to_date`, `ndre_mean_to_date`, `ndvi_change_per_10d`,
   `ndre_trend`, `ndvi_area_to_date`.
4. **Context**: `days_after_planting`, `genotype`, `nitrogen_lb_ac`.
5. Then test whether within-plot spread adds anything: `cur_ndvi_std`, `cur_ndvi_p10`,
   `cur_nir_p90`, `cur_red_edge_median`.

This comparison is automated: `python progressive_experiment.py --imagery-table
data/interim/imagery/satellite_features.parquet` (see `AGENT3_HANDOFF.md` at the repo root).

For "how early is useful", compare records_only against TP1..TP6 on the same plots (the
population is fixed per dataset for this reason). Remember TPk is a different calendar date at
each site. `as_of_date` and `days_after_planting` are there if a calendar or DAP cutoff turns
out fairer.

For UAV: compare satellite-only against satellite + `uav_exg_mean_current`,
`uav_green_frac_current`, `uav_ngrdi_mean_current`, `uav_exg_std_current` on Ames rows only
(the only site with UAV).

## Features rejected, and why

- **More indices** (CIre, MCARI, OSAVI, MSAVI, ...): with six bands they are near-duplicates of
  NDVI/NDRE/EVI, and the brief puts temporal features first. SAVI is kept as current-image
  statistics only, with no temporal set, because at these reflectances it tracks NDVI almost linearly.
- **GLCM/texture on satellite**: plots are ~12 x 21 pixels, and co-occurrence statistics on
  ~150 pixels are noisy and hard to interpret. Percentiles and std cover within-plot spread.
- **Growth-curve fits** (logistic / double logistic per plot): not identifiable from 1-2 points
  at TP1-TP2, and the TP1 image is already mid-season.
- **Area from planting**: it needs an assumed bare-soil index at planting. Area is integrated
  from the first image instead.
- **Season-wide normalisation** (per-plot z-scores over the season, site scaling fitted on all
  TPs): uses future images.
- **Temporal QA flags as features** (implausible change, fewer pixels than the plot median): they
  compare with later images. They're review-only; the feature QA columns use same-date information only.
- **Ground-truth measurements** (stand count, days/GDD to anthesis): in-season or post-season.
  Days to anthesis could become a legitimate feature for cutoffs after the plot's anthesis
  date. That's a decision for Agent 1/3, not something to copy in by default.
- **UAV absolute brightness as a signal**: the PNGs are uncalibrated. `r/g/b_mean` are kept for
  QA; the chromatic indices are the features.

## Database / PostGIS

I didn't use Postgres: `pgadmin.aboutsharma.com` is blocked from this container, and Parquet is
the interchange format anyway. The progressive table is ~3,000 rows x 143 columns (a few MB),
far under the 1 GB budget, if the dashboard wants it in SQL. PostGIS opportunity, not built:
`satellite_image_features.parquet` has each plot's valid-pixel centroid (`centroid_x/y`, EPSG
32615), enough for a plots geometry table. The feature it would enable is a
**neighbour-relative index**: the plot minus the mean of its k nearest plots on the same date.
That is sharper than the site mean when fields have gradients, and a KD-tree on the centroids
would do it without PostGIS.

## For Agent 1

- `canonical_observations.csv` matches the canonical `observations` columns (plus `time_point`
  and `n_pixels`) if you'd rather not decode imagery in the adapter.
- If your plot ids differ from `<site>-<experiment>-<range>-<row>`, pass a manifest with a
  `plot_id` column and everything joins on that.
- Site names are normalised with `canonical_site()` ("Missouri Valley" -> "MOValley"), the same
  ids as the practice pipeline.
