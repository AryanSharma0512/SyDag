"""
Progressive feature tables: records_only, TP1, ..., TPn (long form, one row per plot x cutoff).

A TPk row describes a plot as it could have been known on its site's TPk acquisition date
(`as_of_date`). Rows are computed from a table that has already been cut down to what
existed then: satellite images with time_point <= k and date <= as_of_date. The plot's own
history, the site's same-date means and every normalisation are computed after that cut,
so deleting or altering TP(k+1)..TPn imagery cannot change a TPk row.
tests/test_imagery_leakage.py deletes and alters later imagery to check exactly that.

records_only rows hold what was known at planting (design and management), no imagery.
"""

import numpy as np
import pandas as pd

from soilsignal_ml.imagery.discover import PLANTING_KNOWN
from soilsignal_ml.imagery.satellite import CORE_INDICES, DEFAULT_BANDS, INDICES, STATS

TEMPORAL_INDICES = ("ndvi", "ndre", "gndvi", "evi")
# Indices whose average gap to the site mean over the season so far is also kept.
RELATIVE_AVG_INDICES = ("ndvi", "ndre")
TEMPORAL_FEATURES = (
    "current",
    "previous",
    "change_from_previous",
    "change_per_10d",
    "mean_to_date",
    "min_to_date",
    "max_to_date",
    "trend",
    "area_to_date",
    "vs_site_same_date_mean",
)
ID_COLUMNS = ["plot_id", "site_id", "cutoff", "cutoff_tp", "as_of_date"]
TIMING_COLUMNS = [
    "planting_date",
    "planting_day_of_year",
    "days_after_planting",
    "satellite_images_available",
    "latest_image_tp",
    "latest_image_date",
    "latest_image_dap",
    "days_since_latest_image",
    "days_since_previous_satellite_image",
]
QA_COLUMNS = [
    "cur_valid_fraction",
    "cur_n_valid_pixels",
    "cur_image_flags",
    "cur_image_flag_count",
    "images_flagged_to_date",
]
TARGET = "final_yield"
RECORDS_ONLY = "records_only"

# Per-image flags that depend on that image alone (safe to carry into features).
LOW_VALID_PIXELS = 10
LOW_VALID_FRACTION_OF_PLOT = 0.9
# Fewer valid pixels than this share of the median plot in the same acquisition: plots in a
# trial share a size, so a much smaller footprint means clipping or misregistration.
LOW_VS_SITE_SAME_DATE = 0.5
SATURATED_SHARE = 0.01
OUT_OF_RANGE_SHARE = 0.01


class LeakageError(AssertionError):
    """An image from after the cutoff reached a cutoff's feature computation."""


def current_stat_columns() -> list[str]:
    """Current-image distribution statistics, prefixed cur_. The mean of each temporal
    index is left out because it is exactly `<index>_current`."""
    cols = [f"cur_{b}_{s}" for b in DEFAULT_BANDS for s in STATS]
    cols += [
        f"cur_{i}_{s}"
        for i in INDICES
        for s in STATS
        if not (i in TEMPORAL_INDICES and s == "mean")
    ]
    cols += ["cur_ndvi_cover_frac", *[f"cur_{i}_core_mean" for i in CORE_INDICES]]
    return cols


def temporal_columns() -> list[str]:
    cols = [f"{i}_{f}" for i in TEMPORAL_INDICES for f in TEMPORAL_FEATURES]
    cols += [f"{i}_vs_site_mean_avg_to_date" for i in RELATIVE_AVG_INDICES]
    return cols


def schema(planting_known: list[str]) -> list[str]:
    return [
        *ID_COLUMNS,
        *planting_known,
        *TIMING_COLUMNS,
        *temporal_columns(),
        *current_stat_columns(),
        *QA_COLUMNS,
        TARGET,
    ]


# ---- which images count ----------------------------------------------------------------


def image_flags(img: pd.DataFrame) -> pd.Series:
    """Flags computed from each image and, at most, the other images of the same
    acquisition (same site and time point). Never from other dates."""
    n_valid = img["n_valid"].fillna(0)
    in_plot = img["n_in_plot"].where(img["n_in_plot"] > 0)
    same_date = n_valid.groupby([img["site_id"], img["time_point"]]).transform("median")
    checks = {
        "low_valid_pixels": (n_valid < LOW_VALID_PIXELS)
        | (img["valid_fraction_of_plot"] < LOW_VALID_FRACTION_OF_PLOT),
        "small_footprint": n_valid < LOW_VS_SITE_SAME_DATE * same_date,
        "saturated": img["n_saturated"] / in_plot > SATURATED_SHARE,
        "index_out_of_range": img[[f"{i}_n_out_of_range" for i in INDICES]].sum(axis=1)
        / n_valid.where(n_valid > 0)
        > OUT_OF_RANGE_SHARE,
        "negative_ndvi": img["ndvi_mean"] < 0,
    }
    flags = pd.DataFrame({k: v.fillna(False).astype(bool) for k, v in checks.items()})
    return flags.apply(lambda r: ";".join(k for k, v in r.items() if v), axis=1)


def usable_images(images: pd.DataFrame, acquisitions: pd.DataFrame | None) -> pd.DataFrame:
    """Satellite images that decoded, have a known band layout and at least one valid
    pixel, with their acquisition date attached. One image per plot and time point: when
    two files claim the same plot and time point, the one with more valid pixels wins."""
    img = images[images["modality"] == "satellite"].copy()
    ok = img["plot_id"].notna() & img["time_point"].notna()
    if "error" in img:
        ok &= img["error"].isna()
    ok &= img.get("band_order_source", pd.Series("unknown", index=img.index)) != "unknown"
    ok &= img.get("n_valid", pd.Series(0, index=img.index)).fillna(0) >= 1
    img = img[ok].copy()
    img["time_point"] = img["time_point"].astype(int)
    if "date" not in img or img["date"].isna().all():
        img = img.drop(columns=["date"], errors="ignore")
        if acquisitions is not None and len(acquisitions):
            sat = acquisitions[acquisitions["modality"] == "satellite"]
            img = img.merge(
                sat[["site_id", "time_point", "date"]], on=["site_id", "time_point"], how="left"
            )
        else:
            img["date"] = pd.NaT
    img["date"] = pd.to_datetime(img["date"]).dt.normalize()
    img["image_flags"] = image_flags(img) if len(img) else pd.Series(dtype=str)
    img = img.sort_values(
        ["plot_id", "time_point", "n_valid", "path"], ascending=[True, True, False, True]
    )
    return img.drop_duplicates(["plot_id", "time_point"]).reset_index(drop=True)


def cutoff_dates(
    images: pd.DataFrame, acquisitions: pd.DataFrame | None, k: int
) -> dict[str, pd.Timestamp]:
    """as_of_date for cutoff TPk at each site that has a TPk acquisition. Taken from the
    acquisition table, else from the TPk images' own dates (NaT when neither exists)."""
    out: dict[str, pd.Timestamp] = {}
    if acquisitions is not None and len(acquisitions):
        sat = acquisitions[
            (acquisitions["modality"] == "satellite") & (acquisitions["time_point"] == k)
        ]
        out.update({r.site_id: pd.Timestamp(r.date) for r in sat.itertuples()})
    at_k = images[images["time_point"] == k]
    for site, g in at_k.groupby("site_id"):
        if site not in out:
            d = g["date"].dropna()
            out[site] = d.mode().iloc[0] if len(d) else pd.NaT
    return out


def visible_at(images: pd.DataFrame, k: int, as_of: dict[str, pd.Timestamp]) -> pd.DataFrame:
    """The images that existed at cutoff TPk, per site."""
    site_as_of = images["site_id"].map(as_of)
    keep = images["site_id"].isin(as_of) & (images["time_point"] <= k)
    keep &= images["date"].isna() | site_as_of.isna() | (images["date"] <= site_as_of)
    return images[keep]


def assert_point_in_time(visible: pd.DataFrame, k: int, as_of: dict[str, pd.Timestamp]) -> None:
    late = visible[visible["time_point"] > k]
    site_as_of = visible["site_id"].map(as_of)
    late = pd.concat([late, visible[site_as_of.notna() & (visible["date"] > site_as_of)]])
    if len(late):
        sample = ", ".join(late["path"].astype(str).head(3))
        raise LeakageError(
            f"TP{k}: {len(late)} image(s) after the cutoff reached features: {sample}"
        )


# ---- rows ------------------------------------------------------------------------------


def _days(a, b) -> float:
    if pd.isna(a) or pd.isna(b):
        return np.nan
    return float((pd.Timestamp(a) - pd.Timestamp(b)).days)


def _temporal(
    values: np.ndarray, x: np.ndarray | None, site_mean: np.ndarray, index: str
) -> dict[str, float]:
    """Features of one index's per-image means over the images seen so far."""
    finite = np.isfinite(values)
    out = {f"{index}_{f}": np.nan for f in TEMPORAL_FEATURES}
    if not finite.any():
        return out
    v = values[finite]
    xs = x[finite] if x is not None else None
    out[f"{index}_current"] = float(v[-1])
    out[f"{index}_mean_to_date"] = float(v.mean())
    out[f"{index}_min_to_date"] = float(v.min())
    out[f"{index}_max_to_date"] = float(v.max())
    ref = site_mean[finite][-1]
    out[f"{index}_vs_site_same_date_mean"] = float(v[-1] - ref) if np.isfinite(ref) else np.nan
    if len(v) >= 2:
        out[f"{index}_previous"] = float(v[-2])
        out[f"{index}_change_from_previous"] = float(v[-1] - v[-2])
        if xs is not None and np.isfinite(xs).all():
            gap = xs[-1] - xs[-2]
            if gap > 0:
                out[f"{index}_change_per_10d"] = float((v[-1] - v[-2]) / gap * 10)
            if np.ptp(xs) > 0:
                out[f"{index}_trend"] = float(np.polyfit(xs, v, 1)[0] * 10)
                out[f"{index}_area_to_date"] = float(np.trapezoid(v, xs))
    if index in RELATIVE_AVG_INDICES:
        gaps = v - site_mean[finite]
        gaps = gaps[np.isfinite(gaps)]
        out[f"{index}_vs_site_mean_avg_to_date"] = float(gaps.mean()) if gaps.size else np.nan
    return out


def _plot_row(
    hist: pd.DataFrame, as_of: pd.Timestamp, planting: pd.Timestamp, site_means: pd.DataFrame
) -> dict:
    hist = hist.sort_values(["time_point", "date"])
    n = len(hist)
    row: dict = {"satellite_images_available": n}
    if n == 0:
        return row
    cur = hist.iloc[-1]
    dates = hist["date"]
    row["latest_image_tp"] = int(cur["time_point"])
    row["latest_image_date"] = cur["date"]
    row["latest_image_dap"] = _days(cur["date"], planting)
    row["days_since_latest_image"] = _days(as_of, cur["date"])
    if n >= 2:
        row["days_since_previous_satellite_image"] = _days(cur["date"], hist.iloc[-2]["date"])
    x = None
    if dates.notna().all():
        x = ((dates - dates.iloc[0]).dt.days).to_numpy(dtype=float)
    ref = site_means.reindex(list(zip(hist["site_id"], hist["time_point"], strict=True)))
    for index in TEMPORAL_INDICES:
        row.update(
            _temporal(
                hist[f"{index}_mean"].to_numpy(dtype=float),
                x,
                ref[f"{index}_mean"].to_numpy(dtype=float),
                index,
            )
        )
    for col in current_stat_columns():
        row[col] = cur.get(col[len("cur_") :], np.nan)
    row["cur_valid_fraction"] = cur["valid_fraction"]
    row["cur_n_valid_pixels"] = cur["n_valid"]
    row["cur_image_flags"] = cur["image_flags"]
    row["cur_image_flag_count"] = len([f for f in str(cur["image_flags"]).split(";") if f])
    row["images_flagged_to_date"] = int((hist["image_flags"] != "").sum())
    return row


def _plot_info(plots: pd.DataFrame | None) -> tuple[pd.DataFrame, list[str]]:
    if plots is None or not len(plots):
        empty = pd.DataFrame(columns=["plot_id", "site_id", "planting_date", TARGET])
        return empty.set_index("plot_id", drop=False), []
    known = [c for c in PLANTING_KNOWN if c in plots]
    info = plots.drop_duplicates("plot_id").copy()
    info["planting_date"] = pd.to_datetime(info.get("planting_date"), errors="coerce")
    return info.set_index("plot_id", drop=False), known


def plot_population(images: pd.DataFrame) -> pd.DataFrame:
    """The plots every cutoff describes: those with at least one satellite image file in
    the dataset (decoded or not), with the site their files name.

    Fixing the population per dataset keeps records_only, TP1 ... TPn comparable (the same
    plots at every cutoff), and keeps ground-truth plots that were never imaged out of the
    tables. It decides which rows exist, never a feature value: a row's features still come
    only from imagery on or before its cutoff."""
    sat = images[(images["modality"] == "satellite") & images["plot_id"].notna()]
    return sat.sort_values("path").drop_duplicates("plot_id")[["plot_id", "site_id"]]


def _base_row(pid: str, site: str, p: pd.Series | None, known: list[str]) -> dict:
    planting = p["planting_date"] if p is not None else pd.NaT
    return {
        "plot_id": pid,
        "site_id": site,
        **({c: p[c] for c in known} if p is not None else {}),
        "planting_date": planting,
        TARGET: p[TARGET] if p is not None else np.nan,
    }


def records_only_rows(plots: pd.DataFrame | None, population: pd.DataFrame) -> pd.DataFrame:
    """What was known at planting, for every plot in the population."""
    info, known = _plot_info(plots)
    rows = []
    for pid, site in zip(population["plot_id"], population["site_id"], strict=True):
        p = info.loc[pid] if pid in info.index else None
        row = _base_row(pid, p["site_id"] if p is not None else site, p, known)
        row.update(
            cutoff=RECORDS_ONLY,
            cutoff_tp=0,
            as_of_date=row["planting_date"],
            days_after_planting=0.0 if pd.notna(row["planting_date"]) else np.nan,
            satellite_images_available=0,
        )
        rows.append(row)
    return pd.DataFrame(rows)


def cutoff_rows(
    visible: pd.DataFrame,
    plots: pd.DataFrame | None,
    k: int,
    as_of: dict[str, pd.Timestamp],
    population: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Rows for cutoff TPk from the images visible at TPk and nothing else. Every plot of
    the population at a site with a TPk acquisition gets a row, imaged or not."""
    assert_point_in_time(visible, k, as_of)
    info, known = _plot_info(plots)
    if population is None:
        population = visible.drop_duplicates("plot_id")[["plot_id", "site_id"]]
    means = visible.groupby(["site_id", "time_point"])[
        [f"{i}_mean" for i in TEMPORAL_INDICES]
    ].mean()
    by_plot = dict(tuple(visible.groupby("plot_id")))
    rows = []
    for pid, site in zip(population["plot_id"], population["site_id"], strict=True):
        p = info.loc[pid] if pid in info.index else None
        site = p["site_id"] if p is not None else site
        if site not in as_of:
            continue
        day = as_of[site]
        row = _base_row(pid, site, p, known)
        row.update(
            cutoff=f"TP{k}",
            cutoff_tp=k,
            as_of_date=day,
            days_after_planting=_days(day, row["planting_date"]),
        )
        hist = by_plot.get(pid, visible.iloc[0:0])
        row.update(_plot_row(hist, day, row["planting_date"], means))
        rows.append(row)
    return pd.DataFrame(rows)


def build_progressive(
    images: pd.DataFrame,
    plots: pd.DataFrame | None = None,
    acquisitions: pd.DataFrame | None = None,
    max_tp: int | None = None,
) -> pd.DataFrame:
    """The long-form progressive table: records_only, then TP1..TPmax."""
    usable = usable_images(images, acquisitions)
    if max_tp is None:
        tps = list(usable["time_point"])
        if acquisitions is not None and len(acquisitions):
            tps += list(acquisitions.loc[acquisitions["modality"] == "satellite", "time_point"])
        max_tp = int(max(tps)) if tps else 0
    _, known = _plot_info(plots)
    population = plot_population(images)
    frames = [records_only_rows(plots, population)]
    for k in range(1, max_tp + 1):
        as_of = cutoff_dates(usable, acquisitions, k)
        frames.append(cutoff_rows(visible_at(usable, k, as_of), plots, k, as_of, population))
    frames = [f for f in frames if len(f)]
    table = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    table = table.reindex(columns=schema(known))
    for col in ("as_of_date", "planting_date", "latest_image_date"):
        table[col] = pd.to_datetime(table[col])
    table["cur_image_flags"] = table["cur_image_flags"].astype("string")
    for col in ("site_id", "cutoff", "plot_id"):
        table[col] = table[col].astype("string")
    table["planting_day_of_year"] = table["planting_date"].dt.dayofyear.astype(float)
    return table.sort_values(["cutoff_tp", "site_id", "plot_id"], ignore_index=True)


def cutoff_names(table: pd.DataFrame) -> list[str]:
    return list(dict.fromkeys(table.sort_values("cutoff_tp")["cutoff"]))
