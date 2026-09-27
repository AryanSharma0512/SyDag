"""
Leave-one-season-out backtest of the historical weather outlook.

For every site, every season that passed QC, every as-of date and every horizon:
pretend that season is the current one, build the outlook from the OTHER seasons only
(the engine always leaves the outlook's own season out, and reads the current season
only through the as-of date), then compare it with what that season actually did.

Scored against the same outlook with equal weights (climatology), so any skill is the
analog weighting's alone:
    RPS / RPSS   ranked probability score over adverse < typical < favorable
    Brier        multi-category Brier score
    accuracy     most likely category was the observed one (ties share credit)
    reliability  forecast probability vs observed frequency, pooled
    CRPS / CRPSS continuous horizon outcomes (rain, GDD, heat, water deficit)
"""

import math
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.weather_outlook.analogs import tercile
from app.weather_outlook.features import from_record, horizon_outcomes
from app.weather_outlook.history import WeatherLibrary, month_day
from app.weather_outlook.scenarios import OutlookError, WeatherOutlook
from app.weather_outlook.stress import score_trajectory
from soilsignal_ml.weather_outlook.history import PUBLISH_DIR, REPORT_DIR, load_config

CRPS_OUTCOMES = ("precip_mm", "gdd", "kdd_29c", "heat_days", "water_deficit_mm")
RELIABILITY_BINS = np.linspace(0, 1, 6)


def rps(probs: np.ndarray, observed: int) -> float:
    cum_f = np.cumsum(probs)[:-1]
    cum_o = np.cumsum(np.eye(3)[observed])[:-1]
    return float(np.sum((cum_f - cum_o) ** 2) / 2)


def brier(probs: np.ndarray, observed: int) -> float:
    return float(np.sum((probs - np.eye(3)[observed]) ** 2))


def hit(probs: np.ndarray, observed: int) -> float:
    best = np.flatnonzero(np.isclose(probs, probs.max()))
    return 1.0 / len(best) if observed in best else 0.0


def crps(values: np.ndarray, weights: np.ndarray, observed: float) -> float:
    """CRPS of a weighted ensemble: E|X - y| - 0.5 E|X - X'|."""
    keep = ~np.isnan(values)
    x, w = values[keep], weights[keep] / weights[keep].sum()
    return float(
        np.sum(w * np.abs(x - observed))
        - 0.5 * np.sum(np.outer(w, w) * np.abs(x[:, None] - x[None, :]))
    )


def run_case(engine: WeatherOutlook, site: str, year: int, md: str, horizon) -> dict | None:
    as_of = month_day(year, md)
    try:
        outlook = engine.generate(
            site, as_of, horizon, bootstrap=False, stages=False, weighting="analog"
        )
    except OutlookError:
        return None
    info, record = outlook.site, engine.library.record(site)
    stage_end = max(outlook.end, month_day(year, engine.settings.season_end))
    actual = outlook.observed.concat(from_record(record, as_of + timedelta(1), stage_end))
    realized = score_trajectory(
        actual, as_of, outlook.end, outlook.planting, info.root_zone_water_mm, info.irrigated
    )
    outcomes = horizon_outcomes(actual, as_of, outlook.end, outlook.planting)
    cat = outlook.categories
    row = {
        "site": info.name,
        "season": year,
        "as_of": md,
        "horizon": str(horizon),
        "n_seasons": outlook.n_seasons,
        "ess": outlook.weights.ess,
        "bandwidth": outlook.weights.bandwidth,
        "method": outlook.weights.method,
        "categories_available": cat.available,
    }
    if cat.available:
        observed = tercile(realized.score, cat.scores)
        clim = cat.climatology
        row |= {
            "observed": observed,
            "p_adverse": cat.probabilities[0],
            "p_typical": cat.probabilities[1],
            "p_favorable": cat.probabilities[2],
            "c_adverse": clim[0],
            "c_typical": clim[1],
            "c_favorable": clim[2],
            "rps": rps(cat.probabilities, observed),
            "rps_clim": rps(clim, observed),
            "brier": brier(cat.probabilities, observed),
            "brier_clim": brier(clim, observed),
            "hit": hit(cat.probabilities, observed),
            "hit_clim": hit(clim, observed),
        }
    w = outlook.weight_array()
    uniform = np.full(len(w), 1 / len(w))
    for name in CRPS_OUTCOMES:
        values = outlook.outcome_array(name)
        row[f"crps_{name}"] = crps(values, w, outcomes[name])
        row[f"crps_clim_{name}"] = crps(values, uniform, outcomes[name])
    return row


def run_cases(library: WeatherLibrary, sites: list[str] | None, cfg: dict) -> pd.DataFrame:
    engine = WeatherOutlook(library)
    rows = []
    for site, info in library.sites.items():
        if sites and site not in sites:
            continue
        for year in info.seasons:
            for md in cfg["backtest"]["as_of"]:
                for h in cfg["backtest"]["horizons"]:
                    horizon = "season" if h == "season" else int(h)
                    row = run_case(engine, site, year, md, horizon)
                    if row:
                        rows.append(row)
        print(f"  {site}: {sum(r['site'] == site for r in rows)} cases")
    return pd.DataFrame(rows)


def _skill(frame: pd.DataFrame, score: str) -> float:
    ref = frame[f"{score}_clim"].mean()
    return float(1 - frame[score].mean() / ref) if ref > 0 else math.nan


def _season_ci(
    frame: pd.DataFrame, score: str, samples: int = 1000, seed: int = 0
) -> tuple[float, float]:
    """Bootstrap interval of the skill score, resampling whole seasons (cases within a
    season share its weather, so they are not independent)."""
    rng = np.random.default_rng(seed)
    keys = frame[["site", "season"]].drop_duplicates().to_numpy()
    groups = {tuple(k): g for k, g in frame.groupby(["site", "season"])}
    stats = []
    for _ in range(samples):
        pick = keys[rng.integers(0, len(keys), len(keys))]
        stats.append(_skill(pd.concat([groups[tuple(k)] for k in pick]), score))
    return tuple(np.nanpercentile(stats, [5, 95]))


def summarize(cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cat = cases[cases["categories_available"]]
    for keys, g in cat.groupby(["site", "as_of", "horizon"]):
        rows.append(dict(zip(["site", "as_of", "horizon"], keys, strict=True)) | _metrics(g))
    for keys, g in cat.groupby(["as_of", "horizon"]):
        rows.append({"site": "ALL", "as_of": keys[0], "horizon": keys[1]} | _metrics(g))
    return pd.DataFrame(rows)


def _metrics(g: pd.DataFrame) -> dict:
    out = {
        "cases": len(g),
        "seasons": g["season"].nunique(),
        "mean_ess": round(g["ess"].mean(), 1),
        "rps": round(g["rps"].mean(), 4),
        "rps_clim": round(g["rps_clim"].mean(), 4),
        "rpss": round(_skill(g, "rps"), 3),
        "brier": round(g["brier"].mean(), 4),
        "brier_clim": round(g["brier_clim"].mean(), 4),
        "bss": round(_skill(g, "brier"), 3),
        "accuracy": round(g["hit"].mean(), 3),
        "accuracy_clim": round(g["hit_clim"].mean(), 3),
    }
    for name in CRPS_OUTCOMES:
        out[f"crpss_{name}"] = round(
            _skill(g.rename(columns={f"crps_{name}": "c", f"crps_clim_{name}": "c_clim"}), "c"), 3
        )
    return out


def reliability(cases: pd.DataFrame, prefix: str) -> pd.DataFrame:
    cat = cases[cases["categories_available"]]
    rows = []
    for k, name in enumerate(("adverse", "typical", "favorable")):
        rows.append(
            pd.DataFrame(
                {
                    "category": name,
                    "p": cat[f"{prefix}_{name}"],
                    "o": (cat["observed"] == k).astype(float),
                }
            )
        )
    pooled = pd.concat(rows)
    pooled["bin"] = pd.cut(pooled["p"], RELIABILITY_BINS, include_lowest=True)
    return (
        pooled.groupby("bin", observed=True)
        .agg(forecast=("p", "mean"), observed=("o", "mean"), n=("o", "size"))
        .reset_index()
    )


def run_backtest(library_name: str, sites: list[str] | None, report_only: bool = False) -> Path:
    cfg = load_config()
    library = WeatherLibrary(PUBLISH_DIR / library_name)
    out = REPORT_DIR / library_name
    (out / "figures").mkdir(parents=True, exist_ok=True)
    if report_only:
        cases = pd.read_csv(out / "cases.csv", dtype={"as_of": str, "horizon": str})
    else:
        print(f"backtest {library_name}")
        cases = run_cases(library, sites, cfg)
        cases.to_csv(out / "cases.csv", index=False)
    summary = summarize(cases)
    summary.to_csv(out / "summary.csv", index=False)
    from soilsignal_ml.weather_outlook.report import write_backtest_report

    write_backtest_report(library, cases, summary, out, cfg)
    print(f"wrote {out}")
    return out


def overall(cases: pd.DataFrame) -> dict:
    cat = cases[cases["categories_available"]]
    out = {"cases": len(cases), "categorical_cases": len(cat)}
    if len(cat):
        out |= _metrics(cat)
        out["rpss_ci"] = _season_ci(cat, "rps")
    out["site_seasons"] = int(cases[["site", "season"]].drop_duplicates().shape[0])
    for name in CRPS_OUTCOMES:
        g = cases.rename(columns={f"crps_{name}": "c", f"crps_clim_{name}": "c_clim"})
        out[f"crpss_{name}_ci"] = _season_ci(g, "c")
    return out
