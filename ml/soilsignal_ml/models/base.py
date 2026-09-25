"""
A model family: how to build the estimator and which hyperparameters to search.

Every estimator is built only from scikit-learn or CatBoost classes, so the exported
joblib file loads in the backend without any code from ml/.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import optuna

Params = dict[str, Any]
# (params, numeric columns, categorical columns, seed) -> unfitted estimator
Factory = Callable[[Params, list[str], list[str], int], Any]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    algorithm: str
    make: Factory
    space: Callable[[optuna.Trial], Params] | None = None
    defaults: Params = field(default_factory=dict)
    # Ordering used to prefer the simpler model when scores are close.
    complexity: int = 0
    # Library the backend needs to load this model.
    library: str = "scikit-learn"
