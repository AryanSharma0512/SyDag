"""
Gradient-boosted trees: each tree fits what the previous trees got wrong.

    hist_gradient_boosting  scikit-learn's histogram boosting (the LightGBM algorithm),
                            native categorical and missing-value handling, no new dependency
    catboost                CatBoost, ordered boosting with native categorical features

LightGBM and XGBoost need the OpenMP runtime, which the training machine lacks; the
histogram model covers LightGBM's algorithm.
"""

import numpy as np
import optuna
from catboost import CatBoostRegressor
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from soilsignal_ml.models.base import ModelSpec, Params


def _hgb(params: Params, numeric: list[str], categorical: list[str], seed: int):
    transformers = [("num", "passthrough", numeric)]
    mask = [False] * len(numeric)
    if categorical:
        encoder = OrdinalEncoder(
            handle_unknown="use_encoded_value", unknown_value=np.nan, encoded_missing_value=np.nan
        )
        transformers.insert(0, ("cat", encoder, categorical))
        mask = [True] * len(categorical) + mask
    return Pipeline(
        [
            ("prep", ColumnTransformer(transformers, remainder="drop")),
            (
                "model",
                HistGradientBoostingRegressor(
                    categorical_features=mask, random_state=seed, early_stopping=False, **params
                ),
            ),
        ]
    )


def _hgb_space(trial: optuna.Trial) -> Params:
    return {
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "max_iter": trial.suggest_int("max_iter", 100, 800, step=50),
        "max_depth": trial.suggest_categorical("max_depth", [None, 3, 4, 6, 8]),
        "max_leaf_nodes": trial.suggest_int("max_leaf_nodes", 7, 63, log=True),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 5, 80, log=True),
        "l2_regularization": trial.suggest_float("l2_regularization", 1e-3, 10.0, log=True),
        "max_features": trial.suggest_float("max_features", 0.3, 1.0),
    }


def _catboost(params: Params, numeric: list[str], categorical: list[str], seed: int):
    return CatBoostRegressor(
        cat_features=categorical or None,
        random_seed=seed,
        verbose=0,
        allow_writing_files=False,
        thread_count=-1,
        **params,
    )


def _catboost_space(trial: optuna.Trial) -> Params:
    return {
        "iterations": trial.suggest_int("iterations", 200, 1000, step=100),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "depth": trial.suggest_int("depth", 3, 8),
        "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 30.0, log=True),
        "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 1, 60, log=True),
        "rsm": trial.suggest_float("rsm", 0.3, 1.0),
    }


HIST_GRADIENT_BOOSTING = ModelSpec(
    "hist_gradient_boosting",
    "HistGradientBoostingRegressor",
    _hgb,
    _hgb_space,
    {"learning_rate": 0.05, "max_iter": 300},
    complexity=3,
)
CATBOOST = ModelSpec(
    "catboost",
    "CatBoostRegressor",
    _catboost,
    _catboost_space,
    {"iterations": 500, "learning_rate": 0.05, "depth": 6},
    complexity=4,
    library="catboost",
)
