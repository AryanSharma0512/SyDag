"""Data checks: the practice data passes, and each check catches what it's for."""

import pandas as pd

from soilsignal_ml.ingest.validate import validate


def test_practice_dataset_passes(dataset):
    assert validate(dataset) == []


def test_checks_catch_common_mistakes(dataset):
    broken = type(dataset)(**{**dataset.__dict__})
    broken.plots = dataset.plots.copy()
    broken.plots.loc[broken.plots.index[0], "final_yield"] = 11_000  # kg/ha mistaken for bu/ac
    broken.plots = pd.concat([broken.plots, broken.plots.head(1)])  # duplicate target row
    broken.observations = dataset.observations.copy()
    broken.observations.loc[broken.observations.index[0], "ndvi"] = 1.7
    broken.weather = dataset.weather.copy()
    broken.weather.loc[broken.weather.index[0], "prcp_mm"] = 900.0
    broken.weather.loc[broken.weather.index[1], "tmax_f"] = 200.0
    problems = " | ".join(validate(broken))
    for expected in (
        "outside (0.0, 400.0)",
        "duplicate plot rows",
        "ndvi values outside",
        "daily rainfall outside",
        "tmax_f outside",
    ):
        assert expected in problems


def test_weather_record_is_complete_for_the_season(dataset):
    w = dataset.weather
    for site, g in w.groupby("site_id"):
        planting = dataset.plots.loc[dataset.plots["site_id"] == site, "planting_date"].min()
        season = g[(g["date"] >= planting) & (g["date"] <= pd.Timestamp("2022-09-30").date())]
        complete = season[["tmax_f", "tmin_f", "prcp_mm"]].notna().all(axis=1).mean()
        assert complete > 0.97, f"{site} weather only {complete:.0%} complete"
