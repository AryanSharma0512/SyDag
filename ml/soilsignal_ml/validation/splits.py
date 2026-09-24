"""
Grouped validation. A random row split would put plots from the same field, site and
weather in both train and test and overstate accuracy, so every split here keeps a
group (plot, field, site or year) entirely on one side, and checks it.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

# Column that identifies the group for each strategy.
GROUP_COLUMNS = {"plot": "plot_id", "field": "field_id", "site": "site_id", "year": "year"}
DESCRIPTIONS = {
    "plot": "grouped 5-fold by plot",
    "field": "grouped 4-fold by field",
    "site": "leave-one-site-out",
    "year": "leave-one-year-out",
}


class OverlapError(AssertionError):
    """A group appears in both the training and the test side of a split."""


@dataclass(frozen=True)
class Fold:
    name: str
    train: np.ndarray  # positional indices into the frame
    test: np.ndarray


def holdout_mask(frame: pd.DataFrame, site: str) -> np.ndarray:
    """True for rows of the final held-out site."""
    if site not in set(frame["site_id"]):
        raise ValueError(f"held-out site {site!r} is not in the dataset")
    return (frame["site_id"] == site).to_numpy()


def folds(frame: pd.DataFrame, strategy: str) -> list[Fold]:
    column = GROUP_COLUMNS[strategy]
    groups = frame[column].to_numpy()
    unique = pd.unique(groups)
    if strategy in ("site", "year"):
        if len(unique) < 2:
            raise ValueError(
                f"{DESCRIPTIONS[strategy]} needs at least 2 groups, found {len(unique)}"
            )
        out = [
            Fold(str(g), np.nonzero(groups != g)[0], np.nonzero(groups == g)[0])
            for g in sorted(unique)
        ]
    else:
        k = 5 if strategy == "plot" else min(4, len(unique))
        splitter = GroupKFold(n_splits=k)
        out = [
            Fold(f"fold{i + 1}", train, test)
            for i, (train, test) in enumerate(splitter.split(frame, groups=groups))
        ]
    for fold in out:
        assert_separated(frame, fold, column)
    return out


def assert_separated(frame: pd.DataFrame, fold: Fold, column: str) -> None:
    shared = set(frame[column].iloc[fold.train]) & set(frame[column].iloc[fold.test])
    if shared:
        raise OverlapError(f"{column} in both train and test: {sorted(map(str, shared))[:5]}")
    if len(np.intersect1d(fold.train, fold.test)):
        raise OverlapError("a row is in both train and test")


def available_strategies(frame: pd.DataFrame) -> Iterator[str]:
    for strategy, column in GROUP_COLUMNS.items():
        if frame[column].nunique() >= 2:
            yield strategy
