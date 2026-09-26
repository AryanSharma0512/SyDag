"""Historical weather outlook: formulas shared with the feature pipeline, no future
leakage, the outlook's own season never an analog, fixed categories, and the contract."""

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.features.weather import weather_features
from app.weather_outlook.analogs import (
    category_probabilities,
    effective_sample_size,
    percentile_rank,
    round_probabilities,
    weighted_quantile,
)
from app.weather_outlook.contract import to_contract, trajectories_frame
from app.weather_outlook.features import (
    DESCRIPTOR_SOURCES,
    descriptors,
    from_record,
    horizon_outcomes,
    stage_outcomes,
)
from app.weather_outlook.history import DAILY_FILE, MANIFEST_FILE, WeatherLibrary
from app.weather_outlook.scenarios import OutlookError, WeatherOutlook, couple_yield

SEASONS = list(range(2005, 2017))
PUBLISHED = Path(__file__).resolve().parents[1] / "data" / "weather_history"


def synthetic_daily(seed: int = 7, years=SEASONS) -> pd.DataFrame:
    """Plausible Corn Belt weather: a seasonal cycle, year-to-year anomalies, dry spells,
    heavy-rain days and a few missing days."""
    rng = np.random.default_rng(seed)
    rows = []
    for year in years:
        warm = rng.normal(0, 1.5)
        wet = rng.lognormal(0, 0.35)
        day = date(year, 1, 1)
        while day.year == year:
            doy = day.timetuple().tm_yday
            cycle = 13 * math.sin(2 * math.pi * (doy - 110) / 365)
            tmax = 16 + cycle + warm + rng.normal(0, 3.5)
            tmin = tmax - rng.uniform(7, 14)
            rain = rng.exponential(9 * wet) if rng.random() < 0.3 else 0.0
            rows.append(
                {
                    "site": "Testville",
                    "date": day.isoformat(),
                    "station_id": "TEST1",
                    "tmax_c": np.nan if rng.random() < 0.004 else round(tmax, 2),
                    "tmin_c": round(tmin, 2),
                    "precip_mm": np.nan if rng.random() < 0.004 else round(rain, 2),
                }
            )
            day += timedelta(1)
    return pd.DataFrame(rows)


def write_library(directory: Path, daily: pd.DataFrame, irrigated: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    daily.to_csv(directory / DAILY_FILE, index=False, compression="gzip")
    manifest = {
        "library": "test",
        "label": "Synthetic test library",
        "outlook": {"bootstrap_samples": 60, "robust_min_seasons": 20},
        "sites": {
            "Testville": {
                "latitude": 42.0,
                "longitude": -93.6,
                "irrigated": irrigated,
                "reference_planting": "05-05",
                "root_zone_water_mm": 180,
                "station": {"id": "TEST1", "name": "Test station", "source": "synthetic"},
                "seasons": SEASONS,
                "excluded_seasons": {},
                "observed_through": daily["date"].max(),
            }
        },
    }
    (directory / MANIFEST_FILE).write_text(json.dumps(manifest))
    return directory


@pytest.fixture(scope="module")
def library(tmp_path_factory) -> WeatherLibrary:
    return WeatherLibrary(write_library(tmp_path_factory.mktemp("lib"), synthetic_daily()))


@pytest.fixture(scope="module")
def engine(library) -> WeatherOutlook:
    return WeatherOutlook(library)


# --- the same formulas as the feature pipeline ------------------------------------------


@pytest.mark.parametrize("as_of", [date(2010, 4, 20), date(2010, 6, 1), date(2010, 7, 20)])
def test_horizon_outcomes_are_the_feature_pipelines_numbers(library, as_of):
    record = library.record("Testville")
    planting, end = date(2010, 5, 5), date(2010, 10, 15)
    season = from_record(record, date(2010, 4, 1), end)
    outcomes = horizon_outcomes(season, as_of, end, planting)
    days = season.daily_weather()
    window = [d for d in days if d.day > as_of]
    ref, _ = weather_features(window, as_of + timedelta(1), end, record.info.latitude)
    pairs = {
        "gdd": "gdd_since_planting",
        "precip_mm": "rain_since_planting_mm",
        "heat_days": "heat_days_since_planting",
        "kdd_29c": "killing_degree_days_29c",
        "warm_nights": "warm_nights_since_planting",
        "longest_dry_spell_days": "longest_dry_spell_days",
        "very_heavy_rain_days": "very_heavy_rain_days",
    }
    for ours, theirs in pairs.items():
        assert outcomes[ours] == pytest.approx(ref[theirs], abs=1e-9), ours
    full, _ = weather_features(days, planting, end, record.info.latitude)
    before = weather_features(days, planting, as_of, record.info.latitude)[0]
    expected = full["water_deficit_since_planting_mm"] - before.get(
        "water_deficit_since_planting_mm", 0.0
    )
    assert outcomes["water_deficit_mm"] == pytest.approx(expected, abs=1e-6)
    stages = stage_outcomes(season, end, planting)
    assert stages, "silking should be reached by mid October"
    for key, value in stages.items():
        assert value == pytest.approx(full[key], abs=1e-6), key


def test_descriptors_are_the_feature_pipelines_numbers(library):
    record = library.record("Testville")
    as_of, start = date(2011, 6, 15), date(2011, 4, 1)
    ours = descriptors(record, as_of, start, date(2011, 5, 5))
    ref, _ = weather_features(record.daily_weather(start, as_of), start, as_of, 42.0)
    for name, key in DESCRIPTOR_SOURCES.items():
        assert ours[name] == pytest.approx(ref[key]), name
    assert ours["tmean_30d_c"] == pytest.approx((ref["tmean_30d_f"] - 32) * 5 / 9)


# --- no leakage -------------------------------------------------------------------------


def _contract(engine: WeatherOutlook, **kwargs) -> dict:
    return to_contract(engine.generate("Testville", date(2012, 6, 10), 60, **kwargs))


def test_changing_the_current_season_after_as_of_changes_nothing(tmp_path):
    daily = synthetic_daily()
    base = WeatherOutlook(WeatherLibrary(write_library(tmp_path / "a", daily)))
    tampered = daily.copy()
    after = pd.to_datetime(tampered["date"]) > "2012-06-10"
    this_year = pd.to_datetime(tampered["date"]).dt.year == 2012
    tampered.loc[after & this_year, "precip_mm"] = 150.0
    tampered.loc[after & this_year, "tmax_c"] += 12
    tampered.loc[after & this_year, "tmin_c"] -= 12
    other = WeatherOutlook(WeatherLibrary(write_library(tmp_path / "b", tampered)))
    assert _contract(base) == _contract(other)


def test_changing_the_current_season_up_to_as_of_does_change_the_outlook(tmp_path):
    """The control for the leakage test: the season so far is what the analogs match on."""
    daily = synthetic_daily()
    base = WeatherOutlook(WeatherLibrary(write_library(tmp_path / "a", daily)))
    changed = daily.copy()
    before = (pd.to_datetime(changed["date"]) <= "2012-06-10") & (
        pd.to_datetime(changed["date"]) >= "2012-04-01"
    )
    changed.loc[before, "precip_mm"] = 0.0
    other = WeatherOutlook(WeatherLibrary(write_library(tmp_path / "b", changed)))
    assert _contract(base)["analogs"] != _contract(other)["analogs"]


def test_supplied_current_weather_is_read_only_through_as_of(engine, library):
    record = library.record("Testville")
    days = record.daily_weather(date(2012, 1, 1), date(2012, 12, 31))
    later = [d if d.day <= date(2012, 6, 10) else type(d)(d.day, 120.0, 90.0, 300.0) for d in days]
    a = _contract(engine, current_weather=days)
    b = _contract(engine, current_weather=later)
    assert a == b


def test_the_outlooks_own_season_is_never_an_analog(engine):
    outlook = engine.generate("Testville", date(2012, 6, 10), 60)
    assert 2012 not in outlook.seasons
    assert 2012 not in [tr.season for tr in outlook.trajectories]
    assert outlook.left_out[2012]
    fewer = engine.generate("Testville", date(2012, 6, 10), 60, exclude_seasons=[2007, 2008])
    assert {2007, 2008}.isdisjoint(fewer.seasons)
    assert fewer.n_seasons == outlook.n_seasons - 2


def test_trajectories_are_dated_in_the_outlook_season(engine):
    outlook = engine.generate("Testville", date(2012, 6, 10), 30)
    for tr in outlook.trajectories:
        assert tr.future.first == date(2012, 6, 11)
        assert len(tr.future) == 30
        assert tr.weather[-1].day == date(2012, 7, 10)
        season = outlook.season_weather(tr)
        assert season[-1].day == date(2012, 7, 10)
        assert max(d.day for d in season if d.day <= date(2012, 6, 10)) == date(2012, 6, 10)
    frame = trajectories_frame(outlook)
    assert len(frame) == 30 * outlook.n_seasons
    assert set(frame["source_season"]) == set(outlook.seasons)


# --- weights and categories -------------------------------------------------------------


@pytest.mark.parametrize("horizon", [30, 60, 90, "season"])
def test_every_horizon_gives_a_coherent_outlook(engine, horizon):
    outlook = engine.generate("Testville", date(2013, 7, 1), horizon)
    w = outlook.weight_array()
    assert w.sum() == pytest.approx(1.0)
    assert 1 <= outlook.weights.ess <= outlook.n_seasons + 1e-9
    # the ESS floor: never fewer effective seasons than the configured share
    assert outlook.weights.ess >= outlook.settings.min_ess_fraction * outlook.n_seasons - 1e-6
    cats = outlook.categories
    if cats.available:
        assert cats.probabilities.sum() == pytest.approx(1.0)
        # categories come from the unweighted ensemble: about a third each
        assert np.all(np.abs(cats.climatology - 1 / 3) <= 0.1)
        doc = to_contract(outlook)
        assert sum(doc["probabilities"].values()) == pytest.approx(1.0)
        assert all(round(v * 100) == pytest.approx(v * 100) for v in doc["probabilities"].values())
        for lo, hi in doc["probabilityIntervals"].values():
            assert 0 <= lo <= hi <= 1


def test_early_season_uses_equal_weights(engine):
    outlook = engine.generate("Testville", date(2012, 4, 10), 30)
    assert outlook.weights.method == "climatology"
    assert np.allclose(outlook.weight_array(), 1 / outlook.n_seasons)


def test_similar_seasons_get_more_weight(engine):
    outlook = engine.generate("Testville", date(2012, 7, 15), 60)
    by_distance = sorted(outlook.trajectories, key=lambda tr: tr.distance)
    assert by_distance[0].weight >= by_distance[-1].weight


def test_irrigated_sites_are_scored_on_heat(tmp_path):
    engine = WeatherOutlook(
        WeatherLibrary(write_library(tmp_path, synthetic_daily(), irrigated=True))
    )
    outlook = engine.generate("Testville", date(2012, 6, 20), "season")
    assert outlook.categories.basis.scorer == "stage_weighted_heat"
    assert all(tr.score <= 0 for tr in outlook.trajectories)


def test_category_helpers():
    ref = np.array([1.0, 2, 3, 4, 5, 6])
    assert percentile_rank(3.5, ref) == pytest.approx(0.5)
    assert percentile_rank(3.0, np.full(4, 3.0)) == pytest.approx(0.5)
    cats, probs = category_probabilities(ref, np.full(6, 1 / 6))
    assert list(cats) == [0, 0, 1, 1, 2, 2]
    assert probs == pytest.approx([1 / 3] * 3)
    assert effective_sample_size(np.full(10, 0.1)) == pytest.approx(10)
    assert effective_sample_size(np.array([1.0, 0, 0])) == pytest.approx(1)
    assert sum(round_probabilities(np.array([0.333, 0.333, 0.334]))) == pytest.approx(1.0)
    assert weighted_quantile(np.array([1.0, 2, 3]), np.ones(3), 0.5) == pytest.approx(2)


# --- requests the library cannot answer -----------------------------------------------------


def test_requests_outside_the_library_are_refused(engine):
    with pytest.raises(OutlookError, match="unknown site"):
        engine.generate("Nowhere", date(2012, 6, 1), 30)
    with pytest.raises(OutlookError, match="horizon"):
        engine.generate("Testville", date(2012, 6, 1), 0)
    with pytest.raises(OutlookError, match="after"):
        engine.generate("Testville", date(2012, 10, 1), 90)
    with pytest.raises(OutlookError, match="observations end"):
        engine.generate("Testville", date(2017, 6, 1), 30)


# --- the yield model's view ------------------------------------------------------------------


def test_yield_coupling_scores_each_trajectory(engine):
    outlook = engine.generate("Testville", date(2012, 6, 10), "season")

    def rain_model(weather) -> float:
        return 150 + sum(d.prcp_mm or 0 for d in weather if d.day > date(2012, 6, 10)) / 10

    coupled = couple_yield(outlook, rain_model)
    assert coupled.outlook.categories.basis.scorer == "yield_model"
    assert coupled.outlook.categories.available
    rain = coupled.outlook.outcome_array("precip_mm")
    assert np.argmax(coupled.yields) == np.argmax(rain)
    doc = to_contract(coupled.outlook, coupled)
    assert doc["categoryBasis"]["provisional"] is False
    assert set(doc["yield"]["perSeason"]) == {str(s) for s in outlook.seasons}
    low, high = doc["yield"]["byCategory"]["adverse"], doc["yield"]["byCategory"]["favorable"]
    assert low < high


def test_a_weather_blind_model_cannot_define_categories(engine):
    outlook = engine.generate("Testville", date(2012, 6, 10), "season")
    coupled = couple_yield(outlook, lambda weather: 180.0)
    assert not coupled.outlook.categories.available
    assert "does not respond" in coupled.outlook.categories.reason
    assert to_contract(coupled.outlook, coupled)["probabilities"] is None


# --- the published libraries ------------------------------------------------------------------


@pytest.mark.skipif(not (PUBLISHED / "supplied").exists(), reason="no published library")
def test_supplied_library_is_labelled_exploratory():
    engine = WeatherOutlook(WeatherLibrary(PUBLISHED / "supplied"))
    doc = to_contract(engine.generate("Ames", date(2023, 6, 1), 60))
    assert doc["historicalSeasons"] == 5
    assert doc["exploratory"] is True
    assert doc["reliability"].startswith("Exploratory, based on 5 historical seasons")


@pytest.mark.skipif(not (PUBLISHED / "long").exists(), reason="no published library")
def test_long_library_answers_the_briefs_example_calls():
    engine = WeatherOutlook(WeatherLibrary(PUBLISHED / "long"))
    for site, as_of, horizon in [
        ("Ames", date(2023, 5, 1), 30),
        ("Ames", date(2023, 5, 1), 60),
        ("Ames", date(2023, 6, 15), 60),
        ("Lincoln", date(2023, 7, 1), "season"),
    ]:
        doc = to_contract(engine.generate(site, as_of, horizon))
        assert doc["historicalSeasons"] >= 20
        assert not doc["exploratory"]
        assert as_of.year not in doc["seasonsUsed"]


# --- the endpoint ----------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import app
    from app.weather_outlook.service import get_engine

    write_library(tmp_path / "test", synthetic_daily())
    monkeypatch.setenv("SOILSIGNAL_WEATHER_HISTORY_DIR", str(tmp_path))
    monkeypatch.setenv("SOILSIGNAL_WEATHER_OUTLOOK_LIBRARY", "test")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


def test_endpoint_serves_the_contract(api):
    res = api.get(
        "/api/weather-outlook",
        params={"site": "testville", "asOfDate": "2012-06-01", "horizonDays": "60"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["site"] == "Testville"
    assert body["horizonDays"] == 60
    assert body["historicalSeasons"] == len(SEASONS) - 1
    assert body["exploratory"] is True
    assert set(body["probabilities"]) == {"adverse", "typical", "favorable"}
    assert "precipitationMm" in body["weatherSummary"]
    season = api.get(
        "/api/weather-outlook",
        params={"site": "Testville", "asOfDate": "2012-07-01", "horizonDays": "season"},
    ).json()
    assert season["horizonEnd"] == "2012-10-15"
    assert "stageSummary" in season


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"site": "Nowhere", "asOfDate": "2012-06-01"}, 404),
        ({"site": "Testville", "asOfDate": "2012-06-01", "horizonDays": "-3"}, 422),
        ({"site": "Testville", "asOfDate": "2012-06-01", "horizonDays": "soon"}, 422),
        ({"site": "Testville", "asOfDate": "2012-10-20", "horizonDays": "90"}, 422),
        ({"site": "Testville", "asOfDate": "2012-06-01", "library": "missing"}, 503),
        ({"site": "Testville", "asOfDate": "2012-06-01", "library": "../etc"}, 404),
    ],
)
def test_endpoint_rejects_what_it_cannot_answer(api, params, status):
    assert api.get("/api/weather-outlook", params=params).status_code == status


def test_a_site_without_analog_weighting_uses_equal_weights(tmp_path):
    directory = write_library(tmp_path, synthetic_daily())
    manifest = json.loads((directory / MANIFEST_FILE).read_text())
    manifest["sites"]["Testville"]["analog_weighting"] = False
    (directory / MANIFEST_FILE).write_text(json.dumps(manifest))
    engine = WeatherOutlook(WeatherLibrary(directory))
    outlook = engine.generate("Testville", date(2012, 7, 15), 60)
    assert outlook.weights.method == "climatology"
    assert np.allclose(outlook.weight_array(), 1 / outlook.n_seasons)
    assert "did not beat equal weights" in to_contract(outlook)["weighting"]
    forced = engine.generate("Testville", date(2012, 7, 15), 60, weighting="analog")
    assert forced.weights.method == "historical_analogs"
