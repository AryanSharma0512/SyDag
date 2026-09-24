"""
Vegetation indices and their in-season summaries.

Indices are computed only from bands the sensor actually has; nothing is filled
in for a missing band. Summaries use only images taken on or before the forecast date.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import date

import numpy as np

from app.features.inputs import CanopyObservation

Bands = Mapping[str, np.ndarray]

# name -> (required bands, formula on surface reflectance 0-1)
INDEX_FORMULAS: dict[str, tuple[tuple[str, ...], Callable[[Bands], np.ndarray]]] = {
    "ndvi": (("nir", "red"), lambda b: (b["nir"] - b["red"]) / (b["nir"] + b["red"])),
    "ndre": (
        ("nir", "red_edge"),
        lambda b: (b["nir"] - b["red_edge"]) / (b["nir"] + b["red_edge"]),
    ),
    "gndvi": (("nir", "green"), lambda b: (b["nir"] - b["green"]) / (b["nir"] + b["green"])),
    # Enhanced vegetation index (Huete et al. 2002), less prone to saturation over dense canopy.
    "evi": (
        ("nir", "red", "blue"),
        lambda b: 2.5 * (b["nir"] - b["red"]) / (b["nir"] + 6 * b["red"] - 7.5 * b["blue"] + 1),
    ),
}
INDEX_NAMES = tuple(INDEX_FORMULAS)
# Indices compared against the same-day mean of neighbouring plots.
RELATIVE_INDICES = ("ndvi", "ndre")
# An image within this many days of estimated silking counts as "at silking".
NEAR_SILKING_DAYS = 10


def compute_indices(bands: Bands) -> dict[str, np.ndarray]:
    """Per-pixel indices for whichever indices the available bands support.
    Values outside [-1, 1] (e.g. a near-zero EVI denominator) become NaN."""
    out: dict[str, np.ndarray] = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        for name, (required, formula) in INDEX_FORMULAS.items():
            if all(band in bands for band in required):
                values = np.asarray(formula(bands), dtype=float)
                out[name] = np.where(np.abs(values) <= 1, values, np.nan)
    return out


def _series(observations: Sequence[CanopyObservation], index: str) -> list[tuple[date, float]]:
    return sorted(
        (o.day, float(o.values[index]))
        for o in observations
        if index in o.values and np.isfinite(o.values[index])
    )


def canopy_features(
    observations: Sequence[CanopyObservation],
    reference: Sequence[CanopyObservation],
    as_of: date,
    silking: date | None,
) -> dict[str, float]:
    """Summaries of each index over images taken on or before as_of.
    Returns nothing for an index that has no image yet."""
    seen = [o for o in observations if o.day <= as_of]
    features: dict[str, float] = {}
    if seen:
        features["canopy_images_to_date"] = float(len(seen))
        features["days_since_canopy_image"] = float((as_of - max(o.day for o in seen)).days)
    ref_by_day = {o.day: o.values for o in reference if o.day <= as_of}

    for index in INDEX_NAMES:
        series = _series(seen, index)
        if not series:
            continue
        days = np.array([(d - series[0][0]).days for d, _ in series], dtype=float)
        values = np.array([v for _, v in series])
        latest_day, latest = series[-1]
        features[f"{index}_current"] = latest
        features[f"{index}_mean_to_date"] = float(values.mean())
        features[f"{index}_max_to_date"] = float(values.max())
        features[f"{index}_min_to_date"] = float(values.min())
        if len(series) >= 2:
            features[f"{index}_change_from_previous"] = float(values[-1] - values[-2])
            # Least-squares trend in index units per 10 days.
            features[f"{index}_trend_per_10d"] = float(np.polyfit(days, values, 1)[0] * 10)
            features[f"{index}_area_to_date"] = float(np.trapezoid(values, days))
        if silking is not None:
            near = [(abs((d - silking).days), v) for d, v in series]
            gap, value = min(near)
            if gap <= NEAR_SILKING_DAYS:
                features[f"{index}_near_silking"] = value
        if index in RELATIVE_INDICES:
            ref = ref_by_day.get(latest_day, {}).get(index)
            if ref is not None and np.isfinite(ref):
                features[f"{index}_vs_site_mean"] = latest - float(ref)
    return features
