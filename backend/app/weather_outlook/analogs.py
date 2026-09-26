"""
Analog weighting and category probabilities.

Seasons are compared on descriptors standardized within the site and the date (the
library's own seasons on the same month-day), with the median and interquartile range so
one extreme season cannot set the scale. Similar seasons get more weight through a
Gaussian kernel; the bandwidth widens until the effective number of seasons is not too
small, so a handful of close analogs never carries the whole outlook.

Categories are fixed before any weighting: each trajectory's score is ranked against the
unweighted historical ensemble (lower third adverse, middle typical, upper third
favorable). Weights then move probability between those fixed categories.
"""

import math
from dataclasses import dataclass

import numpy as np

CATEGORIES = ("adverse", "typical", "favorable")
TERCILES = ("below", "near", "above")
IQR_TO_SIGMA = 1.349  # IQR of a normal distribution in standard deviations
MAD_TO_SIGMA = 1.4826
BANDWIDTH_STEP = 1.25
MAX_WIDENINGS = 40


def effective_sample_size(weights: np.ndarray) -> float:
    total = weights.sum()
    return float(total**2 / np.sum(weights**2)) if total > 0 else 0.0


def robust_scale(values: np.ndarray) -> tuple[float, float]:
    """Median and a robust standard deviation (IQR, else MAD); scale 0 if constant."""
    finite = values[~np.isnan(values)]
    if finite.size == 0:
        return math.nan, 0.0
    median = float(np.median(finite))
    q1, q3 = np.percentile(finite, [25, 75])
    scale = float(q3 - q1) / IQR_TO_SIGMA
    if scale <= 0:
        scale = float(np.median(np.abs(finite - median))) * MAD_TO_SIGMA
    return median, scale


def standardize(
    current: np.ndarray, library: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Robust z-scores of the current season and each library season, per descriptor.
    Descriptors that do not vary across the library (e.g. no heat days yet anywhere) or
    are missing for the current season are dropped. Returns (z_current, z_library, used)."""
    used = np.zeros(library.shape[1], dtype=bool)
    zc = np.full(library.shape[1], np.nan)
    zl = np.full(library.shape, np.nan)
    for j in range(library.shape[1]):
        median, scale = robust_scale(library[:, j])
        if scale > 0 and not math.isnan(current[j]):
            used[j] = True
            zc[j] = (current[j] - median) / scale
            zl[:, j] = (library[:, j] - median) / scale
    return zc[used], zl[:, used], used


def distances(zc: np.ndarray, zl: np.ndarray) -> np.ndarray:
    """Root-mean-square difference in z units over the descriptors both seasons have."""
    if zl.shape[1] == 0:
        return np.zeros(zl.shape[0])
    diff = zl - zc
    return np.sqrt(np.nanmean(diff**2, axis=1))


@dataclass(frozen=True)
class Weights:
    weights: np.ndarray  # normalized, sums to 1
    distances: np.ndarray
    bandwidth: float  # used; inf means equal weights
    ess: float
    method: str  # "historical_analogs" or "climatology"


def kernel_weights(dist: np.ndarray, bandwidth: float, min_ess_fraction: float) -> Weights:
    n = len(dist)
    target = min_ess_fraction * n
    h = bandwidth
    for _ in range(MAX_WIDENINGS):
        # Relative to the closest season, so distant seasons cannot underflow every weight.
        w = np.exp(-(dist**2 - np.min(dist) ** 2) / (2 * h**2))
        if w.sum() > 0 and effective_sample_size(w) >= target - 1e-9:
            w = w / w.sum()
            return Weights(w, dist, h, effective_sample_size(w), "historical_analogs")
        h *= BANDWIDTH_STEP
    return equal_weights(n, dist)


def equal_weights(n: int, dist: np.ndarray | None = None) -> Weights:
    w = np.full(n, 1.0 / n)
    return Weights(w, dist if dist is not None else np.zeros(n), math.inf, float(n), "climatology")


def analog_weights(
    current: np.ndarray,
    library: np.ndarray,
    bandwidth: float,
    min_ess_fraction: float,
) -> Weights:
    zc, zl, _ = standardize(current, library)
    if zl.shape[1] == 0:
        return equal_weights(library.shape[0])
    return kernel_weights(distances(zc, zl), bandwidth, min_ess_fraction)


def percentile_rank(value: float, reference: np.ndarray) -> float:
    """Mid-rank percentile of value within reference: ties share the middle of their
    block, so a value equal to every reference value sits at 0.5."""
    below = np.sum(reference < value)
    equal = np.sum(reference == value)
    return float((below + 0.5 * equal) / len(reference))


def tercile(value: float, reference: np.ndarray) -> int:
    """0, 1 or 2: lower, middle or upper third of the reference distribution."""
    p = percentile_rank(value, reference)
    return 0 if p < 1 / 3 else (2 if p > 2 / 3 else 1)


def category_probabilities(
    scores: np.ndarray, weights: np.ndarray, reference: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Per trajectory, its tercile against the reference scores (default: the trajectories
    themselves, unweighted); and the weighted probability of each tercile."""
    reference = scores if reference is None else reference
    cats = np.array([tercile(s, reference) for s in scores])
    probs = np.array([weights[cats == k].sum() for k in range(3)])
    return cats, probs


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Quantile of a weighted sample (linear interpolation between member mid-points)."""
    keep = ~np.isnan(values)
    values, weights = values[keep], weights[keep]
    if values.size == 0:
        return math.nan
    order = np.argsort(values)
    v, w = values[order], weights[order] / weights.sum()
    cum = np.cumsum(w) - w / 2
    return float(np.interp(q, cum, v))


def round_probabilities(probs: np.ndarray) -> list[float]:
    """Whole percentages that still sum to 100 (largest remainder)."""
    raw = np.asarray(probs, dtype=float) * 100
    floor = np.floor(raw)
    short = int(round(100 - floor.sum()))
    order = np.argsort(-(raw - floor))
    for k in order[:short]:
        floor[k] += 1
    return [float(v) / 100 for v in floor]
