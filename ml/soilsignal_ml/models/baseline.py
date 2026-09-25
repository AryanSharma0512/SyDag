"""
Model 0 and Model 1: the bars every other model has to clear.

    mean   predicts the training-set average yield for every plot
    ridge  linear model on the same features (median-imputed, scaled, one-hot hybrids)
"""

import optuna
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from soilsignal_ml.models.base import ModelSpec, Params


def _mean(params: Params, numeric: list[str], categorical: list[str], seed: int):
    return DummyRegressor(strategy="mean")


def _ridge(params: Params, numeric: list[str], categorical: list[str], seed: int):
    transformers = [
        (
            "num",
            make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()),
            numeric,
        ),
    ]
    if categorical:
        transformers.append(
            (
                "cat",
                make_pipeline(
                    SimpleImputer(strategy="most_frequent"),
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                ),
                categorical,
            )
        )
    return Pipeline(
        [
            ("prep", ColumnTransformer(transformers, remainder="drop")),
            ("model", Ridge(alpha=params.get("alpha", 1.0))),
        ]
    )


def _ridge_space(trial: optuna.Trial) -> Params:
    return {"alpha": trial.suggest_float("alpha", 1e-2, 1e3, log=True)}


MEAN = ModelSpec("mean", "DummyRegressor(mean)", _mean, complexity=0)
RIDGE = ModelSpec("ridge", "Ridge", _ridge, _ridge_space, {"alpha": 1.0}, complexity=1)
