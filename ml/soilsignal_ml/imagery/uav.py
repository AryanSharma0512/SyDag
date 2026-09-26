"""
Lightweight UAV features from the RGB plot PNGs, joined to the progressive table by date.

UAV images are uncalibrated RGB: digital numbers depend on exposure and sun angle, so
absolute brightness is not comparable between flights. The features lean on chromatic
coordinates (r, g, b = R, G, B / (R + G + B)), which cancel overall brightness:

    ExG   = 2g - r - b                    excess green (Woebbecke et al. 1995)
    ExGR  = ExG - (1.4r - g)              excess green minus excess red (Meyer & Neto 2008)
    NGRDI = (G - R) / (G + R)             normalised green-red difference (Tucker 1979)
    VARI  = (G - R) / (G + R - B)         visible atmospherically resistant index (Gitelson 2002)
    green_frac = share of plot pixels with ExGR > 0 (canopy-cover proxy)
    texture    = mean absolute difference between neighbouring plot pixels (grey level)

Padding: pixels where R = G = B = 0, or alpha = 0 when the PNG has an alpha channel.

A UAV flight counts for a cutoff only if its acquisition date is on or before the
cutoff's as_of_date. UAV images without a known date are never joined.
"""

import io

import numpy as np
import pandas as pd
from PIL import Image

UAV_VERSION = "uav-1"
UAV_INDICES = ("exg", "exgr", "ngrdi", "vari")
UAV_STATS = ("mean", "median", "std", "p10", "p90")
# Per-image columns carried into the progressive table as uav_<name>_current.
UAV_CURRENT = (
    "r_mean",
    "g_mean",
    "b_mean",
    "exg_mean",
    "exg_std",
    "exg_p10",
    "exg_p90",
    "exgr_mean",
    "ngrdi_mean",
    "ngrdi_std",
    "vari_mean",
    "green_frac",
    "texture",
)
UAV_CHANGE = ("exg_mean", "green_frac", "ngrdi_mean")


def uav_image_stats(data: bytes) -> dict:
    """Read one PNG and summarise its plot pixels. Never raises for a bad file."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            mode = im.mode
            size = im.size
            alpha = np.asarray(im.getchannel("A")) if "A" in im.getbands() else None
            rgb = np.asarray(im.convert("RGB"), dtype=np.float64)
        out = _stats(rgb, alpha)
        out.update(mode=mode, width=size[0], height=size[1], error=None)
    except Exception as exc:  # any decoder failure is a corrupt-image flag
        out = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    out["extractor_version"] = UAV_VERSION
    return out


def _summary(values: np.ndarray, prefix: str, out: dict) -> None:
    values = values[np.isfinite(values)]
    if not values.size:
        out.update({f"{prefix}_{s}": np.nan for s in UAV_STATS})
        return
    p10, p50, p90 = np.percentile(values, (10, 50, 90))
    out.update(
        {
            f"{prefix}_mean": float(values.mean()),
            f"{prefix}_median": float(p50),
            f"{prefix}_std": float(values.std()),
            f"{prefix}_p10": float(p10),
            f"{prefix}_p90": float(p90),
        }
    )


def _stats(rgb: np.ndarray, alpha: np.ndarray | None) -> dict:
    padding = (rgb == 0).all(axis=2)
    if alpha is not None:
        padding |= alpha == 0
    valid = ~padding
    n_total, n_valid = int(valid.size), int(valid.sum())
    out: dict = {
        "n_pixels_total": n_total,
        "n_valid": n_valid,
        "valid_fraction": n_valid / n_total if n_total else np.nan,
    }
    px = rgb[valid] / 255.0
    R, G, B = px[:, 0], px[:, 1], px[:, 2]
    total = R + G + B
    with np.errstate(divide="ignore", invalid="ignore"):
        r, g, b = R / total, G / total, B / total
        idx = {
            "exg": 2 * g - r - b,
            "exgr": (2 * g - r - b) - (1.4 * r - g),
            "ngrdi": (G - R) / (G + R),
            "vari": (G - R) / (G + R - B),
        }
    idx["vari"] = np.where(np.abs(idx["vari"]) <= 1, idx["vari"], np.nan)
    out["r_mean"] = float(R.mean()) if n_valid else np.nan
    out["g_mean"] = float(G.mean()) if n_valid else np.nan
    out["b_mean"] = float(B.mean()) if n_valid else np.nan
    out["brightness_mean"] = float(total.mean() / 3) if n_valid else np.nan
    for name in UAV_INDICES:
        _summary(idx[name], name, out)
    exgr = idx["exgr"][np.isfinite(idx["exgr"])]
    out["green_frac"] = float((exgr > 0).mean()) if exgr.size else np.nan
    grey = rgb.mean(axis=2) / 255.0
    dx = np.abs(np.diff(grey, axis=1))[valid[:, 1:] & valid[:, :-1]]
    dy = np.abs(np.diff(grey, axis=0))[valid[1:, :] & valid[:-1, :]]
    both = np.concatenate([dx, dy])
    out["texture"] = float(both.mean()) if both.size else np.nan
    return out


def usable_uav(images: pd.DataFrame, acquisitions: pd.DataFrame | None) -> pd.DataFrame:
    """UAV images that decoded and have plot pixels, with their flight date attached."""
    u = images[images["modality"] == "uav"].copy()
    u = u[u["error"].isna() & (u["n_valid"].fillna(0) > 0) & u["plot_id"].notna()]
    u["time_point"] = u["time_point"].astype(int)
    if "date" not in u or u["date"].isna().all():
        u = u.drop(columns=["date"], errors="ignore")
        if acquisitions is not None and len(acquisitions):
            a = acquisitions[acquisitions["modality"] == "uav"][["site_id", "time_point", "date"]]
            u = u.merge(a, on=["site_id", "time_point"], how="left")
        else:
            u["date"] = pd.NaT
    u["date"] = pd.to_datetime(u["date"]).dt.normalize()
    u = u.sort_values(["plot_id", "time_point", "n_valid"], ascending=[True, True, False])
    return u.drop_duplicates(["plot_id", "time_point"]).dropna(subset=["date"])


def uav_columns() -> list[str]:
    cols = ["uav_images_available", "uav_latest_tp", "uav_latest_date", "days_since_uav_image"]
    cols += [f"uav_{c}_current" for c in UAV_CURRENT]
    cols += [f"uav_{c}_change_from_previous" for c in UAV_CHANGE]
    return cols


def uav_as_of(table: pd.DataFrame, uav: pd.DataFrame) -> pd.DataFrame:
    """UAV features for each progressive row, from flights on or before its as_of_date."""
    by_plot = {pid: g.sort_values("date") for pid, g in uav.groupby("plot_id")}
    rows = []
    for pid, as_of in zip(table["plot_id"], table["as_of_date"], strict=True):
        row = dict.fromkeys(uav_columns(), np.nan)
        hist = by_plot.get(pid)
        if hist is not None and pd.notna(as_of):
            hist = hist[hist["date"] <= as_of]
        else:
            hist = None
        row["uav_images_available"] = 0 if hist is None else len(hist)
        if hist is not None and len(hist):
            cur = hist.iloc[-1]
            row["uav_latest_tp"] = int(cur["time_point"])
            row["uav_latest_date"] = cur["date"]
            row["days_since_uav_image"] = float((as_of - cur["date"]).days)
            for c in UAV_CURRENT:
                row[f"uav_{c}_current"] = cur[c]
            if len(hist) >= 2:
                prev = hist.iloc[-2]
                for c in UAV_CHANGE:
                    row[f"uav_{c}_change_from_previous"] = cur[c] - prev[c]
        rows.append(row)
    out = pd.DataFrame(rows, index=table.index)
    out["uav_latest_date"] = pd.to_datetime(out["uav_latest_date"])
    return out


def uav_flags(images: pd.DataFrame) -> pd.DataFrame:
    u = images[images["modality"] == "uav"]
    rows = []

    def add(df, flag, detail=""):
        for _, r in df.iterrows():
            rows.append(
                {
                    "path": r["path"],
                    "modality": "uav",
                    "site_id": r["site_id"],
                    "time_point": r["time_point"],
                    "plot_id": r["plot_id"],
                    "flag": flag,
                    "detail": detail,
                }
            )

    add(u[u["error"].notna()], "corrupt")
    ok = u[u["error"].isna()]
    add(ok[ok["n_valid"] == 0], "no_valid_pixels")
    add(ok[(ok["n_valid"] > 0) & (ok["valid_fraction"] < 0.2)], "low_valid_pixels")
    add(u[u["sha1"].duplicated(keep=False)], "duplicate_content")
    site_tps = ok.groupby("site_id")["time_point"].apply(set)
    for pid, g in ok.groupby("plot_id"):
        site = g["site_id"].iloc[0]
        for tp in sorted(site_tps[site] - set(g["time_point"])):
            rows.append(
                {
                    "path": None,
                    "modality": "uav",
                    "site_id": site,
                    "time_point": tp,
                    "plot_id": pid,
                    "flag": "missing_tp",
                    "detail": "",
                }
            )
    return pd.DataFrame(
        rows, columns=["path", "modality", "site_id", "time_point", "plot_id", "flag", "detail"]
    )
