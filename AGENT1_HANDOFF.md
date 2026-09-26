# Agent 1 handoff: challenge dataset ingestion, joins, dates, spatial metadata

For Agents 2 and 3 and the humans on the ML team. Last updated 2026-09-26, after rebasing
on `main` (Agent 3's progressive framework, PR #13) and a real-data smoke test through
Agent 2's imagery pipeline (PR #12/#15) into Agent 3's experiments.

## TL;DR

- **Every file in the shared Drive folder is inventoried and joined to the ground truth** on
  one key: `plot_id = {year}-{site}-{experiment}-{range}-{row}` (e.g. `2022-Ames-4231-17-3`).
  2,012 satellite TIFFs and 430 UAV PNGs; 1,960 + 412 are usable; nothing was dropped.
- **All 2,426 distinct image files were downloaded and read.** All 1,996 local satellite
  files have 6 bands in the order Red, Green, Blue, NIR, Red Edge, Deep Blue (the organizers'
  README lists another order and is wrong). CRS is EPSG:32615 at Ames and Crawfordsville and
  EPSG:32614 at Lincoln.
- **Acquisition dates are real dates** from `DateofCollection.xlsx`, per site and modality.
  TP numbers mean different dates at different sites.
- **One adapter:** `HackathonDatasetAdapter` in `ingest/dataset_adapter.py` is the challenge
  adapter, registered as dataset **`sydag26`**. This is the name Agents 2 and 3 already
  use. The stub and the earlier `challenge2022` name are gone.
- **The records-only baseline is records only:** genotype, nitrogen, irrigation and planting
  date. NOAA weather, SSURGO soil and NASS county yields exist only as separate context
  tables in the canonical dataset. They are never columns of `plots.parquet`, and a test
  guards that.
- **Smoke test passed on real data:** Agent 1 tables → Agent 2 `imagery run` → Agent 3
  `progressive_experiment.py --imagery-table … --plots …`. The plot ids, sites, yields and
  cutoff dates line up exactly. See [Real-data smoke test](#real-data-smoke-test).
- **The subset is sparse in time:** at Crawfordsville and Lincoln each time point images a
  mostly different set of plots. Only Ames TP1 to TP5 is a real panel (~94 to 118 plots).
- **This is the same dataset the practice models were trained on** (Shrestha et al. 2024).
  Do not score the practice models on Ames or Lincoln as if they were unseen.

## Final interface: what Agents 2 and 3 read

All paths are relative to the repository root. `ml/data/challenge/` is committed. The raw
folder and `ml/data/processed/` are git-ignored and rebuilt by the commands below.

| File | Rows | Read by | Shape |
|---|---|---|---|
| `ml/data/challenge/plots.parquet` | 2,291 (every ground-truth plot, 5 sites) | Agent 2 `--plots` | `plot_id, year, site_id, field_id, experiment, range, row, genotype, nitrogen_lb_ac, irrigated, planting_date, final_yield, latitude, longitude`, … |
| `ml/data/challenge/benchmark_plots.parquet` | 1,026 plots with a usable satellite image (960 with yield) | **Agent 3 `--plots`** | same columns as `plots.parquet`; the benchmark population, identical to Agent 2's table and the canonical `sydag26` |
| `ml/data/challenge/images.parquet` | 2,372 usable images | Agent 2 `--manifest` | `path` (relative to `ml/data/raw/challenge/`), `modality` (satellite/uav), `site_id`, `time_point` (int), `plot_id`, `date`, `experiment, range, row, tp_label, image_id` |
| `ml/data/challenge/acquisition_dates.parquet` | 54 passes, both modalities, 6 sites | Agent 2 `--acquisitions` | `site_id, year, modality, time_point` (int), `tp_label, date, day_of_year, location_label` |
| `ml/data/challenge/satellite_acquisitions.parquet` | 36 satellite passes | Agent 3 `--acquisitions` | `site_id, year, tp, date` (satellite only: Agent 3 rejects two dates for one pass) |
| `ml/data/challenge/satellite_manifest.parquet`, `uav_manifest.parquet` | 2,012 / 430 files | audit, humans | every file incl. unmatched and duplicates: `match_status, use, is_duplicate`, raster metadata |
| `ml/data/challenge/observations.parquet` | 2,372 | reference | usable images: `plot_id, date, source, time_point, tp_label, image_path, image_id, days_after_planting` |
| `ml/data/challenge/sites.parquet`, `drive_inventory.parquet`, `challenge_manifest.json` | – | humans | sites; every Drive file (no ids); counts, anomalies, schemas |
| `ml/data/processed/sydag26/` | 1,026 plots, 1,960 observations | Agent 3 `--canonical sydag26`, `train` | canonical CSVs: `plots, observations` (ndvi, ndre, gndvi, evi, nir, `time_point`), and the **context** tables `weather, soil, county_yields, sites` |
| `ml/experiments/reports/sydag26_dataset_profile.md` | – | humans | profile of the canonical dataset |

Conventions: `modality` is satellite | uav. `time_point` is the pass number per site and
modality, as an int (`tp_label` is the "TP3" spelling). `date` is the acquisition date, and
all dates are `datetime64` in Parquet. `site_id` uses the ground-truth spelling (`Ames`,
`Crawfordsville`, `Lincoln`, `MOValley`, `Scottsbluff`). `year` is 2022. `final_yield` is
bu/ac at 15.5% moisture. `planting_date` is null only on fill plots, which have no yield.

## Commands

From `ml/` (the backend's environment with the `ml` group). **`--dataset` goes before the
command.**

```bash
PY="uv run --project ../backend --group ml python"

# 0. The organizers' folder at ml/data/raw/challenge/ (Groundtruth/ or GroundTruth/,
#    Satellite/, UAV/). This session fetched each file by id from a Drive listing:
#    https://drive.usercontent.google.com/download?id=<id>&export=download

# 1. Inventory + joins + raster metadata -> ml/data/challenge/  (6 s; restartable, cached)
$PY -m soilsignal_ml challenge --inventory data/challenge/drive_inventory.parquet
#    (tonight's run used --drive-listing data/raw/challenge/_drive_listing instead)

# 2. Canonical tables -> ml/data/processed/sydag26/  (about 10 s; NOAA sometimes drops a
#    connection: just rerun). County yields need SOILSIGNAL_NASS_API_KEY in backend/.env.
$PY -m soilsignal_ml --dataset sydag26 ingest
$PY -m soilsignal_ml --dataset sydag26 validate
#    `profile` always overwrites the practice report; the challenge profile was written to
#    experiments/reports/sydag26_dataset_profile.md with ingest.profile.build_profile().

# 3. Downstream, as smoke-tested (Agent 2's code is on PR #15's branch):
$PY -m soilsignal_ml.imagery run --data-root data/raw/challenge \
    --manifest data/challenge/images.parquet --plots data/challenge/plots.parquet \
    --acquisitions data/challenge/acquisition_dates.parquet
$PY progressive_experiment.py --imagery-table data/interim/imagery/satellite_features.parquet \
    --plots data/challenge/benchmark_plots.parquet --name sydag26
#    or straight from the canonical tables (no Agent 2 step):
$PY progressive_experiment.py --canonical sydag26 --name sydag26-canonical

# 4. Optional database
$PY -m soilsignal_ml challenge-sql
cd data/challenge/postgres && psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f load.sql

# Tests
uv run --project ../backend --group ml --group dev pytest tests/test_challenge.py
```

## Records only vs context (the benchmark)

The benchmark is **records only** (hybrid, nitrogen, irrigation, planting date), then
records **+ satellite TP1**, **+ TP1–TP2**, and so on. Public context is kept apart:

- Every stage, records only included, is scored on the same plots: those with a satellite
  image (`benchmark_plots.parquet`). Passing the full `plots.parquet` to Agent 3 would add 652
  MOValley and Scottsbluff plots that can never have imagery, plus two imagery-free sites in
  leave-one-site-out.
- `plots.parquet` carries no weather, soil or county-yield column. That is checked by
  `test_records_only_baseline_has_no_weather_or_soil`, which also feeds the file through
  Agent 3's contract and asserts that its record set is at most `genotype, nitrogen_lb_ac,
  irrigated, planting_day_of_year`.
- Agent 2's `records_only` rows carry only planting-known columns (checked on the real run:
  no weather, soil or county columns anywhere in its 143 columns).
- Agent 3's `--canonical` loader reads only the canonical `plots` and `observations`. The
  `weather`, `soil` and `county_yields` tables in `ml/data/processed/sydag26/` are **optional
  enrichment**, available for a separate "records + context" comparison later. They are used
  automatically only by the legacy `train` pipeline, whose feature-set screening names them
  explicitly (`Crop plus weather`, `… soil`).
- The NASS key is in `backend/.env` (git-ignored, never committed). County yields for 2013 to
  2022 match the practice profile exactly. NOAA's nearest-station search is not stable
  between runs for Lincoln (Lincoln 8 ENE, 4.2 km, or Lincoln Airport, 12.6 km). That changes
  the context weather only.

## What I inspected

| Source | How | Result |
|---|---|---|
| `Documentation/Readme.md`, `Documentation.ipynb` | Drive connector, decoded locally | Layout, file naming, band list, notebook code (see anomalies) |
| `Groundtruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv` | **byte-exact** (289,497 bytes = Drive size) | 2,291 plots, 5 sites, 18 columns |
| `Groundtruth/DateofCollection.xlsx` | byte-exact (8,444 bytes; zip CRCs pass) | 54 site/modality/TP dates (6 sites incl. North Platte) |
| `Satellite/`, `UAV/` listings | Drive metadata (name, size, upload time) for every file | 2,446 entries → 2,442 files (4 listed twice) |
| All images | direct download by file id; size checked against Drive per file | 2,426 files, all read; the 16 Lincoln second uploads are byte-identical |

Two sample GeoTIFFs reproduce the producer's embedded per-band statistics to 4 decimals. For
`Crawfordsville-4353-9-42`, NDVI, NDRE, GNDVI, EVI and NIR match the practice pipeline
(`backend/data/practice/shrestha2024.json`) to 5 decimals, and the centroid is within 0.17 m.

## What I implemented

All in `ml/soilsignal_ml/ingest/`, inside the existing pipeline:

| Module | Does |
|---|---|
| `challenge.py` | Ground-truth loader and cleaning, `DateofCollection.xlsx` parser, filename parser, file inventory from disk and/or a Drive listing, manifest joins (match status, duplicates, days after planting), restartable raster-metadata pass, plot coordinates, and the downstream views (`images`, `satellite_acquisitions`) |
| `imagery.py` | Per-file metadata: GeoTIFF (band order from the GDAL band descriptions, CRS, pixel size, bbox, valid/padding pixels, centroid, per-band means, sha256) and PNG (size, alpha mask, valid pixels, means) |
| `challenge_report.py` | Writes the Parquet outputs (dates as datetime64) and `challenge_manifest.json`. Drops Drive ids and machine paths |
| `dataset_adapter.py` → `HackathonDatasetAdapter` (`sydag26`) | Canonical `plots`, `observations` (ndvi, ndre, gndvi, evi, nir; `time_point`), `sites`. Indices come from Agent 2's `ml/data/interim/imagery/canonical_observations.csv` when it exists, else from the GeoTIFFs |
| `challenge_postgres.py` | CSV + `load.sql`; PostGIS points and footprints when the extension exists |
| `__main__.py` | `challenge` and `challenge-sql` commands |

Tests: `ml/tests/test_challenge.py` (20). They build a synthetic copy of the folder and check
the key, cleaning, date joins, every match status, duplicates, metadata, restartability,
private fields, the adapter, the lower-case `Groundtruth` folder, the downstream shapes
(Agent 3's own contract functions) and the records-only guard. Three tests use the real
files when present.

## Exact folder assumptions

A local copy of the shared folder at `ml/data/raw/challenge/` (override with `--raw`):

```
Groundtruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv  # folder names matched case-insensitively
Groundtruth/DateofCollection.xlsx          # Sheet1: Location, Date, Image, time
Satellite/<Location>/TP1..TP6/<Location>-TP<n>-<experiment>_<range>_<row>.TIF
UAV/<Location>/TP1..TP3/<Location>-TP<n>-<experiment>_<range>_<row>.PNG
Documentation/                             # not read by the code
```

- Every file under `Satellite/` and `UAV/` is inventoried at any depth. A file outside the
  `<Sensor>/<Location>/<TP>/` pattern gets `match_status = folder_name_mismatch` or
  `unparseable_name`; it is never skipped.
- The folder's location and TP must equal the name's location and TP.
- Modality is decided by the top folder. The extension must be TIF/TIFF (satellite) or PNG (UAV).
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
  `practice_plot_id` = the practice pipeline's id for the same plot (no year), computed with
  `dataset_adapter.plot_id`. It is also the imagery stage's default id when run without the
  manifest.
- **Year:** the CSV has no year column. It is the planting year, 2022 for every site. Fill
  plots take their site's year, and the loader raises if a site spans two years.
- **Image → plot:** exact match on (site_id, experiment, range, row). Image → date: exact
  match on (site_id, modality, time_point) in `acquisition_dates`.
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

## Real-data smoke test

Run on the downloaded subset, to prove the hand-offs, not to pick a model. Outputs were
written to a scratch folder, not committed. Agent 2's code was run from a separate checkout
of PR #15's branch and was not merged into this PR.

1. **Agent 1 → Agent 2.** `soilsignal_ml.imagery run --manifest images.parquet --plots
   plots.parquet --acquisitions acquisition_dates.parquet` read all 1,960 satellite and 412
   UAV images in 44 s. It wrote 7,182 rows = 1,026 plots × (records only + TP1–TP6).
   - Every `plot_id` is in `plots.parquet`, and `site_id` and `final_yield` agree row for row.
   - Each site's cutoff dates equal `acquisition_dates.parquet`, and the per-site/TP image
     counts equal the usable counts here.
   - The `records_only` rows hold planting-known columns only, and none of the 143 columns
     is weather, soil or county data.
   - The first attempt found one interface bug: Python `date` objects in Parquet come back as
     `object`, and Agent 2 calls `.dt` on the manifest's `date`. All Parquet dates are now
     datetime64.
2. **Agent 2 → Agent 3.** `progressive_experiment.py --imagery-table satellite_features.parquet
   --plots benchmark_plots.parquet --models mean catboost --fast` (headline: leave-one-site-out,
   3 folds). A first attempt with the full `plots.parquet` pulled in the two sites that have
   no imagery, which is why `benchmark_plots.parquet` exists:

   | Stage | Acquired | Median DAP | MAE | ΔMAE vs records (95% CI) | Better in |
   |---|---|---|---|---|---|
   | Records only | – | – | 94.0 | reference | – |
   | + TP1 | Jul 10–18 | 57 | 92.5 | +1.5 (+1.0 to +2.0) | 2/3 sites |
   | + TP1–TP2 | Jul 20–Aug 6 | 70 | 84.4 | +9.6 (+9.0 to +10.4) | 3/3 |
   | + TP1–TP3 | Aug 2–Sep 3 | 83 | 82.9 | +11.1 (+10.3 to +12.0) | 3/3 |
   | + TP1–TP4 | Aug 31–Sep 13 | 112 | 83.9 | +10.2 (+9.2 to +11.1) | 3/3 |
   | + TP1–TP5 | Sep 11–Oct 1 | 120 | 85.5 | +8.6 (+7.5 to +9.7) | 2/3 |
   | + TP1–TP6 | Sep 24–Oct 9 | 128 | 89.9 | +4.1 (+3.2 to +5.2) | 2/3 |

   960 plots, 3 sites, primary model CatBoost with `--fast` settings. Agent 3's own criteria:
   stages TP2–TP4 pass the accuracy checks; no stage passes all five (90% interval coverage
   is about 60–67% under leave-one-site-out with 3 sites, as their handoff predicts).
   Records-only MAE (94.0) is identical to the direct canonical run below, so both paths
   score the same plots with the same records.

3. **Agent 1 → Agent 3 directly.** `progressive_experiment.py --canonical sydag26 --models mean
   catboost --fast` runs end to end too: 5 indices per pass, accumulated by Agent 3. MAE was
   94.0 for records only, 89.5 for + TP1–TP2 and 94.7 for + TP1–TP6.

With 3 sites whose yield levels differ several-fold (Lincoln's 2022 drought), leave-one-site-out
MAE is dominated by the site level. Treat these numbers as plumbing checks, and read Agent 3's
real run with all models.

## For Agent 2

- Run with **all three** Agent 1 inputs: `--manifest ml/data/challenge/images.parquet`,
  `--plots ml/data/challenge/plots.parquet` and `--acquisitions
  ml/data/challenge/acquisition_dates.parquet`. Without `--manifest`, your parser builds
  practice-style ids (`Ames-4231-17-3`), which do not match `plots.parquet`
  (`2022-Ames-4231-17-3`). `plots.parquet` keeps that id as `practice_plot_id` for
  cross-reference.
- `images.parquet` lists usable images only (matched, first copy of any duplicate upload).
  `satellite_manifest.parquet` / `uav_manifest.parquet` list every file, with `match_status`
  and the raster metadata (`band_names`, `crs_epsg`, centroid, per-band means `mean_red` …
  `mean_deep_blue` over valid pixels) to check your extraction against.
- `HackathonDatasetAdapter` reads your `data/interim/imagery/canonical_observations.csv` when it
  exists, so the canonical tables do not decode the TIFFs a second time.

## For Agent 3

- Inputs: **`--plots ml/data/challenge/benchmark_plots.parquet`** with Agent 2's
  `--imagery-table`, plus `--acquisitions ml/data/challenge/satellite_acquisitions.parquet`
  for the `--tp-features` / `--tp-observations` routes. `--canonical sydag26` also works.
- Use `benchmark_plots.parquet`, not `plots.parquet`. The contract keeps every plot with a
  yield, so the full table would add the 652 MOValley/Scottsbluff plots that have no imagery.
  The benchmark population is 960 plots with a yield and at least one satellite image.
- There is no `harvest_date` in the ground truth, so your Oct 15 default applies.
- Timing: all images fall 54 to 151 days after planting (Jul 10 to Oct 9). The first pass per
  site is Crawfordsville 07-10, Ames 07-15, Lincoln 07-18. Nothing is observed before July.
- Sparse panel: only Ames TP1–TP5 follows the same ~94 plots. At Crawfordsville and Lincoln any
  two passes share only 8 to 42 plots. `plots.parquet` → `satellite_time_points` lists the
  passes per plot, and `challenge_manifest.json` → `images.satellite.time_points_per_plot_by_site`
  counts them.
- Within-site NDVI–yield correlation by pass (`sydag26_dataset_profile.md`):

  | Site | TP1 | TP2 | TP3 | TP4 | TP5 | TP6 |
  |---|---|---|---|---|---|---|
  | Ames | -0.00 | 0.36 | 0.65 | 0.69 | 0.60 | 0.29 |
  | Crawfordsville | 0.19 | 0.17 | 0.38 | 0.34 | 0.04 | -0.31 |
  | Lincoln | 0.46 | 0.64 | -0.22 | -0.55 | -0.52 | -0.54 |

- The Ames 75 lb N block (experiment 4233) has no images in this subset.

## What tomorrow's humans should verify first

1. Run Agent 3's full model set on the chain above (step 3 of [Commands](#commands)) and read
   `summary.md` critically. The smoke test used 2 models and `--fast`.
2. When the full dataset arrives, rerun step 1 on it. Then check `challenge_manifest.json`:
   `raster_metadata.satellite.metadata_status` should be all `read`, `band_order_not_ok` and
   `partial_zero_pixel_files` empty, and `crs_epsg_by_site` one EPSG per site. The same code
   and names apply.
3. Ask the organizers whether **UAV for Crawfordsville and Lincoln** is coming.
4. Look at 3 or 4 images by eye (one per site, early and late pass) against `images.parquet`.
5. Decide the evaluation split given the practice-model overlap (see TL;DR).
6. `pyarrow` is in the backend's `ml` dependency group (training only). PR #15 adds it too, so
   expect a trivial `uv.lock` conflict; regenerate the lock rather than hand-merging it.
7. The 5 end-to-end ML tests still skipped need a local `train` → `export` → `showcase` run.

## Coordination-doc post

> **[Agent 1]** Challenge ingestion is on PR #14 (rebased on main after #13). Guide:
> `AGENT1_HANDOFF.md`.
> **Plot key:** `plot_id = {year}-{site}-{experiment}-{range}-{row}` (e.g. `2022-Ames-4231-17-3`);
> `practice_plot_id` keeps the practice-style id.
> **Files (committed, `ml/data/challenge/`):**
> - `plots.parquet` (all 2,291 GT plots) → Agent 2 `--plots`
> - `benchmark_plots.parquet` (1,026 imaged plots) → **Agent 3 `--plots`**. The full table would add 2 sites with no imagery to your records-only stage and site folds.
> - `images.parquet` → Agent 2 `--manifest` (path, modality, site_id, time_point int, plot_id, date)
> - `acquisition_dates.parquet` → Agent 2 `--acquisitions` (both modalities)
> - `satellite_acquisitions.parquet` → Agent 3 `--acquisitions` (site_id, year, tp, date; satellite only)
>
> **Conventions:** `time_point` is an int per site and modality (`tp_label` = "TP3"); dates are
> datetime64; site ids use the ground-truth spelling (MOValley etc.).
> **Canonical dataset:** `sydag26` (`HackathonDatasetAdapter`, the only challenge adapter). Build
> with `python -m soilsignal_ml --dataset sydag26 ingest` (`--dataset` goes before the command).
> **Records only** = genotype, nitrogen, irrigation, planting date. Weather, soil and county
> yields are separate context tables in `data/processed/sydag26/`, never plot columns.
> **Agent 2:** always pass `--manifest`, or your ids won't match `plots.parquet`.
> **Smoke test on the real subset passed:** Agent 1 → Agent 2 `imagery run` (7,182 rows) →
> Agent 3 `--imagery-table` + `benchmark_plots` (960 plots, 3 sites, LOSO). Plumbing numbers
> only (2 models, `--fast`): records only MAE 94.0; + TP1 92.5; + TP1–TP3 82.9. Fix made on my
> side: Parquet dates are datetime64 (Agent 2 uses `.dt` on the manifest date).
> **Subset facts:** 3 sites, sparse per-plot TP coverage (only Ames TP1–5 is a panel), UAV at
> Ames only, first pass mid-July, README band order wrong (the files are R,G,B,NIR,RE,DB).
