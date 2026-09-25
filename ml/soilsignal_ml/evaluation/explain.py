"""
Global model drivers for the feature schema: permutation importance measured on
held-out sites, and each feature's direction of association.

Importance is measured on each leave-one-site-out test fold (never on training
rows, which overstates it) and averaged.
"""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.inspection import permutation_importance

from app.model.explain import baseline_contributions

MIN_DIRECTION_CORRELATION = 0.1


def typical_values(frame: pd.DataFrame, categorical: list[str]) -> dict[str, object]:
    out: dict[str, object] = {}
    for c in frame.columns:
        if c in categorical:
            mode = frame[c].dropna().mode()
            out[c] = mode.iloc[0] if len(mode) else None
        else:
            med = frame[c].median()
            out[c] = None if pd.isna(med) else float(med)
    return out


def fold_permutation_importance(model, X: pd.DataFrame, y, seed: int) -> pd.Series:
    result = permutation_importance(
        model, X, y, scoring="neg_mean_absolute_error", n_repeats=5, random_state=seed, n_jobs=1
    )
    # Importance in bu/ac of MAE lost when the feature is shuffled; negatives are noise.
    return pd.Series(np.clip(result.importances_mean, 0, None), index=X.columns)


def directions(model, X: pd.DataFrame, typical: dict, categorical: list[str]) -> dict[str, str]:
    contrib = baseline_contributions(model, X, {k: v for k, v in typical.items() if v is not None})
    out = {}
    for c in X.columns:
        if c in categorical or c not in contrib or X[c].nunique() < 2:
            out[c] = "neutral"
            continue
        mask = X[c].notna()
        if contrib.loc[mask, c].nunique() < 2:
            out[c] = "neutral"
            continue
        rho = spearmanr(X.loc[mask, c], contrib.loc[mask, c]).statistic
        if np.isnan(rho) or abs(rho) < MIN_DIRECTION_CORRELATION:
            out[c] = "neutral"
        else:
            out[c] = "positive" if rho > 0 else "negative"
    return out
