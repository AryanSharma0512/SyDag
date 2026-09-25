"""
Prediction intervals from out-of-fold residuals.

Each dev plot is predicted by a model that never saw its site, so its residual is an
honest sample of the error on a new site. The interval offsets are the lower and upper
quantiles of those residuals (a cross-validation analogue of split-conformal
prediction; Barber et al. 2021, "CV+"). Coverage is then checked on the held-out site,
which played no part in setting them.
"""

import numpy as np


def interval_offsets(residuals, level: float) -> tuple[float, float]:
    """(lower, upper) offsets to add to a point prediction. residual = actual - predicted."""
    r = np.asarray(residuals, float)
    alpha = (1 - level) / 2
    n = len(r)
    # Finite-sample conformal correction: use the ceil((n+1)(1-alpha))/n quantile.
    upper_q = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    lower_q = max(0.0, np.floor((n + 1) * alpha) / n)
    lower = float(np.quantile(r, lower_q, method="lower"))
    upper = float(np.quantile(r, upper_q, method="higher"))
    return min(0.0, lower), max(0.0, upper)


def coverage(y_true, y_pred, offsets: tuple[float, float]) -> float:
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    inside = (y_true >= y_pred + offsets[0]) & (y_true <= y_pred + offsets[1])
    return float(inside.mean())
