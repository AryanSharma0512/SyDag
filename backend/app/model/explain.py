"""
Per-prediction drivers, model-agnostic and dependency-free.

A feature's contribution is how much the prediction moves when that feature alone is
replaced by its typical training value (the median, or the most common category):

    contribution_j = f(x) - f(x with x_j := typical_j)

Positive means this field's value of the feature pushes the forecast up relative to a
typical field. It describes what the model associates with yield, not a cause.
"""

from typing import Any

import numpy as np
import pandas as pd


def baseline_contributions(
    estimator: Any, frame: pd.DataFrame, typical: dict[str, Any]
) -> pd.DataFrame:
    """One row per input row, one column per feature that has a typical value.
    All swapped copies go through the model in a single predict call."""
    names = [n for n in typical if n in frame.columns]
    copies = [frame]
    for name in names:
        swapped = frame.copy()
        swapped[name] = pd.Series([typical[name]] * len(frame), index=frame.index).astype(
            frame[name].dtype
        )
        copies.append(swapped)
    preds = np.asarray(estimator.predict(pd.concat(copies, ignore_index=True)), dtype=float)
    preds = preds.reshape(len(copies), len(frame))
    return pd.DataFrame(
        {name: preds[0] - preds[i + 1] for i, name in enumerate(names)}, index=frame.index
    )
