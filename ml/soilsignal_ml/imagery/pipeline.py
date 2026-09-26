"""
The whole imagery run: discover -> extract (cached) -> QA -> progressive tables -> UAV -> reports.

    out/
      satellite_image_features.parquet   one row per TIFF: masking metadata + statistics
      satellite_features.parquet         progressive long table (records_only, TP1..TPn)
      progressive/<cutoff>.parquet       the same rows, one file per cutoff
      uav_image_features.parquet         one row per UAV PNG
      satellite_uav_features.parquet     progressive table + UAV columns (by flight date)
      canonical_observations.csv         plot x date index means in the canonical
                                         `observations` layout (for the dataset adapter)
      quality_flags.csv                  every flag, satellite and UAV
      reports/                           feature_quality_report.md, feature_dictionary.md,
                                         benchmark_report.md (when benchmarked)
      visual_qa/                         contact sheets + the sample they show
      cache/                             per-image results keyed by file hash (resumable)
      run_summary.json
"""

import json
import platform
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from soilsignal_ml import ML_ROOT
from soilsignal_ml.imagery import qa
from soilsignal_ml.imagery.dictionary import dictionary_markdown
from soilsignal_ml.imagery.discover import (
    discover_images,
    find_dates,
    find_ground_truth,
    load_manifest,
    read_acquisitions,
    read_plots,
)
from soilsignal_ml.imagery.extract import extract_images, satellite_kwargs
from soilsignal_ml.imagery.progressive import TEMPORAL_INDICES, build_progressive, cutoff_names
from soilsignal_ml.imagery.satellite import (
    DEFAULT_BANDS,
    EXTRACTOR_VERSION,
    image_stats,
    raster_stats,
    read_raster,
)
from soilsignal_ml.imagery.uav import UAV_VERSION, uav_as_of, uav_flags, uav_image_stats, usable_uav

DEFAULT_OUT = ML_ROOT / "data" / "interim" / "imagery"


def load_inputs(
    data_root: Path,
    manifest: Path | None = None,
    plots: Path | None = None,
    acquisitions: Path | None = None,
    progress=print,
) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    """Images, plots and acquisition dates: from the given files, else found under data_root."""
    images = load_manifest(manifest, data_root) if manifest else discover_images(data_root)
    progress(f"images: {images['modality'].value_counts().to_dict()}")
    plots_path = plots or find_ground_truth(data_root)
    dates_path = acquisitions or find_dates(data_root)
    plots_df = read_plots(plots_path) if plots_path else None
    acq_df = read_acquisitions(dates_path) if dates_path else None
    progress(f"plots table: {plots_path or 'none'}; acquisition dates: {dates_path or 'none'}")
    return images, plots_df, acq_df


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def canonical_observations(images: pd.DataFrame) -> pd.DataFrame:
    """Plot x date index means in the canonical `observations` layout
    (ml/soilsignal_ml/ingest/canonical.py), so the dataset adapter needn't decode again."""
    ok = images[images["error"].isna() & (images["n_valid"] > 0) & images["date"].notna()]
    out = pd.DataFrame(
        {
            "plot_id": ok["plot_id"],
            "date": pd.to_datetime(ok["date"]).dt.date,
            "source": "satellite",
            "time_point": ok["time_point"],
            "n_pixels": ok["n_valid"].astype(int),
            **{i: ok[f"{i}_mean"] for i in TEMPORAL_INDICES},
        }
    )
    return out.sort_values(["plot_id", "date"]).reset_index(drop=True)


def run(
    data_root: Path,
    out: Path = DEFAULT_OUT,
    *,
    manifest: Path | None = None,
    plots: Path | None = None,
    acquisitions: Path | None = None,
    workers: int | None = None,
    limit: int | None = None,
    band_order: tuple[str, ...] | None = None,
    reflectance_scale: float | None = None,
    uav: bool = True,
    visual_qa: bool = True,
    retry_errors: bool = False,
    note: str = "",
    progress=print,
) -> dict:
    data_root, out = Path(data_root), Path(out)
    started = time.perf_counter()
    images, plots_df, acq = load_inputs(data_root, manifest, plots, acquisitions, progress)
    sat = images[images["modality"] == "satellite"]
    if limit:
        sat = (
            sat.sort_values("path")
            .groupby(["site_id", "time_point"], dropna=False)
            .head(max(1, limit // max(1, sat.groupby(["site_id", "time_point"]).ngroups)))
        )
        progress(f"--limit: {len(sat)} satellite images spread over every site and TP")
    sat_stats, sat_timing = extract_images(
        sat,
        data_root,
        out / "cache" / "satellite_stats.jsonl",
        fn=image_stats,
        version=EXTRACTOR_VERSION,
        kwargs=satellite_kwargs(band_order, reflectance_scale),
        workers=workers,
        retry_errors=retry_errors,
        progress=progress,
    )
    if acq is not None and "date" not in sat_stats:
        a = acq[acq["modality"] == "satellite"][["site_id", "time_point", "date"]]
        sat_stats = sat_stats.merge(a, on=["site_id", "time_point"], how="left")
    _write(sat_stats, out / "satellite_image_features.parquet")
    canonical_observations(sat_stats).to_csv(out / "canonical_observations.csv", index=False)

    flags = qa.satellite_flags(sat_stats, plots_df, acq)
    table = build_progressive(sat_stats, plots_df, acq)
    _write(table, out / "satellite_features.parquet")
    for cutoff in cutoff_names(table):
        _write(table[table["cutoff"] == cutoff], out / "progressive" / f"{cutoff}.parquet")
    progress(f"progressive table: {table.shape[0]} rows x {table.shape[1]} columns")

    uav_stats, uav_timing, u_flags = None, None, None
    uav_imgs = images[images["modality"] == "uav"]
    if uav and len(uav_imgs):
        uav_stats, uav_timing = extract_images(
            uav_imgs,
            data_root,
            out / "cache" / "uav_stats.jsonl",
            fn=uav_image_stats,
            version=UAV_VERSION,
            workers=workers,
            retry_errors=retry_errors,
            progress=progress,
        )
        if acq is not None:
            a = acq[acq["modality"] == "uav"][["site_id", "time_point", "date"]]
            uav_stats = uav_stats.merge(a, on=["site_id", "time_point"], how="left")
        _write(uav_stats, out / "uav_image_features.parquet")
        u_flags = uav_flags(uav_stats)
        joined = pd.concat([table, uav_as_of(table, usable_uav(uav_stats, acq))], axis=1)
        _write(joined, out / "satellite_uav_features.parquet")
        progress(f"UAV: {len(uav_stats)} images joined by flight date")
    all_flags = pd.concat([f for f in (flags, u_flags) if f is not None], ignore_index=True)
    all_flags.to_csv(out / "quality_flags.csv", index=False)

    reports = out / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    context = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "data_root": str(data_root),
        "note": note,
        "acquisitions": acq,
        "plots": plots_df,
    }
    (reports / "feature_quality_report.md").write_text(
        qa.quality_report(sat_stats, flags, table, context, uav_stats, u_flags)
    )
    known = [
        c
        for c in ("field_id", "experiment", "genotype", "nitrogen_lb_ac", "irrigated")
        if c in table
    ]
    counts = feature_counts(table)
    (reports / "feature_dictionary.md").write_text(dictionary_markdown(known, counts))

    sheets = []
    if visual_qa and len(sat_stats):
        sample = qa.visual_sample(sat_stats, flags)
        (out / "visual_qa").mkdir(exist_ok=True)
        keep = ["path", "site_id", "time_point", "plot_id", "ndvi_mean", "valid_fraction_of_plot"]
        sample[[*keep, "why"]].to_csv(out / "visual_qa" / "sample.csv", index=False)
        sheets = [str(p) for p in qa.contact_sheets(sample, data_root, out / "visual_qa")]

    summary = {
        "data_root": str(data_root),
        "out": str(out),
        "extractor_version": EXTRACTOR_VERSION,
        "satellite": sat_timing,
        "uav": uav_timing,
        "rows": int(len(table)),
        "cutoffs": cutoff_names(table),
        "feature_counts": counts,
        "flags": all_flags.groupby("flag").size().to_dict() if len(all_flags) else {},
        "contact_sheets": sheets,
        "seconds": round(time.perf_counter() - started, 2),
    }
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    progress(f"done in {summary['seconds']} s -> {out}")
    return summary


def feature_counts(table: pd.DataFrame) -> dict:
    """Columns by availability class, and how many are numeric candidate model inputs."""
    from soilsignal_ml.imagery.dictionary import describe

    avail = pd.Series({c: describe(c)[1] for c in table.columns})
    counts = avail.value_counts().to_dict()
    counts["total columns"] = int(len(table.columns))
    numeric = [
        c
        for c in table.columns
        if avail[c] not in ("identifier", "target") and pd.api.types.is_numeric_dtype(table[c])
    ]
    counts["numeric feature columns"] = len(numeric)
    return counts


# ---- benchmark --------------------------------------------------------------------------


def benchmark(
    data_root: Path,
    out: Path = DEFAULT_OUT,
    sample: int = 200,
    workers: int | None = None,
    progress=print,
) -> Path:
    """Time read / decode / statistics per image on a sample, then parallel throughput,
    and extrapolate to the whole set. Writes reports/benchmark_report.md."""
    import os

    data_root, out = Path(data_root), Path(out)
    images = discover_images(data_root)
    sat = images[images["modality"] == "satellite"].sort_values("path")
    uav_imgs = images[images["modality"] == "uav"]
    pick = sat.sample(min(sample, len(sat)), random_state=0) if len(sat) else sat
    t_read, t_decode, t_stats, sizes = [], [], [], []
    for p in pick["path"]:
        t0 = time.perf_counter()
        data = (data_root / p).read_bytes()
        t1 = time.perf_counter()
        try:
            raster = read_raster(data, DEFAULT_BANDS)
            t2 = time.perf_counter()
            raster_stats(raster)
            t3 = time.perf_counter()
        except Exception:  # corrupt files are timed as reads only
            continue
        t_read.append(t1 - t0)
        t_decode.append(t2 - t1)
        t_stats.append(t3 - t2)
        sizes.append(len(data))
    tmp = out / "cache" / "_benchmark"
    shutil.rmtree(tmp, ignore_errors=True)
    n_workers = workers or os.cpu_count() or 1
    runs = {}
    for w in sorted({1, n_workers}):
        _, timing = extract_images(
            pick, data_root, tmp / f"w{w}.jsonl", workers=w, progress=lambda m: None
        )
        runs[w] = timing
    uav_rate = None
    if len(uav_imgs):
        upick = uav_imgs.sample(min(50, len(uav_imgs)), random_state=0)
        _, ut = extract_images(
            upick,
            data_root,
            tmp / "uav.jsonl",
            fn=uav_image_stats,
            version=UAV_VERSION,
            workers=n_workers,
            progress=lambda m: None,
        )
        uav_rate = ut["images"] / max(ut["wall_seconds"], 1e-9)
    shutil.rmtree(tmp, ignore_errors=True)

    ms = lambda xs: 1000 * float(np.median(xs)) if xs else float("nan")  # noqa: E731
    best = max(runs.values(), key=lambda t: t["images"] / max(t["wall_seconds"], 1e-9))
    rate = best["images"] / max(best["wall_seconds"], 1e-9)
    lines = [
        "# Benchmark report",
        "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} on {platform.node()} "
        f"({platform.processor() or platform.machine()}, {os.cpu_count()} CPUs, "
        f"Python {platform.python_version()}).",
        f"Data root: `{data_root}`: {len(sat)} satellite TIFFs, {len(uav_imgs)} UAV images.",
        "",
        f"## Per image (median of {len(t_read)} TIFFs, one process)",
        "",
        "| Step | ms |",
        "|---|---|",
        f"| read bytes | {ms(t_read):.2f} |",
        f"| decode (tifffile) + band layout | {ms(t_decode):.2f} |",
        f"| mask + statistics + indices | {ms(t_stats):.2f} |",
        "",
        f"Median file size {np.median(sizes) / 1024 if sizes else float('nan'):.1f} KB.",
        "",
        "## Throughput (cold cache, includes hashing)",
        "",
        "| Workers | Images | Seconds | Images/s |",
        "|---|---|---|---|",
    ]
    for w, t in runs.items():
        per_s = t["images"] / max(t["wall_seconds"], 1e-9)
        lines.append(f"| {w} | {t['images']} | {t['wall_seconds']:.2f} | {per_s:.0f} |")
    lines += [
        "",
        f"Estimated full satellite extraction: {len(sat) / rate:.1f} s for {len(sat)} images "
        f"at {rate:.0f} images/s.",
    ]
    if uav_rate:
        lines.append(
            f"UAV PNGs: {uav_rate:.0f} images/s, so about {len(uav_imgs) / uav_rate:.1f} s "
            f"for {len(uav_imgs)} images."
        )
    lines += [
        "",
        "A rerun re-reads and hashes every file but decodes only new or changed ones, so it costs "
        "roughly the read + hash time.",
    ]
    path = out / "reports" / "benchmark_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    progress(f"wrote {path}")
    return path
