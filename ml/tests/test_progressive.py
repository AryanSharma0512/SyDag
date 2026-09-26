"""Progressive early-signal experiments: inputs, leakage, validation, metrics, outputs."""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from soilsignal_ml.progressive import contract, criteria, report
from soilsignal_ml.progressive.folds import (
    Scheme,
    headline,
    inner_folds,
    make_folds,
    schemes,
)
from soilsignal_ml.progressive.intervals import conformal_quantile
from soilsignal_ml.progressive.metrics import paired_bootstrap_delta, scouting
from soilsignal_ml.progressive.runner import RunConfig, run
from soilsignal_ml.progressive.spatial import local_xy, morans_i
from soilsignal_ml.progressive.stages import build_stages, stage_frame, stage_timing
from soilsignal_ml.progressive.synthetic import make_frames, synthetic_data
from soilsignal_ml.validation.splits import OverlapError

FAST = {
    "hist_gradient_boosting": {"max_iter": 40},
    "random_forest": {"n_estimators": 30},
    "catboost": {"iterations": 60},
}


@pytest.fixture(scope="module")
def frames():
    return make_frames(seed=3, scale=0.12, with_2023=True)


@pytest.fixture(scope="module")
def data(frames):
    plots, obs, acq = frames
    return contract.from_frames(
        "fixture", plots, tp_observations=obs, acquisitions=acq, synthetic=True
    )


# ---- contract ---------------------------------------------------------------------------


def test_source_column_names_are_mapped():
    raw = pd.DataFrame(
        {
            "plot_id": ["a", "b"],
            "location": ["S1", "S1"],
            "year": [2022, 2022],
            "plantingDate": ["2022-05-01", "2022-05-03"],
            "yieldPerAcre": [150.0, None],
            "hybrid": ["H1", "H2"],
            "poundsOfNitrogenPerAcre": [150, 75],
        }
    )
    p = contract.normalize_plots(raw)
    assert list(p["site_id"]) == ["S1"]  # the unharvested plot is dropped
    assert {"final_yield", "genotype", "nitrogen_lb_ac", "planting_day_of_year"} <= set(p)


def test_target_like_feature_names_are_refused():
    with pytest.raises(contract.ContractError, match="look like the target"):
        contract.check_feature_names(["ndvi_latest", "yield_tp3"])
    contract.check_feature_names(["yield_tp3"], allow={"yield_tp3"})


def test_wide_features_hide_later_time_points():
    wide = pd.DataFrame({"plot_id": ["a"], "ndvi_tp1": [0.5], "ndvi_tp2": [0.6], "TP3_evi": [0.4]})
    long, _ = contract.wide_to_long(wide)
    tp1 = long[long["tp"] == 1].iloc[0]
    assert tp1["ndvi_tp1"] == 0.5 and np.isnan(tp1["ndvi_tp2"]) and np.isnan(tp1["TP3_evi"])
    tp3 = long[long["tp"] == 3].iloc[0]
    assert tp3[["ndvi_tp1", "ndvi_tp2", "TP3_evi"]].notna().all()


def test_cumulative_features_never_see_a_later_pass(frames):
    """Leakage: changing TP4-TP6 values must leave the TP1-TP3 features untouched."""
    plots, obs, acq = frames
    p = contract.normalize_plots(plots)
    a = contract.normalize_acquisitions(acq)
    before = contract.accumulate(obs, p, a, ["ndvi", "ndre"])
    tampered = obs.copy()
    late = tampered["tp"] > 3
    tampered.loc[late, ["ndvi", "ndre"]] = 99.0
    after = contract.accumulate(tampered, p, a, ["ndvi", "ndre"])
    for k in (1, 2, 3):
        x = before[before["tp"] == k].set_index("plot_id").sort_index()
        y = after[after["tp"] == k].set_index("plot_id").sort_index()
        pd.testing.assert_frame_equal(x, y)
    assert (after[after["tp"] == 6]["ndvi_max"] == 99.0).any()


def test_cumulative_and_per_pass_inputs_agree(frames, data):
    """Handing over Agent 2-style cumulative rows gives the same table as per-pass rows."""
    plots, _, acq = frames
    again = contract.from_frames(
        "fixture", plots, tp_features=data.tp_features, acquisitions=acq, synthetic=True
    )
    pd.testing.assert_frame_equal(
        again.tp_features.reset_index(drop=True), data.tp_features.reset_index(drop=True)
    )


def test_acquisition_dates_can_come_from_the_feature_table(frames, data):
    plots, obs, _ = frames
    dated = obs[["plot_id", "tp", "date"]].drop_duplicates(["plot_id", "tp"])
    feats = data.tp_features.merge(dated, on=["plot_id", "tp"])
    d = contract.from_frames("fixture", plots, tp_features=feats)
    assert len(d.acquisitions) == 24  # 4 site-seasons x 6 passes


def test_canonical_practice_dataset_path(frames, tmp_path):
    """`--canonical shrestha2024` reads the existing pipeline's tables (time_point column)."""
    from soilsignal_ml.ingest.canonical import CanonicalDataset

    plots, obs, _ = frames
    empty = pd.DataFrame
    CanonicalDataset(
        name="practice",
        plots=plots,
        observations=obs.rename(columns={"tp": "time_point"}).assign(source="satellite"),
        weather=empty(columns=["site_id", "date", "tmax_f", "tmin_f", "prcp_mm"]),
        soil=empty(columns=["plot_id"]),
        county_yields=empty(columns=["site_id", "year", "yield"]),
        sites=empty(columns=["site_id"]),
        provenance={"dataset": "practice"},
    ).save(tmp_path)
    d = contract.from_canonical("practice", root=tmp_path)
    assert len(d.acquisitions) == 24 and "ndvi_rel_latest" in d.imagery_columns
    assert "nir_latest" in d.imagery_columns


# ---- stages -------------------------------------------------------------------------------


def test_tp_stages_are_cumulative(data):
    stages = build_stages(data, "tp")
    assert [s.key for s in stages] == ["records", "tp1", "tp2", "tp3", "tp4", "tp5", "tp6"]
    assert (stages[0].visible_tp == 0).all()
    assert (stages[3].visible_tp <= 3).all() and (stages[3].visible_tp == 3).mean() > 0.9
    frame, cols = stage_frame(data, stages[0])
    assert cols == [] and len(frame) == len(data.plots)


def test_stage_timing_reports_dates_not_just_labels(data):
    stage = build_stages(data, "tp")[2]
    t = stage_timing(data, stage)
    ames = next(p for p in t["per_site_year"] if p["site_id"] == "Ames" and p["year"] == 2022)
    assert ames["date"] == "2022-07-23" and ames["dap_median"] == 62  # planted May 22
    lincoln = next(p for p in t["per_site_year"] if p["site_id"] == "Lincoln")
    assert lincoln["date"] == "2022-08-06"  # same TP label, two weeks later
    assert t["harvest_basis"].startswith("assumed")


def test_dap_stages_use_each_plots_own_planting(data):
    stages = build_stages(data, "dap", [70])
    vis = stages[1].visible_tp
    site = data.plots.set_index("plot_id")["site_id"].reindex(vis.index).to_numpy()
    # By day 70: Crawfordsville (planted May 11) has Jul 10 + Jul 20; Lincoln (May 22) only
    # Jul 18, its second pass (Aug 6) is day 76.
    assert vis[site == "Crawfordsville"].max() == 2
    assert vis[site == "Lincoln"].max() == 1


# ---- validation ---------------------------------------------------------------------------


def test_grouped_schemes_keep_groups_apart(data):
    frame = data.plots
    for name, column in (("site", "site_id"), ("year", "year"), ("site_year", "site_year")):
        for fold in make_folds(frame, Scheme(name, True, "")):
            assert not set(frame[column].iloc[fold.train]) & set(frame[column].iloc[fold.test])
    (fold,) = make_folds(frame, Scheme("temporal", True, "", 2023))
    assert set(frame["year"].iloc[fold.train]) == {2022}
    assert set(frame["year"].iloc[fold.test]) == {2023}


def test_temporal_is_skipped_with_a_reason_when_the_later_season_is_thin(data):
    available = schemes(data.plots, min_test_plots=10_000)
    temporal = next(s for s in available if s.name == "temporal")
    assert not temporal.usable and "too few" in temporal.reason
    assert headline(available).name == "site"
    usable = schemes(data.plots, min_test_plots=10)
    assert headline(usable).name == "temporal"


def test_inner_folds_never_include_the_outer_test_group(data):
    frame = data.plots
    for fold in make_folds(frame, Scheme("site", True, "")):
        train = frame.iloc[fold.train]
        inner, used = inner_folds(train, Scheme("site", True, ""))
        assert used == "site"
        tested = set().union(*(set(train["site_id"].iloc[f.test]) for f in inner))
        assert fold.name not in tested


def test_overlap_is_still_asserted(data):
    frame = data.plots.copy()
    frame.loc[frame.index[:5], "site_id"] = "Lincoln"
    frame.loc[frame.index[:5], "site_year"] = "Lincoln-2022"
    folds = make_folds(frame, Scheme("site", True, ""))
    assert all(len(f.test) for f in folds)
    with pytest.raises(OverlapError):
        from soilsignal_ml.validation.splits import Fold, assert_separated

        assert_separated(frame, Fold("x", np.arange(10), np.arange(5, 15)), "plot_id")


# ---- metrics ------------------------------------------------------------------------------


def test_scouting_recall_perfect_random_and_missing():
    rng = np.random.default_rng(0)
    y = rng.normal(150, 30, 400)
    units = np.repeat(["a", "b"], 200)
    perfect = scouting(y, y, units, budgets=(0.2,))[0]
    assert perfect["recall"] == pytest.approx(perfect["oracle_recall"])
    assert perfect["oracle_recall"] == pytest.approx(0.8, abs=0.02)
    noise = np.mean(
        [
            scouting(y, rng.normal(size=400), units, budgets=(0.2,), seed=s)[0]["recall"]
            for s in range(30)
        ]
    )
    assert noise == pytest.approx(0.2, abs=0.05)
    missing = y.copy()
    missing[:50] = np.nan  # unscored plots go last, but still count
    r = scouting(y, missing, units, budgets=(0.2,))[0]
    assert r["n_poor"] == perfect["n_poor"]


def test_paired_bootstrap_sign():
    base = np.full(200, 10.0)
    better = np.full(200, 7.0) + np.random.default_rng(1).normal(0, 1, 200)
    lo, hi = paired_bootstrap_delta(base, better, np.repeat([0, 1], 100), n_boot=300)
    assert 0 < lo < 3 < hi


def test_conformal_quantile_is_conservative():
    scores = np.arange(1, 101, dtype=float)
    assert conformal_quantile(scores, 0.9) == 91.0  # ceil(101 * 0.9) = 91st smallest


def test_morans_i_detects_clustered_errors():
    gx, gy = np.meshgrid(np.arange(20), np.arange(20))
    xy = np.column_stack([gx.ravel() * 5.5, gy.ravel() * 7.0])
    smooth = np.sin(xy[:, 0] / 30) + np.cos(xy[:, 1] / 30)
    clustered = morans_i(smooth, xy, permutations=199)
    scattered = morans_i(np.random.default_rng(0).normal(size=400), xy, permutations=199)
    assert clustered["morans_i"] > 0.5 and clustered["p_value"] < 0.01
    assert abs(scattered["morans_i"]) < 0.1 and scattered["p_value"] > 0.01
    lat = 41.0 + xy[:, 1] / 111_320
    assert np.allclose(
        local_xy(lat, np.full(400, -93.0))[:, 1] - xy[:, 1], -xy[:, 1].mean(), atol=0.01
    )


# ---- criteria -----------------------------------------------------------------------------


def test_criteria_report_values_and_the_first_stage_passing_all():
    stages = [
        SimpleNamespace(key=k, label=k, order=i, uses_imagery=i > 0)
        for i, k in enumerate(["records", "tp1", "tp2"])
    ]

    def row(stage, model, mae, delta, ci, wins, cov):
        return {
            "validation": "site", "stage": stage, "model": model, "mae": mae,
            "delta_mae_vs_records": delta,
            "pct_mae_reduction_vs_records": 100 * delta / (mae + delta),
            "delta_mae_ci_low": ci, "group_wins": wins, "n_groups": 3,
            "coverage": cov, "coverage_min_group": cov - 0.05, "interval_width": 80,
        }  # fmt: skip

    rows = [
        row("tp1", "catboost", 40, 1, -1, 1, 0.9),
        row("tp2", "catboost", 30, 11, 5, 3, 0.9),
        row("tp1", "ridge", 40, 1, -1, 1, 0.9),
        row("tp2", "ridge", 32, 9, 4, 3, 0.9),
    ]
    scout = [
        {"validation": "site", "stage": s, "ranker": r, "budget": 0.2, "recall": v,
         "random_recall": 0.2}
        for s, r, v in [("tp1", "relative_forecast", 0.3), ("tp1", "records_only", 0.3),
                        ("tp2", "relative_forecast", 0.45), ("tp2", "records_only", 0.3)]
    ]  # fmt: skip
    timing = {"tp1": {"lead_days_median": 90}, "tp2": {"lead_days_median": 60}}
    cfg = RunConfig(models=["mean", "ridge", "catboost"], primary_model="catboost")
    out = criteria.evaluate(rows, scout, timing, stages, "site", cfg)
    assert out["earliest_candidate"] == "tp2"
    tp1 = out["stages"][0]["checks"]
    assert tp1["beats_records"]["passed"] is False and tp1["early"]["passed"] is True
    assert out["stages_passing_accuracy_checks"] == ["tp2"]


# ---- end to end ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def result(data):
    cfg = RunConfig(
        models=["mean", "ridge", "hist_gradient_boosting"],
        primary_model="hist_gradient_boosting",
        params=FAST,
        n_boot=100,
        min_test_plots=10,
        schemes=["site", "temporal", "random"],
    )
    return run(data, cfg, progress=lambda *_: None)


def test_run_covers_every_stage_model_and_scheme(result):
    assert result["headline_validation"]["name"] == "temporal"
    keys = {(r["validation"], r["stage"], r["model"]) for r in result["results"]}
    for stage in ("records", "tp1", "tp6"):
        assert ("temporal", stage, "ridge") in keys and (
            "site",
            stage,
            "hist_gradient_boosting",
        ) in keys
    assert ("temporal", "records", "mean") in keys and ("temporal", "tp3", "mean") not in keys
    assert ("random", "tp3", "ridge") not in keys  # contrasts run the primary model only
    tp3 = next(
        r
        for r in result["results"]
        if (r["validation"], r["stage"], r["model"]) == ("site", "tp3", "hist_gradient_boosting")
    )
    for field in (
        "mae",
        "rmse",
        "r2",
        "bias",
        "spearman_within",
        "coverage",
        "interval_width",
        "delta_mae_vs_records",
        "pct_mae_reduction_vs_records",
        "delta_mae_ci_low",
        "group_wins",
    ):
        assert field in tp3
    assert {s["ranker"] for s in result["scouting"]} >= {
        "forecast",
        "lower_bound",
        "relative_forecast",
        "records_only",
        "naive_imagery",
    }
    assert result["spatial"] and result["timing"]["tp2"]["dap_median"] > 0


def test_outputs_match_the_backend_contract(result, tmp_path):
    written = report.write_outputs(result, tmp_path)
    names = {p.name for p in written}
    assert {
        "progressive_results.csv",
        "progressive_results.json",
        "imagery_ablation.json",
        "summary.md",
        "mae_vs_stage.png",
        "scouting_recall_vs_stage.png",
    } <= names
    from app.forecast.evaluation import imagery_ablation

    ablation = imagery_ablation(tmp_path)  # the API's own reader
    assert ablation.status == "ready" and [v.uses_imagery for v in ablation.variants] == [
        False,
        True,
    ]
    body = json.loads((tmp_path / "progressive_results.json").read_text())
    assert body["synthetic"] is True and body["progression_table"][0]["stage"] == "mean"
    assert "SYNTHETIC FIXTURE" in (tmp_path / "summary.md").read_text()
    geo = json.loads((tmp_path / "predictions.geojson").read_text())
    assert geo["features"] and "resid_tp3" in geo["features"][0]["properties"]


def test_synthetic_runs_are_never_published(result, tmp_path):
    report.write_outputs(result, tmp_path)
    with pytest.raises(report.PublishError):
        report.publish(result, tmp_path, target=tmp_path / "artifacts")
    real = {**result, "synthetic": False}
    path = report.publish(real, tmp_path, target=tmp_path / "artifacts")
    assert path.exists()


def test_cli_entry_points(tmp_path, capsys):
    from soilsignal_ml.__main__ import main

    with pytest.raises(SystemExit):
        main(["progressive", "--help"])
    assert "--tp-features" in capsys.readouterr().out


def test_synthetic_fixture_is_labelled():
    d = synthetic_data(scale=0.05)
    assert d.synthetic and "Not a result" in d.provenance["warning"]
