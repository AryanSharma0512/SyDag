"""
Write the website's frozen results from the ML team's temporal run.

    cd backend && uv run python -m scripts.build_final_results

Reads ml/experiments/temporal_final_2022/:

    temporal_plot_predictions.csv   out-of-fold forecast per plot and satellite stage
    temporal_model_coordinates.csv  validation per site and stage, as the ML team reported it
    uav_matched_comparison.json     the separate matched satellite vs satellite + UAV experiment

and writes backend/artifacts/final_results.json (contract: app/results.py), then checks it
against the contract. Nothing is retrained and no number is typed in by hand: every
forecast, range and metric comes from those files.

Only the `deployed` series feeds the website: at each stage, the best inner-validated
model available so far. The raw per-stage models, the satellite-only models and the
pre-season model stay research history, except that the pre-season metrics are the
baseline each site's stages are compared against.

- Plot forecasts: stage TPk is dated by the site's k-th satellite acquisition
  (data/trial_sites.json); `dap` is each plot's own. Forecast yields are floored at
  0 bu/ac for display (a few very low-yield plots have negative point predictions);
  every metric is computed on the raw model outputs.
- `performance`: pooled out-of-fold MAE and RMSE across the five site-specific models per
  stage. R² is left out on purpose: pooled across sites it mostly measures the yield
  differences between sites. Each stage's DAP is the median across sites, and the label
  says so with the sites' range.
- `site_performance`: each site's own metrics from the coordinates file, cross-checked
  against the plot rows (the run stops if they disagree).
- Featured plot per site: the plot whose harvested yield is closest to the site median,
  the rule the ML team fixed in advance (ties go to the lower plot id). `--featured`
  overrides it for a site.
- `earliest_useful_dap` stays unset unless `--earliest-useful-mae` names the rule.
"""

import argparse
import json
import math
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from app.results import RESULTS_FILE, LoadedResults, ResultsError, parse

BACKEND = Path(__file__).resolve().parent.parent
RUN_DIR = BACKEND.parent / "ml" / "experiments" / "temporal_final_2022"
PREDICTIONS = RUN_DIR / "temporal_plot_predictions.csv"
COORDINATES = RUN_DIR / "temporal_model_coordinates.csv"
UAV = RUN_DIR / "uav_matched_comparison.json"
SITES = BACKEND / "data" / "trial_sites.json"
OUT = BACKEND / "artifacts" / RESULTS_FILE

RESULTS_VERSION = "temporal-final-2022-20260927"
SERIES = "deployed"
PRESEASON = "preseason"
INTERVAL_LEVEL = 0.9
# The coordinates file and the plot rows are the same run; they may differ by rounding only.
TOLERANCE = {"r2": 0.002, "mae": 0.01, "rmse": 0.01, "coverage": 0.002, "width": 0.01}

MODEL = {
    "name": "Site-specific cumulative yield models",
    "validation": (
        "Nested cross-validation within site; fixed outer folds across TP1–TP6 "
        "(5 folds, Missouri Valley 4 folds); model selected by inner-CV MAE"
    ),
    "description": (
        "At each satellite cutoff the system uses only information available through that "
        "date. Candidate models include Random Forest, HistGradientBoosting, XGBoost, "
        "CatBoost and ElasticNet. The deployed forecast retains the best inner-validated "
        "model available so far."
    ),
    "features": [
        "genotype",
        "nitrogen rate",
        "irrigation",
        "plot length",
        "planting timing",
        "NDVI trajectory",
        "NDRE trajectory",
        "NIR trajectory",
        "GNDVI trajectory",
        "SAVI trajectory",
        "red-edge and spectral trajectory features",
    ],
}
INTERVAL_METHOD = "CV+ conformal prediction; site-specific nested cross-validation"

PREDICTION_COLUMNS = {
    "location",
    "plot_id",
    "timepoint",
    "dap",
    "actual_yield_bu_ac",
    "predicted_yield_bu_ac",
    "lower_90",
    "upper_90",
    "series",
}
COORDINATE_COLUMNS = {
    "location",
    "timepoint",
    "dap",
    "dap_min",
    "dap_max",
    "n_plots",
    "n_folds",
    "deployed_r2",
    "deployed_mae",
    "deployed_rmse",
    "deployed_pi_coverage_90",
    "deployed_median_pi_width_90",
    "preseason_agronomic_r2",
    "preseason_agronomic_mae",
    "preseason_agronomic_median_pi_width_90",
}


class BuildError(Exception):
    """The inputs are missing something the website needs, or disagree with each other."""


def _read_csv(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.is_file():
        raise BuildError(f"missing {path}")
    frame = pd.read_csv(path)
    missing = required - set(frame.columns)
    if missing:
        raise BuildError(f"{path.name} lacks {sorted(missing)}; it has {sorted(frame.columns)}")
    return frame


def _stage_number(stage: str) -> int:
    if not (stage.startswith("TP") and stage[2:].isdigit()):
        raise BuildError(f"unexpected timepoint {stage!r}; expected TP1, TP2, ...")
    return int(stage[2:])


def _metrics(actual: pd.Series, predicted: pd.Series, lower: pd.Series, upper: pd.Series) -> dict:
    err = predicted - actual
    return {
        "r2": 1 - float((err**2).sum()) / float(((actual - actual.mean()) ** 2).sum()),
        "mae": float(err.abs().mean()),
        "rmse": math.sqrt(float((err**2).mean())),
        "coverage": float(((actual >= lower) & (actual <= upper)).mean()),
        "width": float((upper - lower).median()),
        "n": int(len(actual)),
    }


def _group_metrics(rows: pd.DataFrame) -> dict:
    actual, predicted = rows["actual_yield_bu_ac"], rows["predicted_yield_bu_ac"]
    return _metrics(actual, predicted, rows["lower_90"], rows["upper_90"])


def _check(where: str, computed: dict, reported: dict) -> None:
    for key, value in reported.items():
        if abs(computed[key] - value) > TOLERANCE[key]:
            raise BuildError(
                f"{where}: {key} from the plot rows is {computed[key]:.4f}, "
                f"the coordinates file says {value:.4f}"
            )


def _site_calendar(path: Path) -> dict[str, tuple[int, list[date]]]:
    """Season and satellite acquisition dates per site id, from the trial-site registry."""
    sites = json.loads(path.read_text())["sites"]
    calendar = {}
    for site in sites:
        seasons = site["seasons"]
        if len(seasons) != 1:
            raise BuildError(f"{site['id']}: expected one season in {path.name}")
        acquired = [date.fromisoformat(d) for d in seasons[0]["satellite"]["acquisition_dates"]]
        calendar[site["id"]] = (seasons[0]["year"], acquired)
    return calendar


def _featured(deployed: pd.DataFrame, overrides: list[str]) -> set[str]:
    """Per site: the plot whose harvested yield is closest to the site median."""
    by_plot = deployed.groupby(["location", "plot_id"], as_index=False)
    per_plot = by_plot["actual_yield_bu_ac"].first()
    chosen = {}
    for site, plots in per_plot.groupby("location"):
        gap = (plots["actual_yield_bu_ac"] - plots["actual_yield_bu_ac"].median()).abs().round(6)
        ranked = plots.assign(gap=gap).sort_values(["gap", "plot_id"])
        chosen[site] = ranked["plot_id"].iloc[0]
    known = dict(zip(per_plot["plot_id"], per_plot["location"], strict=True))
    for plot_id in overrides:
        if plot_id not in known:
            raise BuildError(f"--featured {plot_id}: no such plot in the deployed series")
        chosen[known[plot_id]] = plot_id
    return set(chosen.values())


def _plots(deployed: pd.DataFrame, calendar: dict, featured: set[str]) -> list[dict]:
    plots = []
    for (site, plot_id), rows in deployed.groupby(["location", "plot_id"], sort=True):
        if site not in calendar:
            raise BuildError(f"{site} is not in {SITES.name}")
        season, acquired = calendar[site]
        forecasts, planted = [], set()
        for row in rows.sort_values("stage_number").itertuples():
            if row.stage_number > len(acquired):
                raise BuildError(f"{site} has no acquisition date for {row.timepoint}")
            when = acquired[row.stage_number - 1]
            dap = int(row.dap)
            planted.add(when - timedelta(days=dap))
            # Displayed yields are floored at zero; the range keeps the model's own bounds
            # (the website floors the lower bound when it draws it).
            point = max(0.0, row.predicted_yield_bu_ac)
            forecasts.append(
                {
                    "date": when.isoformat(),
                    "dap": dap,
                    "stage": row.timepoint,
                    "yield": round(point, 2),
                    "lower": round(min(row.lower_90, point), 2),
                    "upper": round(max(row.upper_90, point), 2),
                }
            )
        if len(planted) != 1:
            raise BuildError(f"{plot_id}: dates and DAP imply more than one planting date")
        plots.append(
            {
                "plot_id": plot_id,
                "site": site,
                "season": season,
                "planting_date": planted.pop().isoformat(),
                "featured": plot_id in featured,
                "forecasts": forecasts,
            }
        )
    return plots


def _pooled_performance(deployed: pd.DataFrame, coords: pd.DataFrame) -> list[dict]:
    rows = []
    for stage, group in deployed.groupby("timepoint"):
        at = coords[coords["timepoint"] == stage]
        m = _group_metrics(group)
        low, high = int(at["dap_min"].min()), int(at["dap_max"].max())
        rows.append(
            {
                "dap": int(round(float(at["dap"].median()))),
                "stage": stage,
                "label": f"{stage} · site DAP {low}–{high}",
                "mae": round(m["mae"], 2),
                "rmse": round(m["rmse"], 2),
                "r2": None,
                "n": int(group["plot_id"].nunique()),
            }
        )
    return sorted(rows, key=lambda r: _stage_number(r["stage"]))


def _site_performance(
    coords: pd.DataFrame, deployed: pd.DataFrame, preseason: pd.DataFrame, calendar: dict
) -> list[dict]:
    out = []
    for site, at in coords.groupby("location", sort=False):
        at = at.assign(stage_number=at["timepoint"].map(_stage_number)).sort_values("stage_number")
        stages = []
        for row in at.itertuples():
            reported = {
                "r2": row.deployed_r2,
                "mae": row.deployed_mae,
                "rmse": row.deployed_rmse,
                "coverage": row.deployed_pi_coverage_90,
                "width": row.deployed_median_pi_width_90,
            }
            here = (deployed["location"] == site) & (deployed["timepoint"] == row.timepoint)
            rows = deployed[here]
            _check(f"{site} {row.timepoint}", _group_metrics(rows), reported)
            stages.append(
                {
                    "stage": row.timepoint,
                    "dap": int(row.dap),
                    "dap_min": int(row.dap_min),
                    "dap_max": int(row.dap_max),
                    "r2": round(row.deployed_r2, 3),
                    "mae": round(row.deployed_mae, 2),
                    "rmse": round(row.deployed_rmse, 2),
                    "coverage": round(row.deployed_pi_coverage_90, 3),
                    "median_interval_width": round(row.deployed_median_pi_width_90, 2),
                    "n": int(row.n_plots),
                }
            )
        first = at.iloc[0]
        base_rows = preseason[preseason["location"] == site]
        base = _group_metrics(base_rows)
        _check(
            f"{site} pre-season",
            base,
            {
                "r2": first.preseason_agronomic_r2,
                "mae": first.preseason_agronomic_mae,
                "width": first.preseason_agronomic_median_pi_width_90,
            },
        )
        out.append(
            {
                "site": site,
                "season": calendar[site][0],
                "plots": int(first.n_plots),
                "folds": int(first.n_folds),
                "preseason": {
                    "r2": round(first.preseason_agronomic_r2, 3),
                    "mae": round(first.preseason_agronomic_mae, 2),
                    "rmse": round(base["rmse"], 2),
                    "coverage": round(base["coverage"], 3),
                    "median_interval_width": round(first.preseason_agronomic_median_pi_width_90, 2),
                    "n": base["n"],
                },
                "stages": stages,
            }
        )
    return out


def _dumps(doc: dict) -> str:
    """Indented, with one plot per line: readable, and a new run diffs by plot."""
    plots = doc.pop("plots")
    head = json.dumps(doc, indent=2, ensure_ascii=False)
    lines = ",\n    ".join(json.dumps(p, ensure_ascii=False, separators=(",", ":")) for p in plots)
    doc["plots"] = plots
    return f'{head[:-2]},\n  "plots": [\n    {lines}\n  ]\n}}\n'


def build(
    predictions: Path = PREDICTIONS,
    coordinates: Path = COORDINATES,
    uav: Path | None = UAV,
    sites: Path = SITES,
    featured: list[str] | None = None,
    earliest_useful_mae: float | None = None,
    results_version: str = RESULTS_VERSION,
) -> dict:
    frame = _read_csv(predictions, PREDICTION_COLUMNS)
    coords = _read_csv(coordinates, COORDINATE_COLUMNS)
    if frame[sorted(PREDICTION_COLUMNS)].isna().any().any():
        raise BuildError(f"{predictions.name} has empty values")
    deployed = frame[frame["series"] == SERIES].copy()
    preseason = frame[frame["series"] == PRESEASON]
    if deployed.empty:
        raise BuildError(f"{predictions.name} has no {SERIES!r} rows")
    deployed["stage_number"] = deployed["timepoint"].map(_stage_number)
    per_plot = deployed.groupby("plot_id")["timepoint"].agg(["count", "nunique"])
    if (per_plot["count"] != per_plot["nunique"]).any():
        raise BuildError("a plot has more than one deployed forecast for a stage")

    calendar = _site_calendar(sites)
    plots = _plots(deployed, calendar, _featured(deployed, featured or []))
    performance = _pooled_performance(deployed, coords)
    everything = _group_metrics(deployed)

    earliest = None
    if earliest_useful_mae is not None:
        earliest = next((p for p in performance if p["mae"] <= earliest_useful_mae), None)
    season_years = sorted({p["season"] for p in plots})
    doc = {
        "contract_version": 1,
        "results_version": results_version,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "dataset_label": (
            f"SyDAg {'/'.join(map(str, season_years))} maize trials · {len(plots):,} plots · "
            f"{deployed['location'].nunique()} sites"
        ),
        "unit": "bu/ac",
        "model": MODEL,
        "interval": {
            "level": INTERVAL_LEVEL,
            "coverage": round(everything["coverage"], 3),
            "method": INTERVAL_METHOD,
        },
        "performance": performance,
        "earliest_useful_dap": earliest["dap"] if earliest else None,
        "earliest_useful_rule": (
            f"First satellite stage where pooled out-of-fold MAE across the five site-specific "
            f"deployed models is ≤{earliest_useful_mae:g} bu/ac."
            if earliest
            else None
        ),
        "site_performance": _site_performance(coords, deployed, preseason, calendar),
        "maturity": [],
        "uav": json.loads(uav.read_text()) if uav else None,
        "plots": plots,
    }
    return doc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS)
    parser.add_argument("--coordinates", type=Path, default=COORDINATES)
    parser.add_argument("--uav", type=Path, default=UAV)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--version", default=RESULTS_VERSION, help="results_version to write")
    parser.add_argument(
        "--featured",
        action="append",
        default=[],
        metavar="PLOT_ID",
        help="open this plot's site on it instead of the median-yield plot (repeatable)",
    )
    parser.add_argument(
        "--earliest-useful-mae",
        type=float,
        help="set earliest_useful_dap to the first stage whose pooled MAE is at most this",
    )
    args = parser.parse_args(argv)
    try:
        doc = build(
            args.predictions,
            args.coordinates,
            args.uav,
            featured=args.featured,
            earliest_useful_mae=args.earliest_useful_mae,
            results_version=args.version,
        )
        text = _dumps(doc)
        loaded = LoadedResults(parse(text))
    except (BuildError, ResultsError, OSError, ValueError) as err:
        print(f"FAILED: {err}")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)

    plots = doc["plots"]
    frame = pd.read_csv(args.predictions)
    floored = int(((frame["series"] == SERIES) & (frame["predicted_yield_bu_ac"] < 0)).sum())
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    print(f"  {doc['dataset_label']}; {sum(len(p['forecasts']) for p in plots):,} forecasts")
    print(f"  plots by site: {[(c.site, c.plots) for c in loaded.summary.plot_counts]}")
    print(f"  forecasts floored at 0 bu/ac: {floored}")
    print(f"  interval coverage {doc['interval']['coverage']} (nominal {INTERVAL_LEVEL})")
    for p in doc["performance"]:
        print(f"  {p['label']}: MAE {p['mae']}, RMSE {p['rmse']}, median DAP {p['dap']}")
    print(f"  featured: {sorted(p['plot_id'] for p in plots if p['featured'])}")
    print(f"  earliest useful DAP: {doc['earliest_useful_dap']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
