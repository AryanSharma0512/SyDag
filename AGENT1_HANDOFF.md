# Agent 1 handoff: challenge dataset ingestion, joins, dates, spatial metadata

Written 2026-09-26 (night before data day) for Agents 2 and 3 and the humans on the ML team.

## TL;DR

- **Every file in the shared Drive folder is inventoried and joined to the ground truth** on
  one key: `plot_id = {year}-{site}-{experiment}-{range}-{row}` (e.g. `2022-Ames-4231-17-3`).
  2,012 satellite TIFFs and 430 UAV PNGs; 1,960 + 412 are usable; nothing was dropped.
- **Acquisition dates are real dates** from `DateofCollection.xlsx`, per site and sensor.
  TP numbers mean different dates at different sites.
- **Band order confirmed from the files:** Red, Green, Blue, NIR, Red Edge, Deep Blue. The
  organizers' README lists them in a different order and is wrong; their notebook is right.
- **Spatial metadata:** each GeoTIFF carries its UTM CRS, pixel size (0.30 m) and origin. The
  plot centroid is computed from the plot's own pixels, and agrees with the practice
  pipeline's coordinate to 0.17 m.
- **Full extraction done.** Once network access was opened, all 2,426 distinct image files
  were downloaded (sizes match Drive) and every one was read. All 1,996 local satellite files
  have 6 bands in the expected order; the 16 Lincoln duplicate uploads are byte-identical.
  The canonical dataset `challenge2022` was built with NOAA weather and SSURGO soil and passes
  every data check; its profile is `ml/experiments/reports/challenge_dataset_profile.md`.
- **The subset is sparse in time:** at Crawfordsville and Lincoln each time point images a
  mostly different set of plots. Only Ames TP1 to TP5 is a real panel (~94 to 118 plots).
  See [For Agent 3](#for-agent-3-and-the-early-season-question).
- **This is the same dataset the practice models were trained on** (Shrestha et al. 2024).
  Same file names, same yields and the same per-site counts. The practice models have seen
  Ames and Lincoln, so do not score them on this data as if it were unseen.

## What I inspected

| Source | How | Result |
|---|---|---|
| `Documentation/Readme.md`, `Documentation.ipynb` | Drive connector, decoded locally | Layout, file naming, band list, notebook code (see anomalies) |
| `GroundTruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv` | Drive connector, **byte-exact** (289,497 bytes = Drive size) | 2,291 plots, 5 sites, 18 columns |
| `GroundTruth/DateofCollection.xlsx` | Drive connector, byte-exact (8,444 bytes; zip CRCs pass) | 54 site/sensor/TP dates (6 sites incl. North Platte) |
| `Satellite/`, `UAV/` folder listings | Drive connector metadata (name, size, upload time) for every file | 2,446 entries → 2,442 files (4 listed twice) |
| QA sample: 2 GeoTIFFs, 2 PNGs | Drive connector, byte-exact (see below) | Formats, bands, CRS, padding, centroids, indices verified |
| All images | Direct Drive download by file id once the network was opened; size checked against Drive per file | 2,426 files (the 16 Lincoln second uploads compared separately: identical), all read |

The two sample GeoTIFFs are `Satellite/Ames/TP3/Ames-TP3-4231_17_3.TIF` and
`Satellite/Crawfordsville/TP2/Crawfordsville-TP2-4353_9_42.TIF`. For both, the per-band means
over the plot pixels reproduce the `STATISTICS_MEAN` values the producer embedded in the file,
to 4 decimals, so the pixel data is exact. For the Crawfordsville plot, the four vegetation
indices and the NIR mean match the practice pipeline's values
(`backend/data/practice/shrestha2024.json`) to 5 decimals.

## What I implemented

All in `ml/soilsignal_ml/ingest/`, inside the existing pipeline (same environment, CLI and
canonical tables):

| Module | Does |
|---|---|
| `challenge.py` | Ground-truth loader and cleaning, `DateofCollection.xlsx` parser, filename parser, file inventory from disk and/or a Drive listing / the committed inventory, manifest joins (match status, duplicates, days after planting), restartable raster-metadata pass, plot coordinates |
| `imagery.py` | Per-file metadata: GeoTIFF (bands and their order from the GDAL band descriptions, CRS, pixel size, bbox, valid/padding pixels, centroid and bbox-centre lat/lon, per-band means for QA, sha256) and PNG (size, mode, alpha mask, valid pixels, means) |
| `challenge_report.py` | Writes the Parquet outputs and `challenge_manifest.json` (counts, anomalies, schemas). Drops Drive ids and machine paths |
| `challenge_adapter.py` | `ChallengeDatasetAdapter` (dataset `challenge2022`) → canonical `plots`, `observations` (ndvi, ndre, gndvi, evi, nir), `sites`; `ingest` then adds weather/soil/county yields as usual |
| `challenge_postgres.py` | CSV + `load.sql` for Postgres; PostGIS points and footprints when the extension exists |
| `__main__.py` | New commands `challenge` and `challenge-sql`; `--dataset challenge2022 ingest` |

Tests: `ml/tests/test_challenge.py` (15 tests). They build a synthetic copy of the folder
(ground truth, workbook, hand-built GeoTIFFs with known geometry and padding, an RGBA PNG) and
check the key, the cleaning rules, the date joins, every match status, duplicates, metadata,
restartability, that outputs hold no private fields, and the adapter. Three tests use the
real files when present.

### `HackathonDatasetAdapter`

`ingest/dataset_adapter.py`, which holds the `HackathonDatasetAdapter` stub, was not opened in
this session (a tool-permission rule blocked reading it). So the implementation lives in
`ChallengeDatasetAdapter` and is registered in `__main__.py` alongside the existing `ADAPTERS`.
The stub itself is untouched. Humans: either make the stub delegate
(`HackathonDatasetAdapter = ChallengeDatasetAdapter`) or delete it. Nothing else depends on it.

## Exact folder assumptions

A local copy of the shared folder at `ml/data/raw/challenge/` (override with `--raw`):

```
GroundTruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv
GroundTruth/DateofCollection.xlsx          # Sheet1: Location, Date, Image, time
Satellite/<Location>/TP1..TP6/<Location>-TP<n>-<experiment>_<range>_<row>.TIF
UAV/<Location>/TP1..TP3/<Location>-TP<n>-<experiment>_<range>_<row>.PNG
Documentation/                             # not read by the code
```

- Every file under `Satellite/` and `UAV/` is inventoried at any depth. A file outside the
  `<Sensor>/<Location>/<TP>/` pattern gets `match_status = folder_name_mismatch` or
  `unparseable_name`; it is never skipped.
- The folder's location and TP must equal the name's location and TP.
- Sensor is decided by the top folder. The extension must be TIF/TIFF (satellite) or PNG (UAV).
- If Drive's "download folder" zip renames a clashing name (e.g. `... (1).TIF`), that file
  shows up as `unparseable_name`, which is the intended behaviour.

## Exact filename parsing logic

```
^(?P<location>[^-]+)-(?P<time_point>TP\d+)-(?P<experiment>.+)_(?P<range>\d+)_(?P<row>\d+)\.(?P<ext>[A-Za-z]+)$
```

`Ames-TP3-4231_17_3.TIF` → location `Ames`, TP3, experiment `4231`, **range 17, row 3**.
The last two `_` fields are always range then row. This is how the organizers' notebook splits
names, and it matches the practice ids (`Crawfordsville-4351-11-16` is range 11, row 16:
PHN46 X PHK56 at 225 lb N in both sources). The experiment string is kept verbatim
(`4231`, `hybrids`, and in the full dataset `Hyrbrids` at MOValley and `n75`/`n150`/`n225` at
Scottsbluff). Location → `site_id` uses the ground-truth spelling. Aliases (for the workbook):
`Missouri Valley` → `MOValley`, `Crawfordville` → `Crawfordsville`, `North Platte` → `NorthPlatte`.

## The plot key and the join

- **Key:** (year, site_id, experiment, range, row). It is unique in the ground truth (checked;
  `load_plots` raises on a duplicate). `plot_id = f"{year}-{site}-{experiment}-{range}-{row}"`.
  `experiment` is `NA` for the 16 Scottsbluff fill plots that have none.
  `practice_plot_id` = the practice pipeline's id for the same plot (no year).
- **Year:** the CSV has no year column. It is the planting year, 2022 for every site. Fill
  plots take their site's year, and the loader raises if a site spans two years.
- **Image → plot:** exact match on (site_id, experiment, range, row). Image → date: exact
  match on (site_id, sensor, time_point) in `acquisition_dates`.
- **`gt_row`** is the row position in the CSV, which the organizers' notebook uses as a
  record id. The CSV's own `index` column is **not unique** and is kept only as `gt_index`.

### Ground-truth cleaning rules (nothing fabricated)

| Rule | Why |
|---|---|
| `nitrogen_lb_ac` = null where `poundsOfNitrogenPerAcre` is 0 **and** genotype or treatment is missing (`nitrogen_placeholder_zero`) | Every 0 is on a fill plot. No 0 N treatment exists (rates are 75/150/225 or 250, and 175 at MOValley) |
| `irrigated` = `irrigationProvided > 0` (only Scottsbluff: 16.9); null where missing | Raw value kept as `irrigation_provided` (units undocumented) |
| `planting_date` kept as recorded (null on fill plots); `planting_date_filled` adds the one date shared by the plot's site + experiment; `planting_date_source` says which | Needed for days-after-planting on fill plots. Ames has two dates: 4231/4232 on 05-22, 4233 on 05-23 |
| `field_id = {year}-{site}-{experiment}` | One trial block. At Ames/Crawfordsville each experiment is a single N rate; Lincoln is one block with all three |
| `is_hybrid_plot` = genotype present | Fill/border plots have no genotype and no yield |

## Dataset statistics

### Ground truth (all 5 sites; images only for the first 3)

| Site | Plots | Hybrid plots | With yield | Hybrids | Experiments | N (lb/ac) | Planted | Irrigated | Images tonight |
|---|---|---|---|---|---|---|---|---|---|
| Ames | 536 | 487 | 487 | 84 | 4231, 4232, 4233 | 75, 150, 250 | 05-22 / 05-23 | no | satellite + UAV |
| Crawfordsville | 522 | 489 | 488 | 84 | 4351, 4352, 4353 | 75, 150, 225 | 05-11 | no | satellite |
| Lincoln | 532 | 504 | 504 | 84 | hybrids | 75, 150, 225 | 05-22 | no | satellite |
| MOValley | 176 | 168 | 163 | 84 | Hyrbrids | 175 | 04-29 | no | none |
| Scottsbluff | 525 | 509 | 489 | 84 | n75, n150, n225 (+16 NA) | 75, 150, 225 | 05-19 | yes | none |

In scope (3 imaged sites): 1,590 plots, 1,480 hybrid plots, 1,479 with final yield, 84 hybrids.
No duplicate plot ids.

Missing fields: fill plots lack genotype, treatment, N, irrigation, plot length and planting
date. `totalStandCount` is absent at Lincoln and Scottsbluff. `daysToAnthesis` and
`GDDToAnthesis` exist only at Lincoln and Scottsbluff. Hybrid plots without a yield:
Crawfordsville 1, MOValley 5, Scottsbluff 20. Full per-column counts are in
`challenge_manifest.json` → `ground_truth.sites.*.missing`.

### Acquisition dates (2022)

| Site | Sat TP1 | TP2 | TP3 | TP4 | TP5 | TP6 | UAV TP1 | TP2 | TP3 |
|---|---|---|---|---|---|---|---|---|---|
| Ames | 07-15 | 07-23 | 08-10 | 08-31 | 09-11 | 09-24 | 07-12 | 07-26 | 08-10 |
| Crawfordsville | 07-10 | 07-20 | 08-02 | 09-13 | 10-01 | 10-09 | 07-12 | 07-26 | 08-11 |
| Lincoln | 07-18 | 08-06 | 09-03 | 09-11 | 09-19 | 09-27 | 07-13 | 07-28 | 08-04 |
| MOValley | 07-13 | 07-21 | 08-08 | 09-03 | 09-11 | 09-19 | 07-13 | 07-27 | 08-10 |
| Scottsbluff | 07-04 | 07-17 | 08-07 | 08-18 | 09-09 | 09-24 | 07-08 | 07-22 | 08-12 |
| North Platte | 07-09 | 07-17 | 08-04 | 08-22 | 09-02 | 09-25 | 07-13 | 07-19 | 08-03 |

The first image anywhere is 54 to 60 days after planting (mid-July). **Nothing in this
dataset is observed before July**, so "early season" here means July. Satellite TPs are
chronological within every site (checked).

### Images

| Sensor | Site | TP1 | TP2 | TP3 | TP4 | TP5 | TP6 | Files | Usable | Distinct plots |
|---|---|---|---|---|---|---|---|---|---|---|
| Satellite | Ames | 114 | 108 | 124 | 108 | 100 | 144 | 698 | 662 | 256 |
| Satellite | Crawfordsville | 77 | 93 | 81 | 80 | 78 | 91 | 500 | 500 | 332 |
| Satellite | Lincoln | 133 | 133 | 149 | 133 | 133 | 133 | 814 | 798 | 438 |
| UAV | Ames | 126 | 132 | 172 | – | – | – | 430 | 412 | 166 |

Days after planting at each satellite TP: Ames 54/62/80/101/112/125; Crawfordsville
60/70/83/125/143/151; Lincoln 57/76/104/112/120/128.

Satellite: 2,012 files, 48.7 MB (about 24 KB each). UAV: 430 files, 184 MB (0.3 to 0.5 MB each).

**Time points per imaged plot** (satellite, usable):

| Site | 1 TP | 2 TPs | 3 TPs | 4 TPs | 5 TPs |
|---|---|---|---|---|---|
| Ames | 148 | 6 | 0 | 8 | 94 |
| Crawfordsville | 199 | 105 | 22 | 5 | 1 |
| Lincoln | 200 | 142 | 73 | 20 | 3 |

Ames TP1 to TP5 cover the same ~94 to 118 experiment-4231 plots. Ames TP6 is a disjoint set
(62 of 4231 plus 76 of 4232). At Crawfordsville and Lincoln any two TPs share only 8 to 42
plots. UAV (Ames) covers 120 plots at all three flights.

### Satellite files (from the files themselves)

- 6 bands, uint16, LZW, tiled 128×128. GDAL nodata = 0. Band descriptions:
  `Pleiades NEO Red (0.618-0.689)`, `Green (0.533-0.59)`, `Blue (0.446-0.52)`,
  `NIR (0.768-0.888)`, `Red Edge (0.696-0.749)`, `Deep Blue (0.416-0.456) um`.
  `band_order_ok` checks this per file.
- DN = reflectance × 10,000 (NIR ≈ 4,400 to 5,000 over July canopy). The 1e-4 scale
  reproduces the practice indices exactly.
- GeoTIFF: projected WGS 84 / UTM. **EPSG:32615 at Ames and Crawfordsville, EPSG:32614 at
  Lincoln** (all files). Pixel size 0.30 m, pixel-is-area. The code reads the CRS per file.
- All 1,996 local files: 6 bands, uint16, `band_order_ok` everywhere. Boxes are 11–12 × 21–22 px.
  Lincoln plots run east–west, so its images are 21–22 px wide and 11–12 px tall. Each plot
  has 200–231 valid pixels (18.0–20.8 m²); 76–100% of the box is plot. No file has a pixel
  that is zero in only some bands, and none is empty. So a valid pixel = all 6 bands
  non-zero, the same as the organizers' `Red > 0`.
- The files contain several stale IFDs from in-place edits. `tifffile` reads the right one.
- **Plot coordinate** = median over the plot's images of the valid-pixel centroid, with
  `coord_spread_m` reported. `bbox_center_lat/lon` (the practice convention) is also kept.
  They differ by 0.17 m on the Crawfordsville sample. The spread is 0 for every plot: each
  plot is clipped with the same polygon on every date, so the images are co-registered by
  construction. The spread is not a check of satellite geolocation.
- Median NDVI by site and date reproduces the practice profile: Crawfordsville falls from
  0.86 to 0.24 by October, and Lincoln from 0.79 to 0.35 (2022 drought).

### UAV files

All 430 read: RGBA, uint8, 355–385 × 701–760 px. Alpha is 0 exactly where RGB is 0 in every
file (`alpha_rgb_disagree_pixels` = 0); 2.5–3.1% is padding. **Not georeferenced** and **not
calibrated**: the median plot RGB is 35/57/38 at TP1, 77/112/70 at TP2 and 105/131/87 at TP3,
and the one sample plot goes from 27/46/35 to 103/130/86. Use
within-flight relative values (for example GLI, NGRDI, or ranks within a flight), never
absolute DN across flights. The organizers' notebook computes GLI and NGRDI.

## Anomalies

1. **README band order is wrong** (see above). Use the file descriptions or the notebook.
2. **UAV imagery is only present for Ames**; the brief expected all three locations.
3. **Satellite/Ames has two `TP6` folders on Drive**; the second is empty.
4. **16 duplicate uploads in Satellite/Lincoln/TP3**: same name, same size, same modified
   time, different Drive ids, uploaded about 3 s apart. They are
   `Lincoln-TP3-hybrids_{12_18, 12_20, 12_21, 12_22, 12_33, 12_38, 12_4, 13_11, 13_12, 13_13,
   13_14, 13_15, 13_17, 13_18, 13_23, 13_3}.TIF`. The first upload is kept (`use`), the copy
   has `is_duplicate`. Downloaded and compared: all 16 are byte-identical to the kept copies.
5. The Drive listing returned 4 Ames TP2 files twice (same Drive id). This is a listing
   artifact and each is counted once.
6. **54 images match no ground-truth plot**, all at Ames **range 1** (the ground truth starts
   at range 2): satellite `4231_1_{2..7}` at TP1 to TP5 and `4232_1_{17..22}` at TP6 (36);
   UAV `4231_1_{2..7}` at TP1 to TP3 (18). They are border plots, kept as
   `not_in_ground_truth`.
7. Among usable images, 126 satellite and 24 UAV images are of **fill plots** (no genotype,
   no yield). That leaves **1,834 satellite and 388 UAV images of hybrid plots with a final
   yield**, the rows that can train a model.
8. The CSV's `index` column is not unique; experiment codes include the typo `Hyrbrids`; 16
   Scottsbluff fill plots have no experiment code; `poundsOfNitrogenPerAcre` uses 0 as a
   placeholder.
9. `DateofCollection.xlsx` Sheet1 uses "Missouri Valley". Sheet2 (the organizers' satellite
   vs UAV date gaps) spells "Crawfordville" and is informational only (not parsed).
10. The Drive "modified" time was preserved for Ames (2023) but not for Crawfordsville and
    Lincoln (re-uploaded 2026-09-25/26). Don't use it for anything.
11. **Ames images cover experiments 4231 (250 lb N) and 4232 (150 lb N) only.** There are no
    images of 4233, so the Ames 75 lb N block is absent from this subset.

## Assumptions (to verify)

- Reflectance scale 1e-4. This is standard for Pleiades NEO, matches the practice pipeline,
  and gives plausible values, but the organizers don't document it.
- A satellite pixel is valid if all six bands are non-zero; a UAV pixel if alpha > 0.
- `plot_length_ft`: 17.5 and 22.5 are feet. The README says plots differ in length between
  locations but gives no unit.
- The fill plot planting date equals its experiment's date (`planting_date_filled`, flagged).
- The organizers subsampled plots per time point for this subset. The full dataset (same
  names) should be a much denser panel: the practice profile had 13,650 images for
  2,275 plots.

## Postgres / PostGIS decisions

- The mini PC's database was not reachable from this session, so nothing was loaded there.
- `python -m soilsignal_ml challenge-sql` writes `ml/data/challenge/postgres/`: one CSV per
  table plus `load.sql`, which creates schema `challenge` with `sites`, `plots`,
  `acquisition_dates`, `images` (both sensors) and `observations`, including primary keys,
  foreign keys and indexes. The DDL is generated from the Parquet schemas.
- If the server offers PostGIS, `load.sql` also adds `plots.geom` and `sites.geom`
  (Point, 4326) and `images.footprint` (each GeoTIFF's bounding box, transformed from its UTM
  zone). Without PostGIS it prints a notice and keeps lat/lon columns.
- **Tested** on a local PostgreSQL 16 + PostGIS 3.4 with full raster metadata: loads cleanly,
  **9.4 MB** in total. It has 1,026 plot points and 1,996 image footprints across 2 UTM
  zones, and every plot point is within 0.24 m of its footprints' centres. No image bytes are
  stored, only paths.
- Deliberately not done: per-pixel data in the database, a Python driver dependency
  (`psql` is enough), and plot polygons (the footprint is the image bbox). The exact plot
  polygon could be vectorised from the valid-pixel mask tomorrow if the maps work needs it.

## Commands to reproduce

From `ml/` (the backend's environment with the `ml` group, which now includes `pyarrow`):

```bash
# 0. Get the data: download the shared Drive folder and unzip so that
#    ml/data/raw/challenge/{GroundTruth,Satellite,UAV,Documentation}/ exist.
#    (This session fetched each file by id from a Drive listing:
#     https://drive.usercontent.google.com/download?id=<id>&export=download)

# 1. Inventory + joins + raster metadata for every local file. Restartable: metadata is
#    cached per file (path, size, mtime) in ml/data/challenge/cache/ and checkpointed every
#    200 files. --inventory also lists files that are on Drive but not on disk yet.
uv run --project ../backend --group ml python -m soilsignal_ml challenge \
    --inventory data/challenge/drive_inventory.parquet --workers 8
#    Quick dev pass over a sample:  add --limit 200
#    Tonight's run (from saved Drive listings): --drive-listing data/raw/challenge/_drive_listing

# 2. Canonical tables for training (indices from the GeoTIFFs, or from Agent 2's
#    ml/data/challenge/satellite_features.parquet if present) + weather/soil/county context
#    (--dataset goes before the command; NOAA sometimes drops a connection: rerun on error.
#    `profile` overwrites the practice report, so the challenge one was written to
#    experiments/reports/challenge_dataset_profile.md with build_profile() instead.)
uv run --project ../backend --group ml python -m soilsignal_ml --dataset challenge2022 ingest
uv run --project ../backend --group ml python -m soilsignal_ml --dataset challenge2022 validate

# 3. Optional database
uv run --project ../backend --group ml python -m soilsignal_ml challenge-sql
cd data/challenge/postgres && psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f load.sql

# Tests
uv run --project ../backend --group ml --group dev pytest tests/test_challenge.py
```

Measured here: step 1 reads all 2,426 files in 6 s (4 cores). `ingest` takes about 10 s
(weather and soil fetches).

## What Agent 2 should consume

- **`ml/data/challenge/satellite_manifest.parquet`**, filtered to `use == True`. Each row is
  one plot image: `image_id`, `plot_id`, `site_id`, `time_point`, **`date`**,
  `days_after_planting`, `image_path` (relative to `ml/data/raw/challenge/`), plus the raster
  metadata of every file, including per-band means over the plot pixels (`mean_red` …
  `mean_deep_blue`) as a baseline to check your extraction against. Join to targets and
  management through `plots.parquet` on `plot_id`.
- The canonical observations built here (`ml/data/processed/challenge2022/observations.csv`,
  git-ignored; rebuild with step 2) already hold ndvi, ndre, gndvi, evi and nir per image.
- **Bands:** index 0 to 5 = red, green, blue, nir, red_edge, deep_blue. Reflectance = DN × 1e-4.
  Valid pixel = all bands > 0.
- **Output contract:** to feed the existing training pipeline, write
  `ml/data/challenge/satellite_features.parquet` with `image_id` plus any of `ndvi`, `ndre`,
  `gndvi`, `evi` (mean of the per-pixel index over valid pixels) and `nir` (mean NIR
  reflectance). `ChallengeDatasetAdapter` picks it up automatically. Extra columns (other
  indices, percentiles, texture) are fine: keep them there and extend
  `backend/app/features/vegetation.py` and `catalog.py` if they should become model features.
  `challenge_adapter.image_indices()` is the reference implementation; it reproduces the
  practice values exactly.
- `uav_manifest.parquet` has the same structure for the PNGs (Ames only). Mask with alpha.
- Always use `date` or `days_after_planting`. **Never compare TP numbers across sites.**

## For Agent 3 and the early-season question

- All images fall 54 to 151 days after planting (July 10 to October 9). The earliest image
  per site is Crawfordsville 07-10, Ames 07-15, Lincoln 07-18 (UAV: 07-12, 07-12, 07-13).
- In this subset, per-plot time series exist only at Ames (94 plots with TP1 to TP5). At
  Crawfordsville and Lincoln, compare cutoffs cross-sectionally ("models using the images
  available by date D") rather than as per-plot trajectories, or wait for the full dataset.
  `plots.parquet` has `satellite_time_points` per plot for exactly this.
- Before trusting per-plot trajectories, check how many plots are imaged at every TP
  (`challenge_manifest.json` → `images.satellite.time_points_per_plot_by_site`).
- **Within-site NDVI vs yield correlation, by image** (`challenge_dataset_profile.md`):

  | Site | Img 1 | Img 2 | Img 3 | Img 4 | Img 5 | Img 6 |
  |---|---|---|---|---|---|---|
  | Ames | -0.00 | 0.36 | 0.65 | 0.69 | 0.60 | 0.29 |
  | Crawfordsville | 0.19 | 0.17 | 0.38 | 0.34 | 0.04 | -0.31 |
  | Lincoln | 0.46 | 0.64 | -0.22 | -0.55 | -0.52 | -0.54 |

  At Ames the signal peaks at Aug 10 to Aug 31. At Lincoln it is strongest early (Aug 6) and
  inverts once the drought sets in, which matches the practice data. At Crawfordsville it is
  weak throughout.
- The held-out-site logic in `ml/configs/project.yaml` holds out Crawfordsville. The practice
  models were trained on the other sites, which are the same plots as this data, so any
  evaluation on Ames/Lincoln with those models is in-sample.

## What tomorrow's humans should verify first

1. Done here for the subset: every file was read, band order and CRS were consistent, there
   were no partial-zero pixels, and the coordinate spread was 0. Repeat the check when the
   full dataset arrives: in `challenge_manifest.json`,
   `raster_metadata.satellite.metadata_status` should be all `read`, `band_order_not_ok` and
   `partial_zero_pixel_files` empty, and `crs_epsg_by_site` one EPSG per site.
2. Whether the **full** dataset (more files than this subset) has the same layout. Rerun step 1
   without `--inventory` on the full download; unmatched and duplicate counts are reported.
3. Ask the organizers or teammates whether **UAV for Crawfordsville and Lincoln** is coming.
4. Look at 3 or 4 images by eye (one per site, early and late TP) against the manifest's
   `plot_id` and `date`.
5. Decide the evaluation split in light of the practice-model overlap (see TL;DR).
6. Set `SOILSIGNAL_NASS_API_KEY` locally and rerun step 2 to add county yield history
   (skipped here).
7. `pyarrow` was added to the backend's `ml` dependency group (Parquet I/O). With it
   installed, pandas 3 stores strings with Arrow. After ingesting the practice dataset here,
   the ML suite passes (46 tests, including the practice-data checks) and so does the backend
   suite (139). The 5 end-to-end tests still skipped need a local `train` → `export` →
   `showcase` run; do that once before trusting a retrain.
