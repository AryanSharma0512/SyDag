"""
Plot imagery -> point-in-time features for progressive (TP1..TP6) yield models.

    discover     find plot images under a data root (or read a manifest); plots; dates
    satellite    one GeoTIFF: band layout, valid-pixel mask, band and index statistics
    extract      batch extraction with a content-hash cache (resumable, parallel)
    progressive  records_only, TP1..TPn rows; each cutoff sees only imagery through it
    qa           quality flags, the quality report, visual-QA contact sheets
    uav          lightweight RGB features from UAV PNGs, joined by flight date
    dictionary   the feature dictionary, generated from the column lists
    pipeline     the whole run, and the benchmark
    synthetic    a small fake dataset in the same layout, for tests and benchmarks

Run from ml/: uv run --project ../backend --group ml python -m soilsignal_ml.imagery --help
"""
