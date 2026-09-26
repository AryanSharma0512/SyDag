"""
Run every information stage x model x validation scheme and collect the evidence.

For the headline scheme every candidate model runs; other grouped schemes run the
secondary models (primary + mean by default); the optimistic contrasts (field blocks,
random plots) run the primary model only and carry no intervals. Nothing here picks a
winner: criteria.py states which stages meet which checks.
"""

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from soilsignal_ml import ML_ROOT
from soilsignal_ml.models.train import prepare
from soilsignal_ml.progressive import criteria as crit
from soilsignal_ml.progressive.contract import CATEGORICAL_RECORDS, ExperimentData
from soilsignal_ml.progressive.folds import (
    CONTRASTS,
    headline,
    inner_folds,
    make_folds,
    schemes,
)
from soilsignal_ml.progressive.intervals import cqr_band, fit_cqr, residual_offsets
from soilsignal_ml.progressive.metrics import (
    accuracy,
    interval_stats,
    paired_bootstrap_delta,
    per_group_mae,
    scouting,
    spearman,
    spearman_within,
)
from soilsignal_ml.progressive.models import registry
from soilsignal_ml.progressive.spatial import residual_autocorrelation
from soilsignal_ml.progressive.stages import build_stages, stage_frame, stage_timing

CONFIG = ML_ROOT / "configs" / "progressive.yaml"


@dataclass
class RunConfig:
    stage_mode: str = "tp"
    stage_cutoffs: list | None = None
    models: list[str] = field(
        default_factory=lambda: [
            "mean",
            "ridge",
            "random_forest",
            "hist_gradient_boosting",
            "catboost",
        ]
    )
    primary_model: str = "catboost"
    secondary_models: list[str] = field(default_factory=lambda: ["mean"])
    schemes: list[str] | str = "auto"
    test_year: int | None = None
    min_test_plots: int = 100
    min_test_imaged: float = 0.5
    level: float = 0.90
    nested_intervals: bool = True
    cqr: bool = True
    budgets: list[float] = field(default_factory=lambda: [0.10, 0.20, 0.25])
    poor_quantile: float = 0.25
    scouting_unit: str = "site_year"
    naive_ranking_column: str | None = "ndvi_latest"
    n_boot: int = 2000
    seed: int = 42
    harvest_mmdd: str = "10-15"
    params: dict = field(default_factory=dict)
    criteria: dict = field(default_factory=dict)
    spatial_neighbours: int = 8

    @classmethod
    def load(cls, path: Path = CONFIG, **overrides) -> "RunConfig":
        values = yaml.safe_load(path.read_text()) if path and Path(path).exists() else {}
        values = {k: v for k, v in (values or {}).items() if k in cls.__dataclass_fields__}
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)


@dataclass
class Prediction:
    scheme: str
    stage: str
    model: str
    pred: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    fold: np.ndarray
    seconds: float
    inner_scheme: str


def _feature_lists(data: ExperimentData, imagery: list[str]) -> tuple[list[str], list[str]]:
    records = data.record_columns
    categorical = [c for c in records if c in CATEGORICAL_RECORDS]
    numeric = [c for c in records if c not in categorical] + imagery
    return numeric, categorical


def cross_predict(spec, params, X, y, frame, folds, scheme, cfg, numeric, categorical):
    n = len(y)
    pred, lower, upper = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    fold_of = np.empty(n, dtype=object)
    with_intervals = scheme.name not in CONTRASTS
    inner_used = ""
    started = time.perf_counter()
    for fold in folds:
        Xtr, ytr = X.iloc[fold.train], y[fold.train]
        model = spec.make(params, numeric, categorical, cfg.seed).fit(Xtr, ytr)
        p = model.predict(X.iloc[fold.test])
        pred[fold.test] = p
        fold_of[fold.test] = fold.name
        if with_intervals and cfg.nested_intervals:
            inner, inner_used = inner_folds(frame.iloc[fold.train], scheme, cfg.seed)
            residuals = []
            for f in inner:
                m = spec.make(params, numeric, categorical, cfg.seed).fit(
                    Xtr.iloc[f.train], ytr[f.train]
                )
                residuals.append(ytr[f.test] - m.predict(Xtr.iloc[f.test]))
            lo, hi = residual_offsets(np.concatenate(residuals), cfg.level)
            lower[fold.test], upper[fold.test] = p + lo, p + hi
    if with_intervals and not cfg.nested_intervals:
        # Fast fallback: calibrated on the same out-of-fold residuals it is scored on.
        lo, hi = residual_offsets(y - pred, cfg.level)
        lower, upper = pred + lo, pred + hi
        inner_used = "pooled out-of-fold (in-sample coverage)"
    return pred, lower, upper, fold_of, time.perf_counter() - started, inner_used


def cross_cqr(X, y, frame, folds, scheme, cfg, numeric, categorical):
    n = len(y)
    lower, upper = np.full(n, np.nan), np.full(n, np.nan)
    for fold in folds:
        inner, _ = inner_folds(frame.iloc[fold.train], scheme, cfg.seed)
        lo_m, hi_m, corr = fit_cqr(
            X.iloc[fold.train], y[fold.train], inner, numeric, categorical, cfg.seed, cfg.level
        )
        lower[fold.test], upper[fold.test] = cqr_band(lo_m, hi_m, corr, X.iloc[fold.test])
    return lower, upper


def cross_relative(spec, params, X, y, units, folds, cfg, numeric, categorical) -> np.ndarray:
    """Out-of-fold scores from the same model family trained on yield minus its
    site-season mean. Scouting ranks plots within a site-season, where the unknown site
    mean cancels out, so this model spends its capacity on within-site differences instead
    of the between-site offsets that dominate a yield forecast's error."""
    score = np.full(len(y), np.nan)
    for fold in folds:
        tr = fold.train
        centred = y[tr] - pd.Series(y[tr]).groupby(units[tr]).transform("mean").to_numpy()
        model = spec.make(params, numeric, categorical, cfg.seed).fit(X.iloc[tr], centred)
        score[fold.test] = model.predict(X.iloc[fold.test])
    return score


def run(data: ExperimentData, cfg: RunConfig, progress=print) -> dict:
    specs = registry()
    unknown = [m for m in [*cfg.models, cfg.primary_model] if m not in specs]
    if unknown:
        raise ValueError(f"unknown or uninstalled models {unknown}; available {sorted(specs)}")
    stages = build_stages(data, cfg.stage_mode, cfg.stage_cutoffs)
    frame = data.plots.reset_index(drop=True)
    frame["_imaged"] = frame["plot_id"].isin(data.tp_features["plot_id"])
    y = frame["final_yield"].to_numpy(float)
    units = frame[cfg.scouting_unit].astype(str).to_numpy()

    available = schemes(
        frame,
        test_year=cfg.test_year,
        min_test_plots=cfg.min_test_plots,
        min_test_imaged=cfg.min_test_imaged,
    )
    head = headline(available)
    wanted = [s.name for s in available if s.usable] if cfg.schemes == "auto" else cfg.schemes
    run_schemes = [s for s in available if s.usable and s.name in wanted]
    if head.name not in [s.name for s in run_schemes]:
        run_schemes.insert(0, head)
    notes = list(data.notes) + [
        f"{s.name} validation not run: {s.reason}" for s in available if not s.usable
    ]
    progress(
        f"{data.name}: {len(frame)} plots, {frame['site_id'].nunique()} sites, "
        f"{frame['year'].nunique()} season(s); headline validation: {head.description}"
    )

    predictions: dict[tuple[str, str, str], Prediction] = {}
    cqr_bands: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    relative: dict[tuple[str, str], np.ndarray] = {}
    features_used: dict[str, list[str]] = {}
    for scheme in run_schemes:
        folds = make_folds(frame, scheme, cfg.seed)
        if scheme.name == head.name:
            models = cfg.models
        elif scheme.name in CONTRASTS:
            models = [cfg.primary_model]
        else:
            models = list(dict.fromkeys([*cfg.secondary_models, cfg.primary_model]))
        progress(f"\n== {scheme.description}: {len(folds)} folds, models {models}")
        for stage in stages:
            sf, imagery = stage_frame(data, stage)
            numeric, categorical = _feature_lists(data, imagery)
            features_used[stage.key] = numeric + categorical
            X = prepare(sf, numeric, categorical)
            for name in models:
                if name == "mean" and stage.uses_imagery:
                    continue  # Baseline A ignores features: once, at the records stage
                spec = specs[name]
                params = {**spec.defaults, **cfg.params.get(name, {})}
                pred, lo, hi, fold_of, secs, inner = cross_predict(
                    spec, params, X, y, frame, folds, scheme, cfg, numeric, categorical
                )
                predictions[(scheme.name, stage.key, name)] = Prediction(
                    scheme.name, stage.key, name, pred, lo, hi, fold_of, secs, inner
                )
                mae = np.nanmean(np.abs(y - pred))
                progress(
                    f"  {stage.short:8s} {name:24s} {len(numeric) + len(categorical):3d} feat"
                    f"  MAE {mae:6.1f}  ({secs:.1f}s)"
                )
            if scheme.name == head.name:
                spec = specs[cfg.primary_model]
                params = {**spec.defaults, **cfg.params.get(cfg.primary_model, {})}
                relative[(scheme.name, stage.key)] = cross_relative(
                    spec, params, X, y, units, folds, cfg, numeric, categorical
                )
                if cfg.cqr:
                    cqr_bands[(scheme.name, stage.key)] = cross_cqr(
                        X, y, frame, folds, scheme, cfg, numeric, categorical
                    )

    for scheme in run_schemes:
        used = {p.inner_scheme for p in predictions.values() if p.scheme == scheme.name}
        if scheme.name == "temporal" and used and used != {"year"}:
            notes.append(
                "temporal intervals are calibrated with "
                + ", ".join(sorted(used))
                + " folds inside the training season(s): no earlier season-to-season shift "
                "exists to calibrate on, so expect wide intervals and over-coverage"
            )
    timing = {s.key: stage_timing(data, s, cfg.harvest_mmdd) for s in stages}
    rows = _result_rows(frame, y, units, stages, predictions, cqr_bands, run_schemes, cfg)
    for row in rows:
        row.update({f"timing_{k}": v for k, v in timing[row["stage"]].items() if _flat(v)})
    scout = _scouting_rows(data, y, units, stages, predictions, cqr_bands, relative, head, cfg)
    criteria = crit.evaluate(rows, scout, timing, stages, head.name, cfg)
    spatial = _spatial(frame, y, stages, predictions, head, cfg)
    return {
        "dataset": data.name,
        "synthetic": data.synthetic,
        "provenance": data.provenance,
        "config": asdict(cfg),
        "headline_validation": {"name": head.name, "description": head.description},
        "validation_schemes": [
            {"name": s.name, "usable": s.usable, "reason": s.reason, "ran": s in run_schemes}
            for s in available
        ],
        "notes": notes,
        "n_plots": int(len(frame)),
        "sites": sorted(frame["site_id"].unique().tolist()),
        "years": sorted(int(v) for v in frame["year"].unique()),
        "stages": [
            {"key": s.key, "label": s.label, "order": s.order, "uses_imagery": s.uses_imagery}
            for s in stages
        ],
        "features": features_used,
        "timing": timing,
        "results": rows,
        "scouting": scout,
        "criteria": criteria,
        "spatial": spatial,
        "predictions": _prediction_table(frame, predictions, cqr_bands, head, cfg),
    }


def _flat(value) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _result_rows(frame, y, units, stages, predictions, cqr_bands, run_schemes, cfg) -> list[dict]:
    stage_by_key = {s.key: s for s in stages}
    rows = []
    for (scheme, stage_key, model), p in predictions.items():
        ok = np.isfinite(p.pred)
        stage = stage_by_key[stage_key]
        acc = accuracy(y[ok], p.pred[ok])
        by_group = per_group_mae(y[ok], p.pred[ok], units[ok])
        by_fold = per_group_mae(y[ok], p.pred[ok], p.fold[ok])
        iv = interval_stats(y, p.lower, p.upper)
        iv_groups = [
            interval_stats(y[units == u], p.lower[units == u], p.upper[units == u])["coverage"]
            for u in np.unique(units)
        ]
        row = {
            "validation": scheme,
            "stage": stage_key,
            "stage_order": stage.order,
            "stage_label": "Baseline A: training mean" if model == "mean" else stage.label,
            "uses_imagery": stage.uses_imagery,
            "model": model,
            **acc,
            "spearman_within": spearman_within(y[ok], p.pred[ok], units[ok]),
            "spearman_pooled": spearman(y[ok], p.pred[ok]),
            "fold_mae_mean": float(np.mean(list(by_fold.values()))),
            "fold_mae_sd": float(np.std(list(by_fold.values()))),
            "n_folds": len(by_fold),
            "coverage": iv["coverage"],
            "interval_width": iv["width"],
            "coverage_min_group": float(np.nanmin(iv_groups))
            if np.isfinite(iv_groups).any()
            else float("nan"),
            "interval_calibration": p.inner_scheme,
            "seconds": round(p.seconds, 2),
            "group_mae": by_group,
        }
        band = cqr_bands.get((scheme, stage_key))
        if band is not None and model == cfg.primary_model:
            cq = interval_stats(y, *band)
            row["cqr_coverage"], row["cqr_width"] = cq["coverage"], cq["width"]
        rows.append(row)

    # Imagery value: every imagery stage against records only, same scheme.
    index = {(r["validation"], r["stage"], r["model"]): r for r in rows}
    for r in rows:
        base = index.get((r["validation"], "records", r["model"]))
        records_rows = [
            x
            for x in rows
            if x["validation"] == r["validation"]
            and x["stage"] == "records"
            and x["model"] != "mean"
        ]
        best_records = min(records_rows, key=lambda x: x["mae"]) if records_rows else None
        mean_row = index.get((r["validation"], "records", "mean"))
        r["delta_mae_vs_mean"] = mean_row["mae"] - r["mae"] if mean_row else float("nan")
        if base is None or r["model"] == "mean":
            continue
        r["delta_mae_vs_records"] = base["mae"] - r["mae"]
        r["pct_mae_reduction_vs_records"] = 100 * (base["mae"] - r["mae"]) / base["mae"]
        if best_records is not None:
            r["delta_mae_vs_best_records"] = best_records["mae"] - r["mae"]
            r["best_records_model"] = best_records["model"]
        if not r["uses_imagery"]:
            continue
        pb = predictions[(r["validation"], "records", r["model"])]
        pi = predictions[(r["validation"], r["stage"], r["model"])]
        ok = np.isfinite(pb.pred) & np.isfinite(pi.pred)
        lo, hi = paired_bootstrap_delta(
            np.abs(y[ok] - pb.pred[ok]),
            np.abs(y[ok] - pi.pred[ok]),
            units[ok],
            n_boot=cfg.n_boot,
            seed=cfg.seed,
        )
        r["delta_mae_ci_low"], r["delta_mae_ci_high"] = lo, hi
        wins = [
            r["group_mae"][g] < base["group_mae"][g]
            for g in r["group_mae"]
            if g in base["group_mae"]
        ]
        r["group_wins"] = int(sum(wins))
        r["n_groups"] = len(wins)
    return rows


def _scouting_rows(data, y, units, stages, predictions, cqr_bands, relative, head, cfg):
    """Rankings compared at every stage on the headline scheme (lowest score scouted first):
    forecast           the primary model's yield forecast
    lower_bound        the CQR 90% lower bound (downside risk; per-plot width)
    relative_forecast  the same model family trained on yield minus its site-season mean
    records_only       the criterion's ranking method with records only (flat reference)
    naive_imagery      the latest vegetation index, no model (what a scout could do alone)"""
    method = {**crit.DEFAULTS, **(cfg.criteria or {})}["scouting_ranker"]

    def scores(stage_key: str) -> dict[str, np.ndarray]:
        out = {}
        p = predictions.get((head.name, stage_key, cfg.primary_model))
        if p is not None:
            out["forecast"] = p.pred
        band = cqr_bands.get((head.name, stage_key))
        if band is not None:
            out["lower_bound"] = band[0]
        if (head.name, stage_key) in relative:
            out["relative_forecast"] = relative[(head.name, stage_key)]
        return out

    reference = scores("records").get(method)
    # Only plots the headline scheme held out (a later-season test leaves earlier seasons
    # without an out-of-fold forecast).
    base = predictions.get((head.name, "records", cfg.primary_model))
    held_out = np.isfinite(base.pred) if base is not None else np.ones(len(y), bool)
    rows = []
    for stage in stages:
        rankers = scores(stage.key)
        if reference is not None:
            rankers["records_only"] = reference
        if stage.uses_imagery and cfg.naive_ranking_column:
            sf, _ = stage_frame(data, stage)
            if cfg.naive_ranking_column in sf:
                rankers["naive_imagery"] = sf[cfg.naive_ranking_column].to_numpy(float)
        for ranker, score in rankers.items():
            m = held_out
            for r in scouting(y[m], score[m], units[m], cfg.budgets, cfg.poor_quantile, cfg.seed):
                rows.append(
                    {
                        "validation": head.name,
                        "stage": stage.key,
                        "stage_order": stage.order,
                        "stage_label": stage.label,
                        "ranker": ranker,
                        "method": method if ranker == "records_only" else ranker,
                        **r,
                    }
                )
    return rows


def _spatial(frame, y, stages, predictions, head, cfg) -> list[dict]:
    if not {"latitude", "longitude"} <= set(frame.columns) or frame["latitude"].isna().all():
        return []
    out = []
    for stage in stages:
        p = predictions.get((head.name, stage.key, cfg.primary_model))
        if p is None:
            continue
        for r in residual_autocorrelation(
            frame, y - p.pred, k=cfg.spatial_neighbours, seed=cfg.seed
        ):
            out.append({"stage": stage.key, "stage_label": stage.label, **r})
    return out


def _prediction_table(frame, predictions, cqr_bands, head, cfg) -> pd.DataFrame:
    cols = [
        c for c in ("plot_id", "site_id", "year", "field_id", "latitude", "longitude") if c in frame
    ]
    parts = []
    for (scheme, stage, model), p in predictions.items():
        if scheme != head.name or model != cfg.primary_model:
            continue
        part = frame[cols].copy()
        part["stage"] = stage
        part["actual"] = frame["final_yield"].to_numpy()
        part["predicted"] = p.pred
        part["lower"], part["upper"] = p.lower, p.upper
        band = cqr_bands.get((scheme, stage))
        part["cqr_lower"], part["cqr_upper"] = band if band is not None else (np.nan, np.nan)
        part["residual"] = part["actual"] - part["predicted"]
        part["fold"] = p.fold
        parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
