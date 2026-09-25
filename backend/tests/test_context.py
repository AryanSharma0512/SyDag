"""
Location context (/api/context/*). Upstream services are replayed from responses
recorded for Purdue Plot 104 (tests/fixtures/context), so no test touches the network.
"""

import csv
import io
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.context import service as service_module
from app.context.cache import ContextCache
from app.context.http import NoData, UpstreamError
from app.context.service import LocationContextService
from app.context.soil import parse_profile, water_class
from app.context.weather import DailyObservation, summarize
from app.context.yield_history import _bushels
from app.context_routes import get_context_service
from app.main import app
from app.schemas import County

FIXTURES = Path(__file__).parent / "fixtures" / "context"
LAT, LON = 40.4883, -86.9982  # Purdue Plot 104
NOW = datetime(2026, 9, 24, tzinfo=UTC)


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


class FakeGov:
    """Replays recorded USDA / NOAA / FCC responses. Hosts in `down` fail like an outage."""

    def __init__(self, **overrides) -> None:
        self.down: set[str] = set()
        self.requests: list[httpx.Request] = []
        self.overrides = overrides

    def payload(self, name: str):
        return self.overrides[name] if name in self.overrides else load(name)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.url.host
        if host in self.down:
            raise httpx.ConnectError("simulated outage", request=request)
        if host == "sdmdataaccess.sc.egov.usda.gov":
            is_horizons = b"FROM chorizon h" in request.content
            return httpx.Response(
                200, json=self.payload("sda_horizons" if is_horizons else "sda_map_unit")
            )
        if host == "geo.fcc.gov":
            return httpx.Response(200, json=self.payload("fcc_county"))
        if host == "www.ncei.noaa.gov":
            is_search = "/search/" in request.url.path
            return httpx.Response(
                200, json=self.payload("ncei_search" if is_search else "ncei_daily")
            )
        if host == "quickstats.nass.usda.gov":
            if request.url.params.get("key") != "test-key":
                return httpx.Response(401, json={"error": ["unauthorized"]})
            return httpx.Response(200, json=self.payload("nass_yields"))
        return httpx.Response(404)

    def calls_to(self, host: str) -> int:
        return sum(1 for r in self.requests if r.url.host == host)


def make_service(tmp_path, fake: FakeGov, nass_key: str | None = None) -> LocationContextService:
    settings = Settings(_env_file=None, cache_dir=tmp_path / "cache", nass_api_key=nass_key)
    client = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return LocationContextService(client, ContextCache(settings.cache_dir), settings)


@pytest.fixture
def gov():
    return FakeGov()


@pytest.fixture
def api(tmp_path, gov):
    """TestClient whose context service talks to `gov`. Set api.nass_key to enable NASS."""
    client = TestClient(app)
    client.nass_key = None
    app.dependency_overrides[get_context_service] = lambda: make_service(
        tmp_path, gov, client.nass_key
    )
    yield client
    app.dependency_overrides.pop(get_context_service, None)


# ---- soil (USDA NRCS SSURGO) ---------------------------------------------------


def test_soil_profile_from_recorded_ssurgo(tmp_path, gov):
    profile, _ = make_service(tmp_path, gov).soil(LAT, LON)
    assert (profile.series, profile.texture, profile.drainage, profile.hydrologic_group) == (
        "Chalmers",
        "Silty clay loam",
        "Poorly drained",
        "B/D",
    )
    assert profile.map_unit_name.startswith("Chalmers silty clay loam")
    assert profile.available_water_capacity == pytest.approx(0.196, abs=0.001)
    assert profile.available_water_storage_cm == pytest.approx(19.6, abs=0.05)
    assert profile.available_water_class == "High"
    assert (profile.organic_matter, profile.ph, profile.root_zone_depth_cm) == (4.5, 6.7, 152.0)
    assert profile.source == "USDA NRCS SSURGO"


MAP_UNIT = {"mukey": "1", "muname": "Urban land-Carmi complex"}
URBAN = (
    MAP_UNIT
    | {"cokey": "10", "compname": "Urban land", "comppct_r": "60"}
    | {"compkind": "Miscellaneous area"}
)
CARMI = MAP_UNIT | {"cokey": "11", "compname": "Carmi", "comppct_r": "40", "compkind": "Series"}


def test_soil_skips_land_cover_components():
    assert parse_profile([URBAN, CARMI], [], NOW).series == "Carmi"


def test_soil_only_land_cover_is_no_data():
    with pytest.raises(NoData, match="maps this location as urban land"):
        parse_profile([URBAN], [], NOW)


@pytest.mark.parametrize(
    "storage, expected",
    [(None, None), (9.9, "Low"), (10.0, "Moderate"), (14.9, "Moderate"), (15.0, "High")],
)
def test_water_class(storage, expected):
    assert water_class(storage) == expected


def test_county_from_fcc(tmp_path, gov):
    assert make_service(tmp_path, gov).county(LAT, LON) == County(
        name="Tippecanoe County", state_code="IN", state_name="Indiana", fips="18157"
    )


# ---- weather (NOAA NCEI GHCN-Daily) --------------------------------------------


def test_weather_from_recorded_noaa(tmp_path, gov):
    observed, _ = make_service(tmp_path, gov).weather(
        LAT, LON, [date(2026, 7, 22), date(2026, 5, 30)]
    )
    assert (observed.station.id, observed.station.name) == (
        "USC00129430",
        "West Lafayette 6 NW, IN",
    )
    assert observed.station.distance_km == pytest.approx(1.6, abs=0.1)
    jul22, may30 = observed.summaries  # request order is kept
    assert jul22.as_of == "2026-07-22"
    assert (jul22.rainfall_last_30_days_mm, jul22.gdd_since_season_start) == (75.9, 1562)
    assert (jul22.heat_days, jul22.longest_dry_spell_days) == (3, 8)
    assert may30.gdd_since_season_start == 388
    assert 0.9 <= jul22.data_completeness <= 1


def day(n: int, prcp: float | None = 0.0, tmax: float | None = 80.0, tmin: float | None = 60.0):
    return DailyObservation(date(2026, 7, n), prcp, tmax, tmin)


def test_summary_arithmetic():
    days = [
        day(1, 0.0, 100, 40),  # GDD capped/floored: (86 + 50) / 2 - 50 = 18; heat day
        day(2, 0.0, 45, 30),  # below base: 0 GDD
        day(3, 0.5, 95, 70),  # wet; exactly 95 °F is a heat day; GDD (86 + 70) / 2 - 50 = 28
        day(4),  # dry, GDD 20
        day(5),
        day(6),
        day(7, None),  # rain not recorded: breaks the dry run and the completeness count
        day(8),
        day(9, 0.03),  # under 1 mm still counts as dry, so Jul 8-11 is the longest run
        day(10),
        day(11),
    ]
    s = summarize(days, date(2026, 7, 11), season_start=date(2026, 7, 1))
    assert s.gdd_since_season_start == 18 + 0 + 28 + 20 * 8
    assert s.heat_days == 2
    assert s.longest_dry_spell_days == 4  # Jul 8-11, through the 0.03-inch day
    assert s.rainfall_last_7_days_mm == round(0.03 * 25.4, 1)  # Jul 5-11
    assert s.rainfall_last_30_days_mm == round(0.53 * 25.4, 1)
    assert s.data_completeness == round(10 / 11, 2)
    assert s.observed_through == "2026-07-11"


def test_summary_before_season_start_has_no_season_totals():
    s = summarize([day(1, 0.2), day(2)], date(2026, 7, 2), season_start=date(2026, 7, 5))
    assert (s.gdd_since_season_start, s.heat_days, s.longest_dry_spell_days) == (0, 0, 0)
    assert s.data_completeness == 0.0
    assert s.rainfall_last_7_days_mm == round(0.2 * 25.4, 1)


def station(sid, lon, lat, start="1990-01-01", end="2026-09-20", types=("PRCP", "TMAX", "TMIN")):
    return {
        "stations": [{"id": sid, "name": f"{sid}, IN US"}],
        "location": {"coordinates": [lon, lat]},
        "startDate": f"{start}T00:00:00",
        "endDate": f"{end}T23:59:59",
        "dataTypes": [{"id": t} for t in types],
    }


def test_station_choice_prefers_complete_records_over_distance(tmp_path):
    results = [
        station("CLOSE_BUT_ENDS_EARLY", LON, LAT + 0.01, end="2026-06-30"),
        station("NO_TEMPERATURE", LON, LAT, types=("PRCP",)),
        station("STARTS_LATE", LON, LAT, start="2026-06-01"),
        station("FARTHER_COMPLETE", LON, LAT + 0.2),
    ]
    gov = FakeGov(ncei_search={"results": results})
    observed, _ = make_service(tmp_path, gov).weather(LAT, LON, [date(2026, 7, 22)])
    assert observed.station.id == "FARTHER_COMPLETE"


def test_station_search_widens_then_gives_up(tmp_path):
    gov = FakeGov(ncei_search={"results": []})
    with pytest.raises(NoData, match="no NOAA station"):
        make_service(tmp_path, gov).weather(LAT, LON, [date(2026, 7, 22)])
    assert gov.calls_to("www.ncei.noaa.gov") == 2  # both search radii were tried


# ---- county yields (USDA NASS Quick Stats) -------------------------------------


def test_yield_history_parsing_and_request(tmp_path, gov):
    history, _ = make_service(tmp_path, gov, nass_key="test-key").yield_history(LAT, LON, 2025)
    assert [(y.year, y.yield_) for y in history.years] == [
        (2020, 187.6),
        (2021, 194.0),
        (2023, 202.1),  # 2022 is withheld ("(D)"); the combined-counties row is ignored
        (2024, 198.9),
        (2025, 205.4),
    ]
    assert history.five_year_average == 197.6
    assert history.county.name == "Tippecanoe County"
    params = next(r for r in gov.requests if r.url.host == "quickstats.nass.usda.gov").url.params
    assert (params["state_alpha"], params["county_ansi"]) == ("IN", "157")
    # Quick Stats ignores year__LE when year__GE is also sent, so the years are listed.
    assert params.get_list("year") == [str(y) for y in range(2016, 2026)]


def test_yield_history_drops_years_after_through_year(tmp_path):
    gov = FakeGov(
        nass_yields={
            "data": [
                {"year": 2021, "Value": "180.0", "county_ansi": "157"},
                {"year": 2022, "Value": "190.0", "county_ansi": "157"},
                {"year": 2023, "Value": "200.0", "county_ansi": "157"},
            ]
        }
    )
    history, _ = make_service(tmp_path, gov, nass_key="test-key").yield_history(LAT, LON, 2022)
    assert [y.year for y in history.years] == [2021, 2022]


@pytest.mark.parametrize(
    "raw, expected", [("205.4", 205.4), ("1,234.5", 1234.5), ("(D)", None), (" (NA) ", None)]
)
def test_nass_value_parsing(raw, expected):
    assert _bushels(raw) == expected


def test_yield_history_without_published_values_is_no_data(tmp_path):
    gov = FakeGov(nass_yields={"data": [{"year": 2025, "Value": "(D)", "county_ansi": "157"}]})
    with pytest.raises(NoData, match="no published corn yields for Tippecanoe County"):
        make_service(tmp_path, gov, nass_key="test-key").yield_history(LAT, LON, 2025)


# ---- cache ---------------------------------------------------------------------


def test_cache_serves_fresh_entries_without_refetching(tmp_path):
    cache, calls = ContextCache(tmp_path), []
    fetch = lambda: calls.append(1) or {"v": len(calls)}  # noqa: E731
    first = cache.get_or_fetch("ns", "k", timedelta(hours=1), fetch)
    second = cache.get_or_fetch("ns", "k", timedelta(hours=1), fetch)
    assert first.value == second.value == {"v": 1} and len(calls) == 1


def test_cache_refetches_expired_and_never_expires_without_ttl(tmp_path):
    cache, calls = ContextCache(tmp_path), []
    fetch = lambda: calls.append(1) or len(calls)  # noqa: E731
    cache.get_or_fetch("ns", "k", timedelta(0), fetch)
    assert cache.get_or_fetch("ns", "k", timedelta(0), fetch).value == 2
    cache.get_or_fetch("forever", "k", None, fetch)
    assert cache.get_or_fetch("forever", "k", None, fetch).value == 3


def test_cache_serves_stale_copy_when_refresh_fails(tmp_path):
    cache = ContextCache(tmp_path)
    cache.get_or_fetch("ns", "k", timedelta(0), lambda: "saved")

    def failing():
        raise UpstreamError("Test service", "down")

    entry = cache.get_or_fetch("ns", "k", timedelta(0), failing)
    assert (entry.value, entry.stale) == ("saved", True)
    with pytest.raises(UpstreamError):
        cache.get_or_fetch("ns", "never-fetched", timedelta(0), failing)


def test_cache_survives_corrupt_entries_and_unwritable_disk(tmp_path):
    cache = ContextCache(tmp_path)
    path = cache._path("ns", "k")
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert cache.get_or_fetch("ns", "k", None, lambda: "fresh").value == "fresh"
    blocked = tmp_path / "a-file"
    blocked.write_text("")
    assert ContextCache(blocked).get_or_fetch("ns", "k", None, lambda: "ok").value == "ok"


# ---- endpoints -----------------------------------------------------------------

DATES = "date=2026-07-22&date=2026-05-30"


def test_all_combines_sources_and_reports_each_status(api):
    res = api.get(f"/api/context/all?lat={LAT}&lon={LON}&{DATES}")
    assert res.status_code == 200
    body = res.json()
    assert body["county"] == {
        "name": "Tippecanoe County",
        "stateCode": "IN",
        "stateName": "Indiana",
        "fips": "18157",
    }
    assert body["soil"]["status"] == "ok" and body["soil"]["data"]["series"] == "Chalmers"
    assert body["weather"]["status"] == "ok"
    assert [s["asOf"] for s in body["weather"]["data"]["summaries"]] == ["2026-07-22", "2026-05-30"]
    assert body["yieldHistory"]["status"] == "not_configured"
    assert "SOILSIGNAL_NASS_API_KEY" in body["yieldHistory"]["message"]


def test_all_with_nass_key(api):
    api.nass_key = "test-key"
    body = api.get(f"/api/context/all?lat={LAT}&lon={LON}&{DATES}").json()
    history = body["yieldHistory"]
    assert history["status"] == "ok"
    assert history["data"]["fiveYearAverage"] == 197.6
    assert history["data"]["years"][-1] == {"year": 2025, "yield": 205.4}


def test_one_source_failing_leaves_the_others(api, gov):
    gov.down.add("www.ncei.noaa.gov")
    body = api.get(f"/api/context/all?lat={LAT}&lon={LON}&{DATES}").json()
    assert body["weather"] == {
        "status": "unavailable",
        "data": None,
        "message": "NOAA NCEI did not respond. Try again shortly.",
    }
    assert body["soil"]["status"] == "ok"


def test_second_request_is_served_from_cache(api, gov):
    api.get(f"/api/context/all?lat={LAT}&lon={LON}&{DATES}")
    before = len(gov.requests)
    assert api.get(f"/api/context/all?lat={LAT}&lon={LON}&{DATES}").status_code == 200
    assert len(gov.requests) == before


def test_stale_copy_is_served_and_flagged_when_a_source_goes_down(api, gov, monkeypatch):
    monkeypatch.setattr(service_module, "SOIL_TTL", timedelta(0))
    api.get(f"/api/context/all?lat={LAT}&lon={LON}&{DATES}")
    gov.down.add("sdmdataaccess.sc.egov.usda.gov")
    soil = api.get(f"/api/context/all?lat={LAT}&lon={LON}&{DATES}").json()["soil"]
    assert soil["status"] == "ok" and soil["data"]["series"] == "Chalmers"
    assert soil["message"].startswith("The source did not respond, so this is the copy from")


def test_single_source_endpoints(api):
    soil = api.get(f"/api/context/soil?lat={LAT}&lon={LON}").json()
    assert {"series", "availableWaterCapacity", "hydrologicGroup", "retrievedAt"} <= soil.keys()
    weather = api.get(f"/api/context/weather?lat={LAT}&lon={LON}&date=2026-07-22").json()
    assert [s["asOf"] for s in weather["summaries"]] == ["2026-07-22"]
    assert weather["station"]["id"] == "USC00129430"


@pytest.mark.parametrize(
    "setup, path, status, detail",
    [
        (None, "/api/context/yield-history?lat={lat}&lon={lon}", 503, "SOILSIGNAL_NASS_API_KEY"),
        (
            "sda-down",
            "/api/context/soil?lat={lat}&lon={lon}",
            502,
            "Soil Data Access did not respond",
        ),
        ("no-survey", "/api/context/soil?lat={lat}&lon={lon}", 404, "no soil survey"),
        ("bad-key", "/api/context/yield-history?lat={lat}&lon={lon}", 502, "USDA NASS Quick Stats"),
    ],
)
def test_single_source_errors(api, gov, setup, path, status, detail):
    if setup == "sda-down":
        gov.down.add("sdmdataaccess.sc.egov.usda.gov")
    elif setup == "no-survey":
        gov.overrides["sda_map_unit"] = {}
    elif setup == "bad-key":
        api.nass_key = "wrong-key"
    res = api.get(path.format(lat=LAT, lon=LON))
    assert res.status_code == status
    assert detail in res.json()["detail"]


@pytest.mark.parametrize(
    "query",
    [
        f"lat=95&lon={LON}&date=2026-07-22",  # latitude out of range
        f"lat={LAT}&lon={LON}",  # no date
        f"lat={LAT}&lon={LON}&date=July-22",  # not ISO
        # 25 dates, one over the limit:
        f"lat={LAT}&lon={LON}&" + "&".join(f"date=2026-06-{d:02d}" for d in range(1, 26)),
    ],
)
def test_all_validates_its_query(api, query):
    assert api.get(f"/api/context/all?{query}").status_code == 422


def test_blank_nass_key_counts_as_not_configured(monkeypatch):
    monkeypatch.setenv("SOILSIGNAL_NASS_API_KEY", "  ")
    assert Settings(_env_file=None).nass_api_key is None


def test_yield_history_from_recorded_nass(tmp_path):
    gov = FakeGov(nass_yields=load("nass_yields_recorded"))
    history, _ = make_service(tmp_path, gov, nass_key="test-key").yield_history(LAT, LON, 2025)
    assert [y.year for y in history.years] == list(range(2017, 2026))
    assert (history.years[-1].yield_, history.years[-2].yield_) == (233.4, 220.0)  # "220" parses
    assert history.five_year_average == 214.3


# ---- CSV export ----------------------------------------------------------------


def csv_rows(res) -> list[list[str]]:
    return list(csv.reader(io.StringIO(res.text)))


def test_export_weather_csv(api):
    res = api.get(f"/api/context/export?lat={LAT}&lon={LON}&type=weather&{DATES}")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert res.headers["content-disposition"] == (
        'attachment; filename="soilsignal-weather-40.4883_-86.9982.csv"'
    )
    header, *rows = csv_rows(res)
    assert header[:4] == ["latitude", "longitude", "asOf", "observedThrough"]
    assert [r[header.index("asOf")] for r in rows] == ["2026-07-22", "2026-05-30"]
    assert {r[header.index("stationId")] for r in rows} == {"USC00129430"}
    # The same derived values the JSON endpoint returns.
    summary = api.get(f"/api/context/all?lat={LAT}&lon={LON}&{DATES}").json()["weather"]["data"][
        "summaries"
    ][0]
    assert float(rows[0][header.index("rainfallLast30DaysMm")]) == summary["rainfallLast30DaysMm"]
    assert float(rows[0][header.index("gddSinceSeasonStart")]) == summary["gddSinceSeasonStart"]


def test_export_soil_csv_is_key_value(api):
    rows = csv_rows(api.get(f"/api/context/export?lat={LAT}&lon={LON}&type=soil&{DATES}"))
    assert rows[0] == ["property", "value"]
    props = dict(rows[1:])
    assert props["latitude"] == "40.4883"
    assert props["series"] == "Chalmers"
    assert props["source"] == "USDA NRCS SSURGO"
    assert "retrievedAt" in props


def test_export_yield_history_csv(api):
    api.nass_key = "test-key"
    res = api.get(f"/api/context/export?lat={LAT}&lon={LON}&type=yield-history&{DATES}")
    header, *rows = csv_rows(res)
    assert header[2:5] == ["year", "yield", "unit"]
    assert rows[-1][2:6] == ["2025", "205.4", "bu/ac", "Tippecanoe County"]
    assert "test-key" not in res.text


def test_export_all_reports_every_status(api):
    res = api.get(f"/api/context/export?lat={LAT}&lon={LON}&type=all&{DATES}")
    assert res.status_code == 200
    rows = csv_rows(res)
    assert rows[0] == ["dataset", "record", "property", "value"]
    statuses = {r[0]: r[3] for r in rows if r[2] == "status"}
    assert statuses == {"soil": "ok", "weather": "ok", "yieldHistory": "not_configured"}
    assert ["weather", "2026-05-30", "asOf", "2026-05-30"] in rows
    assert ["soil", "", "series", "Chalmers"] in rows


@pytest.mark.parametrize(
    "query, status",
    [
        (f"type=yield-history&{DATES}", 503),  # no NASS key
        (f"type=raw&{DATES}", 422),
        ("type=weather", 422),  # no date
    ],
)
def test_export_errors(api, query, status):
    assert api.get(f"/api/context/export?lat={LAT}&lon={LON}&{query}").status_code == status
