"""Grouped validation keeps every group on one side of every split."""

import numpy as np
import pytest

from soilsignal_ml.validation.splits import (
    GROUP_COLUMNS,
    Fold,
    OverlapError,
    assert_separated,
    folds,
    holdout_mask,
)


@pytest.mark.parametrize("strategy", ["plot", "field", "site"])
def test_no_group_on_both_sides(frame, strategy):
    column = GROUP_COLUMNS[strategy]
    for fold in folds(frame, strategy):
        train, test = set(frame[column].iloc[fold.train]), set(frame[column].iloc[fold.test])
        assert not train & test
        assert len(fold.train) + len(fold.test) == len(frame)


def test_leave_one_site_out_tests_each_site_once(frame):
    tested = [set(frame["site_id"].iloc[f.test]) for f in folds(frame, "site")]
    assert tested == [{"A"}, {"B"}, {"C"}]


def test_overlap_is_detected(frame):
    bad = Fold("bad", np.arange(0, 30), np.arange(20, 40))
    with pytest.raises(OverlapError):
        assert_separated(frame, bad, "site_id")


def test_year_split_needs_two_years(frame):
    with pytest.raises(ValueError, match="at least 2 groups"):
        folds(frame, "year")


def test_holdout_site_is_separate(frame):
    mask = holdout_mask(frame, "C")
    assert set(frame.loc[mask, "site_id"]) == {"C"}
    assert "C" not in set(frame.loc[~mask, "site_id"])
    with pytest.raises(ValueError):
        holdout_mask(frame, "Nowhere")


def test_practice_holdout_site_never_reaches_development(dataset):
    from soilsignal_ml.models.train import load_project

    site = load_project()["holdout_site"]
    plots = dataset.plots
    dev = plots[~holdout_mask(plots, site)]
    assert site not in set(dev["site_id"])
    for fold in folds(dev.reset_index(drop=True), "site"):
        assert site not in set(dev["site_id"].iloc[fold.test])
