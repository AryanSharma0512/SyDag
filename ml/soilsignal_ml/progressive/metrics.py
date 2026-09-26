"""
Metrics for one stage x model x validation scheme, all on out-of-fold predictions.

Accuracy   MAE (headline), RMSE, R², mean bias (predicted - actual)
Ranking    Spearman within each scouting unit (a site-season), averaged; pooled Spearman
           is also kept but mostly measures between-site differences
Intervals  empirical coverage of the nominal 90% interval and its mean width
Imagery    delta MAE vs records only (positive = imagery helped) with a paired bootstrap
           interval, and how many held-out groups improved
Scouting   if only X% of plots can be visited, the share of the eventual bottom quartile
           (within each site-season) that the ranking sends scouts to
"""

import math

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from soilsignal_ml.evaluation.metrics import regression_metrics

MIN_UNIT_PLOTS = 8


def accuracy(y, pred) -> dict[str, float]:
    m = regression_metrics(y, pred)
    return {k: m[k] for k in ("mae", "rmse", "r2", "bias", "relative_mae", "n")}


def spearman(y, pred) -> float:
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    if len(y) < 3 or np.ptp(y) == 0 or np.ptp(pred) == 0:
        return float("nan")
    return float(spearmanr(y, pred).statistic)


def spearman_within(y, pred, units) -> float:
    """Mean of per-unit Spearman correlations (units with at least MIN_UNIT_PLOTS plots)."""
    frame = pd.DataFrame({"y": y, "p": pred, "u": units})
    values = [spearman(g["y"], g["p"]) for _, g in frame.groupby("u") if len(g) >= MIN_UNIT_PLOTS]
    values = [v for v in values if np.isfinite(v)]
    return float(np.mean(values)) if values else float("nan")


def interval_stats(y, lower, upper) -> dict[str, float]:
    y, lower, upper = (np.asarray(a, float) for a in (y, lower, upper))
    ok = np.isfinite(lower) & np.isfinite(upper)
    if not ok.any():
        return {"coverage": float("nan"), "width": float("nan")}
    inside = (y[ok] >= lower[ok]) & (y[ok] <= upper[ok])
    return {"coverage": float(inside.mean()), "width": float(np.mean(upper[ok] - lower[ok]))}


def paired_bootstrap_delta(
    abs_err_base, abs_err_new, strata, n_boot: int = 2000, seed: int = 42, level: float = 0.95
) -> tuple[float, float]:
    """Interval for MAE(base) - MAE(new), resampling plots within each stratum (fold).

    Plots in one held-out group are not independent, so with few groups this interval is
    narrower than the true between-group uncertainty. Read it together with the per-group
    win count, never alone."""
    a, b = np.asarray(abs_err_base, float), np.asarray(abs_err_new, float)
    diff = a - b
    rng = np.random.default_rng(seed)
    strata = np.asarray(strata)
    groups = [np.nonzero(strata == s)[0] for s in pd.unique(strata)]
    stats = np.empty(n_boot)
    for i in range(n_boot):
        idx = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in groups])
        stats[i] = diff[idx].mean()
    alpha = (1 - level) / 2
    return float(np.quantile(stats, alpha)), float(np.quantile(stats, 1 - alpha))


def per_group_mae(y, pred, groups) -> dict[str, float]:
    frame = pd.DataFrame({"e": np.abs(np.asarray(y) - np.asarray(pred)), "g": groups})
    return {str(k): float(v) for k, v in frame.groupby("g")["e"].mean().items()}


# ---- scouting -----------------------------------------------------------------------------


def _rank_order(score: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Lowest score first; ties broken at random (records-only models give replicate plots
    identical forecasts, and file order must not decide who gets scouted). A missing score
    (e.g. no image of that plot yet) is ranked last, never dropped, so every ranking is
    judged on the same plots."""
    score = np.where(np.isfinite(score), score, np.inf)
    return np.lexsort((rng.random(len(score)), score))


def scouting(
    y,
    score,
    units,
    budgets=(0.10, 0.20, 0.25),
    poor_quantile: float = 0.25,
    seed: int = 42,
) -> list[dict]:
    """Recall of each unit's bottom-quartile plots when scouts visit the lowest-scoring
    budget share of plots in that unit. Pooled over units (sum of hits / sum of poor
    plots) and averaged per unit. Random selection recalls `budget` on average; a
    perfect ranking recalls min(1, budget / poor_quantile)."""
    frame = pd.DataFrame({"y": np.asarray(y, float), "s": np.asarray(score, float), "u": units})
    rng = np.random.default_rng(seed)
    rows = []
    for budget in budgets:
        hits = poor_total = selected_total = n_total = 0
        per_unit = []
        oracle_hits = 0
        for _, g in frame.groupby("u"):
            n = len(g)
            if n < MIN_UNIT_PLOTS:
                continue
            threshold = np.quantile(g["y"], poor_quantile)
            poor = (g["y"] <= threshold).to_numpy()
            k = max(1, int(math.floor(budget * n + 0.5)))
            chosen = _rank_order(g["s"].to_numpy(), rng)[:k]
            h = int(poor[chosen].sum())
            hits += h
            poor_total += int(poor.sum())
            selected_total += k
            n_total += n
            oracle_hits += min(k, int(poor.sum()))
            per_unit.append(h / poor.sum())
        if not per_unit:
            continue
        recall = hits / poor_total
        random_recall = selected_total / n_total
        oracle = oracle_hits / poor_total
        rows.append(
            {
                "budget": budget,
                "recall": recall,
                "recall_unit_mean": float(np.mean(per_unit)),
                "precision": hits / selected_total,
                "random_recall": random_recall,
                "oracle_recall": oracle,
                "lift": recall / random_recall if random_recall else float("nan"),
                "skill": (recall - random_recall) / (oracle - random_recall)
                if oracle > random_recall
                else float("nan"),
                "n_units": len(per_unit),
                "n_poor": poor_total,
                "n_selected": selected_total,
                "hits": hits,
            }
        )
    return rows
