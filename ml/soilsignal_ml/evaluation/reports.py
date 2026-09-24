"""
Experiment report: ml/experiments/reports/model_report.md, built from each cutoff's
training summary (ml/experiments/candidates/<cutoff>/summary.json).
"""

import json
from datetime import date

from soilsignal_ml import ML_ROOT
from soilsignal_ml.models.train import CANDIDATES, LADDER, load_cutoffs, load_project

REPORTS = ML_ROOT / "experiments" / "reports"
NAMES = {
    "mean": "Mean baseline",
    "ridge": "Ridge",
    "random_forest": "Random Forest",
    "hist_gradient_boosting": "HistGradientBoosting",
    "catboost": "CatBoost",
}


def _f(value, digits: int = 1) -> str:
    if value is None or value != value:
        return "–"
    return f"{value:.{digits}f}"


def _pct(value) -> str:
    return "–" if value is None or value != value else f"{100 * value:.0f}%"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def load_summaries() -> list[dict]:
    return [
        json.loads((CANDIDATES / cfg["name"] / "summary.json").read_text())
        for cfg in load_cutoffs()
        if (CANDIDATES / cfg["name"] / "summary.json").exists()
    ]


def build_report() -> str:
    project = load_project()
    summaries = load_summaries()
    first = summaries[0]
    holdout = project["holdout_site"]
    out = [
        "# SoilSignal progressive yield model: experiment report",
        "",
        f"Generated {date.today().isoformat()} from `ml/experiments/candidates/*/summary.json` "
        f"(code `{first['context']['git_sha']}`, dataset version `{first['context']['dataset_version']}`).",
        "",
        "## Setup",
        "",
        f"- **Data:** {first['n_dev']} development plots at {len(first['dev_sites'])} sites "
        f"({', '.join(first['dev_sites'])}) plus the held-out site **{holdout}**. Public practice data "
        "(Shrestha et al. 2024), 2022 season, 84 hybrids, 0–250 lb N/ac, six Pléiades Neo images per plot.",
        "- **Validation:** leave-one-site-out CV on the development sites for feature-set screening, "
        f"tuning ({project['optuna_trials']} Optuna trials per model, minimizing mean fold MAE), model "
        f"selection and interval calibration. {holdout} is scored once, after selection, with nothing "
        "fitted to it.",
        "- **Selection rule:** feature sets and models are ranked by **mean + 1 SD of fold MAE** (brief §45: "
        "consistency across sites matters, not only the average), and a more complex model must win by "
        f"more than {int(100 * project['simpler_model_margin'])}%. A rehearsal run used the mean alone and "
        "picked Ridge for August, which extrapolated badly on the held-out site. The rule was corrected "
        "before this run, so the held-out site informed it and is a lightly used test rather than a "
        "pristine one (`experiments/rehearsal/model_report.md`).",
        "- **Point-in-time:** each cutoff's features come from `build_features(inputs, as_of)`, which drops "
        "and then asserts against anything dated after the cutoff.",
        f"- **Intervals:** {int(100 * project['interval_level'])}% intervals from out-of-fold residual "
        "quantiles (conformal-style finite-sample correction). Coverage below is on data that played no "
        "part in setting them.",
        "",
        "## Progressive performance: how early does SoilSignal become useful?",
        "",
        f"Selected model per cutoff. *CV* = mean over leave-one-site-out folds (± spread between sites). "
        f"*Held-out* = {holdout}, never seen during development.",
        "",
    ]
    rows = []
    for s in summaries:
        cv, h, iv = s["cv"], s["holdout"], s["interval"]
        rows.append(
            [
                s["config"]["label"],
                NAMES[s["model"]],
                s["feature_set"],
                str(len(s["features"])),
                f"{_f(cv['cv_mae'])} ± {_f(cv['cv_mae_std'])}",
                _f(h["mae"]),
                _f(h["rmse"]),
                _f(h["r2"], 2),
                _pct(h["relative_mae"]),
                f"{_f(iv['lower_offset'], 0)} / +{_f(iv['upper_offset'], 0)}",
                _pct(h["interval_coverage"]),
            ]
        )
    out.append(
        _table(
            [
                "Information available",
                "Model",
                "Feature set",
                "Features",
                "CV MAE",
                "Held-out MAE",
                "Held-out RMSE",
                "Held-out R²",
                "Held-out MAE / mean yield",
                "90% interval (bu/ac)",
                "Held-out coverage",
            ],
            rows,
        )
    )

    out += [
        "",
        "## Model comparison (leave-one-site-out CV MAE, bu/ac; tuned on the selected feature set)",
        "",
    ]
    header = ["Model"] + [s["config"]["label"] for s in summaries]
    rows = []
    for spec in LADDER:
        rows.append(
            [NAMES[spec.name]]
            + [
                f"{_f(s['comparison'][spec.name]['site']['cv_mae'])} ± {_f(s['comparison'][spec.name]['site']['cv_mae_std'])}"
                for s in summaries
            ]
        )
    out.append(_table(header, rows))
    out += [
        "",
        f"Same models, fitted on all development sites and scored once on {holdout} (MAE, bu/ac). "
        "Shown for context: selection above used CV only.",
        "",
    ]
    rows = [
        [NAMES[spec.name]] + [_f(s["holdout_all"][spec.name]["mae"]) for s in summaries]
        for spec in LADDER
    ]
    out.append(_table(header, rows))

    out += [
        "",
        "## Why grouped validation matters",
        "",
        "MAE of each cutoff's selected model under three splits of the development sites. Random-like "
        "splits (grouped by plot) share a site's weather, soil and management between train and test, so "
        "they look far better than what a new location will see.",
        "",
    ]
    rows = []
    for s in summaries:
        c = s["comparison"][s["model"]]
        rows.append(
            [
                s["config"]["label"],
                NAMES[s["model"]],
                _f(c["plot"]["cv_mae"]),
                _f(c["field"]["cv_mae"]),
                _f(c["site"]["cv_mae"]),
            ]
        )
    out.append(
        _table(
            [
                "Cutoff",
                "Model",
                "Grouped by plot (5-fold)",
                "Grouped by field (4-fold)",
                "Leave-one-site-out",
            ],
            rows,
        )
    )

    out += ["", "### Leave-one-site-out, fold by fold (selected model, MAE bu/ac)", ""]
    sites = [f["group"] for f in summaries[0]["cv"]["per_fold"]]
    rows = [[s["config"]["label"]] + [_f(f["mae"]) for f in s["cv"]["per_fold"]] for s in summaries]
    out.append(_table(["Cutoff"] + [f"Test site: {g}" for g in sites], rows))

    out += [
        "",
        "## Feature ablation",
        "",
        "Each group combination is cross-validated (leave-one-site-out, default parameters, best of "
        "Ridge / Random Forest / HistGradientBoosting / CatBoost). The lowest mean + 1 SD picks the feature "
        f"set; held-out MAE on {holdout} is shown for context only. Cells: CV MAE ± SD (held-out MAE).",
        "",
    ]
    labels = list(dict.fromkeys(label for s in summaries for label in s["ablation"]))
    rows = []
    for label in labels:
        row = [label]
        for s in summaries:
            a = s["ablation"].get(label)
            mark = " **←**" if label == s["feature_set"] else ""
            row.append(
                "–"
                if a is None
                else f"{_f(a['cv_mae'])} ± {_f(a['cv_mae_std'])} ({_f(a['holdout_mae'])}){mark}"
            )
        rows.append(row)
    out.append(
        _table(
            ["Feature set: CV MAE (held-out MAE)"] + [s["config"]["label"] for s in summaries], rows
        )
    )
    out += [
        "",
        "A dash means the set adds no columns at that cutoff: before the first satellite image, "
        '"Crop signals" is the same as "Management only". Sets that produce identical columns are '
        "evaluated once.",
        "",
        "## Seasonal ablation: what another month of data buys",
        "",
    ]
    rows, prev = [], None
    for s in summaries:
        mae = s["holdout"]["mae"]
        rows.append(
            [
                s["config"]["label"],
                _f(s["cv"]["cv_mae"]),
                _f(mae),
                "–" if prev is None else _f(mae - prev),
            ]
        )
        prev = mae
    out.append(_table(["Cutoff", "CV MAE", "Held-out MAE", "Change vs previous cutoff"], rows))

    out += ["", "## Top model drivers (permutation importance on held-out-site folds)", ""]
    for s in summaries:
        imp = sorted(s["importance"].items(), key=lambda kv: kv[1], reverse=True)[:6]
        total = sum(v for _, v in s["importance"].items()) or 1
        items = ", ".join(
            f"`{k}` {100 * v / total:.0f}% ({s['direction'].get(k, 'neutral')})"
            for k, v in imp
            if v > 0
        )
        out.append(
            f"- **{s['config']['label']}** ({NAMES[s['model']]}): {items or 'none (constant prediction)'}"
        )

    out += [
        "",
        "## Agronomic sensitivity checks",
        "",
        "For the plot whose forecast is closest to the median, one feature is swept from its 5th to 95th "
        "percentile with everything else fixed. *Investigate* marks a response opposite to the literature "
        "(see `ml/research/agronomy_thresholds.md`). A flat response means the feature isn't in the "
        "selected set, or the model doesn't use it for this plot.",
        "",
    ]
    rows = []
    for s in summaries:
        for c in s["sensitivity"]:
            rows.append(
                [
                    s["config"]["label"],
                    f"`{c['feature']}`",
                    f"{c['range'][0]} → {c['range'][1]}",
                    f"{c['prediction_low_to_high']:+.1f}",
                    c["observed"],
                    c["expected"],
                    c["status"],
                ]
            )
    out.append(
        _table(
            [
                "Cutoff",
                "Feature",
                "Swept range",
                "Forecast change (bu/ac)",
                "Model",
                "Literature",
                "Status",
            ],
            rows,
        )
        if rows
        else "_No selected feature has a literature expectation._"
    )

    out += [
        "",
        "## Reading these numbers honestly",
        "",
        "- **Four development sites are very few.** Site means range from about 41 bu/ac (Lincoln, 2022 "
        "drought, rainfed) to about 165 bu/ac. Leave-one-site-out CV asks each model to forecast a site "
        "unlike any it trained on, and the Lincoln fold dominates the CV average. Grouped-by-plot numbers are "
        "several times better only because they don't ask that question.",
        "- **Site-level context rarely transfers from so few sites.** Weather, soil, county history and "
        "planting date take four or five distinct values in training, so a model can use them as site "
        "identifiers. The ablation measures whether they help a new site rather than assuming it; they "
        "remain on the dashboard as context either way.",
        "- **One season.** Leave-one-year-out validation is impossible with 2022 only.",
        "- **Intervals are wide by design.** They come from errors on unseen sites. More sites and years "
        "(the challenge data) should narrow them.",
        "- Comparable published work is summarized in `ml/research/model_benchmarks.md`. Its numbers "
        "are only comparable when the prediction date and validation split match.",
    ]
    return "\n".join(out) + "\n"


def write_report() -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "model_report.md"
    path.write_text(build_report())
    return str(path)
