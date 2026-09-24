"""Point-in-time integrity on the real practice data."""

from dataclasses import replace
from datetime import date

import pytest

from app.features.build import build_features
from app.features.inputs import CanopyObservation, DailyWeather
from soilsignal_ml.features.build import ID_COLUMNS, cutoff_date, feature_table
from soilsignal_ml.models.train import load_cutoffs


@pytest.fixture(scope="module")
def plot(dataset):
    return dataset.plots.dropna(subset=["final_yield"]).iloc[0]


@pytest.mark.parametrize("cfg", load_cutoffs(), ids=lambda c: c["name"])
def test_future_data_cannot_change_features(dataset, plot, cfg):
    inputs = dataset.field_inputs(plot)
    as_of = cutoff_date(int(plot["year"]), cfg["as_of"])
    poisoned = replace(
        inputs,
        weather=tuple(inputs.weather)
        + tuple(DailyWeather(date(as_of.year, 12, d), 140.0, 120.0, 500.0) for d in range(1, 20)),
        canopy=tuple(inputs.canopy) + (CanopyObservation(date(as_of.year, 12, 1), {"ndvi": -1.0}),),
        county_yields={**inputs.county_yields, as_of.year: 1.0, as_of.year + 1: 1.0},
    )
    assert build_features(poisoned, as_of) == build_features(inputs, as_of)


def test_no_crop_observations_before_the_first_image(dataset):
    first_image = min(dataset.observations["date"])
    for cfg in load_cutoffs():
        as_of = cutoff_date(2022, cfg["as_of"])
        if as_of < first_image:
            sample = dataset.plots.dropna(subset=["final_yield"]).head(50)
            for _, p in sample.iterrows():
                features = build_features(dataset.field_inputs(p), as_of)
                assert not [
                    k for k in features if k.startswith(("ndvi", "ndre", "gndvi", "evi", "canopy"))
                ]


def test_target_never_leaks_into_features(dataset):
    table = feature_table(dataset, "08-31")
    features = [c for c in table.columns if c not in ID_COLUMNS]
    assert "final_yield" not in features
    assert not [c for c in features if "yield" in c and not c.startswith("county_yield")]
