"""
Figures for the progressive experiments (static PNGs for the report and the slides).

    mae_vs_stage.png            MAE by information stage, one line per model, Baseline A
    delta_mae_vs_stage.png      MAE reduction vs records only (primary model, 95% interval)
    interval_vs_stage.png       90% interval width and coverage (two panels, one axis each)
    scouting_recall_vs_stage.png  bottom-quartile recall by ranking, one panel per budget
    validation_contrast.png     the same model under grouped vs optimistic splits

Every x-axis shows the TP label and the median days after planting, because TP labels are
not dates. Colours follow the entity (model / ranking) in a fixed validated order; marker
shapes and end labels carry identity too, and every value is in the CSVs.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#8a8984"
SURFACE, GRID = "#fcfcfb", "#e6e5e0"
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]
MARKERS = ["o", "s", "D", "^", "v", "P", "X"]
MODEL_ORDER = [
    "ridge",
    "random_forest",
    "hist_gradient_boosting",
    "catboost",
    "xgboost",
    "lightgbm",
]
MODEL_LABEL = {
    "mean": "Training mean (Baseline A)",
    "ridge": "Ridge",
    "random_forest": "Random forest",
    "hist_gradient_boosting": "HistGradientBoosting",
    "catboost": "CatBoost",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
}
RANKER_ORDER = ["forecast", "lower_bound", "relative_forecast", "records_only", "naive_imagery"]
RANKER_LABEL = {
    "forecast": "Lowest yield forecast",
    "lower_bound": "Lowest 90% lower bound (CQR)",
    "relative_forecast": "Within-site model (yield vs site mean)",
    "records_only": "Records only (criterion's ranking)",
    "naive_imagery": "Lowest latest NDVI (no model)",
}


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(1)
    ax.grid(axis="y", color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)


def _figure(ncols: int = 1, nrows: int = 1, width: float = 8.0, height: float = 4.2):
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(width, height), squeeze=False, facecolor=SURFACE, sharex=True
    )
    for ax in axes.flat:
        _style(ax)
    return fig, axes


def _stage_ticks(ax, result, with_dap: bool = True) -> list[str]:
    keys = [s["key"] for s in result["stages"]]
    labels = []
    for s in result["stages"]:
        t = result["timing"].get(s["key"], {})
        top = (
            "Rec."
            if not s["uses_imagery"] and not with_dap
            else ("Records" if not s["uses_imagery"] else s["key"].upper())
        )
        dap = t.get("dap_median")
        labels.append(f"{top}\n{dap:.0f} DAP" if with_dap and dap is not None else top)
    ax.set_xticks(range(len(keys)), labels)
    return keys


def _title(fig, title: str, subtitle: str) -> None:
    fig.text(0.01, 0.98, title, fontsize=12, fontweight="bold", color=INK, va="top")
    fig.text(0.01, 0.925, subtitle, fontsize=9, color=INK_2, va="top")


def _headline_rows(result, model=None):
    scheme = result["headline_validation"]["name"]
    rows = [r for r in result["results"] if r["validation"] == scheme]
    return [r for r in rows if model is None or r["model"] == model]


def _series(rows, keys, field):
    by = {r["stage"]: r.get(field) for r in rows}
    return np.array([np.nan if by.get(k) is None else by[k] for k in keys], dtype=float)


def _line(ax, x, y, i, label, width=2.0, end_label=True, clip=None):
    """One series. With `clip=(low, high)`, values off the scale are drawn at the edge and
    labelled with their true value, so one extreme model can't flatten the others."""
    ok = np.isfinite(y)
    if clip is not None:
        raw, y = y, np.clip(y, *clip)
        for xi, (r, c) in enumerate(zip(raw, y, strict=True)):
            if np.isfinite(r) and r != c:
                ax.annotate(
                    f"{r:.0f} (off scale)",
                    (x[xi], c),
                    xytext=(6, -10 if c == clip[1] else 6),
                    textcoords="offset points",
                    fontsize=7.5,
                    color=INK_2,
                )
    ax.plot(
        np.asarray(x)[ok],
        y[ok],
        color=SLOTS[i % len(SLOTS)],
        linewidth=width,
        solid_capstyle="round",
        solid_joinstyle="round",
        marker=MARKERS[i % len(MARKERS)],
        markersize=6.5,
        markeredgecolor=SURFACE,
        markeredgewidth=1.5,
        label=label,
        zorder=3,
    )
    if end_label and ok.any():
        last = np.nonzero(ok)[0][-1]
        ax.annotate(
            label,
            (x[last], y[last]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=INK_2,
        )


def _subtitle(result) -> str:
    tag = "SYNTHETIC FIXTURE, NOT A RESULT · " if result.get("synthetic") else ""
    return f"{tag}{result['dataset']} · {result['headline_validation']['description']}"


def mae_vs_stage(result, path: Path) -> Path:
    fig, axes = _figure(width=8.6)
    ax = axes[0, 0]
    keys = _stage_ticks(ax, result)
    x = np.arange(len(keys))
    rows = _headline_rows(result)
    mean = next((r for r in rows if r["model"] == "mean"), None)
    if mean:
        ax.axhline(mean["mae"], color=MUTED, linewidth=1, zorder=1)
        ax.annotate(
            f"Training mean (Baseline A) {mean['mae']:.0f}",
            (len(keys) - 1, mean["mae"]),
            xytext=(0, -11),
            textcoords="offset points",
            fontsize=8,
            color=INK_2,
            ha="right",
        )
    models = [m for m in MODEL_ORDER if any(r["model"] == m for r in rows)]
    maes = np.array([r["mae"] for r in rows if r["model"] in models], dtype=float)
    ceiling = max(1.5 * np.nanpercentile(maes, 75), 1.3 * (mean["mae"] if mean else 0))
    clip = (0.0, ceiling) if np.nanmax(maes) > ceiling else None
    for i, m in enumerate(models):
        y = _series([r for r in rows if r["model"] == m], keys, "mae")
        _line(ax, x, y, i, MODEL_LABEL.get(m, m), clip=clip)
    ax.set_ylabel("MAE, bu/ac (lower is better)", color=INK_2, fontsize=9)
    ax.set_xlim(-0.3, len(keys) - 0.3 + 1.2)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=8, loc="lower left", ncols=2, labelcolor=INK_2)
    _title(fig, "Forecast error as imagery accumulates", _subtitle(result))
    return _save(fig, path)


def delta_mae_vs_stage(result, path: Path) -> Path:
    primary = result["config"]["primary_model"]
    fig, axes = _figure(width=8.6)
    ax = axes[0, 0]
    keys = _stage_ticks(ax, result)
    x = np.arange(len(keys))
    ax.axhline(0, color=MUTED, linewidth=1, zorder=1)
    rows = _headline_rows(result)
    models = [m for m in MODEL_ORDER if any(r["model"] == m for r in rows)]
    deltas = np.array(
        [r.get("delta_mae_vs_records", np.nan) for r in rows if r["model"] in models], float
    )
    span = (
        2.5 * np.nanmax(np.abs(np.nanpercentile(deltas, [15, 85])))
        if np.isfinite(deltas).any()
        else 0
    )
    clip = (-span, span) if span and np.nanmax(np.abs(deltas)) > span else None
    for i, m in enumerate(models):
        mr = [r for r in rows if r["model"] == m]
        y = _series(mr, keys, "delta_mae_vs_records")
        if m == primary:
            lo, hi = _series(mr, keys, "delta_mae_ci_low"), _series(mr, keys, "delta_mae_ci_high")
            ok = np.isfinite(lo) & np.isfinite(hi)
            ax.fill_between(x[ok], lo[ok], hi[ok], color=SLOTS[i], alpha=0.12, linewidth=0)
        _line(ax, x, y, i, MODEL_LABEL.get(m, m), width=2.4 if m == primary else 1.4, clip=clip)
    ax.set_ylabel("MAE reduction vs records only, bu/ac", color=INK_2, fontsize=9)
    ax.set_xlim(-0.3, len(keys) - 0.3 + 1.2)
    ax.legend(frameon=False, fontsize=8, loc="best", labelcolor=INK_2)
    _title(
        fig,
        "What imagery adds over field records (above 0 = better)",
        _subtitle(result) + f" · band: 95% paired bootstrap, {MODEL_LABEL.get(primary, primary)}",
    )
    return _save(fig, path)


def interval_vs_stage(result, path: Path) -> Path:
    primary = result["config"]["primary_model"]
    level = result["config"]["level"]
    fig, axes = _figure(nrows=2, width=8.6, height=5.6)
    top, bottom = axes[0, 0], axes[1, 0]
    keys = _stage_ticks(bottom, result)
    x = np.arange(len(keys))
    rows = _headline_rows(result, primary)
    series = [("interval_width", "coverage", "Constant-width (nested conformal)", 0)]
    if any(r.get("cqr_width") is not None for r in rows):
        series.append(("cqr_width", "cqr_coverage", "Per-plot width (CQR)", 1))
    for width_field, cov_field, label, i in series:
        _line(top, x, _series(rows, keys, width_field), i, label, end_label=False)
        _line(bottom, x, _series(rows, keys, cov_field), i, label, end_label=False)
    bottom.axhline(level, color=MUTED, linewidth=1, zorder=1)
    bottom.annotate(
        f"nominal {level:.0%}", (0, level), xytext=(2, 4), textcoords="offset points",
        fontsize=8, color=INK_2,
    )  # fmt: skip
    top.set_ylabel("Mean 90% interval width, bu/ac", color=INK_2, fontsize=9)
    bottom.set_ylabel("Coverage on held-out groups", color=INK_2, fontsize=9)
    bottom.set_ylim(0, 1.05)
    top.set_ylim(bottom=0)
    for ax in (top, bottom):
        ax.set_xlim(-0.3, len(keys) - 0.7)
    top.legend(frameon=False, fontsize=8, loc="lower left", labelcolor=INK_2)
    _title(fig, "How wide the 90% range is, and whether it holds", _subtitle(result))
    return _save(fig, path, top=0.86)


def scouting_recall_vs_stage(result, path: Path) -> Path:
    scout = result["scouting"]
    budgets = sorted({s["budget"] for s in scout})
    if not budgets:
        return path
    fig, axes = _figure(ncols=len(budgets), width=4.0 * len(budgets), height=4.4)
    for j, budget in enumerate(budgets):
        ax = axes[0, j]
        keys = _stage_ticks(ax, result, with_dap=False)
        x = np.arange(len(keys))
        rows = [s for s in scout if abs(s["budget"] - budget) < 1e-9]
        rnd = np.nanmean([s["random_recall"] for s in rows])
        orc = np.nanmean([s["oracle_recall"] for s in rows])
        for value, text in ((rnd, "random"), (orc, "perfect ranking")):
            ax.axhline(value, color=MUTED, linewidth=1, zorder=1)
            ax.annotate(
                f"{text} {value:.0%}", (len(keys) - 1, value), xytext=(0, 3),
                textcoords="offset points", fontsize=7.5, color=INK_2, ha="right",
            )  # fmt: skip
        for i, ranker in enumerate(r for r in RANKER_ORDER if any(s["ranker"] == r for s in rows)):
            y = _series([s for s in rows if s["ranker"] == ranker], keys, "recall")
            _line(ax, x, y, i, RANKER_LABEL[ranker], end_label=False)
        ax.set_ylim(0, 1.0)
        ax.set_title(f"Scouting {budget:.0%} of plots", fontsize=10, color=INK, loc="left")
        if j == 0:
            ax.set_ylabel("Share of bottom-quartile plots found", color=INK_2, fontsize=9)
    axes[0, 0].legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK_2)
    _title(
        fig,
        "Would SoilSignal send scouts to the plots that end up worst?",
        _subtitle(result) + " · bottom quartile within each site-season",
    )
    return _save(fig, path, top=0.8)


def validation_contrast(result, path: Path) -> Path:
    primary = result["config"]["primary_model"]
    rows = [r for r in result["results"] if r["model"] == primary]
    schemes = [s["name"] for s in result["validation_schemes"] if s["ran"]]
    fig, axes = _figure(width=8.6)
    ax = axes[0, 0]
    keys = _stage_ticks(ax, result)
    x = np.arange(len(keys))
    names = {
        "temporal": "Later season",
        "site": "Unseen site",
        "year": "Unseen year",
        "site_year": "Unseen site-season",
        "field": "Unseen block (optimistic)",
        "random": "Random plots (optimistic)",
    }
    for i, scheme in enumerate(schemes):
        y = _series([r for r in rows if r["validation"] == scheme], keys, "mae")
        _line(ax, x, y, i, names.get(scheme, scheme))
    ax.set_ylabel("MAE, bu/ac", color=INK_2, fontsize=9)
    ax.set_ylim(bottom=0)
    ax.set_xlim(-0.3, len(keys) - 0.3 + 1.6)
    ax.legend(frameon=False, fontsize=8, loc="lower left", ncols=2, labelcolor=INK_2)
    _title(
        fig,
        "Random splits flatter the model; grouped splits are the honest test",
        _subtitle(result) + f" · {MODEL_LABEL.get(primary, primary)}",
    )
    return _save(fig, path)


def _save(fig, path: Path, top: float = 0.85) -> Path:
    fig.subplots_adjust(top=top, left=0.09, right=0.97, bottom=0.14, hspace=0.18, wspace=0.18)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return path


def write_all(result, directory: Path) -> list[Path]:
    return [
        mae_vs_stage(result, directory / "mae_vs_stage.png"),
        delta_mae_vs_stage(result, directory / "delta_mae_vs_stage.png"),
        interval_vs_stage(result, directory / "interval_vs_stage.png"),
        scouting_recall_vs_stage(result, directory / "scouting_recall_vs_stage.png"),
        validation_contrast(result, directory / "validation_contrast.png"),
    ]


if __name__ == "__main__":
    # Re-render the figures from a finished run without refitting anything:
    #   python -m soilsignal_ml.progressive.figures experiments/progressive/<run>
    import json
    import sys

    run_dir = Path(sys.argv[1])
    loaded = json.loads((run_dir / "progressive_results.json").read_text())
    for written in write_all(loaded, run_dir / "figures"):
        print(written)
