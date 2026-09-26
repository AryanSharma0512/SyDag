# Feature quality report (imagery)

**Status: the full extraction has not run on the challenge imagery yet.** This container can
reach the Google Drive folder only through the Drive connector, which returns files as base64
text. Bulk download is blocked (the environment's network policy denies `drive.google.com`).
What follows is (1) what was checked on the real files through the connector, (2) the checks
the pipeline runs, and (3) proof on synthetic data that each check fires. The run on the mini PC
writes the real report to `ml/data/interim/imagery/reports/feature_quality_report.md`. Copy it
over this file when it exists.

## 1. Checked on the real data (Drive folder "Sample data / Sydag Data")

Layout, as listed on 2026-09-26:

```
Sydag Data/
  Satellite/{Ames, Crawfordsville, Lincoln}/TP<n>/<Site>-TP<n>-<exp>_<range>_<row>.TIF   (~24 KB each)
  UAV/Ames/TP<n>/<Site>-TP<n>-<exp>_<range>_<row>.PNG                                     (~0.4-0.5 MB each)
  Groundtruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv, DateofCollection.xlsx
  Documentation/Readme.md, Documentation.ipynb
```

Only `UAV/Ames` existed when listed. The brief expects UAV at all three sites, so either the
upload was still in progress or the subset has UAV for Ames only. The run's report will say which.

One TIFF was downloaded and inspected: `Satellite/Ames/TP5/Ames-TP5-4231_11_3.TIF`.

| Property | Value |
|---|---|
| Size | 12 x 21 pixels, 6 samples per pixel, uint16, LZW, 128 x 128 tiles, interleaved |
| Pixel size | 0.3 m (pansharpened Pléiades Neo) |
| CRS | WGS 84 / UTM zone 15N (EPSG 32615) |
| GDAL nodata | 0 (padding outside the plot polygon is 0 in every band) |
| Band descriptions, in file order | Red (0.618-0.689 µm), Green (0.533-0.59), Blue (0.446-0.52), NIR (0.768-0.888), Red Edge (0.696-0.749), Deep Blue (0.416-0.456) |
| Embedded band means (DN) | red 439, green 584, blue 393, NIR 3318, red edge 1831, deep blue 350, so NDVI of the band means is ~0.77 |
| Embedded band minima (DN) | red 1, blue 1, deep blue 69, green 104 |

Findings:

- **The Readme's band order is wrong for these files.** It lists NIR, red edge, red, green,
  blue, deep blue. The files' own GDAL band descriptions, and the NIR-dominant band means, say
  red, green, blue, NIR, red edge, deep blue. That is also the order the practice pipeline uses
  (`BANDS` in `ingest/dataset_adapter.py`). The extractor reads the descriptions of every file
  and records `band_order_source` and `band_order_agrees`. A file whose descriptions contradict
  the configured order is flagged (`band_order_mismatch`).
- The file carries several IFDs from in-place metadata edits. The header points to the current
  one, and the reader uses `pages[0]` only.
- Some plot pixels have DN 1 (reflectance 0.0001) in red or blue. They are positive, so they
  stay valid under the masking rule. `n_near_zero` counts them per image so the real run shows
  how common they are before anyone changes the rule.
- `DateofCollection.xlsx`, sheet 1, gives these acquisition dates for the three subset sites
  (2022). Sheet 2 is scratch work and is ignored.

| Site | Sat TP1 | TP2 | TP3 | TP4 | TP5 | TP6 | UAV TP1 | TP2 | TP3 |
|---|---|---|---|---|---|---|---|---|---|
| Ames | 07-15 | 07-23 | 08-10 | 08-31 | 09-11 | 09-24 | 07-12 | 07-26 | 08-10 |
| Crawfordsville | 07-10 | 07-20 | 08-02 | 09-13 | 10-01 | 10-09 | 07-12 | 07-26 | 08-11 |
| Lincoln | 07-18 | 08-06 | 09-03 | 09-11 | 09-19 | 09-27 | 07-13 | 07-28 | 08-04 |

The earliest satellite image at every site is mid-July, so "TP1" is already mid-season. The
planting dates in the ground truth will say how many days after planting that is. Lincoln's
TP4-TP6 are 8 days apart, and those are the pairs the "implausible change between close
acquisitions" check is designed for. At Ames the first UAV flight (07-12) comes 3 days before
the first satellite image.

## 2. What the run checks

Nothing is deleted or corrected. Each check writes rows to `quality_flags.csv` and a count to
the report. Flags marked *review only* compare dates of the same plot and are never features.

| Flag | Rule |
|---|---|
| `corrupt` | file can't be decoded (the run continues) |
| `unparsed_path` | site / TP / plot not readable from file name or folders |
| `unexpected_band_count` | not 6 bands |
| `band_order_unknown` | band count doesn't match the configured order and the file has no band descriptions; no statistics are computed |
| `band_order_mismatch` | the file's band descriptions contradict the configured order |
| `brightest_band_not_nir` | a vegetated image (NDVI > 0.5) whose brightest band isn't NIR: an independent band-order check |
| `no_valid_pixels`, `low_valid_pixels` | < 10 valid pixels, or < 90% of plot pixels valid |
| `small_footprint` | valid pixels < 50% of the median plot in the same acquisition |
| `fewer_pixels_than_plot_median` | < 50% of the plot's median over its images (review only) |
| `saturated_pixels` | plot pixels with reflectance > 1 |
| `partial_zero_pixels` | > 5% of plot pixels have a zero in some bands but not all |
| `index_out_of_range` | per-pixel index outside [-1, 1] (set to NaN; happens to EVI when its denominator nears 0) |
| `negative_ndvi` | plot-mean NDVI < 0 |
| `duplicate_content` | byte-identical files (SHA-1) |
| `duplicate_plot_tp` | two files for the same plot and TP (the one with more valid pixels is used) |
| `missing_tp` | a plot lacks a usable image at a TP its site was imaged |
| `no_acquisition_date`, `dates_not_increasing` | date table gaps or TP order that disagrees with dates |
| `image_not_in_plots_table` | imaged plot missing from the ground truth |
| `implausible_change` | NDVI change from the previous image > 0.15 from the site's median change *and* > 5 robust SD, or > 0.30 within 14 days (review only) |
| `footprint_change` | valid-pixel count halves or doubles between consecutive images (review only) |

The report also tabulates images per site and TP, masking statistics per site (pixels, valid
fraction, saturated and near-zero pixels), the brightest band per TP, NDVI/NDRE/EVI by site and
TP, plots-table coverage, and rows per cutoff. `visual_qa/` holds contact sheets (false colour
NIR/R/G and NDVI, fixed stretch) for the highest, median and lowest NDVI plot of every site x TP,
the lowest valid fractions, and flagged images.

## 3. Validation on synthetic data

`python -m soilsignal_ml.imagery synthetic` writes a dataset in the real layout and format
(21 x 12 px, 0.3 m, LZW, GDAL descriptions, nodata 0) and plants one of each defect. At full
scale (3 sites x 130 plots x 6 TPs = 2,339 TIFFs, 1,170 UAV PNGs) every planted defect was flagged:

| Planted | Flagged as |
|---|---|
| truncated TIFF | `corrupt`, and `missing_tp` for that plot |
| 4-band TIFF | `unexpected_band_count` (NDVI still computed from the described bands; NDRE empty) |
| file copied over another plot's | `duplicate_content` on both paths |
| every 5th plot pixel at DN 12,000 | `saturated_pixels`, `low_valid_pixels` (those pixels excluded) |
| footprint clipped to 19 of 124 pixels | `small_footprint`, `fewer_pixels_than_plot_median`, `footprint_change` |
| deleted file | `missing_tp`; the TP4 row carries TP3 forward with `days_since_latest_image` = 18 |
| TP5 image replaced by bare soil | `implausible_change` (NDVI -0.55 in 18 days against a site median of -0.05), and again on recovery at TP6 |

These cases are asserted in `ml/tests/test_imagery.py::test_every_planted_defect_is_flagged`.
