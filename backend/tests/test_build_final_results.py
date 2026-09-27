"""scripts/build_final_results.py: the ML team's temporal CSVs to the results contract.

The CSVs written here are small test fixtures, not model output."""

import json

import pandas as pd
import pytest

from app.results import LoadedResults, parse
from scripts.build_final_results import BuildError, _dumps, _group_metrics, build

DATES = {"Ames": ["2022-07-15", "2022-07-23"], "Lincoln": ["2022-07-18", "2022-08-06"]}
PLANTED = {"Ames": "2022-05-22", "Lincoln": "2022-05-22"}
# (site, plot, actual, [(TP1 prediction), (TP2 prediction)])
PLOTS = [
    ("Ames", "2022_Ames_4231_1_1", 150.0, [140.0, 148.0]),
    ("Ames", "2022_Ames_4231_1_2", 170.0, [160.0, 168.0]),
    ("Ames", "2022_Ames_4231_1_3", 190.0, [175.0, 185.0]),
    ("Lincoln", "2022_Lincoln_hybrids_1_1", 10.0, [-4.0, 6.0]),
    ("Lincoln", "2022_Lincoln_hybrids_1_2", 40.0, [45.0, 42.0]),
    ("Lincoln", "2022_Lincoln_hybrids_1_3", 90.0, [70.0, 80.0]),
]


def _rows() -> pd.DataFrame:
    rows = []
    for site, plot, actual, predicted in PLOTS:
        dap = [(pd.Timestamp(d) - pd.Timestamp(PLANTED[site])).days for d in DATES[site]]
        for series, stages in [
            ("deployed", [("TP1", dap[0], predicted[0]), ("TP2", dap[1], predicted[1])]),
            ("raw_satellite_only", [("TP1", dap[0], 0.0), ("TP2", dap[1], 0.0)]),
            ("preseason", [("TP0", 0, actual - 12.0)]),
        ]:
            for stage, d, pred in stages:
                rows.append(
                    {
                        "location": site,
                        "plot_id": plot,
                        "timepoint": stage,
                        "dap": float(d),
                        "actual_yield_bu_ac": actual,
                        "predicted_yield_bu_ac": pred,
                        "lower_90": pred - 20.0,
                        "upper_90": pred + 20.0,
                        "series": series,
                    }
                )
    return pd.DataFrame(rows)


def _coordinates(rows: pd.DataFrame) -> pd.DataFrame:
    out = []
    deployed = rows[rows["series"] == "deployed"]
    for (site, stage), group in deployed.groupby(["location", "timepoint"]):
        m = _group_metrics(group)
        base = _group_metrics(rows[(rows["series"] == "preseason") & (rows["location"] == site)])
        out.append(
            {
                "location": site,
                "timepoint": stage,
                "dap": int(group["dap"].median()),
                "dap_min": int(group["dap"].min()),
                "dap_max": int(group["dap"].max()),
                "n_plots": len(group),
                "n_folds": 3,
                "deployed_r2": m["r2"],
                "deployed_mae": m["mae"],
                "deployed_rmse": m["rmse"],
                "deployed_pi_coverage_90": m["coverage"],
                "deployed_median_pi_width_90": m["width"],
                "preseason_agronomic_r2": base["r2"],
                "preseason_agronomic_mae": base["mae"],
                "preseason_agronomic_median_pi_width_90": base["width"],
            }
        )
    return pd.DataFrame(out)


@pytest.fixture
def run(tmp_path):
    rows = _rows()
    paths = {
        "predictions": tmp_path / "predictions.csv",
        "coordinates": tmp_path / "coordinates.csv",
        "uav": tmp_path / "uav.json",
        "sites": tmp_path / "sites.json",
    }
    rows.to_csv(paths["predictions"], index=False)
    _coordinates(rows).to_csv(paths["coordinates"], index=False)
    paths["uav"].write_text(
        json.dumps(
            {
                "matched": True,
                "sites": ["Ames"],
                "satellite_only": {"mae": 16.21},
                "satellite_plus_uav": {"mae": 16.13},
            }
        )
    )
    sites = [
        {"id": s, "seasons": [{"year": 2022, "satellite": {"acquisition_dates": d}}]}
        for s, d in DATES.items()
    ]
    paths["sites"].write_text(json.dumps({"sites": sites}))
    return paths


def test_builds_a_valid_artifact_from_the_deployed_series(run):
    doc = build(**run)
    loaded = LoadedResults(parse(_dumps(doc)))
    assert [(c.site, c.plots, c.observations) for c in loaded.summary.plot_counts] == [
        ("Ames", 3, 6),
        ("Lincoln", 3, 6),
    ]
    ames = next(p for p in doc["plots"] if p["plot_id"] == "2022_Ames_4231_1_1")
    assert ames["planting_date"] == "2022-05-22"
    assert [(f["date"], f["stage"], f["yield"]) for f in ames["forecasts"]] == [
        ("2022-07-15", "TP1", 140.0),
        ("2022-07-23", "TP2", 148.0),
    ]
    assert doc["dataset_label"] == "SyDAg 2022 maize trials · 6 plots · 2 sites"
    assert doc["uav"]["satellite_plus_uav"]["mae"] == 16.13
    assert doc["maturity"] == [] and doc["earliest_useful_dap"] is None


def test_negative_forecasts_are_floored_but_metrics_use_raw_outputs(run):
    doc = build(**run)
    low = next(p for p in doc["plots"] if p["plot_id"] == "2022_Lincoln_hybrids_1_1")
    tp1 = low["forecasts"][0]
    assert (tp1["yield"], tp1["lower"], tp1["upper"]) == (0.0, -24.0, 16.0)
    # Pooled TP1 MAE over all six plots uses the raw -4 (|−4 − 10| = 14), not 0.
    tp1_errors = [10, 10, 15, 14, 5, 20]
    assert doc["performance"][0]["mae"] == round(sum(tp1_errors) / 6, 2)
    assert doc["performance"][0]["r2"] is None
    assert doc["performance"][0]["stage"] == "TP1"
    assert doc["performance"][0]["label"].startswith("TP1 · site DAP ")


def test_site_validation_carries_the_preseason_baseline(run):
    doc = build(**run)
    ames = next(s for s in doc["site_performance"] if s["site"] == "Ames")
    assert ames["folds"] == 3 and ames["plots"] == 3
    assert ames["preseason"]["mae"] == 12.0
    assert [s["stage"] for s in ames["stages"]] == ["TP1", "TP2"]


def test_the_featured_plot_is_the_median_yield_plot_unless_overridden(run):
    featured = {p["plot_id"] for p in build(**run)["plots"] if p["featured"]}
    assert featured == {"2022_Ames_4231_1_2", "2022_Lincoln_hybrids_1_2"}
    doc = build(**run, featured=["2022_Ames_4231_1_3"])
    assert {p["plot_id"] for p in doc["plots"] if p["featured"]} == {
        "2022_Ames_4231_1_3",
        "2022_Lincoln_hybrids_1_2",
    }


def test_earliest_useful_stage_only_with_an_explicit_rule(run):
    doc = build(**run, earliest_useful_mae=9.0)
    assert doc["earliest_useful_dap"] == doc["performance"][1]["dap"]
    assert "≤9 bu/ac" in doc["earliest_useful_rule"]


def test_disagreeing_inputs_stop_the_build(run):
    coords = pd.read_csv(run["coordinates"])
    coords.loc[0, "deployed_mae"] += 1.0
    coords.to_csv(run["coordinates"], index=False)
    with pytest.raises(BuildError, match="coordinates file says"):
        build(**run)


def test_missing_columns_are_named(run):
    rows = pd.read_csv(run["predictions"]).drop(columns=["lower_90"])
    rows.to_csv(run["predictions"], index=False)
    with pytest.raises(BuildError, match="lower_90"):
        build(**run)
