"""
Data checks on a canonical dataset. Each returns plain-language problems; an empty
list means the dataset is fit to train on.
"""

import pandas as pd

from soilsignal_ml.ingest.canonical import CanonicalDataset

# Plausible ranges. Corn grain yield above 400 bu/ac has never been recorded in the
# US yield contest; below 0 is impossible.
YIELD_RANGE = (0.0, 400.0)
INDEX_RANGE = (-1.0, 1.0)
DAILY_RAIN_MAX_MM = 400.0  # far above any US daily record in the Corn Belt
TEMP_RANGE_F = (-60.0, 130.0)


def validate(ds: CanonicalDataset) -> list[str]:
    problems: list[str] = []
    p = ds.plots

    if "final_yield" not in p or p["final_yield"].notna().sum() == 0:
        problems.append("target 'final_yield' is missing")
    else:
        y = p["final_yield"].dropna()
        bad = y[(y < YIELD_RANGE[0]) | (y > YIELD_RANGE[1])]
        if len(bad):
            problems.append(f"{len(bad)} yields outside {YIELD_RANGE} bu/ac (unit mix-up?)")
    if p["plot_id"].duplicated().any():
        problems.append(f"{p['plot_id'].duplicated().sum()} duplicate plot rows")
    if pd.to_datetime(p["planting_date"], errors="coerce").isna().any():
        problems.append("planting dates missing or unparseable")
    lat, lon = p["latitude"], p["longitude"]
    if lat.isna().any():
        problems.append(f"{lat.isna().sum()} plots without coordinates")
    if ((lat.abs() > 90) | (lon.abs() > 180)).any():
        problems.append("coordinates out of range")

    o = ds.observations
    if o.duplicated(["plot_id", "date", "source"]).any():
        problems.append("duplicate plot images (same plot, date and source)")
    for index in ds.indices():
        v = o[index].dropna()
        out = v[(v < INDEX_RANGE[0]) | (v > INDEX_RANGE[1])]
        if len(out):
            problems.append(f"{len(out)} {index} values outside [-1, 1]")
    if "ndvi" in o and o["ndvi"].median() < 0.1:
        problems.append("median NDVI below 0.1: bands may be in the wrong order")
    unknown = set(o["plot_id"]) - set(p["plot_id"])
    if unknown:
        problems.append(f"{len(unknown)} imaged plots are not in the plot table")
    early = o.merge(p[["plot_id", "planting_date"]], on="plot_id")
    early = early[pd.to_datetime(early["date"]) < pd.to_datetime(early["planting_date"])]
    if len(early):
        problems.append(f"{len(early)} images dated before planting")

    w = ds.weather
    if len(w):
        if w.duplicated(["site_id", "date"]).any():
            problems.append("duplicate weather days")
        rain = w["prcp_mm"].dropna()
        if (rain < 0).any() or (rain > DAILY_RAIN_MAX_MM).any():
            problems.append("daily rainfall outside 0-400 mm (inches vs mm?)")
        for col in ("tmax_f", "tmin_f"):
            t = w[col].dropna()
            if ((t < TEMP_RANGE_F[0]) | (t > TEMP_RANGE_F[1])).any():
                problems.append(f"{col} outside plausible °F range (°C vs °F?)")
        if (w["tmin_f"] > w["tmax_f"] + 0.5).any():
            problems.append("days with minimum above maximum temperature")
        missing = set(p["site_id"]) - set(w["site_id"])
        if missing:
            problems.append(f"no weather for sites {sorted(missing)}")
    else:
        problems.append("no weather data")
    return problems
