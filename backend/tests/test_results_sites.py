"""The final-results contract (/api/results) and the trial-site registry (/api/sites).

The results written here are test fixtures, not model output."""

import json
import os

from fastapi.testclient import TestClient

from app.main import app
from app.results import RESULTS_FILE
from app.results import main as check_results

client = TestClient(app)


def _results(**overrides) -> dict:
    doc = {
        "contract_version": 1,
        "results_version": "test-fixture",
        "dataset_label": "Fixture",
        "model": {"name": "Fixture model", "validation": "fixture split"},
        "interval": {"level": 0.9, "coverage": 0.8},
        "performance": [
            {"dap": 40, "mae": 50.0, "r2": -0.2},
            {"dap": 70, "mae": 20.0, "rmse": 25.0, "r2": 0.5, "n": 10},
        ],
        "earliest_useful_dap": 70,
        "sites": [
            {
                "site": "Lincoln",
                "season": 2022,
                "forecasts": [{"date": "2022-08-01", "dap": 71, "yield": 150}],
            }
        ],
        "plots": [
            {
                "plot_id": "1-2-3",
                "site": "Ames",
                "season": 2022,
                "hybrid": "A X B",
                "planting_date": "2022-05-22",
                "forecasts": [
                    {
                        "date": "2022-07-01",
                        "dap": 40,
                        "yield": 170.0,
                        "lower": 120.0,
                        "upper": 210.0,
                    },
                    {
                        "date": "2022-08-01",
                        "dap": 71,
                        "yield": 180.0,
                        "lower": 160.0,
                        "upper": 195.0,
                    },
                ],
                "uav": {"dap": 70, "satellite_only": 180.0, "satellite_plus_uav": 178.0},
            },
            {
                "plot_id": "1-2-4",
                "site": "Ames",
                "season": 2022,
                "forecasts": [{"date": "2022-08-01", "dap": 71, "yield": 175.0}],
            },
        ],
        "maturity": [
            {
                "site": "Ames",
                "season": 2022,
                "as_of": "2022-08-01",
                "gdd_since_planting": 1500,
                "window_start": "2022-09-18",
                "window_end": "2022-09-24",
            }
        ],
        "uav": {
            "matched": True,
            "sites": ["Ames"],
            "satellite_only": {"mae": 21.0},
            "satellite_plus_uav": {"mae": 20.5},
        },
    }
    doc.update(overrides)
    return doc


def _publish(model_dir, doc) -> None:
    path = model_dir / RESULTS_FILE
    path.write_text(json.dumps(doc))
    # A later write within the same clock tick must still be seen as a new file.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


def test_results_are_pending_until_published():
    body = client.get("/api/results").json()
    assert body["status"] == "pending"
    assert body["performance"] == [] and body["uav"] is None
    assert client.get("/api/results/plots", params={"site": "Ames"}).json() == []


def test_results_serve_the_published_file_without_plots(isolated_model_dir):
    _publish(isolated_model_dir, _results())
    body = client.get("/api/results").json()
    assert body["status"] == "ready"
    assert body["resultsVersion"] == "test-fixture"
    assert body["earliestUsefulDap"] == 70
    assert [p["dap"] for p in body["performance"]] == [40, 70]
    assert "plots" not in body
    assert body["plotCounts"] == [{"site": "Ames", "season": 2022, "plots": 2}]
    assert body["uav"]["matched"] is True
    assert body["maturity"][0]["windowStart"] == "2022-09-18"


def test_result_plots_are_filtered_by_site_and_season(isolated_model_dir):
    _publish(isolated_model_dir, _results())
    plots = client.get("/api/results/plots", params={"site": "ames", "season": 2022}).json()
    assert [p["plotId"] for p in plots] == ["1-2-3", "1-2-4"]
    assert plots[0]["forecasts"][1] == {
        "date": "2022-08-01",
        "dap": 71,
        "yield": 180.0,
        "lower": 160.0,
        "upper": 195.0,
    }
    assert plots[0]["uav"]["satellitePlusUav"] == 178.0
    assert client.get("/api/results/plots", params={"site": "Ames", "season": 2023}).json() == []
    assert client.get("/api/results/plots", params={"site": "Lincoln"}).json() == []


def test_results_accept_camel_case(isolated_model_dir):
    doc = _results()
    doc["resultsVersion"] = doc.pop("results_version")
    doc["earliestUsefulDap"] = doc.pop("earliest_useful_dap")
    _publish(isolated_model_dir, doc)
    assert client.get("/api/results").json()["resultsVersion"] == "test-fixture"


def test_a_new_file_is_read_without_a_restart(isolated_model_dir):
    _publish(isolated_model_dir, _results())
    _publish(isolated_model_dir, _results(results_version="second"))
    assert client.get("/api/results").json()["resultsVersion"] == "second"


def test_malformed_results_fail_loudly_and_say_why(isolated_model_dir):
    bad = _results()
    bad["plots"][0]["forecasts"][0]["lower"] = 175.0  # above the forecast
    _publish(isolated_model_dir, bad)
    res = client.get("/api/results")
    assert res.status_code == 503
    assert "lower <= yield <= upper" in res.json()["detail"]
    assert client.get("/api/results/plots", params={"site": "Ames"}).status_code == 503


def test_results_reject_unknown_fields_and_unordered_stages(isolated_model_dir):
    _publish(isolated_model_dir, _results(accuracy_pct=85.1))
    assert client.get("/api/results").status_code == 503
    _publish(
        isolated_model_dir,
        _results(performance=[{"dap": 70, "mae": 20.0}, {"dap": 40, "mae": 50.0}]),
    )
    assert "DAP order" in client.get("/api/results").json()["detail"]
    _publish(isolated_model_dir, _results(performance=[{"dap": 70}]))
    assert "needs mae or r2" in client.get("/api/results").json()["detail"]


def test_results_checker_cli(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_results()))
    assert check_results([str(good)]) == 0
    assert "OK: test-fixture" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_results(contract_version=2)))
    assert check_results([str(bad)]) == 1


def test_sites_come_from_the_inventory_with_honest_imagery_flags():
    sites = {s["id"]: s for s in client.get("/api/sites").json()}
    assert set(sites) == {"Ames", "Crawfordsville", "Lincoln", "MOValley", "Scottsbluff"}
    assert sites["MOValley"]["name"] == "Missouri Valley"
    assert sites["Lincoln"]["stateName"] == "Nebraska"
    imaged = {k for k, s in sites.items() if s["seasons"][0]["satellite"]["plotImages"] > 0}
    assert imaged == {"Ames", "Crawfordsville", "Lincoln"}
    assert {k for k, s in sites.items() if s["seasons"][0]["uav"]["plotImages"] > 0} == {"Ames"}
    assert sites["Scottsbluff"]["irrigated"] is True
    # The weather library the outlook uses, keyed by the data's spelling.
    assert sites["MOValley"]["weather"]["librarySite"] == "MOValley"
    assert sites["Scottsbluff"]["weather"]["analogWeighting"] is True
    assert sites["Ames"]["weather"]["analogWeighting"] is False


def test_sites_report_final_result_plots(isolated_model_dir):
    _publish(isolated_model_dir, _results())
    sites = {s["id"]: s for s in client.get("/api/sites").json()}
    assert sites["Ames"]["forecasts"] == {
        "livePlots": 0,
        "finalPlots": 2,
        "finalSiteForecast": False,
        "seasons": [2022],
    }
    assert sites["Lincoln"]["forecasts"]["finalSiteForecast"] is True
    assert sites["Scottsbluff"]["forecasts"]["seasons"] == []


def test_sites_still_list_when_the_results_file_is_broken(isolated_model_dir):
    _publish(isolated_model_dir, {"contract_version": 1})
    assert len(client.get("/api/sites").json()) == 5


def test_fields_filter_by_site():
    everyone = client.get("/api/fields").json()
    assert everyone  # unchanged without `site`
    assert client.get("/api/fields", params={"site": "Nowhere"}).json() == []
