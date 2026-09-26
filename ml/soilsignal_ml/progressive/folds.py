"""
Validation schemes for the progressive experiments.

Plots at one site share weather, soil, planting date and management, so a random plot
split puts near-copies of each test plot in training and flatters every model. The
headline is always a grouped scheme:

    site       leave-one-site-out: forecast a location the model never saw
    year       leave-one-year-out: forecast a season the model never saw
    site_year  leave-one-site-year-out (needs several years; the least strict grouped one)
    temporal   train on earlier seasons, test on one later season (e.g. 2022 -> 2023)

and two optimistic contrasts, reported only to show how much they flatter:

    field      grouped by experiment block within sites
    random     plot-level 5-fold

Every grouped fold is checked with the existing overlap assertion.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, KFold

from soilsignal_ml.validation.splits import Fold, assert_separated

GROUPED = ("temporal", "site", "year", "site_year")
CONTRASTS = ("field", "random")
DESCRIPTIONS = {
    "site": "leave-one-site-out",
    "year": "leave-one-year-out",
    "site_year": "leave-one-site-year-out",
    "temporal": "train on earlier seasons, test on a later season",
    "field": "grouped by experiment block (optimistic contrast)",
    "random": "random plot 5-fold (optimistic contrast, never the headline)",
}
GROUP_COLUMN = {
    "site": "site_id",
    "year": "year",
    "site_year": "site_year",
    "temporal": "year",
    "field": "field_id",
    "random": "plot_id",
}


@dataclass(frozen=True)
class Scheme:
    name: str
    usable: bool
    reason: str
    test_year: int | None = None

    @property
    def description(self) -> str:
        base = DESCRIPTIONS[self.name]
        return f"{base} ({self.test_year})" if self.test_year else base


def temporal_usable(
    frame: pd.DataFrame, test_year: int | None, min_plots: int, min_imaged: float
) -> Scheme:
    years = sorted(frame["year"].unique())
    if len(years) < 2:
        return Scheme("temporal", False, f"only one labelled season ({years[0]})")
    test_year = test_year or years[-1]
    test = frame[frame["year"] == test_year]
    train = frame[frame["year"] < test_year]
    if train.empty:
        return Scheme("temporal", False, f"no season before {test_year} to train on")
    if len(test) < min_plots:
        return Scheme(
            "temporal",
            False,
            f"{test_year} has {len(test)} labelled plots (< {min_plots}); too few to test on",
            test_year,
        )
    if "_imaged" in test and test["_imaged"].mean() < min_imaged:
        return Scheme(
            "temporal",
            False,
            f"only {test['_imaged'].mean():.0%} of {test_year} plots have imagery",
            test_year,
        )
    sites = ", ".join(sorted(test["site_id"].unique()))
    return Scheme(
        "temporal", True, f"train {years[0]}-{test_year - 1}, test {test_year} ({sites})", test_year
    )


def schemes(
    frame: pd.DataFrame,
    *,
    test_year: int | None = None,
    min_test_plots: int = 100,
    min_test_imaged: float = 0.5,
) -> list[Scheme]:
    out = [temporal_usable(frame, test_year, min_test_plots, min_test_imaged)]
    for name in ("site", "year", "site_year", "field"):
        n = frame[GROUP_COLUMN[name]].nunique()
        if name == "site_year" and frame["year"].nunique() < 2:
            out.append(Scheme(name, False, "one season: identical to leave-one-site-out"))
        elif n < 2:
            out.append(Scheme(name, False, f"only one {GROUP_COLUMN[name]} ({n})"))
        else:
            out.append(Scheme(name, True, f"{n} groups"))
    out.append(Scheme("random", True, "5 folds"))
    return out


def headline(available: list[Scheme]) -> Scheme:
    """Most demanding usable scheme: a later season if one is usable, else an unseen site,
    else an unseen year, else field blocks (flagged as optimistic)."""
    usable = {s.name: s for s in available if s.usable}
    for name in ("temporal", "site", "year", "site_year", "field"):
        if name in usable:
            return usable[name]
    raise ValueError("no grouped validation is possible: need 2+ sites, years or field blocks")


def make_folds(frame: pd.DataFrame, scheme: Scheme, seed: int = 42) -> list[Fold]:
    name = scheme.name
    if name == "temporal":
        years = frame["year"].to_numpy()
        train = np.nonzero(years < scheme.test_year)[0]
        test = np.nonzero(years == scheme.test_year)[0]
        folds = [Fold(str(scheme.test_year), train, test)]
    elif name in ("site", "year", "site_year"):
        groups = frame[GROUP_COLUMN[name]].astype(str).to_numpy()
        folds = [
            Fold(g, np.nonzero(groups != g)[0], np.nonzero(groups == g)[0])
            for g in sorted(pd.unique(groups))
        ]
    elif name == "field":
        groups = frame["field_id"].to_numpy()
        k = min(5, len(pd.unique(groups)))
        folds = [
            Fold(f"block{i + 1}", tr, te)
            for i, (tr, te) in enumerate(GroupKFold(n_splits=k).split(frame, groups=groups))
        ]
    elif name == "random":
        splitter = KFold(5, shuffle=True, random_state=seed)
        return [Fold(f"fold{i + 1}", tr, te) for i, (tr, te) in enumerate(splitter.split(frame))]
    else:
        raise ValueError(f"unknown scheme {name!r}")
    for fold in folds:
        assert_separated(frame, fold, GROUP_COLUMN[name])
    return folds


def inner_folds(train: pd.DataFrame, scheme: Scheme, seed: int = 42) -> tuple[list[Fold], str]:
    """Folds inside one outer training set, for calibrating intervals without touching the
    outer test group. Same grouping as the outer scheme when it still has 2+ groups, then
    the next grouping that does; the name of what was used is returned for the record."""
    order = {
        "temporal": ["year", "site", "field"],
        "site": ["site", "field"],
        "year": ["year", "site", "field"],
        "site_year": ["site_year", "site", "field"],
        "field": ["field"],
        "random": ["random"],
    }[scheme.name]
    frame = train.reset_index(drop=True)
    for name in order:
        column = GROUP_COLUMN[name]
        if name == "random" or frame[column].nunique() >= 2:
            return make_folds(frame, Scheme(name, True, "inner"), seed), name
    return make_folds(frame, Scheme("random", True, "inner"), seed), "random"
