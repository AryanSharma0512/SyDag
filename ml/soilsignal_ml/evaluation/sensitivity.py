"""
Agronomic sanity checks: vary one feature across its training range for a typical
plot, hold the rest fixed, and compare the model's response with the direction the
literature leads us to expect (ml/research/agronomy_thresholds.yaml).

A disagreement is a prompt to investigate (leakage, unit errors, sampling bias,
extrapolation), not a reason to overrule the model.
"""

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

from soilsignal_ml import ML_ROOT

EXPECTATIONS = ML_ROOT / "research" / "agronomy_thresholds.yaml"
GRID_POINTS = 11


def expected_directions() -> dict[str, dict]:
    doc = yaml.safe_load(EXPECTATIONS.read_text())
    return {e["feature"]: e for e in doc.get("sensitivity_expectations", [])}


def representative_row(model, X: pd.DataFrame) -> pd.DataFrame:
    """The dev plot whose prediction is closest to the median prediction."""
    pred = model.predict(X)
    i = int(np.argmin(np.abs(pred - np.median(pred))))
    return X.iloc[[i]]


def sensitivity(model, X: pd.DataFrame) -> list[dict]:
    row = representative_row(model, X)
    out = []
    for feature, expectation in expected_directions().items():
        if feature not in X.columns or X[feature].nunique() < 3:
            continue
        lo, hi = X[feature].quantile([0.05, 0.95])
        if lo == hi:
            continue
        grid = np.linspace(lo, hi, GRID_POINTS)
        frame = pd.concat([row] * GRID_POINTS, ignore_index=True)
        frame[feature] = grid
        pred = np.asarray(model.predict(frame), float)
        change = float(pred[-1] - pred[0])
        spread = float(pred.max() - pred.min())
        rho = spearmanr(grid, pred).statistic if spread > 1e-9 else 0.0
        observed = (
            "flat"
            if spread < 0.5
            else "increase"
            if rho > 0.3
            else "decrease"
            if rho < -0.3
            else "mixed"
        )
        expected = expectation["expected"]
        agrees = (
            observed == "flat"
            or expected == "context"
            or observed == expected
            or (expected in ("increase", "decrease") and observed == "mixed")
        )
        out.append(
            {
                "feature": feature,
                "range": [round(float(lo), 3), round(float(hi), 3)],
                "prediction_low_to_high": round(change, 1),
                "prediction_spread": round(spread, 1),
                "observed": observed,
                "expected": expected,
                "rationale": expectation["rationale"],
                "status": "consistent" if agrees else "investigate",
            }
        )
    return out
