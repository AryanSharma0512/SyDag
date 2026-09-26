"""
Data-quality flags, the quality report and a visual-QA sample.

Nothing is deleted or corrected here. Every check writes rows to quality_flags.csv
(path, plot, time point, flag, detail) and a count to the report; the feature tables keep
every image that decoded with a known band layout, and carry per-image flags as columns.

Flags that compare an image with other dates of the same plot (implausible change,
footprint change, fewer pixels than the plot's other images) are for review only. They
are never features, because they would let later images inform an earlier row.
"""

import numpy as np
import pandas as pd

from soilsignal_ml.imagery.satellite import DEFAULT_BANDS, INDICES, read_raster

EXPECTED_BANDS = len(DEFAULT_BANDS)
CLOSE_DAYS = 14  # acquisitions this close should not differ wildly
JUMP_ABS = 0.30  # |NDVI change| between close acquisitions
JUMP_SITE_DEVIATION = 0.15  # |plot change - site median change|, and ...
JUMP_ROBUST_Z = 5.0  # ... this many robust SDs from the site's median change
FOOTPRINT_RATIO = 0.5  # valid pixels halved or doubled between consecutive images
PARTIAL_ZERO_SHARE = 0.05
LOW_VALID_PIXELS = 10
LOW_VALID_FRACTION_OF_PLOT = 0.9
FEWER_PIXELS_THAN_PLOT_MEDIAN = 0.5

FLAG_TEXT = {
    "corrupt": "file could not be decoded",
    "unparsed_path": "site / time point / plot could not be read from the path",
    "unexpected_band_count": f"band count is not {EXPECTED_BANDS}",
    "band_order_unknown": "band count does not match the configured order and no band descriptions",
    "band_order_mismatch": "the file's band descriptions contradict the configured band order",
    "brightest_band_not_nir": "vegetated image (NDVI > 0.5) whose brightest band is not NIR",
    "no_valid_pixels": "no valid pixel inside the plot",
    "low_valid_pixels": f"< {LOW_VALID_PIXELS} valid pixels or < {LOW_VALID_FRACTION_OF_PLOT:.0%} of plot pixels valid",
    "small_footprint": "valid pixels < 50% of the median plot in the same acquisition",
    "fewer_pixels_than_plot_median": f"valid pixels < {FEWER_PIXELS_THAN_PLOT_MEDIAN:.0%} of the plot's median over its images (review only)",
    "saturated_pixels": "plot pixels with reflectance > 1 in some band",
    "partial_zero_pixels": f"> {PARTIAL_ZERO_SHARE:.0%} of plot pixels have a zero in some (not all) bands",
    "index_out_of_range": "per-pixel index values outside [-1, 1] (set to NaN)",
    "negative_ndvi": "mean NDVI < 0: implausible for a cropped plot",
    "duplicate_content": "byte-identical to another image file",
    "duplicate_plot_tp": "more than one file for the same plot and time point",
    "missing_tp": "plot has no usable image at a time point its site was imaged",
    "no_acquisition_date": "no acquisition date for this site and time point",
    "dates_not_increasing": "the site's acquisition dates do not increase with TP number",
    "image_not_in_plots_table": "image plot id has no row in the plots table",
    "implausible_change": "NDVI change from the previous image is implausible (review only)",
    "footprint_change": "valid-pixel count halved or doubled since the previous image (review only)",
}


def _flag(rows: list, df: pd.DataFrame, flag: str, detail) -> None:
    for (_, r), d in zip(
        df.iterrows(), detail if isinstance(detail, list) else [detail] * len(df), strict=True
    ):
        rows.append(
            {
                "path": r.get("path"),
                "modality": r.get("modality", "satellite"),
                "site_id": r.get("site_id"),
                "time_point": r.get("time_point"),
                "plot_id": r.get("plot_id"),
                "flag": flag,
                "detail": d,
            }
        )


def satellite_flags(
    images: pd.DataFrame,
    plots: pd.DataFrame | None = None,
    acquisitions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Every satellite quality flag, one row per (image or plot, flag)."""
    img = images[images["modality"] == "satellite"].copy()
    rows: list = []
    ok = img["error"].isna() if "error" in img else pd.Series(True, index=img.index)
    _flag(rows, img[~ok], "corrupt", list(img.loc[~ok, "error"].astype(str)))
    _flag(rows, img[img["parse_method"] == "unparsed"], "unparsed_path", "")
    good = img[ok]
    if good.empty:
        return pd.DataFrame(rows)
    nb = good["n_bands"]
    _flag(
        rows,
        good[nb != EXPECTED_BANDS],
        "unexpected_band_count",
        list(nb[nb != EXPECTED_BANDS].astype(int).astype(str)),
    )
    _flag(rows, good[good["band_order_source"] == "unknown"], "band_order_unknown", "")
    mismatch = good[good["band_order_agrees"].eq(False)]
    _flag(rows, mismatch, "band_order_mismatch", list(mismatch["band_names"]))
    veg = good[(good["ndvi_mean"] > 0.5) & good["brightest_band"].notna()]
    odd = veg[veg["brightest_band"] != "nir"]
    _flag(rows, odd, "brightest_band_not_nir", list(odd["brightest_band"]))

    _flag(rows, good[good["n_valid"] == 0], "no_valid_pixels", "")
    low = good[
        (good["n_valid"] > 0)
        & (
            (good["n_valid"] < LOW_VALID_PIXELS)
            | (good["valid_fraction_of_plot"] < LOW_VALID_FRACTION_OF_PLOT)
        )
    ]
    _flag(
        rows,
        low,
        "low_valid_pixels",
        [
            f"{int(v)} valid of {int(p)} plot pixels"
            for v, p in zip(low["n_valid"], low["n_in_plot"], strict=True)
        ],
    )
    site_med = good.groupby(["site_id", "time_point"])["n_valid"].transform("median")
    small = good[(good["n_valid"] > 0) & (good["n_valid"] < 0.5 * site_med)]
    _flag(
        rows,
        small,
        "small_footprint",
        [
            f"{int(v)} vs {m:.0f} for the site's median plot that day"
            for v, m in zip(small["n_valid"], site_med[small.index], strict=True)
        ],
    )
    med = good.groupby("plot_id")["n_valid"].transform("median")
    few = good[(good["n_valid"] > 0) & (good["n_valid"] < FEWER_PIXELS_THAN_PLOT_MEDIAN * med)]
    _flag(
        rows,
        few,
        "fewer_pixels_than_plot_median",
        [
            f"{int(v)} vs plot median {m:.0f}"
            for v, m in zip(few["n_valid"], med[few.index], strict=True)
        ],
    )
    in_plot = good["n_in_plot"].where(good["n_in_plot"] > 0)
    sat = good[good["n_saturated"] > 0]
    _flag(rows, sat, "saturated_pixels", [f"{int(n)} pixels" for n in sat["n_saturated"]])
    pz = good[good["n_nonpositive"] / in_plot > PARTIAL_ZERO_SHARE]
    _flag(
        rows,
        pz,
        "partial_zero_pixels",
        [
            f"{int(n)} of {int(p)}"
            for n, p in zip(pz["n_nonpositive"], pz["n_in_plot"], strict=True)
        ],
    )
    oor_cols = [f"{i}_n_out_of_range" for i in INDICES if f"{i}_n_out_of_range" in good]
    oor = good[good[oor_cols].sum(axis=1) > 0]
    _flag(
        rows,
        oor,
        "index_out_of_range",
        [
            ", ".join(f"{c.split('_')[0]}={int(r[c])}" for c in oor_cols if r[c] > 0)
            for _, r in oor.iterrows()
        ],
    )
    _flag(
        rows,
        good[good["ndvi_mean"] < 0],
        "negative_ndvi",
        list(good.loc[good["ndvi_mean"] < 0, "ndvi_mean"].round(3).astype(str)),
    )

    dup = img[img["sha1"].duplicated(keep=False) & img["sha1"].notna()]
    groups = dup.groupby("sha1")["path"].apply(list)
    _flag(
        rows,
        dup,
        "duplicate_content",
        [
            " = ".join(p for p in groups[s] if p != path)
            for s, path in zip(dup["sha1"], dup["path"], strict=True)
        ],
    )
    dpt = img[img.duplicated(["plot_id", "time_point"], keep=False) & img["plot_id"].notna()]
    _flag(rows, dpt, "duplicate_plot_tp", "")

    usable = good[(good["band_order_source"] != "unknown") & (good["n_valid"] > 0)]
    rows += _coverage_flags(usable, plots, acquisitions)
    rows += _change_flags(usable, acquisitions)
    return pd.DataFrame(
        rows, columns=["path", "modality", "site_id", "time_point", "plot_id", "flag", "detail"]
    )


def _coverage_flags(usable: pd.DataFrame, plots, acquisitions) -> list:
    rows: list = []
    site_tps = usable.groupby("site_id")["time_point"].apply(set)
    for pid, g in usable.groupby("plot_id"):
        site = g["site_id"].iloc[0]
        for tp in sorted(site_tps[site] - set(g["time_point"])):
            rows.append(
                {
                    "path": None,
                    "modality": "satellite",
                    "site_id": site,
                    "time_point": tp,
                    "plot_id": pid,
                    "flag": "missing_tp",
                    "detail": "",
                }
            )
    if plots is not None and len(plots):
        known = set(plots["plot_id"])
        orphan = usable[~usable["plot_id"].isin(known)].drop_duplicates("plot_id")
        _flag(rows, orphan, "image_not_in_plots_table", "")
    if acquisitions is not None and len(acquisitions):
        sat = acquisitions[acquisitions["modality"] == "satellite"]
        have = set(zip(sat["site_id"], sat["time_point"], strict=True))
        for (site, tp), _ in usable.groupby(["site_id", "time_point"]):
            if (site, tp) not in have:
                rows.append(
                    {
                        "path": None,
                        "modality": "satellite",
                        "site_id": site,
                        "time_point": tp,
                        "plot_id": None,
                        "flag": "no_acquisition_date",
                        "detail": "",
                    }
                )
        for site, g in sat.sort_values("time_point").groupby("site_id"):
            if not g["date"].is_monotonic_increasing:
                rows.append(
                    {
                        "path": None,
                        "modality": "satellite",
                        "site_id": site,
                        "time_point": None,
                        "plot_id": None,
                        "flag": "dates_not_increasing",
                        "detail": ", ".join(str(d.date()) for d in g["date"]),
                    }
                )
    return rows


def _change_flags(usable: pd.DataFrame, acquisitions) -> list:
    """Consecutive images of each plot compared with each other and with the site's
    typical change over the same interval. Review only (uses both dates)."""
    rows: list = []
    df = usable.sort_values(["plot_id", "time_point"]).copy()
    if acquisitions is not None and len(acquisitions) and "date" not in df:
        sat = acquisitions[acquisitions["modality"] == "satellite"]
        df = df.merge(
            sat[["site_id", "time_point", "date"]], on=["site_id", "time_point"], how="left"
        )
    prev = df.groupby("plot_id")[["time_point", "ndvi_mean", "n_valid"]].shift(1)
    df["prev_tp"] = prev["time_point"]
    df["d_ndvi"] = df["ndvi_mean"] - prev["ndvi_mean"]
    df["valid_ratio"] = df["n_valid"] / prev["n_valid"]
    if "date" in df:
        df["gap_days"] = df.groupby("plot_id")["date"].diff().dt.days
    else:
        df["gap_days"] = np.nan
    pairs = df.dropna(subset=["prev_tp"])
    site_med = pairs.groupby(["site_id", "prev_tp", "time_point"])["d_ndvi"].transform("median")
    mad = pairs.groupby(["site_id", "prev_tp", "time_point"])["d_ndvi"].transform(
        lambda s: (s - s.median()).abs().median()
    )
    dev = (pairs["d_ndvi"] - site_med).abs()
    robust_z = dev / (1.4826 * mad.replace(0, np.nan))
    close = pairs["gap_days"] <= CLOSE_DAYS
    jump = ((dev > JUMP_SITE_DEVIATION) & (robust_z > JUMP_ROBUST_Z)) | (
        close & (pairs["d_ndvi"].abs() > JUMP_ABS)
    )
    j = pairs[jump.fillna(False)]
    _flag(
        rows,
        j,
        "implausible_change",
        [
            f"NDVI {d:+.2f} since TP{int(p)} ({g:.0f} d) vs site median {m:+.2f}"
            for d, p, g, m in zip(
                j["d_ndvi"],
                j["prev_tp"],
                j["gap_days"].fillna(np.nan),
                site_med[j.index],
                strict=True,
            )
        ],
    )
    fp = pairs[
        (pairs["valid_ratio"] < FOOTPRINT_RATIO) | (pairs["valid_ratio"] > 1 / FOOTPRINT_RATIO)
    ]
    _flag(
        rows,
        fp,
        "footprint_change",
        [
            f"valid pixels x{r:.2f} since TP{int(p)}"
            for r, p in zip(fp["valid_ratio"], fp["prev_tp"], strict=True)
        ],
    )
    return rows


# ---- report ----------------------------------------------------------------------------


def _md_table(df: pd.DataFrame, index: bool = True) -> str:
    if df.empty:
        return "_none_\n"
    df = df.reset_index() if index else df
    head = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = [
        "| "
        + " | ".join(
            "" if pd.isna(v) else (f"{v:.3f}" if isinstance(v, float) else str(v)) for v in row
        )
        + " |"
        for row in df.itertuples(index=False)
    ]
    return "\n".join([head, sep, *body]) + "\n"


def quality_report(
    images: pd.DataFrame,
    flags: pd.DataFrame,
    table: pd.DataFrame | None,
    context: dict,
    uav_images: pd.DataFrame | None = None,
    uav_flags: pd.DataFrame | None = None,
) -> str:
    sat = images[images["modality"] == "satellite"]
    ok = sat[sat["error"].isna()] if "error" in sat else sat
    lines = [
        "# Feature quality report",
        "",
        f"Generated {context.get('generated', '')} from `{context.get('data_root', '')}`. "
        f"{context.get('note', '')}",
        "",
        "Nothing was deleted or corrected. Flags are listed in `quality_flags.csv` "
        "(one row per image or plot and flag). Flags marked *review only* compare an image with other "
        "dates of the same plot and are never used as features.",
        "",
        "## Inputs",
        "",
        f"- Satellite images found: {len(sat)} ({len(ok)} decoded)",
        f"- Plots with at least one satellite image: {ok['plot_id'].nunique()}",
    ]
    plots = context.get("plots")
    if plots is not None and len(plots):
        imaged = set(sat["plot_id"].dropna())
        known = set(plots["plot_id"])
        lines.append(
            f"- Plots table: {len(known)} plots at {plots['site_id'].nunique()} sites. "
            f"{len(imaged & known)} have satellite imagery; that set (plus {len(imaged - known)} "
            "imaged plots missing from the plots table) is the population of every cutoff. "
            "Plots never imaged are left out of the feature tables."
        )
        cover = plots.assign(imaged=plots["plot_id"].isin(imaged)).groupby("site_id")["imaged"]
        lines += ["", "Plots table vs imagery, by site:", ""]
        lines.append(_md_table(pd.DataFrame({"plots": cover.size(), "imaged": cover.sum()})))
    if uav_images is not None and len(uav_images):
        lines.append(
            f"- UAV images found: {len(uav_images)} at {', '.join(sorted(uav_images['site_id'].dropna().unique()))}"
        )
    lines += ["", "Satellite images per site and time point:", ""]
    lines.append(
        _md_table(
            sat.pivot_table(
                index="site_id", columns="time_point", values="path", aggfunc="count", fill_value=0
            )
        )
    )

    if len(ok):
        lines += ["## Masking", ""]
        lines.append(
            "Pixels where every band is 0 (or the GDAL nodata value) are padding outside the plot polygon. "
            "Plot pixels with any band <= 0 or > 1 after scaling are invalid. Statistics use valid pixels only."
        )
        lines.append("")
        m = ok.groupby("site_id").agg(
            images=("path", "count"),
            median_pixels=("n_pixels_total", "median"),
            median_valid=("n_valid", "median"),
            median_valid_fraction=("valid_fraction", "median"),
            min_valid_fraction_of_plot=("valid_fraction_of_plot", "min"),
            saturated_images=("n_saturated", lambda s: int((s > 0).sum())),
            partial_zero_pixels=("n_nonpositive", "sum"),
            near_zero_pixels=("n_near_zero", "sum"),
            valid_pixels=("n_valid", "sum"),
        )
        lines.append(_md_table(m))
        if "pixel_size_x" in ok:
            sizes = ok["pixel_size_x"].round(3).value_counts().to_dict()
            lines.append(
                f"Pixel sizes (m): {sizes}. EPSG codes: {ok['epsg'].value_counts().to_dict()}.\n"
            )

        lines += ["## Band order", ""]
        src = ok["band_order_source"].value_counts().to_dict()
        agree = ok["band_order_agrees"].value_counts(dropna=False).to_dict()
        lines.append(
            f"Band names taken from: {src}. File descriptions agree with the configured order "
            f"({', '.join(DEFAULT_BANDS)}): {agree}."
        )
        veg = ok[ok["ndvi_mean"] > 0.5]
        if len(veg):
            share = (veg["brightest_band"] == "nir").mean()
            lines.append(
                f"Independent check: in {len(veg)} vegetated images (mean NDVI > 0.5) NIR is the "
                f"brightest band in {share:.1%}. Brightest band by time point:\n"
            )
            lines.append(
                _md_table(
                    ok.pivot_table(
                        index="time_point",
                        columns="brightest_band",
                        values="path",
                        aggfunc="count",
                        fill_value=0,
                    )
                )
            )

        lines += [
            "## Index values by site and time point",
            "",
            "Plot-mean NDVI (median across plots, with the 10th and 90th percentiles) and plot-mean NDRE:",
            "",
        ]
        g = ok.groupby(["site_id", "time_point"])
        s = pd.DataFrame(
            {
                "images": g["path"].count(),
                "ndvi_p10": g["ndvi_mean"].quantile(0.1),
                "ndvi_median": g["ndvi_mean"].median(),
                "ndvi_p90": g["ndvi_mean"].quantile(0.9),
                "ndre_median": g["ndre_mean"].median(),
                "evi_median": g["evi_mean"].median(),
            }
        )
        if context.get("acquisitions") is not None:
            acq = context["acquisitions"]
            acq = acq[acq["modality"] == "satellite"].set_index(["site_id", "time_point"])["date"]
            s.insert(0, "date", [acq.get(k, pd.NaT) for k in s.index])
            s["date"] = pd.to_datetime(s["date"]).dt.date
        lines.append(_md_table(s))

    lines += ["## Flags", ""]
    all_flags = (
        pd.concat([f for f in (flags, uav_flags) if f is not None and len(f)], ignore_index=True)
        if (len(flags) or (uav_flags is not None and len(uav_flags)))
        else flags
    )
    if len(all_flags):
        counts = all_flags.groupby(["modality", "flag"]).size().rename("count").reset_index()
        counts["meaning"] = counts["flag"].map(FLAG_TEXT).fillna("")
        lines.append(_md_table(counts, index=False))
        lines += ["Examples (up to 5 per flag):", ""]
        for (modality, flag), grp in all_flags.groupby(["modality", "flag"]):
            lines.append(f"**{modality} / {flag}**")
            lines.append("")
            for r in grp.head(5).itertuples():
                tp = "" if pd.isna(r.time_point) else int(r.time_point)
                where = (
                    r.path if isinstance(r.path, str) else f"{r.site_id} TP{tp} {r.plot_id or ''}"
                )
                lines.append(f"- `{where}` {r.detail or ''}")
            lines.append("")
    else:
        lines.append("_No flags._\n")

    if table is not None and len(table):
        lines += ["## Progressive table", ""]
        c = table.groupby("cutoff", sort=False).agg(
            rows=("plot_id", "count"),
            with_imagery=("satellite_images_available", lambda s: int((s > 0).sum())),
            with_yield=("final_yield", lambda s: int(s.notna().sum())),
            ndvi_current_missing=("ndvi_current", lambda s: int(s.isna().sum())),
        )
        lines.append(_md_table(c))
    return "\n".join(lines) + "\n"


# ---- visual QA --------------------------------------------------------------------------


def visual_sample(
    images: pd.DataFrame, flags: pd.DataFrame, per_group: int = 1, extra: int = 8
) -> pd.DataFrame:
    """A small representative sample: for each site x TP the highest, median and lowest
    NDVI plot, plus the lowest valid-pixel fractions and flagged images."""
    ok = images[
        (images["modality"] == "satellite") & images["error"].isna() & (images["n_valid"] > 0)
    ]
    picks = []
    for (site, tp), g in ok.groupby(["site_id", "time_point"]):
        g = g.sort_values("ndvi_mean")
        for why, idx in (("low NDVI", 0), ("median NDVI", len(g) // 2), ("high NDVI", len(g) - 1)):
            picks.append({**g.iloc[idx].to_dict(), "why": f"{why} {site} TP{tp}"})
    for _, r in ok.nsmallest(extra, "valid_fraction_of_plot").iterrows():
        picks.append(
            {**r.to_dict(), "why": f"low valid fraction {r['valid_fraction_of_plot']:.2f}"}
        )
    flagged = flags.dropna(subset=["path"])
    flagged = flagged[flagged["flag"] != "corrupt"].drop_duplicates("path").head(extra)
    for _, f in flagged.iterrows():
        match = ok[ok["path"] == f["path"]]
        if len(match):
            picks.append({**match.iloc[0].to_dict(), "why": f"flag: {f['flag']}"})
    return pd.DataFrame(picks).drop_duplicates("path").reset_index(drop=True)


def contact_sheets(sample: pd.DataFrame, root, out_dir, per_page: int = 24) -> list:
    """False-colour (NIR, red, green) and NDVI thumbnails with fixed stretches, so
    brightness is comparable across images."""
    import matplotlib

    matplotlib.use("Agg")
    from pathlib import Path

    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for page in range(0, len(sample), per_page):
        chunk = sample.iloc[page : page + per_page]
        cols = 6
        rows = int(np.ceil(len(chunk) * 2 / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.2, rows * 2.6))
        axes = np.atleast_1d(axes).ravel()
        for ax in axes:
            ax.axis("off")
        for i, (_, r) in enumerate(chunk.iterrows()):
            raster = read_raster((Path(root) / r["path"]).read_bytes())
            names = raster.band_names or DEFAULT_BANDS[: raster.pixels.shape[2]]
            refl = raster.pixels.astype(float) / float(r.get("reflectance_scale") or 10_000)
            band = {n: refl[..., k] for k, n in enumerate(names)}
            pad = (raster.pixels == 0).all(axis=2)
            if {"nir", "red", "green"} <= set(band):
                rgb = np.dstack([band["nir"] / 0.5, band["red"] / 0.15, band["green"] / 0.15]).clip(
                    0, 1
                )
                rgb[pad] = 1.0
                axes[2 * i].imshow(rgb, interpolation="nearest")
                with np.errstate(divide="ignore", invalid="ignore"):
                    ndvi = (band["nir"] - band["red"]) / (band["nir"] + band["red"])
                axes[2 * i + 1].imshow(
                    np.ma.masked_where(pad, ndvi),
                    vmin=-0.2,
                    vmax=1.0,
                    cmap="RdYlGn",
                    interpolation="nearest",
                )
            label = f"{r['plot_id']}\nTP{int(r['time_point'])} NDVI {r['ndvi_mean']:.2f} valid {r['valid_fraction_of_plot']:.0%}"
            axes[2 * i].set_title(label, fontsize=6)
            axes[2 * i + 1].set_title(r["why"], fontsize=6)
        fig.suptitle(
            "False colour (NIR/R/G, fixed stretch) and NDVI (-0.2 to 1); padding white", fontsize=8
        )
        fig.tight_layout()
        path = out_dir / f"contact_sheet_{page // per_page + 1:02d}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        written.append(path)
    return written
