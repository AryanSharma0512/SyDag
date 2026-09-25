"""Shared feature engineering: formulas, point-in-time integrity, missing-data behavior."""

import math
from datetime import date, timedelta

import numpy as np
import pytest

from app.features import thresholds as t
from app.features.build import (
    LeakageError,
    assert_point_in_time,
    build_features,
    history_features,
    season_status,
)
from app.features.catalog import CATALOG, info
from app.features.inputs import CanopyObservation, DailyWeather, FieldInputs, SoilInputs
from app.features.temporal import growth_stage
from app.features.vegetation import compute_indices
from app.features.weather import (
    crop_coefficient,
    degree_days_above,
    hargreaves_et0_mm,
    modified_gdd,
)

PLANTING = date(2022, 5, 15)


def _weather(start: date, n: int, seed: int = 0) -> list[DailyWeather]:
    rng = np.random.default_rng(seed)
    return [
        DailyWeather(
            start + timedelta(i),
            float(70 + 25 * rng.random()),
            float(50 + 20 * rng.random()),
            float(rng.choice([0, 0, 0, 2, 12, 25])),
        )
        for i in range(n)
    ]


def _inputs(**overrides) -> FieldInputs:
    base = dict(
        season_year=2022,
        planting_date=PLANTING,
        latitude=41.0,
        management={"genotype": "H1", "nitrogen_lb_ac": 150.0, "irrigated": False},
        canopy=(
            CanopyObservation(date(2022, 7, 10), {"ndvi": 0.80, "ndre": 0.35}),
            CanopyObservation(date(2022, 7, 24), {"ndvi": 0.85, "ndre": 0.37}),
            CanopyObservation(date(2022, 8, 20), {"ndvi": 0.70, "ndre": 0.30}),
        ),
        canopy_reference=(CanopyObservation(date(2022, 7, 24), {"ndvi": 0.80, "ndre": 0.36}),),
        weather=tuple(_weather(date(2022, 4, 1), 200)),
        soil=SoilInputs(20.0, 3.0, 6.5, 150.0, "Poorly drained", 1.0),
        county_yields={2017: 190.0, 2018: 200.0, 2019: 180.0, 2020: 195.0, 2021: 205.0, 2022: 90.0},
    )
    return FieldInputs(**(base | overrides))


def test_modified_gdd_matches_purdue_worked_examples():
    # Nielsen, "Heat Unit Concepts Related to Corn Development", examples 1-3.
    assert modified_gdd(80, 55) == 17.5
    assert modified_gdd(90, 72) == 29
    assert modified_gdd(68, 41) == 9


def test_degree_days_above_threshold():
    assert degree_days_above(28, 15, 29) == 0
    assert degree_days_above(40, 30, 29) == pytest.approx(6.0)
    partial = degree_days_above(35, 20, 29)
    assert 0 < partial < (35 + 20) / 2  # only the part of the day above 29 °C counts


def test_hargreaves_et0_is_plausible_for_midwest_july():
    et0 = hargreaves_et0_mm(date(2022, 7, 15), 41.0, 90, 65)
    assert 5 < et0 < 8  # mm/day


def test_crop_coefficient_follows_fao56_stages():
    assert crop_coefficient(0) == t.KC_INITIAL
    assert crop_coefficient(t.GDD_SILKING) == t.KC_MID
    assert crop_coefficient(5000) == t.KC_END
    assert t.KC_INITIAL < crop_coefficient(800) < t.KC_MID


def test_indices_only_from_available_bands():
    bands = {"nir": np.array([0.5]), "red": np.array([0.05])}
    out = compute_indices(bands)
    assert set(out) == {"ndvi"}  # no red edge, green or blue: nothing else is invented
    assert out["ndvi"][0] == pytest.approx(0.45 / 0.55)


def test_growth_stage_from_heat_units():
    assert growth_stage(50) == "Emergence"
    assert growth_stage(600) == "Vegetative"
    assert growth_stage(t.GDD_SILKING + 10) == "Reproductive"
    assert growth_stage(2200) == "Grain Fill"
    assert growth_stage(3000) == "Maturity"


@pytest.mark.parametrize(
    "as_of", [date(2022, 5, 31), date(2022, 7, 15), date(2022, 7, 31), date(2022, 8, 31)]
)
def test_features_ignore_everything_after_the_forecast_date(as_of):
    """The core leakage test: appending wild future data must not change a single feature."""
    clean = _inputs()
    future_weather = [DailyWeather(as_of + timedelta(i), 130.0, 110.0, 300.0) for i in range(1, 90)]
    future_canopy = [CanopyObservation(as_of + timedelta(3), {"ndvi": -0.9, "ndre": -0.9})]
    polluted = _inputs(
        weather=tuple(d for d in clean.weather if d.day <= as_of) + tuple(future_weather),
        canopy=tuple(o for o in clean.canopy if o.day <= as_of) + tuple(future_canopy),
        canopy_reference=clean.canopy_reference + tuple(future_canopy),
    )
    truncated = _inputs(
        weather=tuple(d for d in clean.weather if d.day <= as_of),
        canopy=tuple(o for o in clean.canopy if o.day <= as_of),
    )
    assert build_features(polluted, as_of) == build_features(truncated, as_of)


def test_current_season_county_yield_is_never_used():
    features = history_features({2020: 180.0, 2021: 200.0, 2019: 190.0, 2022: 50.0}, 2022)
    assert features["county_yield_5yr_avg"] == pytest.approx(190.0)
    assert features["county_yield_prev_year"] == 200.0
    assert build_features(_inputs(), date(2022, 9, 30))["county_yield_5yr_avg"] == pytest.approx(
        194.0
    )


def test_point_in_time_assertion_catches_late_inputs():
    with pytest.raises(LeakageError):
        assert_point_in_time(_inputs(), date(2022, 7, 1))


def test_no_canopy_features_before_first_image():
    early = build_features(_inputs(), date(2022, 6, 30))
    assert not any(k.startswith(("ndvi", "ndre", "canopy")) for k in early)
    later = build_features(_inputs(), date(2022, 7, 31))
    assert later["ndvi_current"] == 0.85
    assert later["ndvi_vs_site_mean"] == pytest.approx(0.05)
    assert later["canopy_images_to_date"] == 2


def test_silking_windows_appear_only_after_silking():
    before = build_features(_inputs(), date(2022, 6, 15))
    assert "rain_around_silking_mm" not in before
    status = season_status(_inputs(), date(2022, 9, 30))
    assert status.silking is not None
    after = build_features(_inputs(), date(2022, 9, 30))
    assert "rain_around_silking_mm" in after and "heat_days_grain_fill" in after


def test_missing_values_are_none_not_nan():
    soil = SoilInputs(None, None, None, None, None, None)
    features = build_features(_inputs(soil=soil), date(2022, 7, 31))
    assert features["soil_ph"] is None
    assert not any(isinstance(v, float) and math.isnan(v) for v in features.values())


def test_every_built_feature_is_described_in_the_catalog():
    features = build_features(_inputs(), date(2022, 9, 30))
    unknown = [k for k in features if k not in CATALOG]
    assert not unknown, f"add these to app/features/catalog.py: {unknown}"
    assert info("genotype").dtype == "category"
