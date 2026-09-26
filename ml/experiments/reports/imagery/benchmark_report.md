# Benchmark report (imagery extraction)

**Measured on synthetic data at the challenge's scale, in the cloud container** (4 vCPUs,
Python 3.13). The challenge files couldn't be bulk-downloaded here (see
`feature_quality_report.md`). Rerun on the mini PC with the real data:

```bash
cd ml
uv run --project ../backend --group ml python -m soilsignal_ml.imagery benchmark --data-root <Sydag Data folder>
```

It writes `ml/data/interim/imagery/reports/benchmark_report.md`. Copy it over this file.

## Data used

`python -m soilsignal_ml.imagery synthetic <dir> --plots-per-site 130 --uav-scale 25`:
3 sites x 130 plots x 6 TPs = 2,339 satellite TIFFs (one deliberately missing) and 1,170 UAV
PNGs (UAV at all three sites, which is more than the Drive subset has).

| | Synthetic | Real (one file checked) |
|---|---|---|
| TIFF pixels | 21 x 12, 6 bands, uint16, LZW | 12 x 21, 6 bands, uint16, LZW |
| TIFF file size | 2.7 KB | 24 KB (mostly repeated GDAL metadata from in-place edits) |
| UAV PNG size | ~270 KB | ~400-490 KB |

The pixel work is the same. Real TIFFs are larger on disk because of metadata, which adds
read and hash time but not decode time. Real UAV PNGs are about 1.7x larger, so expect UAV
throughput at roughly half the synthetic rate.

## Satellite, per image (median of 300 TIFFs, one process)

| Step | ms |
|---|---|
| read bytes | 0.06 |
| decode (tifffile) + band layout | 0.41 |
| mask + statistics + indices (6 bands x 7 stats, 5 indices x 7 stats, erosion core, cover) | 1.40 |

## Throughput (cold cache, including SHA-1 hashing)

| Workers | Images | Seconds | Images/s |
|---|---|---|---|
| 1 | 300 | 0.62 | 480 |
| 4 | 300 | 0.22 | 1,372 |

| Stage (full synthetic set, 4 workers) | Time |
|---|---|
| satellite extraction, 2,339 TIFFs | ~1.5-2 s |
| UAV extraction, 1,170 PNGs | ~12-16 s (75-100 PNGs/s) |
| QA flags, progressive table (2,730 rows x 143 columns), UAV join, reports, 3 contact sheets | ~15 s |
| whole `run`, cold cache | 33 s |
| whole `run`, warm cache (nothing re-decoded) | 16 s |

## What this means

Processing speed isn't a constraint for this dataset. The whole satellite subset (3 sites x
6 TPs x 100-150 plots, i.e. 1,800-2,700 TIFFs) should extract in a few seconds on any recent
machine, so nothing has to be sampled or deferred. The rest of a run is pandas row assembly,
which could be vectorised if the dataset grew 100-fold.

Caching: each image's statistics are stored under the SHA-1 of its bytes plus
`EXTRACTOR_VERSION` in `cache/satellite_stats.jsonl` (UAV: `cache/uav_stats.jsonl`), appended
and flushed image by image. An interrupted run resumes by rerunning the same command, and a
changed file is re-extracted automatically. Bump `EXTRACTOR_VERSION` (`imagery/satellite.py`) or
`UAV_VERSION` (`imagery/uav.py`) after changing masking or statistics.
