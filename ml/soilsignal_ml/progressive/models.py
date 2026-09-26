"""
Candidate models for the progressive experiments.

The same fixed hyperparameters are used at every stage, so a change in error between
stages comes from the information added, not from a lucky tuning run. Override them per
model in configs/progressive.yaml (`params:`) once, before looking at results.

    mean                    Baseline A: the training-set mean yield
    ridge                   linear, one-hot hybrids, median-imputed and scaled
    random_forest           target-encoded hybrids
    hist_gradient_boosting  native categorical and missing-value handling
    catboost                ordered boosting with native categorical hybrids
    xgboost, lightgbm       registered only when the library is installed (the
                            higher-compute machine); not required tonight
"""

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from soilsignal_ml.models.base import ModelSpec, Params
from soilsignal_ml.models.baseline import MEAN, RIDGE
from soilsignal_ml.models.boosted import CATBOOST, HIST_GRADIENT_BOOSTING, _hgb
from soilsignal_ml.models.random_forest import RANDOM_FOREST


def _ordinal_pipeline(estimator, numeric: list[str], categorical: list[str]) -> Pipeline:
    transformers = [("num", "passthrough", numeric)]
    if categorical:
        encoder = OrdinalEncoder(
            handle_unknown="use_encoded_value", unknown_value=np.nan, encoded_missing_value=np.nan
        )
        transformers.insert(0, ("cat", encoder, categorical))
    return Pipeline(
        [("prep", ColumnTransformer(transformers, remainder="drop")), ("model", estimator)]
    )


def _xgboost(params: Params, numeric: list[str], categorical: list[str], seed: int):
    from xgboost import XGBRegressor

    return _ordinal_pipeline(
        XGBRegressor(random_state=seed, n_jobs=-1, tree_method="hist", **params),
        numeric,
        categorical,
    )


def _lightgbm(params: Params, numeric: list[str], categorical: list[str], seed: int):
    from lightgbm import LGBMRegressor

    return _ordinal_pipeline(
        LGBMRegressor(random_state=seed, n_jobs=-1, verbose=-1, **params), numeric, categorical
    )


XGBOOST = ModelSpec(
    "xgboost",
    "XGBRegressor",
    _xgboost,
    None,
    {"n_estimators": 500, "learning_rate": 0.05, "max_depth": 6, "subsample": 0.8},
    complexity=4,
    library="xgboost",
)
LIGHTGBM = ModelSpec(
    "lightgbm",
    "LGBMRegressor",
    _lightgbm,
    None,
    {"n_estimators": 500, "learning_rate": 0.05, "num_leaves": 31, "subsample": 0.8},
    complexity=4,
    library="lightgbm",
)


def _installed(module: str) -> bool:
    try:
        __import__(module)
    except Exception:  # noqa: BLE001  (a broken optional install counts as absent)
        return False
    return True


def registry() -> dict[str, ModelSpec]:
    specs = [MEAN, RIDGE, RANDOM_FOREST, HIST_GRADIENT_BOOSTING, CATBOOST]
    if _installed("xgboost"):
        specs.append(XGBOOST)
    if _installed("lightgbm"):
        specs.append(LIGHTGBM)
    return {s.name: s for s in specs}


def quantile_model(quantile: float, numeric: list[str], categorical: list[str], seed: int):
    """Histogram boosting with the pinball loss, for conformalized quantile regression."""
    params = {
        "loss": "quantile",
        "quantile": quantile,
        "learning_rate": 0.05,
        "max_iter": 300,
        "min_samples_leaf": 20,
    }
    return _hgb(params, numeric, categorical, seed)
