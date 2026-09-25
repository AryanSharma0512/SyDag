"""
Random forest: many decorrelated trees averaged. Trees represent interactions such as
"the same rainfall means different things on different soils" without hand-built terms.
Hybrids are target-encoded (cross-fitted inside fit, so a plot never sees its own yield).
"""

import optuna
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import TargetEncoder

from soilsignal_ml.models.base import ModelSpec, Params


def _forest(params: Params, numeric: list[str], categorical: list[str], seed: int):
    transformers = [("num", "passthrough", numeric)]
    if categorical:
        transformers.insert(
            0,
            (
                "cat",
                TargetEncoder(
                    target_type="continuous", cv=KFold(5, shuffle=True, random_state=seed)
                ),
                categorical,
            ),
        )
    return Pipeline(
        [
            ("prep", ColumnTransformer(transformers, remainder="drop")),
            ("model", RandomForestRegressor(random_state=seed, n_jobs=-1, **params)),
        ]
    )


def _space(trial: optuna.Trial) -> Params:
    bootstrap = trial.suggest_categorical("bootstrap", [True, False])
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 100, 600, step=50),
        "max_depth": trial.suggest_categorical("max_depth", [None, 4, 6, 8, 12, 16]),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 30, log=True),
        "min_samples_split": trial.suggest_int("min_samples_split", 2, 40, log=True),
        "max_features": trial.suggest_categorical("max_features", [1.0, 0.7, 0.5, 0.33, "sqrt"]),
        "bootstrap": bootstrap,
    }
    if bootstrap:
        params["max_samples"] = trial.suggest_float("max_samples", 0.5, 1.0)
    return params


RANDOM_FOREST = ModelSpec(
    "random_forest",
    "RandomForestRegressor",
    _forest,
    _space,
    {"n_estimators": 300, "min_samples_leaf": 5, "max_features": 0.5},
    complexity=2,
)
