"""
Progressive (early-signal) experiments: how early does satellite imagery add enough to a
yield forecast to support in-season scouting decisions?

    contract   what Agent 1 (plots, acquisition dates) and Agent 2 (TP features) hand over,
               normalized into one ExperimentData, with leakage checks
    stages     Records only, then + imagery through TP1 ... TP6 (or by days after planting,
               or by calendar date), with the acquisition timing of each stage
    folds      grouped validation: site, year, site x year, 2022 -> 2023, and the
               optimistic contrasts (field blocks, random plots) that are never the headline
    intervals  nested conformal intervals (constant width) and conformalized quantile
               regression (per-plot width, used for the downside-risk scouting ranking)
    metrics    accuracy, ranking, interval and scouting-recall metrics
    criteria   the transparent "earliest useful forecast" checks; no winner is hardcoded
    runner     runs every stage x model x validation scheme and collects the results
    report     CSV / JSON / Markdown / imagery_ablation.json / GeoJSON writers
    figures    MAE, delta MAE, interval width and scouting recall by stage
    spatial    Moran's I of residuals (the evidence behind the PostGIS recommendation)
    synthetic  a structurally realistic fixture for testing; never a result

Entry point: `python progressive_experiment.py --help` from ml/.
"""
