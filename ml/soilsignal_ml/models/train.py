"""
Progressive training: for each season cutoff, compare the model ladder under grouped
validation, tune inside cross-validation, pick a model, and only then score it on
the held-out site.

    1. features as of the cutoff (backend build_features)
    2. split off the held-out site; it is not touched until step 6
    3. per model: Optuna search minimizing mean leave-one-site-out MAE on dev sites
    4. out-of-fold predictions -> metrics, fold spread, interval offsets, coverage
    5. select: lowest mean + 1 SD of fold MAE, preferring the simpler model within a margin
    6. refit on all dev sites, score once on the held-out site
    7. drivers (permutation importance on held-out folds), sensitivity checks

Before step 3, feature groups are screened (the ablation table): each group combination
is cross-validated with default parameters and the one with the lowest mean + 1 SD of
fold MAE is kept. With only a few
training sites, site-level features (weather, soil, county history, planting date) take
a handful of distinct values and can act as site identifiers, so whether they help a
new site is decided by leave-one-site-out CV, never assumed.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import optuna
import pandas as pd
import yaml

from app.features.catalog import info
from soilsignal_ml import ML_ROOT
from soilsignal_ml.evaluation.explain import (
    directions,
    fold_permutation_importance,
    typical_values,
)
from soilsignal_ml.evaluation.metrics import fold_summary, regression_metrics
from soilsignal_ml.evaluation.sensitivity import sensitivity
from soilsignal_ml.evaluation.uncertainty import coverage, interval_offsets
from soilsignal_ml.experiments import dataset_version, git_sha, new_run_id, record
from soilsignal_ml.features.build import GROUPS, feature_columns, feature_table, select_groups
from soilsignal_ml.ingest.canonical import PROCESSED, CanonicalDataset
from soilsignal_ml.models.base import ModelSpec, Params
from soilsignal_ml.models.baseline import MEAN, RIDGE
from soilsignal_ml.models.boosted import CATBOOST, HIST_GRADIENT_BOOSTING
from soilsignal_ml.models.random_forest import RANDOM_FOREST
from soilsignal_ml.validation.splits import DESCRIPTIONS, folds, holdout_mask

CONFIGS = ML_ROOT / "configs"
INTERIM = ML_ROOT / "data" / "interim"
CANDIDATES = ML_ROOT / "experiments" / "candidates"
LADDER: list[ModelSpec] = [MEAN, RIDGE, RANDOM_FOREST, HIST_GRADIENT_BOOSTING, CATBOOST]
CUTOFF_ORDER = ["may", "june", "july", "august", "full"]
# A feature is used at a cutoff only if it is observable at every training site for at
# least this share of that site's plots. Otherwise its missingness is a site fingerprint
# (e.g. "rain around silking" exists on July 31 only where silking has already happened).
MIN_SITE_COVERAGE = 0.5
# Management (hybrid, nitrogen, irrigation) is what was planted, so every set includes it.
ABLATIONS = {
    "Management only": {"management"},
    "Crop signals": {"management", "crop"},
    "Crop + timing": {"management", "crop", "temporal"},
    "Crop + weather": {"management", "crop", "weather"},
    "Crop + soil": {"management", "crop", "soil"},
    "Crop + weather + soil": {"management", "crop", "weather", "soil"},
    "All (+ timing, county history)": set(GROUPS),
}
optuna.logging.set_verbosity(optuna.logging.WARNING)


def load_project() -> dict:
    return yaml.safe_load((CONFIGS / "project.yaml").read_text())


def load_cutoffs(names: list[str] | None = None) -> list[dict]:
    names = names or CUTOFF_ORDER
    return [yaml.safe_load((CONFIGS / f"{n}.yaml").read_text()) for n in names]


def prepare(frame: pd.DataFrame, numeric: list[str], categorical: list[str]) -> pd.DataFrame:
    """Model input: floats for numeric features, strings for categorical ones."""
    X = frame[numeric + categorical].copy()
    X[numeric] = X[numeric].astype(float)
    for c in categorical:
        X[c] = X[c].where(X[c].notna(), "unknown").astype(str)
    return X[[c for c in frame.columns if c in set(numeric + categorical)]]


@dataclass
class Evaluation:
    spec: ModelSpec
    params: Params
    oof: np.ndarray
    per_fold: list[dict]
    summary: dict
    offsets: tuple[float, float]
    oof_coverage: float
    seconds: float
    tuning: list[dict] = field(default_factory=list)


def cross_validate(spec, params, X, y, fold_list, numeric, categorical, seed):
    oof = np.full(len(y), np.nan)
    per_fold = []
    started = time.perf_counter()
    for fold in fold_list:
        model = spec.make(params, numeric, categorical, seed)
        model.fit(X.iloc[fold.train], y[fold.train])
        pred = model.predict(X.iloc[fold.test])
        oof[fold.test] = pred
        per_fold.append({"group": fold.name, **regression_metrics(y[fold.test], pred)})
    return oof, per_fold, time.perf_counter() - started


def tune(spec, X, y, fold_list, numeric, categorical, seed, trials) -> tuple[Params, list[dict]]:
    if spec.space is None or trials <= 0:
        return dict(spec.defaults), []

    def objective(trial: optuna.Trial) -> float:
        params = spec.space(trial)
        _, per_fold, _ = cross_validate(spec, params, X, y, fold_list, numeric, categorical, seed)
        return float(np.mean([f["mae"] for f in per_fold]))

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.enqueue_trial(spec.defaults)
    study.optimize(objective, n_trials=trials)
    history = [{"number": t.number, "cv_mae": t.value, "params": t.params} for t in study.trials]
    return {**study.best_params}, history


def evaluate(spec, params, X, y, fold_list, numeric, categorical, seed, level, tuning=None):
    oof, per_fold, seconds = cross_validate(
        spec, params, X, y, fold_list, numeric, categorical, seed
    )
    offsets = interval_offsets(y - oof, level)
    return Evaluation(
        spec,
        params,
        oof,
        per_fold,
        fold_summary(per_fold),
        offsets,
        coverage(y, oof, offsets),
        seconds,
        tuning or [],
    )


def risk(e: Evaluation) -> float:
    """Selection score: mean fold MAE plus one standard deviation across folds (brief §45:
    a model that is consistently good on every held-out site beats one that is sometimes
    excellent and sometimes far off)."""
    return e.summary["cv_mae"] + e.summary["cv_mae_std"]


def select(evaluations: list[Evaluation], margin: float) -> Evaluation:
    """Lowest risk; a more complex model must beat every simpler one by `margin`."""
    best = min(evaluations, key=risk)
    for e in sorted(evaluations, key=lambda e: e.spec.complexity):
        if e.spec.complexity >= best.spec.complexity:
            break
        if risk(e) <= risk(best) * (1 + margin):
            return e
    return best


def run_cutoff(ds: CanonicalDataset, cfg: dict, project: dict, trials: int, context: dict) -> dict:
    seed, level = project["seed"], project["interval_level"]
    table = feature_table(ds, cfg["as_of"])
    INTERIM.mkdir(parents=True, exist_ok=True)
    table.to_csv(INTERIM / f"features_{cfg['name']}.csv", index=False)

    test_mask = holdout_mask(table, project["holdout_site"])
    dev, test = table[~test_mask].reset_index(drop=True), table[test_mask].reset_index(drop=True)
    columns = [
        c
        for c in feature_columns(table)
        if dev[c].nunique(dropna=True) > 1
        and dev.groupby("site_id")[c].apply(lambda s: s.notna().mean()).min() >= MIN_SITE_COVERAGE
    ]
    y, y_test = dev["final_yield"].to_numpy(float), test["final_yield"].to_numpy(float)
    site_folds = folds(dev, project["primary_validation"])
    print(
        f"\n== {cfg['label']} (as of {cfg['as_of']}): {len(columns)} usable features, "
        f"{len(dev)} dev plots in {dev['site_id'].nunique()} sites, {len(test)} held-out plots"
    )
    base_row = {
        "dataset": ds.name,
        "dataset_version": context["dataset_version"],
        "git_sha": context["git_sha"],
        "cutoff": cfg["name"],
        "as_of": cfg["as_of"],
        "seed": seed,
    }

    # Feature-group screening (the ablation table): default parameters, dev-site CV only.
    ablation, seen_sets = {}, set()
    for label, groups in ABLATIONS.items():
        cols = select_groups(columns, groups)
        if not cols or tuple(cols) in seen_sets:
            continue
        seen_sets.add(tuple(cols))
        cat = [c for c in cols if info(c).dtype == "category"]
        num = [c for c in cols if c not in cat]
        Xa, Xa_test = prepare(dev, num, cat), prepare(test, num, cat)
        per_model = {}
        for spec in LADDER[1:]:
            ev = evaluate(spec, dict(spec.defaults), Xa, y, site_folds, num, cat, seed, level)
            per_model[spec.name] = ev
            _log(base_row, spec.name, label, len(cols), "site", dev, ev, spec.defaults)
        best = min(per_model.values(), key=risk)
        m = best.spec.make(best.params, num, cat, seed).fit(Xa, y)
        ablation[label] = {
            "columns": cols,
            "n_features": len(cols),
            "best_model": best.spec.name,
            "cv_mae": best.summary["cv_mae"],
            "cv_mae_std": best.summary["cv_mae_std"],
            "risk": risk(best),
            "per_model_cv_mae": {k: v.summary["cv_mae"] for k, v in per_model.items()},
            "per_model_risk": {k: risk(v) for k, v in per_model.items()},
            "holdout_mae": regression_metrics(y_test, m.predict(Xa_test))["mae"],
        }
        print(
            f"  screen {label:32s} {len(cols):3d} features  best {best.spec.name:22s} "
            f"LOSO MAE {best.summary['cv_mae']:6.1f} ± {best.summary['cv_mae_std']:5.1f}"
        )
    feature_set = min(
        ablation, key=lambda k: (round(ablation[k]["risk"], 1), ablation[k]["n_features"])
    )
    columns = ablation[feature_set]["columns"]
    print(f"  feature set: {feature_set} ({len(columns)} features)")

    categorical = [c for c in columns if info(c).dtype == "category"]
    numeric = [c for c in columns if c not in categorical]
    X, X_test = prepare(dev, numeric, categorical), prepare(test, numeric, categorical)
    evaluations: list[Evaluation] = []
    comparison: dict[str, dict] = {}
    for spec in LADDER:
        params, history = tune(spec, X, y, site_folds, numeric, categorical, seed, trials)
        ev = evaluate(spec, params, X, y, site_folds, numeric, categorical, seed, level, history)
        evaluations.append(ev)
        comparison[spec.name] = {"site": ev.summary | {"per_fold": ev.per_fold}}
        _log(base_row, spec.name, f"tuned: {feature_set}", len(columns), "site", dev, ev, params)
        print(
            f"  {spec.name:24s} LOSO MAE {ev.summary['cv_mae']:6.1f}"
            f" ± {ev.summary['cv_mae_std']:5.1f}"
            f"  (tuned {len(history)} trials, {ev.seconds:.1f}s per CV)"
        )
        for strategy in ("plot", "field"):
            other = folds(dev, strategy)
            oof, per_fold, secs = cross_validate(
                spec, params, X, y, other, numeric, categorical, seed
            )
            summary = fold_summary(per_fold)
            comparison[spec.name][strategy] = summary
            fake = Evaluation(spec, params, oof, per_fold, summary, (0.0, 0.0), float("nan"), secs)
            _log(
                base_row,
                spec.name,
                f"tuned: {feature_set}",
                len(columns),
                strategy,
                dev,
                fake,
                params,
            )

    chosen = select(evaluations, project["simpler_model_margin"])
    print(f"  selected: {chosen.spec.name}")

    # Held-out site: one fit on all dev sites, one score. Every model is scored for the
    # report, but the choice above was already made without it.
    holdout = {}
    fitted = {}
    for ev in evaluations:
        model = ev.spec.make(ev.params, numeric, categorical, seed).fit(X, y)
        pred = model.predict(X_test)
        holdout[ev.spec.name] = regression_metrics(y_test, pred) | {
            "interval_coverage": coverage(y_test, pred, ev.offsets)
        }
        fitted[ev.spec.name] = (model, pred)
    final, test_pred = fitted[chosen.spec.name]

    # Drivers: permutation importance on each held-out-site fold, averaged.
    importances = []
    for fold in site_folds:
        m = chosen.spec.make(chosen.params, numeric, categorical, seed).fit(
            X.iloc[fold.train], y[fold.train]
        )
        importances.append(fold_permutation_importance(m, X.iloc[fold.test], y[fold.test], seed))
    importance = pd.concat(importances, axis=1).mean(axis=1)
    typical = typical_values(X, categorical)
    direction = directions(final, X, typical, categorical)
    ranges = {
        c: (float(X[c].quantile(0.01)), float(X[c].quantile(0.99)))
        for c in numeric
        if X[c].notna().any()
    }

    checks = sensitivity(final, X)

    CANDIDATES.mkdir(parents=True, exist_ok=True)
    out = CANDIDATES / cfg["name"]
    out.mkdir(exist_ok=True)
    joblib.dump(final, out / "model.joblib")
    summary = {
        "config": cfg,
        "model": chosen.spec.name,
        "algorithm": chosen.spec.algorithm,
        "library": chosen.spec.library,
        "params": chosen.params,
        "feature_set": feature_set,
        "features": columns,
        "categorical": categorical,
        "n_dev": len(dev),
        "dev_sites": sorted(dev["site_id"].unique()),
        "holdout_site": project["holdout_site"],
        "cv": chosen.summary
        | {"per_fold": chosen.per_fold, "oof": regression_metrics(y, chosen.oof)},
        "interval": {
            "level": level,
            "lower_offset": chosen.offsets[0],
            "upper_offset": chosen.offsets[1],
            "oof_coverage": chosen.oof_coverage,
        },
        "holdout": holdout[chosen.spec.name],
        "comparison": comparison,
        "holdout_all": holdout,
        "ablation": ablation,
        "sensitivity": checks,
        "importance": importance.to_dict(),
        "direction": direction,
        "typical": typical,
        "ranges": ranges,
        "holdout_predictions": pd.DataFrame(
            {"plot_id": test["plot_id"], "actual": y_test, "predicted": test_pred}
        ).to_dict(orient="records"),
        "context": context,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=_json) + "\n")
    print(
        f"  held-out {project['holdout_site']}: MAE {holdout[chosen.spec.name]['mae']:.1f}, "
        f"coverage {holdout[chosen.spec.name]['interval_coverage']:.0%}"
    )
    return summary


def _json(value):
    if isinstance(value, np.integer | np.floating):
        return value.item()
    return str(value)


def _log(base, model, feature_set, n_features, validation, dev, ev: Evaluation, params) -> None:
    groups = sorted(map(str, dev["site_id"].unique()))
    record(
        {
            **base,
            "run_id": new_run_id(base["cutoff"], model, feature_set, validation),
            "model": model,
            "feature_set": feature_set,
            "n_features": n_features,
            "validation": DESCRIPTIONS[validation],
            "train_groups": ";".join(groups),
            "test_groups": ";".join(f["group"] for f in ev.per_fold),
            "mae": round(ev.summary["cv_mae"], 3),
            "rmse": round(ev.summary["cv_rmse"], 3),
            "r2": round(ev.summary["cv_r2"], 4),
            "relative_mae": round(float(np.mean([f["relative_mae"] for f in ev.per_fold])), 4),
            "mae_fold_std": round(ev.summary["cv_mae_std"], 3),
            "interval_coverage": round(ev.oof_coverage, 4) if not np.isnan(ev.oof_coverage) else "",
            "interval_lower": round(ev.offsets[0], 2),
            "interval_upper": round(ev.offsets[1], 2),
            "train_seconds": round(ev.seconds, 2),
            "params": json.dumps(params, default=str),
        },
        {"per_fold": ev.per_fold, "tuning": ev.tuning},
    )


def run_training(
    dataset: str, cutoffs: list[str] | None = None, trials: int | None = None
) -> list[dict]:
    project = load_project()
    ds = CanonicalDataset.load(dataset)
    context = {"git_sha": git_sha(), "dataset_version": dataset_version(Path(PROCESSED / dataset))}
    trials = project["optuna_trials"] if trials is None else trials
    return [run_cutoff(ds, cfg, project, trials, context) for cfg in load_cutoffs(cutoffs)]
