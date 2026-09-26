"""
What the progressive experiments accept, normalized into one ExperimentData.

Agent 1 (canonical data) hands over

    plots          one row per plot. Required: plot_id, site_id, year, planting_date,
                   final_yield (bu/ac). Records known at planting when present: genotype,
                   nitrogen_lb_ac, irrigated. Optional: field_id, latitude, longitude,
                   harvest_date. Common source spellings (location, yieldPerAcre,
                   plantingDate, poundsOfNitrogenPerAcre, ...) are renamed.
    acquisitions   one row per satellite pass: site_id, year, tp, date (DateofCollection).
                   May be omitted when Agent 2's table carries a date per (plot, tp).

Agent 2 (spectral and temporal features) hands over ONE of

    tp_features      CUMULATIVE features. Long: one row per (plot_id, tp) where the row
                     for tp = k was computed from passes 1..k only. Wide: one row per plot
                     with a TP token in each column name (ndvi_tp3, TP3_ndvi, ...); stage k
                     then sees only columns whose token is <= k.
    tp_observations  PER-PASS values: one row per (plot_id, tp) holding that pass's own
                     band / index values. Cumulative features are built here (accumulate).

Nothing in this module fits a model; it only shapes and checks inputs.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_PLOT_COLUMNS = ["plot_id", "site_id", "year", "planting_date", "final_yield"]
# Records a grower knows at (or before) planting. Baseline B uses only these.
RECORD_COLUMNS = ["genotype", "nitrogen_lb_ac", "irrigated", "planting_day_of_year"]
CATEGORICAL_RECORDS = ["genotype"]
ID_COLUMNS = ["plot_id", "site_id", "year", "field_id", "site_year"]
OPTIONAL_PLOT_COLUMNS = ["field_id", "latitude", "longitude", "harvest_date"]

ALIASES = {
    "location": "site_id",
    "site": "site_id",
    "yieldPerAcre": "final_yield",
    "yield_bu_ac": "final_yield",
    "yield": "final_yield",
    "plantingDate": "planting_date",
    "hybrid": "genotype",
    "poundsOfNitrogenPerAcre": "nitrogen_lb_ac",
    "nitrogen": "nitrogen_lb_ac",
    "lat": "latitude",
    "lon": "longitude",
    "lng": "longitude",
    "time_point": "tp",
    "timepoint": "tp",
    "TP": "tp",
    "acquisition_date": "date",
    "image_date": "date",
}
# Never a feature: the target itself, or in-season measurements with no reliable date.
FORBIDDEN_FEATURE = re.compile(
    r"(yield|harvest|anthesis|silking_date|stand_?count|grain|moisture|lodging)", re.I
)
WIDE_TP = re.compile(r"(?:^|[_\-.])tp(\d+)(?:$|[_\-.])", re.I)


class ContractError(ValueError):
    """An input does not match what the progressive experiments need."""


@dataclass
class ExperimentData:
    """Everything one experiment run needs, already normalized.

    plots         one row per labelled plot (records, ids, coordinates, yield)
    tp_features   long, cumulative: one row per (plot_id, tp), numeric feature columns
    acquisitions  site_id, year, tp, date
    """

    name: str
    plots: pd.DataFrame
    tp_features: pd.DataFrame
    acquisitions: pd.DataFrame
    synthetic: bool = False
    provenance: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def imagery_columns(self) -> list[str]:
        return [c for c in self.tp_features.columns if c not in ("plot_id", "tp")]

    @property
    def tps(self) -> list[int]:
        return sorted(int(t) for t in self.tp_features["tp"].unique())

    @property
    def record_columns(self) -> list[str]:
        return [
            c for c in RECORD_COLUMNS if c in self.plots and self.plots[c].nunique(dropna=True) > 1
        ]


# ---- normalization -------------------------------------------------------------------


def _rename(frame: pd.DataFrame) -> pd.DataFrame:
    renames = {k: v for k, v in ALIASES.items() if k in frame.columns and v not in frame.columns}
    return frame.rename(columns=renames)


def parse_tp(value) -> int:
    """'TP3', 'tp3', 3, '3' -> 3."""
    match = re.search(r"\d+", str(value))
    if not match:
        raise ContractError(f"cannot read a time point from {value!r}")
    return int(match.group())


def normalize_plots(plots: pd.DataFrame) -> pd.DataFrame:
    p = _rename(plots.copy())
    missing = [c for c in REQUIRED_PLOT_COLUMNS if c not in p]
    if missing:
        raise ContractError(f"plots table is missing {missing}; has {sorted(p.columns)[:30]}")
    p["plot_id"] = p["plot_id"].astype(str)
    p["site_id"] = p["site_id"].astype(str)
    p["year"] = p["year"].astype(int)
    p["planting_date"] = pd.to_datetime(p["planting_date"])
    if "harvest_date" in p:
        p["harvest_date"] = pd.to_datetime(p["harvest_date"])
    if p["plot_id"].duplicated().any():
        dup = p.loc[p["plot_id"].duplicated(), "plot_id"].head(5).tolist()
        raise ContractError(f"plot_id must be unique; duplicated: {dup}")
    p = p[p["final_yield"].notna()].copy()
    p["final_yield"] = p["final_yield"].astype(float)
    p["planting_day_of_year"] = p["planting_date"].dt.dayofyear.astype(float)
    if "irrigated" in p:
        p["irrigated"] = p["irrigated"].map(
            lambda v: np.nan if pd.isna(v) else float(str(v).lower() in {"1", "true", "yes", "1.0"})
        )
    if "nitrogen_lb_ac" in p:
        p["nitrogen_lb_ac"] = pd.to_numeric(p["nitrogen_lb_ac"], errors="coerce")
    if "genotype" in p:
        p["genotype"] = p["genotype"].astype("string").str.strip()
    if "field_id" not in p:
        p["field_id"] = p["site_id"]
    p["field_id"] = p["field_id"].astype(str)
    p["site_year"] = p["site_id"] + "-" + p["year"].astype(str)
    return p.reset_index(drop=True)


def normalize_acquisitions(acq: pd.DataFrame) -> pd.DataFrame:
    a = _rename(acq.copy())
    missing = [c for c in ("site_id", "year", "tp", "date") if c not in a]
    if missing:
        raise ContractError(f"acquisitions table is missing {missing}")
    a["site_id"] = a["site_id"].astype(str)
    a["year"] = a["year"].astype(int)
    a["tp"] = a["tp"].map(parse_tp)
    a["date"] = pd.to_datetime(a["date"])
    a = a[["site_id", "year", "tp", "date"]].drop_duplicates()
    clash = a.groupby(["site_id", "year", "tp"])["date"].nunique()
    if (clash > 1).any():
        raise ContractError(f"several dates for one pass: {clash[clash > 1].index.tolist()[:5]}")
    return a.sort_values(["site_id", "year", "tp"]).reset_index(drop=True)


def acquisitions_from_dates(table: pd.DataFrame, plots: pd.DataFrame) -> pd.DataFrame:
    """One date per (site, year, tp): the most common image date among that pass's plots."""
    t = table[["plot_id", "tp", "date"]].merge(plots[["plot_id", "site_id", "year"]], on="plot_id")
    t["date"] = pd.to_datetime(t["date"])
    a = t.groupby(["site_id", "year", "tp"])["date"].agg(lambda s: s.mode().iloc[0]).reset_index()
    return normalize_acquisitions(a)


def _numeric_features(frame: pd.DataFrame, drop: set[str]) -> list[str]:
    cols = []
    for c in frame.columns:
        if c in drop:
            continue
        values = pd.to_numeric(frame[c], errors="coerce")
        if values.notna().any():
            cols.append(c)
    return cols


def check_feature_names(columns: list[str], allow: set[str] = frozenset()) -> None:
    bad = [c for c in columns if FORBIDDEN_FEATURE.search(c) and c not in allow]
    if bad:
        raise ContractError(
            f"feature columns look like the target or undated in-season measurements: {bad}. "
            "Remove them, or allow them explicitly (--allow-columns) if they are legitimate."
        )


def wide_to_long(wide: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Wide per-TP columns -> long cumulative rows. Row k keeps columns with token <= k."""
    tokens = {c: int(m.group(1)) for c in wide.columns if (m := WIDE_TP.search(c))}
    if not tokens:
        raise ContractError("no `tp` column and no TP token (e.g. ndvi_tp3) in any column name")
    dropped = [c for c in wide.columns if c not in tokens and c != "plot_id"]
    rows = []
    for k in sorted(set(tokens.values())):
        part = wide[["plot_id", *tokens]].copy()
        for c, t in tokens.items():
            if t > k:
                part[c] = np.nan
        part.insert(1, "tp", k)
        rows.append(part)
    return pd.concat(rows, ignore_index=True), dropped


def normalize_tp_features(
    table: pd.DataFrame, allow: set[str] = frozenset()
) -> tuple[pd.DataFrame, pd.DataFrame | None, list[str]]:
    """(long cumulative features, per-(plot, tp) dates if present, notes)."""
    t = _rename(table.copy())
    notes: list[str] = []
    if "plot_id" not in t:
        raise ContractError("tp_features needs a plot_id column")
    t["plot_id"] = t["plot_id"].astype(str)
    dates = None
    if "tp" in t:
        t["tp"] = t["tp"].map(parse_tp)
        if "date" in t:
            dates = t[["plot_id", "tp", "date"]].copy()
        if t.duplicated(["plot_id", "tp"]).any():
            raise ContractError("tp_features has several rows for one (plot_id, tp)")
    else:
        t, dropped = wide_to_long(t)
        if dropped:
            notes.append(f"wide tp_features: columns without a TP token ignored: {dropped[:10]}")
    drop = {"plot_id", "tp", "date", *ID_COLUMNS, "final_yield", "planting_date"}
    features = _numeric_features(t, drop)
    check_feature_names(features, allow)
    out = t[["plot_id", "tp"]].copy()
    for c in features:
        out[c] = pd.to_numeric(t[c], errors="coerce").astype(float)
    return out, dates, notes


# ---- per-pass values -> cumulative features --------------------------------------------


def accumulate(
    observations: pd.DataFrame,
    plots: pd.DataFrame,
    acquisitions: pd.DataFrame,
    value_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Cumulative features from per-pass values: for each pass k, each value's latest,
    mean, max, min, change since the previous pass, trend per 10 days, and the latest
    and mean value relative to the same pass's site-year mean (neighbouring plots on the
    same image, no yields). Row k uses passes 1..k only, never a later one."""
    obs = _rename(observations.copy())
    obs["plot_id"] = obs["plot_id"].astype(str)
    obs["tp"] = obs["tp"].map(parse_tp)
    if value_columns is None:
        value_columns = _numeric_features(obs, {"plot_id", "tp", "date", "n_pixels", *ID_COLUMNS})
    check_feature_names(value_columns)
    obs = obs[["plot_id", "tp", *value_columns]].merge(
        plots[["plot_id", "site_id", "year"]], on="plot_id", how="inner"
    )
    acq = acquisitions.assign(date=pd.to_datetime(acquisitions["date"]))
    obs = obs.merge(acq, on=["site_id", "year", "tp"], how="left")
    # Trend x-axis: days since the site-year's first pass (10 x pass number without dates).
    first = obs.groupby(["site_id", "year"])["date"].transform("min")
    days = (obs["date"] - first).dt.days.astype(float)
    obs["_x"] = days.where(obs["date"].notna(), obs["tp"] * 10.0)
    site_mean = obs.groupby(["site_id", "year", "tp"])[value_columns].transform("mean")
    for c in value_columns:
        obs[f"{c}__rel"] = obs[c] - site_mean[c]
    obs = obs.sort_values(["plot_id", "tp"]).reset_index(drop=True)

    out = []
    for k in sorted(obs["tp"].unique()):
        seen = obs[obs["tp"] <= k].copy()
        g = seen.groupby("plot_id", sort=False)
        for c in value_columns:
            seen[f"{c}__prev"] = g[c].shift(1)
        last_row = seen.groupby("plot_id", sort=False).tail(1).set_index("plot_id")
        # Latest non-missing value (a cloudy pass does not blank the "latest" reading).
        last = g.last()
        feats = pd.DataFrame(index=last.index)
        feats["passes_to_date"] = g.size().astype(float)
        for c in value_columns:
            feats[f"{c}_latest"] = last[c]
            feats[f"{c}_mean"] = g[c].mean()
            feats[f"{c}_max"] = g[c].max()
            feats[f"{c}_min"] = g[c].min()
            feats[f"{c}_rel_latest"] = last[f"{c}__rel"]
            feats[f"{c}_rel_mean"] = g[f"{c}__rel"].mean()
            feats[f"{c}_change"] = last_row[c] - last_row[f"{c}__prev"]
            feats[f"{c}_trend_10d"] = _slope(seen, c) * 10
        feats = feats.reset_index()
        feats.insert(1, "tp", int(k))
        out.append(feats)
    return pd.concat(out, ignore_index=True)


def _slope(seen: pd.DataFrame, column: str) -> pd.Series:
    """Least-squares slope of column against _x per plot (NaN with fewer than 2 points)."""
    ok = seen[column].notna()
    x, y = seen["_x"].where(ok), seen[column].where(ok)
    frame = pd.DataFrame({"plot_id": seen["plot_id"], "x": x, "y": y, "xy": x * y, "xx": x * x})
    s = frame.groupby("plot_id", sort=False).agg(
        n=("y", "count"), sx=("x", "sum"), sy=("y", "sum"), sxy=("xy", "sum"), sxx=("xx", "sum")
    )
    denom = s["n"] * s["sxx"] - s["sx"] ** 2
    slope = (s["n"] * s["sxy"] - s["sx"] * s["sy"]) / denom.where(denom > 0)
    return slope.where(s["n"] >= 2)


# ---- loaders ---------------------------------------------------------------------------


def _read(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def from_frames(
    name: str,
    plots: pd.DataFrame,
    *,
    tp_features: pd.DataFrame | None = None,
    tp_observations: pd.DataFrame | None = None,
    acquisitions: pd.DataFrame | None = None,
    value_columns: list[str] | None = None,
    allow_columns: set[str] = frozenset(),
    synthetic: bool = False,
    provenance: dict | None = None,
) -> ExperimentData:
    if (tp_features is None) == (tp_observations is None):
        raise ContractError("pass exactly one of tp_features (cumulative) or tp_observations")
    p = normalize_plots(plots)
    notes: list[str] = []
    dates = None
    if tp_features is not None:
        feats, dates, more = normalize_tp_features(tp_features, allow_columns)
        notes += more
    else:
        obs = _rename(tp_observations.copy())
        if "date" in obs and acquisitions is None:
            dates = obs[["plot_id", "tp", "date"]].assign(tp=lambda d: d["tp"].map(parse_tp))
        feats = None
    if acquisitions is not None:
        acq = normalize_acquisitions(acquisitions)
    elif dates is not None:
        acq = acquisitions_from_dates(dates.assign(plot_id=dates["plot_id"].astype(str)), p)
    else:
        acq = pd.DataFrame(columns=["site_id", "year", "tp", "date"])
        notes.append(
            "no acquisition dates: stage timing (date, days after planting) is unavailable, "
            "so stages can only be compared by TP label"
        )
    if feats is None:
        feats = accumulate(tp_observations, p, acq, value_columns)
    feats = feats[feats["plot_id"].isin(p["plot_id"])].reset_index(drop=True)
    unimaged = int((~p["plot_id"].isin(feats["plot_id"])).sum())
    if unimaged:
        notes.append(f"{unimaged} labelled plots have no imagery features (records only)")
    data = ExperimentData(
        name=name,
        plots=p,
        tp_features=feats,
        acquisitions=acq,
        synthetic=synthetic,
        provenance=provenance or {},
        notes=notes,
    )
    validate(data)
    return data


def from_files(
    name: str,
    plots: str | Path,
    *,
    tp_features: str | Path | None = None,
    tp_observations: str | Path | None = None,
    acquisitions: str | Path | None = None,
    value_columns: list[str] | None = None,
    allow_columns: set[str] = frozenset(),
) -> ExperimentData:
    return from_frames(
        name,
        _read(plots),
        tp_features=_read(tp_features) if tp_features else None,
        tp_observations=_read(tp_observations) if tp_observations else None,
        acquisitions=_read(acquisitions) if acquisitions else None,
        value_columns=value_columns,
        allow_columns=allow_columns,
        provenance={
            "plots": str(plots),
            "tp_features": str(tp_features) if tp_features else None,
            "tp_observations": str(tp_observations) if tp_observations else None,
            "acquisitions": str(acquisitions) if acquisitions else None,
        },
    )


def from_canonical(name: str, value_columns: list[str] | None = None) -> ExperimentData:
    """The existing pipeline's canonical dataset (e.g. the ingested practice data)."""
    from soilsignal_ml.ingest.canonical import CanonicalDataset

    ds = CanonicalDataset.load(name)
    obs = ds.observations.copy()
    if "time_point" not in obs:
        raise ContractError(f"{name}: observations have no time_point column")
    obs = obs.rename(columns={"time_point": "tp"})
    if value_columns is None:
        value_columns = [c for c in (*ds.indices(), "nir", "red_edge") if c in obs]
    return from_frames(
        name,
        ds.plots,
        tp_observations=obs,
        value_columns=value_columns,
        provenance=ds.provenance,
    )


def validate(data: ExperimentData) -> None:
    """Fail loudly on inputs that would make the comparison meaningless."""
    problems = []
    if data.tp_features.empty:
        problems.append("no imagery features at all")
    if data.plots["site_id"].nunique() < 2 and data.plots["year"].nunique() < 2:
        data.notes.append(
            "one site and one year: only within-site grouped validation (field blocks) is "
            "possible, which is optimistic; do not headline it"
        )
    bad_tp = sorted(set(data.tp_features["tp"]) - set(range(1, 21)))
    if bad_tp:
        problems.append(f"time points outside 1..20: {bad_tp}")
    if not data.acquisitions.empty:
        joined = data.plots[["site_id", "year"]].drop_duplicates()
        have = data.acquisitions[["site_id", "year"]].drop_duplicates()
        missing = joined.merge(have, how="left", indicator=True).query("_merge == 'left_only'")
        if len(missing):
            data.notes.append(
                "site-years without acquisition dates: "
                + ", ".join(f"{r.site_id} {r.year}" for r in missing.itertuples())
            )
    if problems:
        raise ContractError("; ".join(problems))
