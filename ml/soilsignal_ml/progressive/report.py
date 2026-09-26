"""
Writes one run's evidence to disk.

    progressive_results.csv / .json   every stage x model x validation row (+ everything)
    progression_table.md              the headline table (records only, TP1 ... TP6)
    scouting_results.csv              recall / precision / lift by stage, ranking, budget
    criteria.json                     the earliest-useful checks, value by value
    spatial_autocorrelation.csv       Moran's I of residuals per stage and site-season
    predictions.csv, predictions.geojson   out-of-fold forecasts per plot (map layers)
    imagery_ablation.json             the backend's contract (records vs + imagery)
    imagery_ablation_by_stage.json    the same comparison at every stage, with timing
    summary.md                        the human-readable report
    figures/*.png

`publish()` copies imagery_ablation.json into backend/artifacts/ and refuses a synthetic run.
"""

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from soilsignal_ml import BACKEND_ROOT
from soilsignal_ml.experiments import git_sha
from soilsignal_ml.progressive import figures

ABLATION_FILE = "imagery_ablation.json"
BY_STAGE_FILE = "imagery_ablation_by_stage.json"


class PublishError(RuntimeError):
    """Refused to publish (synthetic data, or a file the backend would reject)."""


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating | float):
        v = float(value)
        return None if math.isnan(v) or math.isinf(v) else round(v, 4)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value


def _headline(result, model=None):
    scheme = result["headline_validation"]["name"]
    model = model or result["config"]["primary_model"]
    return {
        r["stage"]: r
        for r in result["results"]
        if r["validation"] == scheme and r["model"] == model
    }


def progression_table(result) -> list[dict]:
    """The headline table: one row per information stage (primary model, headline scheme)."""
    scheme = result["headline_validation"]["name"]
    rows = _headline(result)
    mean = next(
        (r for r in result["results"] if r["validation"] == scheme and r["model"] == "mean"), None
    )
    budget = result["criteria"]["thresholds"]["scouting_budget"]
    recall = {
        s["stage"]: s
        for s in result["scouting"]
        if s["ranker"] == "forecast" and abs(s["budget"] - budget) < 1e-9
    }
    out = []
    if mean:
        out.append(
            {
                "information": "Baseline A: training mean",
                "stage": "mean",
                "mae": mean["mae"],
                "rmse": mean["rmse"],
                "r2": mean["r2"],
                "bias": mean["bias"],
                "coverage": mean["coverage"],
                "interval_width": mean["interval_width"],
            }
        )
    for s in result["stages"]:
        r = rows.get(s["key"])
        if r is None:
            continue
        t = result["timing"].get(s["key"], {})
        rc = recall.get(s["key"], {})
        out.append(
            {
                "information": s["label"],
                "stage": s["key"],
                "acq_dates": f"{t.get('acq_date_min', '')} to {t.get('acq_date_max', '')}"
                if t.get("acq_date_min")
                else "",
                "dap_median": t.get("dap_median"),
                "passes": t.get("passes_mean"),
                "lead_days_median": t.get("lead_days_median"),
                "mae": r["mae"],
                "delta_mae": r.get("delta_mae_vs_records"),
                "pct_reduction": r.get("pct_mae_reduction_vs_records"),
                "delta_ci": [r.get("delta_mae_ci_low"), r.get("delta_mae_ci_high")],
                "group_wins": f"{r['group_wins']}/{r['n_groups']}" if "group_wins" in r else "",
                "rmse": r["rmse"],
                "r2": r["r2"],
                "bias": r["bias"],
                "spearman_within": r["spearman_within"],
                "coverage": r["coverage"],
                "interval_width": r["interval_width"],
                "cqr_coverage": r.get("cqr_coverage"),
                "cqr_width": r.get("cqr_width"),
                "recall_at_budget": rc.get("recall"),
            }
        )
    return out


def _fmt(v, spec=".1f", dash="–"):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return dash
    return format(v, spec)


def progression_markdown(result) -> str:
    budget = result["criteria"]["thresholds"]["scouting_budget"]
    head = (
        "| Available information | Acquired | Median DAP | Passes | MAE | ΔMAE vs records "
        "(95% CI) | Better in | R² | Bias | Spearman (within site) | 90% coverage | "
        f"Interval width | Recall @ {budget:.0%} |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [head]
    for r in progression_table(result):
        ci = r.get("delta_ci") or [None, None]
        delta = (
            f"{_fmt(r.get('delta_mae'), '+.1f')} ({_fmt(r.get('pct_reduction'), '+.0f')}%; "
            f"{_fmt(ci[0], '+.1f')} to {_fmt(ci[1], '+.1f')})"
            if r.get("delta_mae") is not None and r["stage"] != "records"
            else ("reference" if r["stage"] == "records" else "–")
        )
        lines.append(
            f"| {r['information']} | {r.get('acq_dates') or '–'} | {_fmt(r.get('dap_median'), '.0f')} "
            f"| {_fmt(r.get('passes'), '.1f')} | {_fmt(r['mae'])} | {delta} "
            f"| {r.get('group_wins') or '–'} | {_fmt(r['r2'], '.2f')} | {_fmt(r['bias'], '+.1f')} "
            f"| {_fmt(r.get('spearman_within'), '.2f')} | {_fmt(r.get('coverage'), '.0%')} "
            f"| {_fmt(r.get('interval_width'), '.0f')} | {_fmt(r.get('recall_at_budget'), '.0%')} |"
        )
    return "\n".join(lines)


# ---- backend: imagery_ablation.json ----------------------------------------------------------


def _mmdd(iso: str | None) -> str | None:
    return iso[5:10] if iso else None


def imagery_ablation(result, stage: str | None = None, dataset_label: str | None = None) -> dict:
    """Records only vs + imagery at one stage (default: every pass), in the exact format
    backend/app/forecast/evaluation.py accepts. Same model, same validation, same plots."""
    rows = _headline(result)
    imagery = [s["key"] for s in result["stages"] if s["uses_imagery"] and s["key"] in rows]
    stage = stage or imagery[-1]
    if stage not in rows or stage == "records":
        raise ValueError(f"stage {stage!r} not in this run's imagery stages {imagery}")
    rec, img = rows["records"], rows[stage]
    label = next(s["label"] for s in result["stages"] if s["key"] == stage)
    timing = result["timing"].get(stage, {})
    body = {
        "dataset_label": dataset_label or _dataset_label(result),
        "validation": result["headline_validation"]["description"],
        "as_of": _mmdd(timing.get("acq_date_median")),
        "variants": [
            {
                "id": "records",
                "label": "Field records only",
                "uses_imagery": False,
                "mae": round(rec["mae"], 2),
                "rmse": round(rec["rmse"], 2),
                "r2": round(rec["r2"], 3),
            },
            {
                "id": "imagery",
                "label": f"+ Satellite imagery ({label.removeprefix('+ ')})",
                "uses_imagery": True,
                "mae": round(img["mae"], 2),
                "rmse": round(img["rmse"], 2),
                "r2": round(img["r2"], 3),
            },
        ],
    }
    _validate_with_backend(body)
    return body


def _validate_with_backend(body: dict) -> None:
    """Parse with the backend's own model so a file that would 503 is never written."""
    from app.forecast.evaluation import _AblationFile

    _AblationFile.model_validate(body)


def _dataset_label(result) -> str:
    if result.get("synthetic"):
        return "SYNTHETIC test fixture"
    name = result["dataset"].lower()
    return "Practice data" if "shrestha" in name else "Challenge data"


def imagery_ablation_by_stage(result, dataset_label: str | None = None) -> dict:
    budget = result["criteria"]["thresholds"]["scouting_budget"]
    return _clean(
        {
            "dataset_label": dataset_label or _dataset_label(result),
            "synthetic": result.get("synthetic", False),
            "validation": result["headline_validation"]["description"],
            "model": result["config"]["primary_model"],
            "unit": "bu/ac",
            "scouting_budget": budget,
            "stages": [
                {k: v for k, v in r.items() if k not in ("delta_ci",)}
                | {
                    "delta_mae_ci": r.get("delta_ci"),
                    "as_of_median": _mmdd(
                        result["timing"].get(r["stage"], {}).get("acq_date_median")
                    ),
                }
                for r in progression_table(result)
            ],
            "earliest_candidate": result["criteria"]["earliest_candidate"],
        }
    )


def publish(result, out_dir: Path, target: Path | None = None) -> Path:
    if result.get("synthetic"):
        raise PublishError("refusing to publish a synthetic run to the backend")
    target = target or BACKEND_ROOT / "artifacts"
    source = out_dir / ABLATION_FILE
    body = json.loads(source.read_text())
    _validate_with_backend(body)
    target.mkdir(parents=True, exist_ok=True)
    (target / ABLATION_FILE).write_text(json.dumps(body, indent=2) + "\n")
    (target / BY_STAGE_FILE).write_text((out_dir / BY_STAGE_FILE).read_text())
    return target / ABLATION_FILE


# ---- files --------------------------------------------------------------------------------


def _geojson(pred: pd.DataFrame) -> dict:
    if pred.empty or "latitude" not in pred:
        return {"type": "FeatureCollection", "features": []}
    features = []
    for plot_id, g in pred.dropna(subset=["latitude", "longitude"]).groupby("plot_id"):
        first = g.iloc[0]
        props = {
            "plot_id": plot_id,
            "site_id": first["site_id"],
            "year": int(first["year"]),
            "actual": float(first["actual"]),
        }
        for r in g.itertuples():
            props[f"pred_{r.stage}"] = (
                None if pd.isna(r.predicted) else round(float(r.predicted), 1)
            )
            props[f"resid_{r.stage}"] = None if pd.isna(r.residual) else round(float(r.residual), 1)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        round(float(first["longitude"]), 7),
                        round(float(first["latitude"]), 7),
                    ],
                },
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def write_outputs(result, out_dir: Path, ablation_stage=None, dataset_label=None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    meta = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
    }

    rows = pd.DataFrame(result["results"])
    if "group_mae" in rows:
        rows["group_mae"] = rows["group_mae"].map(lambda d: json.dumps(_clean(d)))
    rows.insert(0, "dataset", result["dataset"])
    rows.insert(1, "synthetic", result.get("synthetic", False))
    rows.to_csv(out_dir / "progressive_results.csv", index=False, float_format="%.4f")
    written.append(out_dir / "progressive_results.csv")

    pd.DataFrame(result["scouting"]).to_csv(
        out_dir / "scouting_results.csv", index=False, float_format="%.4f"
    )
    pd.DataFrame(result["spatial"]).to_csv(
        out_dir / "spatial_autocorrelation.csv", index=False, float_format="%.4f"
    )
    pred = result["predictions"]
    pred.to_csv(out_dir / "predictions.csv", index=False, float_format="%.3f")
    (out_dir / "predictions.geojson").write_text(json.dumps(_geojson(pred)) + "\n")
    written += [
        out_dir / f
        for f in (
            "scouting_results.csv",
            "spatial_autocorrelation.csv",
            "predictions.csv",
            "predictions.geojson",
        )
    ]

    (out_dir / "criteria.json").write_text(json.dumps(_clean(result["criteria"]), indent=2) + "\n")
    body = {k: v for k, v in result.items() if k != "predictions"}
    body = _clean({**meta, **body, "progression_table": progression_table(result)})
    (out_dir / "progressive_results.json").write_text(json.dumps(body, indent=2) + "\n")
    written += [out_dir / "criteria.json", out_dir / "progressive_results.json"]

    ablation = imagery_ablation(result, ablation_stage, dataset_label)
    (out_dir / ABLATION_FILE).write_text(json.dumps(ablation, indent=2) + "\n")
    (out_dir / BY_STAGE_FILE).write_text(
        json.dumps(imagery_ablation_by_stage(result, dataset_label), indent=2) + "\n"
    )
    written += [out_dir / ABLATION_FILE, out_dir / BY_STAGE_FILE]

    (out_dir / "progression_table.md").write_text(progression_markdown(result) + "\n")
    written += figures.write_all(result, out_dir / "figures")
    (out_dir / "summary.md").write_text(summary_markdown(result, meta) + "\n")
    written += [out_dir / "progression_table.md", out_dir / "summary.md"]
    return written


# ---- summary.md ------------------------------------------------------------------------------

_MARK = {True: "yes", False: "no", None: "?"}


def _criteria_markdown(result) -> str:
    c = result["criteria"]
    lines = [
        "| Stage | 1 Beats records | 2 Consistent | 3 Calibrated | 4 Scouting | 5 Early | All |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in c["stages"]:
        ch = s["checks"]
        cells = []
        for name in ("beats_records", "consistent", "calibrated", "scouting", "early"):
            v = ch[name]["value"] or {}
            detail = {
                "beats_records": f"{_fmt(v.get('pct_mae_reduction'), '+.0f')}%, CI low {_fmt(v.get('ci_low'), '+.1f')}",
                "consistent": f"{_fmt(v.get('group_win_share'), '.0%')} groups, {_fmt(v.get('model_agreement'), '.0%')} models",
                "calibrated": f"{_fmt(v.get('coverage'), '.0%')} (worst {_fmt(v.get('worst_group_coverage'), '.0%')})",
                "scouting": f"{_fmt(v.get('recall'), '.0%')} vs {_fmt(v.get('records_recall'), '.0%')}",
                "early": f"{_fmt(v.get('lead_days_median'), '.0f')} d lead",
            }[name]
            cells.append(f"{_MARK[ch[name]['passed']]} ({detail})")
        lines.append(f"| {s['label']} | " + " | ".join(cells) + f" | {_MARK[s['all_passed']]} |")
    return "\n".join(lines)


def _scouting_markdown(result) -> str:
    scout = pd.DataFrame(result["scouting"])
    if scout.empty:
        return "_No scouting evaluation._"
    labels = {s["key"]: s["label"] for s in result["stages"]}
    budgets = sorted(scout["budget"].unique())
    rankers = [r for r in figures.RANKER_ORDER if r in set(scout["ranker"])]
    head = "| Stage | Ranking | " + " | ".join(f"Recall @ {b:.0%}" for b in budgets) + " |"
    lines = [head, "|---|---|" + "---|" * len(budgets)]
    for stage in [s["key"] for s in result["stages"]]:
        for ranker in rankers:
            part = scout[(scout["stage"] == stage) & (scout["ranker"] == ranker)]
            if part.empty or (ranker == "records_only" and stage != "records"):
                continue
            cells = [
                _fmt(part.loc[part["budget"] == b, "recall"].squeeze(), ".0%") for b in budgets
            ]
            lines.append(
                f"| {labels[stage]} | {figures.RANKER_LABEL[ranker]} | " + " | ".join(cells) + " |"
            )
    first = scout.drop_duplicates("budget").set_index("budget")
    ref = ", ".join(
        f"{b:.0%}: random {first.loc[b, 'random_recall']:.0%}, perfect {first.loc[b, 'oracle_recall']:.0%}"
        for b in budgets
    )
    return "\n".join(lines) + f"\n\nReference recall ({ref})."


def _contrast_markdown(result) -> str:
    primary = result["config"]["primary_model"]
    ran = [s["name"] for s in result["validation_schemes"] if s["ran"]]
    by = {
        (r["validation"], r["stage"]): r["mae"] for r in result["results"] if r["model"] == primary
    }
    lines = [
        "| Stage | " + " | ".join(ran) + " |",
        "|---|" + "---|" * len(ran),
    ]
    for s in result["stages"]:
        lines.append(
            f"| {s['label']} | " + " | ".join(_fmt(by.get((v, s["key"]))) for v in ran) + " |"
        )
    return "\n".join(lines)


def _spatial_markdown(result) -> str:
    sp = pd.DataFrame(result["spatial"])
    if sp.empty:
        return "_No coordinates: spatial check skipped._"
    labels = {s["key"]: s["label"] for s in result["stages"]}
    g = sp.groupby("stage", sort=False).agg(
        median_i=("morans_i", "median"),
        significant=("p_value", lambda p: f"{(p < 0.05).sum()}/{len(p)}"),
        spacing=("neighbour_distance_m", "median"),
    )
    lines = [
        "| Stage | Median Moran's I of residuals | Site-seasons with p < 0.05 | Nearest-plot spacing (m) |",
        "|---|---|---|---|",
    ]
    for stage, r in g.iterrows():
        lines.append(
            f"| {labels.get(stage, stage)} | {r.median_i:.2f} | {r.significant} | {r.spacing:.1f} |"
        )
    return "\n".join(lines)


def _timing_markdown(result) -> str:
    lines = [
        "| Stage | Site-season | Last pass | Date | Median DAP | Lead to harvest (d) |",
        "|---|---|---|---|---|---|",
    ]
    for s in result["stages"]:
        for p in result["timing"].get(s["key"], {}).get("per_site_year", []):
            lines.append(
                f"| {s['label']} | {p['site_id']} {p['year']} | TP{p['last_pass']} | {p['date'] or '–'} "
                f"| {_fmt(p['dap_median'], '.0f')} | {_fmt(p['lead_days_median'], '.0f')} |"
            )
    return "\n".join(lines)


def summary_markdown(result, meta: dict) -> str:
    c = result["criteria"]
    primary = figures.MODEL_LABEL.get(
        result["config"]["primary_model"], result["config"]["primary_model"]
    )
    banner = (
        "> **SYNTHETIC FIXTURE: NOT A RESULT.** Random data shaped like the practice dataset, "
        "used to exercise the pipeline and show the output format. Do not quote any number "
        "below.\n\n"
        if result.get("synthetic")
        else ""
    )
    earliest = c["earliest_candidate"]
    earliest_text = (
        f"**{next(s['label'] for s in c['stages'] if s['stage'] == earliest)}** is the first "
        "stage that passes all five checks."
        if earliest
        else "**No stage passes all five checks** with the current thresholds."
    )
    acc = c["stages_passing_accuracy_checks"]
    notes = "\n".join(f"- {n}" for n in result["notes"]) or "- none"
    schemes = "\n".join(
        f"- `{s['name']}`: {'ran' if s['ran'] else 'not run'} ({s['reason']})"
        for s in result["validation_schemes"]
    )
    return f"""# Progressive early-signal experiment: {result["dataset"]}

{banner}Generated {meta["generated"]} (code `{meta["git_sha"]}`). {result["n_plots"]} plots,
sites {", ".join(result["sites"])}, season(s) {", ".join(map(str, result["years"]))}.

**Headline validation:** {result["headline_validation"]["description"]}. **Primary model:**
{primary} (same fixed hyperparameters at every stage). 90% intervals are nested conformal:
calibrated inside each training fold, scored on the held-out group.

## When does imagery start to help?

{progression_markdown(result)}

ΔMAE is records-only MAE minus this stage's MAE (positive = imagery helped), same model,
same folds, same plots. The 95% interval resamples plots within site-seasons, so with few
sites it is narrower than the real between-site uncertainty; read it with "Better in"
(the held-out site-seasons where MAE fell). DAP = days after planting of the last pass
the stage can use; TP labels are not dates.

![MAE by stage](figures/mae_vs_stage.png)
![Delta MAE](figures/delta_mae_vs_stage.png)

## Earliest useful forecast: the evidence

{earliest_text} Stages passing the accuracy checks (1 and 2): {", ".join(acc) if acc else "none"}.
Thresholds (configs/progressive.yaml): `{json.dumps(c["thresholds"])}`. This is evidence for
the team's call, not a verdict.

{_criteria_markdown(result)}

## Scouting: if only X% of plots can be visited

Recall = share of each site-season's eventual bottom-quartile plots that the ranking sends
scouts to (pooled over site-seasons). The lower-bound ranking uses conformalized quantile
regression, whose width varies by plot; with a constant-width interval it would be the same
ranking as the forecast.

{_scouting_markdown(result)}

![Scouting recall](figures/scouting_recall_vs_stage.png)

## Uncertainty

![Interval width and coverage](figures/interval_vs_stage.png)

## Why the headline is grouped (primary model MAE by validation scheme)

{_contrast_markdown(result)}

![Validation contrast](figures/validation_contrast.png)

## Are errors spatially clustered?

{_spatial_markdown(result)}

## Acquisition timing by site-season

{_timing_markdown(result)}

## Validation schemes

{schemes}

## Notes and limitations

{notes}
"""
