"""Weather history QC and backtest scoring (the outlook engine is tested in
backend/tests/test_weather_outlook.py)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from soilsignal_ml.weather_outlook.backtest import brier, crps, hit, rps
from soilsignal_ml.weather_outlook.history import (
    align_observation_day,
    fill_temperature_gaps,
    load_config,
    qc_seasons,
)

YEARS = range(2000, 2016)


def station(seed: int, offset_c: float = 0.0, rain_scale: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range("2000-01-01", "2015-12-31", freq="D")
    base = np.random.default_rng(0)  # shared weather, so neighbours agree
    tmax = 15 + 12 * np.sin(2 * np.pi * (days.dayofyear - 110) / 365) + base.normal(0, 3, len(days))
    rain = np.where(base.random(len(days)) < 0.3, base.exponential(8, len(days)), 0.0)
    return pd.DataFrame(
        {
            "date": days,
            "tmax_c": tmax + offset_c + rng.normal(0, 0.3, len(days)),
            "tmin_c": tmax - 11 + offset_c + rng.normal(0, 0.3, len(days)),
            "precip_mm": rain * rain_scale * rng.uniform(0.9, 1.1, len(days)),
        }
    )


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_a_broken_gauge_is_left_out(cfg):
    primary = station(1)
    broken = (primary["date"].dt.year == 2007) & (primary["date"].dt.month.isin([6, 7, 8]))
    primary.loc[broken, "precip_mm"] = 0.0  # reported zeros while broken, as LNK 1995
    table = qc_seasons(primary, {"N1": station(2), "N2": station(3)}, YEARS, cfg)
    assert not table.loc[2007, "included"]
    assert "every neighbour" in table.loc[2007, "reason"]
    assert table.drop(index=2007)["included"].all()


def test_a_neighbours_station_change_does_not_flag_the_primary(cfg):
    neighbour = station(2)
    moved = neighbour["date"].dt.year >= 2009
    neighbour.loc[moved, "tmin_c"] += 1.8  # the neighbour moved, as Mount Pleasant ~2021
    table = qc_seasons(station(1), {"N1": neighbour, "N2": station(3)}, YEARS, cfg)
    assert table["included"].all()


def test_one_disagreeing_neighbour_is_not_enough(cfg):
    odd = station(2)
    odd.loc[odd["date"].dt.year == 2004, "tmax_c"] += 3
    table = qc_seasons(station(1), {"N1": odd, "N2": station(3)}, YEARS, cfg)
    assert table.loc[2004, "included"]
    assert table.loc[2004, "neighbour_flags"]


def test_incomplete_seasons_are_left_out(cfg):
    primary = station(1)
    gap = (primary["date"] >= "2010-06-01") & (primary["date"] <= "2010-06-20")
    primary.loc[gap, "precip_mm"] = np.nan
    table = qc_seasons(primary, {}, YEARS, cfg)
    assert not table.loc[2010, "included"]
    assert "incomplete" in table.loc[2010, "reason"]


def test_only_short_temperature_gaps_are_filled_and_never_rain():
    frame = station(1)
    frame.loc[[100, 200, 201], "tmax_c"] = np.nan
    frame.loc[300:305, "tmin_c"] = np.nan  # six days: too long
    frame.loc[400, "precip_mm"] = np.nan
    out = fill_temperature_gaps(frame, max_gap=2)
    assert out.loc[[100, 200, 201], "tmax_c"].notna().all()
    assert out.loc[300:305, "tmin_c"].isna().all()
    assert np.isnan(out.loc[400, "precip_mm"])
    assert out["temp_filled"].sum() == 3
    expected = (frame.loc[99, "tmax_c"] + frame.loc[101, "tmax_c"]) / 2
    assert out.loc[100, "tmax_c"] == pytest.approx(expected)


def test_observation_day_alignment():
    frame = pd.DataFrame({"date": pd.to_datetime(["2020-07-02"]), "tmax_c": [30.0]})
    assert align_observation_day(frame, -1)["date"].iloc[0] == pd.Timestamp(date(2020, 7, 1))
    assert align_observation_day(frame, 0) is frame


def test_scores():
    sure = np.array([0.0, 0.0, 1.0])
    assert rps(sure, 2) == 0 and brier(sure, 2) == 0 and hit(sure, 2) == 1
    assert rps(sure, 0) == pytest.approx(1.0)
    even = np.full(3, 1 / 3)
    assert hit(even, 1) == pytest.approx(1 / 3)
    # the far category costs more than the near one: RPS respects the order
    assert rps(np.array([0.1, 0.8, 0.1]), 0) < rps(np.array([0.1, 0.1, 0.8]), 0)
    assert crps(np.array([5.0]), np.array([1.0]), 3.0) == pytest.approx(2.0)
    ensemble = np.array([1.0, 2.0, 3.0])
    assert crps(ensemble, np.ones(3), 2.0) < crps(ensemble, np.ones(3), 10.0)
