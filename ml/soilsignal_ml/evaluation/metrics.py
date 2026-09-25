"""Accuracy metrics. MAE is the headline: 'wrong by about N bu/ac on average'."""

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    mae = float(mean_absolute_error(y_true, y_pred))
    return {
        "mae": mae,
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        # R² is undefined for a single-valued target; report NaN rather than a misleading 0.
        "r2": float(r2_score(y_true, y_pred)) if np.ptp(y_true) > 0 else float("nan"),
        # MAE relative to the mean yield, comparable across datasets.
        "relative_mae": mae / float(np.mean(y_true)) if np.mean(y_true) else float("nan"),
        "bias": float(np.mean(y_pred - y_true)),
        "n": int(len(y_true)),
    }


def fold_summary(per_fold: list[dict[str, float]]) -> dict[str, float]:
    """Mean of each metric across folds, plus the spread of MAE between folds."""
    maes = [f["mae"] for f in per_fold]
    return {
        "cv_mae": float(np.mean(maes)),
        "cv_mae_std": float(np.std(maes)),
        "cv_rmse": float(np.mean([f["rmse"] for f in per_fold])),
        "cv_r2": float(np.nanmean([f["r2"] for f in per_fold])),
    }
