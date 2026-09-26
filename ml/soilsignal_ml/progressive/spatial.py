"""
Are forecast errors spatially clustered within a field?

Moran's I of out-of-fold residuals with k-nearest-neighbour weights (row-standardized),
computed separately in each site-season so between-site offsets don't masquerade as
clustering. A permutation test gives the p-value. I near 0 means errors are scattered;
a clearly positive I means neighbouring plots miss together (drainage, soil or edge
effects the features don't capture), which would justify neighbour-based features or a
residual map layer.

Everything here is a few thousand points: scipy's KD-tree answers it in milliseconds, so
this question does not need a spatial database.
"""

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EARTH_M_PER_DEG = 111_320.0
MIN_PLOTS = 20


def local_xy(lat, lon) -> np.ndarray:
    """Equirectangular metres around the group's centre (fine at field scale)."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    lat0 = np.nanmean(lat)
    x = (lon - np.nanmean(lon)) * EARTH_M_PER_DEG * np.cos(np.radians(lat0))
    y = (lat - lat0) * EARTH_M_PER_DEG
    return np.column_stack([x, y])


def morans_i(values, xy, k: int = 8, permutations: int = 499, seed: int = 42) -> dict:
    z = np.asarray(values, float)
    z = z - z.mean()
    n = len(z)
    k = min(k, n - 1)
    _, idx = cKDTree(xy).query(xy, k=k + 1)
    neighbours = idx[:, 1:]  # drop self

    def stat(v: np.ndarray) -> float:
        lag = v[neighbours].mean(axis=1)  # row-standardized weights
        return float((v * lag).sum() / (v * v).sum())

    observed = stat(z)
    rng = np.random.default_rng(seed)
    null = np.array([stat(rng.permutation(z)) for _ in range(permutations)])
    p = (1 + np.sum(null >= observed)) / (permutations + 1)
    return {
        "morans_i": observed,
        "expected_i": -1 / (n - 1),
        "p_value": float(p),
        "k": int(k),
        "n": int(n),
        "neighbour_distance_m": float(np.median(np.linalg.norm(xy[neighbours[:, 0]] - xy, axis=1))),
    }


def residual_autocorrelation(frame: pd.DataFrame, residuals, k: int = 8, seed: int = 42):
    out = []
    frame = frame.assign(_r=np.asarray(residuals, float))
    for key, g in frame.groupby("site_year"):
        g = g[np.isfinite(g["_r"]) & g["latitude"].notna() & g["longitude"].notna()]
        if len(g) < MIN_PLOTS:
            continue
        xy = local_xy(g["latitude"], g["longitude"])
        out.append({"site_year": key, **morans_i(g["_r"].to_numpy(), xy, k=k, seed=seed)})
    return out
