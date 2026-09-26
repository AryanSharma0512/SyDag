"""
90% prediction intervals whose coverage is measured on groups that set nothing.

residual (nested split-conformal)
    For each outer fold, the training groups are split again (inner folds, same grouping
    where possible). Residuals of models that never saw each inner test group give the
    interval offsets (finite-sample conformal quantile, `evaluation.uncertainty`). The
    offsets are then applied to the outer test group, whose coverage is honest. Width is
    the same for every plot in a fold, so ranking by the lower bound is identical to
    ranking by the forecast.

cqr (conformalized quantile regression, Romano et al. 2019)
    Two quantile models (5th and 95th percentile) give a per-plot band; the inner folds
    conformalize it (score = how far the actual yield falls outside the band). Width
    varies by plot, so the lower bound is a genuine "downside risk" ranking to compare
    with ranking by the forecast.

Pooled out-of-fold residuals (the practice pipeline's method) would calibrate on the same
predictions they are scored on; that is only kept as a fast fallback (`nested: false`).
"""

import math

import numpy as np

from soilsignal_ml.evaluation.uncertainty import interval_offsets
from soilsignal_ml.progressive.models import quantile_model


def conformal_quantile(scores, level: float) -> float:
    """ceil((n + 1) * level) / n empirical quantile of the conformity scores."""
    s = np.sort(np.asarray(scores, float))
    n = len(s)
    if n == 0:
        return float("nan")
    k = min(n, math.ceil((n + 1) * level))
    return float(s[k - 1])


def residual_offsets(residuals, level: float) -> tuple[float, float]:
    return interval_offsets(residuals, level)


def fit_cqr(X, y, inner, numeric, categorical, seed, level):
    """Quantile models fitted on all of (X, y), conformalized with inner-fold scores.
    Returns (lower model, upper model, correction)."""
    alpha = 1 - level
    lo_q, hi_q = alpha / 2, 1 - alpha / 2
    scores = []
    for fold in inner:
        lo = quantile_model(lo_q, numeric, categorical, seed).fit(X.iloc[fold.train], y[fold.train])
        hi = quantile_model(hi_q, numeric, categorical, seed).fit(X.iloc[fold.train], y[fold.train])
        Xt, yt = X.iloc[fold.test], y[fold.test]
        scores.append(np.maximum(lo.predict(Xt) - yt, yt - hi.predict(Xt)))
    correction = conformal_quantile(np.concatenate(scores), level)
    lo = quantile_model(lo_q, numeric, categorical, seed).fit(X, y)
    hi = quantile_model(hi_q, numeric, categorical, seed).fit(X, y)
    return lo, hi, correction


def cqr_band(lo_model, hi_model, correction, X) -> tuple[np.ndarray, np.ndarray]:
    lower, upper = lo_model.predict(X) - correction, hi_model.predict(X) + correction
    # Quantile models are fitted separately and can cross; keep the band ordered.
    return np.minimum(lower, upper), np.maximum(lower, upper)
