"""
Writes the challenge tables (Parquet) and challenge_manifest.json: inputs, counts, joins,
anomalies and the schema of every output, so the next stage can check what it consumes.

Nothing written here holds a Drive file id, an owner's e-mail or a machine-local path.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from soilsignal_ml.ingest.challenge import (
    DATES_XLSX,
    GROUND_TRUTH_CSV,
    SENSOR_TIME_POINTS,
    ChallengeTables,
    find_input,
)
from soilsignal_ml.ingest.imagery import SATELLITE_BANDS, SATELLITE_REFLECTANCE_SCALE, sha256

PRIVATE_COLUMNS = ["local_path", "drive_id"]
GT_FIELDS = [
    "experiment",
    "genotype",
    "nitrogen_treatment",
    "nitrogen_lb_ac",
    "irrigated",
    "plot_length_ft",
    "planting_date",
    "total_stand_count",
    "days_to_anthesis",
    "gdd_to_anthesis",
    "final_yield",
]


def _public(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in PRIVATE_COLUMNS if c in df.columns])


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if hasattr(v, "item"):
        return v.item()
    if v is pd.NA or (isinstance(v, float) and v != v):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _schema(df: pd.DataFrame) -> dict:
    return {"rows": len(df), "columns": {c: str(t) for c, t in df.dtypes.items()}}


def _image_summary(m: pd.DataFrame) -> dict:
    if m.empty:
        return {"files": 0}
    out = {
        "files": len(m),
        "bytes": int(m["size_bytes"].sum()),
        "usable": int(m["use"].sum()),
        "by_status": m["match_status"].value_counts().to_dict(),
        "duplicate_files": int(m["is_duplicate"].sum()),
        "distinct_plots": int(m.loc[m["use"], "plot_id"].nunique()),
        "by_site_time_point": [],
    }
    for (s, tp), g in m.groupby(["site_id", "time_point"], dropna=False):
        out["by_site_time_point"].append(
            {
                "site_id": s,
                "time_point": tp,
                "date": g["date"].iloc[0],
                "days_after_planting_median": g["days_after_planting"].median(),
                "files": len(g),
                "usable": int(g["use"].sum()),
                "not_in_ground_truth": int((g["match_status"] == "not_in_ground_truth").sum()),
                "duplicates": int(g["is_duplicate"].sum()),
                "hybrid_plots_with_yield": int(
                    (g["use"] & g["is_hybrid_plot"].fillna(False) & g["final_yield"].notna()).sum()
                ),
                "bytes": int(g["size_bytes"].sum()),
            }
        )
    used = m[m["use"]]
    per_plot = used.groupby("plot_id")["time_point"].nunique()
    out["time_points_per_plot"] = per_plot.value_counts().sort_index().to_dict()
    for site, g in used.groupby("site_id"):
        n = g.groupby("plot_id")["time_point"].nunique()
        out.setdefault("time_points_per_plot_by_site", {})[site] = (
            n.value_counts().sort_index().to_dict()
        )
    return out


def _raster_summary(m: pd.DataFrame) -> dict:
    if "metadata_status" not in m:
        return {}
    out = {"metadata_status": m["metadata_status"].value_counts().to_dict()}
    r = m[m["metadata_status"] == "read"]
    if r.empty:
        return out
    out.update(
        width_px={
            "min": int(r["width"].min()),
            "median": float(r["width"].median()),
            "max": int(r["width"].max()),
        },
        height_px={
            "min": int(r["height"].min()),
            "median": float(r["height"].median()),
            "max": int(r["height"].max()),
        },
        bands=r["bands"].value_counts().to_dict(),
        dtype=r["dtype"].value_counts().to_dict(),
        valid_fraction={
            "min": float(r["valid_fraction"].min()),
            "median": float(r["valid_fraction"].median()),
        },
        files_without_valid_pixels=r.loc[r["valid_pixels"] == 0, "image_path"].tolist(),
    )
    if "crs_epsg" in r:
        out["crs_epsg_by_site"] = {
            s: sorted(int(x) for x in g["crs_epsg"].dropna().unique())
            for s, g in r.groupby("site_id")
        }
        out["pixel_size_m"] = sorted(r["pixel_size_x_m"].dropna().round(3).unique().tolist())
        out["band_order_ok"] = int(r["band_order_ok"].sum())
        out["band_order_not_ok"] = r.loc[~r["band_order_ok"].astype(bool), "image_path"].tolist()
        out["partial_zero_pixel_files"] = r.loc[r["partial_zero_pixels"] > 0, "image_path"].tolist()
    if "alpha_rgb_disagree_pixels" in r:
        out["alpha_rgb_disagree_files"] = r.loc[
            r["alpha_rgb_disagree_pixels"] > 0, "image_path"
        ].tolist()
    errors = m[m["metadata_status"] == "read_error"]
    if len(errors):
        out["read_errors"] = dict(zip(errors["image_path"], errors["read_error"], strict=True))
    return out


def summarize(t: ChallengeTables, raw_root: Path) -> dict:
    p = t.plots
    sites_with_images = sorted(
        set(t.satellite.loc[t.satellite["use"], "site_id"])
        | set(t.uav.loc[t.uav["use"], "site_id"])
    )
    gt = {}
    for s, g in p.groupby("site_id"):
        gt[s] = {
            "plots": len(g),
            "hybrid_plots": int(g["is_hybrid_plot"].sum()),
            "plots_with_final_yield": int(g["final_yield"].notna().sum()),
            "hybrid_plots_without_yield": int(
                (g["is_hybrid_plot"] & g["final_yield"].isna()).sum()
            ),
            "unique_hybrids": int(g["genotype"].nunique()),
            "experiments": sorted(g["experiment"].dropna().unique().tolist()),
            "nitrogen_lb_ac": sorted(g["nitrogen_lb_ac"].dropna().unique().tolist()),
            "planting_dates": sorted(str(d) for d in g["planting_date"].dropna().unique()),
            "irrigated": bool(g["irrigated"].fillna(False).any()),
            "missing": {c: int(g[c].isna().sum()) for c in GT_FIELDS},
            "has_images": s in sites_with_images,
            "plots_with_coordinates": int(g["latitude"].notna().sum()),
        }
    in_scope = p[p["site_id"].isin(sites_with_images)]

    unmatched = pd.concat([t.satellite, t.uav])
    unmatched = unmatched[unmatched["match_status"] != "ok"]
    dups = pd.concat([t.satellite, t.uav])
    dups = dups[dups["copies"] > 1].sort_values(["image_key", "copy_index"])

    anomalies = []
    if t.notes.get("drive_listing_repeats_dropped"):
        anomalies.append(
            f"Drive listing returned {t.notes['drive_listing_repeats_dropped']} files twice "
            "(same Drive file id); counted once."
        )
    for folder in t.notes.get("empty_drive_folders", []):
        anomalies.append(f"Drive has a second, empty folder at {folder}.")
    for sensor, df in (("satellite", t.satellite), ("uav", t.uav)):
        st = df["match_status"].value_counts().to_dict()
        for status, n in st.items():
            if status != "ok":
                anomalies.append(f"{sensor}: {n} files with status {status}.")
        if df["is_duplicate"].any():
            groups = df[df["copies"] > 1].groupby(["site_id", "tp_label"]).size() // 2
            anomalies.append(
                f"{sensor}: {int(df['is_duplicate'].sum())} duplicate uploads (same plot, time "
                f"point, name and size), by site/TP: "
                + ", ".join(f"{s} {tp}: {n}" for (s, tp), n in groups.items())
                + "; first copy kept (use=True)."
            )
        exp_tp = SENSOR_TIME_POINTS[sensor]
        for s, g in df.groupby("site_id"):
            tps = sorted(g["tp_label"].dropna().unique())
            if len(tps) != exp_tp:
                anomalies.append(f"{sensor} {s}: time points present {tps}, expected {exp_tp}.")
    img_sites = set(t.satellite["site_id"].dropna())
    uav_sites = set(t.uav["site_id"].dropna())
    if img_sites - uav_sites:
        anomalies.append(f"UAV imagery missing for sites {sorted(img_sites - uav_sites)}.")
    anomalies += [
        "README lists satellite bands as 'near infrared, red edge, red, green, blue, deep blue'; "
        "the GeoTIFF band descriptions and the organizers' notebook use Red, Green, Blue, NIR, "
        "Red Edge, Deep Blue (verified on a file whose pixel means reproduce the producer's "
        "embedded statistics). Band order is checked per file (band_order_ok).",
        "Ground truth: poundsOfNitrogenPerAcre is 0 on every plot without a genotype "
        "(fill/border plots). Treated as missing, not as a 0 N treatment.",
        "Ground truth: the CSV's own 'index' column is not unique (kept as gt_index); "
        "gt_row is the row position the organizers' notebook uses as the record id.",
        "Ground truth: experiment codes are verbatim, including 'Hyrbrids' (MOValley) and "
        "'hybrids' (Lincoln); 16 Scottsbluff fill plots have no experiment code.",
        "Ground truth has no range 1 at Ames; the images named Ames-TPn-<exp>_1_<row> are "
        "border plots and stay unmatched (not_in_ground_truth).",
        "DateofCollection.xlsx names Missouri Valley ('MOValley' elsewhere); its second sheet "
        "(satellite vs UAV date gaps) spells Crawfordsville 'Crawfordville'. Aliased to site_id.",
        "TP numbers are per site and sensor: satellite TP4 is Aug 31 at Ames, Sep 11 at Lincoln, "
        "Sep 13 at Crawfordsville. Always join on acquisition date, never on TP.",
        "UAV PNGs are not georeferenced and not radiometrically calibrated (mean RGB differs "
        "several-fold between flights of the same plot).",
        "Ames plots were planted on two dates (experiments 4231/4232 on 2022-05-22, 4233 on "
        "2022-05-23): days_after_planting is per plot.",
    ]

    inputs = {}
    for rel in (GROUND_TRUTH_CSV, DATES_XLSX):
        f = find_input(raw_root, rel)
        if f.exists():
            inputs[rel] = {"bytes": f.stat().st_size, "sha256": sha256(f)}
    manifest = {
        "dataset": "sydag26",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "plot_key": "plot_id = '{year}-{site_id}-{experiment}-{range}-{row}' "
        "(experiment 'NA' when missing); practice_plot_id = '{site_id}-{experiment}-{range}-{row}'",
        "image_filename_pattern": "<Location>-TP<n>-<experiment>_<range>_<row>.<TIF|PNG>",
        "satellite_bands": list(SATELLITE_BANDS),
        "satellite_reflectance_scale": SATELLITE_REFLECTANCE_SCALE,
        "inputs": inputs,
        "file_sources": {k: v for k, v in t.notes.items() if k != "empty_drive_folders"},
        "sites_with_images": sites_with_images,
        "ground_truth": {
            "rows": len(p),
            "sites": gt,
            "in_scope_sites": {
                "plots": len(in_scope),
                "hybrid_plots": int(in_scope["is_hybrid_plot"].sum()),
                "plots_with_final_yield": int(in_scope["final_yield"].notna().sum()),
                "unique_hybrids": int(in_scope["genotype"].nunique()),
            },
            "all_sites_unique_hybrids": int(p["genotype"].nunique()),
            "duplicate_plot_ids": int(p["plot_id"].duplicated().sum()),
        },
        "acquisition_dates": t.acquisition_dates[
            ["site_id", "modality", "time_point", "tp_label", "date"]
        ].to_dict("records"),
        "images": {"satellite": _image_summary(t.satellite), "uav": _image_summary(t.uav)},
        "raster_metadata": {
            "satellite": _raster_summary(t.satellite),
            "uav": _raster_summary(t.uav),
        },
        "plot_coordinates": {
            "plots_with_coordinates": int(p["latitude"].notna().sum()),
            "max_spread_m": None
            if "coord_spread_m" not in p or p["coord_spread_m"].isna().all()
            else float(p["coord_spread_m"].max()),
        },
        "unmatched_files": unmatched[["image_path", "match_status"]].to_dict("records"),
        "duplicate_files": dups[
            ["image_path", "copy_index", "size_bytes", "drive_created_time"]
        ].to_dict("records"),
        "anomalies": anomalies,
    }
    return _jsonable(manifest)


def parquet_ready(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar dates as datetime64 (midnight), the type pandas, the imagery and progressive
    stages and most Parquet readers expect; Python date objects would come back as object."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            values = out[c].dropna()
            if len(values) and all(isinstance(v, date) for v in values.iloc[:200]):
                out[c] = pd.to_datetime(out[c])
    return out


def write_outputs(t: ChallengeTables, out_root: Path, raw_root: Path) -> dict:
    out_root.mkdir(parents=True, exist_ok=True)
    listed = t.listed
    tables = {
        "plots": t.plots,
        "benchmark_plots": t.benchmark_plots(),
        "acquisition_dates": t.acquisition_dates,
        "satellite_acquisitions": t.satellite_acquisitions(),
        "images": t.images(),
        "sites": t.sites,
        "satellite_manifest": _public(t.satellite),
        "uav_manifest": _public(t.uav),
        "observations": t.observations(),
        "drive_inventory": _public(
            listed[
                [
                    "rel_path",
                    "sensor_folder",
                    "location_folder",
                    "tp_folder",
                    "filename",
                    "size_bytes",
                    "drive_created_time",
                    "drive_modified_time",
                ]
            ]
        )
        if len(listed)
        else None,
    }
    schemas = {}
    for name, df in tables.items():
        if df is None:
            continue
        df = parquet_ready(df)
        df.to_parquet(out_root / f"{name}.parquet", index=False)
        schemas[f"{name}.parquet"] = _schema(df)
    manifest = summarize(t, raw_root)
    manifest["outputs"] = schemas
    (out_root / "challenge_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
