"""
The feature dictionary, generated from the same column lists the tables are built from,
so a column can't exist without an entry (tests/test_imagery.py checks it).

Availability classes:
    identifier            row keys; not features
    known at planting     design and management fixed at planting
    observed at cutoff    from the latest satellite image on or before as_of_date
    cumulative to cutoff  from every satellite image on or before as_of_date
    timing                calendar arithmetic on dates known at the cutoff
    QA                    per-image quality of the latest image (point-in-time)
    target                final yield; never a feature
"""

from soilsignal_ml.imagery.discover import PLANTING_KNOWN
from soilsignal_ml.imagery.progressive import (
    RELATIVE_AVG_INDICES,
    TEMPORAL_FEATURES,
    TEMPORAL_INDICES,
    schema,
)
from soilsignal_ml.imagery.satellite import (
    CORE_INDICES,
    COVER_NDVI_THRESHOLD,
    DEFAULT_BANDS,
    INDICES,
    SAVI_L,
    STATS,
)
from soilsignal_ml.imagery.uav import UAV_CHANGE, UAV_CURRENT, uav_columns

BAND_TEXT = {
    "red": "red (Pléiades Neo 0.618-0.689 µm)",
    "green": "green (0.533-0.590 µm)",
    "blue": "blue (0.446-0.520 µm)",
    "nir": "near infrared (0.768-0.888 µm)",
    "red_edge": "red edge (0.696-0.749 µm)",
    "deep_blue": "deep blue (0.416-0.456 µm)",
}
INDEX_TEXT = {
    "ndvi": "NDVI = (NIR - Red) / (NIR + Red)",
    "ndre": "NDRE = (NIR - RedEdge) / (NIR + RedEdge)",
    "gndvi": "GNDVI = (NIR - Green) / (NIR + Green)",
    "evi": "EVI = 2.5 (NIR - Red) / (NIR + 6 Red - 7.5 Blue + 1)",
    "savi": f"SAVI = (1 + L)(NIR - Red) / (NIR + Red + L), L = {SAVI_L}",
}
STAT_TEXT = {
    "mean": "mean",
    "median": "median",
    "std": "standard deviation",
    "p10": "10th percentile",
    "p25": "25th percentile",
    "p75": "75th percentile",
    "p90": "90th percentile",
}
TEMPORAL_TEXT = {
    "current": ("value at the latest image on or before the cutoff", "observed at cutoff"),
    "previous": ("value at the image before that (needs 2 images)", "cumulative to cutoff"),
    "change_from_previous": ("current - previous", "cumulative to cutoff"),
    "change_per_10d": (
        "(current - previous) per 10 days between the two images",
        "cumulative to cutoff",
    ),
    "mean_to_date": ("mean over all images so far", "cumulative to cutoff"),
    "min_to_date": ("minimum over all images so far", "cumulative to cutoff"),
    "max_to_date": ("maximum over all images so far", "cumulative to cutoff"),
    "trend": (
        "least-squares slope over all images so far, per 10 days (needs 2 images)",
        "cumulative to cutoff",
    ),
    "area_to_date": (
        "trapezoidal area under the curve from the first to the latest image, index x days",
        "cumulative to cutoff",
    ),
    "vs_site_same_date_mean": (
        "current minus the mean of all plots at the same site and acquisition",
        "observed at cutoff",
    ),
}
FIXED = {
    "plot_id": (
        "Plot id, `<site>-<experiment>-<range>-<row>` (same convention as the practice pipeline)",
        "identifier",
    ),
    "site_id": ("Site (location)", "identifier"),
    "cutoff": (
        "records_only, TP1 ... TP6: the latest satellite acquisition this row may use",
        "identifier",
    ),
    "cutoff_tp": ("0 for records_only, k for TPk", "identifier"),
    "as_of_date": (
        "Date the row describes: planting date for records_only, else the site's TPk acquisition date",
        "identifier",
    ),
    "field_id": ("Site and experiment (trial) the plot belongs to", "known at planting"),
    "experiment": (
        "Experiment / trial code from the file name or ground truth",
        "known at planting",
    ),
    "genotype": ("Hybrid planted", "known at planting"),
    "nitrogen_lb_ac": ("Nitrogen applied, lb/ac", "known at planting"),
    "irrigated": ("Site irrigated (any irrigation recorded at the site)", "known at planting"),
    "planting_date": ("Planting date (site mode fills a missing plot date)", "known at planting"),
    "planting_day_of_year": ("Day of year of planting", "known at planting"),
    "days_after_planting": ("as_of_date - planting_date, days", "timing"),
    "satellite_images_available": (
        "Usable satellite images of this plot on or before as_of_date",
        "cumulative to cutoff",
    ),
    "latest_image_tp": ("Time point of the latest usable image", "observed at cutoff"),
    "latest_image_date": (
        "Acquisition date of the latest usable image (always <= as_of_date)",
        "observed at cutoff",
    ),
    "latest_image_dap": ("Days after planting of the latest usable image", "timing"),
    "days_since_latest_image": (
        "as_of_date - latest image date; > 0 when this plot's TPk image is missing",
        "timing",
    ),
    "days_since_previous_satellite_image": (
        "Days between the latest and the previous usable image",
        "timing",
    ),
    "cur_valid_fraction": (
        "Valid plot pixels / all pixels in the bounding box, latest image",
        "QA",
    ),
    "cur_n_valid_pixels": ("Valid plot pixels in the latest image", "QA"),
    "cur_image_flags": (
        "Per-image flags on the latest image (low_valid_pixels, small_footprint, saturated, index_out_of_range, negative_ndvi); text, not a model input",
        "QA",
    ),
    "cur_image_flag_count": ("Number of per-image flags on the latest image", "QA"),
    "images_flagged_to_date": ("Images so far with at least one per-image flag", "QA"),
    "final_yield": (
        "Harvested grain yield, bu/ac at 15.5% moisture. The target: never a feature",
        "target",
    ),
}


def describe(column: str) -> tuple[str, str]:
    """(meaning, availability) for any column the tables can contain."""
    if column in FIXED:
        return FIXED[column]
    if column.startswith("uav_") or column == "days_since_uav_image":
        return _uav(column)
    if column.startswith("cur_"):
        name = column[len("cur_") :]
        if name == "ndvi_cover_frac":
            return (
                f"Share of valid pixels with NDVI > {COVER_NDVI_THRESHOLD} (canopy-cover proxy), latest image",
                "observed at cutoff",
            )
        if name.endswith("_core_mean"):
            idx = name[: -len("_core_mean")]
            return (
                f"Mean {idx.upper()} over the plot core (valid pixels one pixel in from the plot edge), latest image",
                "observed at cutoff",
            )
        for b in DEFAULT_BANDS:
            for s in STATS:
                if name == f"{b}_{s}":
                    return (
                        f"{STAT_TEXT[s].capitalize()} surface reflectance (0-1) of {BAND_TEXT[b]} over valid plot pixels, latest image",
                        "observed at cutoff",
                    )
        for i in INDICES:
            for s in STATS:
                if name == f"{i}_{s}":
                    return (
                        f"{STAT_TEXT[s].capitalize()} of per-pixel {INDEX_TEXT[i]}, latest image",
                        "observed at cutoff",
                    )
    for i in TEMPORAL_INDICES:
        for f, (text, avail) in TEMPORAL_TEXT.items():
            if column == f"{i}_{f}":
                return (f"{i.upper()} (plot mean of per-pixel values): {text}", avail)
        if column == f"{i}_vs_site_mean_avg_to_date":
            return (
                f"Mean over images so far of ({i.upper()} - same-date site mean)",
                "cumulative to cutoff",
            )
    raise KeyError(column)


def _uav(column: str) -> tuple[str, str]:
    fixed = {
        "uav_images_available": (
            "UAV flights of this plot on or before as_of_date",
            "cumulative to cutoff",
        ),
        "uav_latest_tp": ("UAV time point of the latest flight", "observed at cutoff"),
        "uav_latest_date": ("Date of the latest UAV flight (<= as_of_date)", "observed at cutoff"),
        "days_since_uav_image": ("as_of_date - latest UAV flight date", "timing"),
    }
    if column in fixed:
        return fixed[column]
    text = {
        "r_mean": "mean red digital number / 255",
        "g_mean": "mean green digital number / 255",
        "b_mean": "mean blue digital number / 255",
        "exg_mean": "mean excess green ExG = 2g - r - b (chromatic coordinates)",
        "exg_std": "standard deviation of ExG (canopy colour variation)",
        "exg_p10": "10th percentile of ExG",
        "exg_p90": "90th percentile of ExG",
        "exgr_mean": "mean ExGR = ExG - (1.4r - g)",
        "ngrdi_mean": "mean NGRDI = (G - R) / (G + R)",
        "ngrdi_std": "standard deviation of NGRDI",
        "vari_mean": "mean VARI = (G - R) / (G + R - B), |VARI| > 1 dropped",
        "green_frac": "share of plot pixels with ExGR > 0 (canopy-cover proxy)",
        "texture": "mean absolute grey-level difference between neighbouring plot pixels",
    }
    for c in UAV_CURRENT:
        if column == f"uav_{c}_current":
            return (f"UAV RGB, latest flight: {text[c]}", "observed at cutoff")
    for c in UAV_CHANGE:
        if column == f"uav_{c}_change_from_previous":
            return (f"UAV RGB: change in {c} since the previous flight", "cumulative to cutoff")
    raise KeyError(column)


def dictionary_markdown(planting_known: list[str] | None = None, counts: dict | None = None) -> str:
    known = list(planting_known if planting_known is not None else PLANTING_KNOWN)
    cols = schema(known)
    lines = [
        "# Feature dictionary: progressive satellite (and UAV) features",
        "",
        "Generated by `python -m soilsignal_ml.imagery dictionary` from the column lists in "
        "`ml/soilsignal_ml/imagery/`. One row per plot x cutoff in `satellite_features.parquet`; "
        "`progressive/<cutoff>.parquet` holds the same rows split by cutoff.",
        "",
        "**Availability**: *known at planting* (design and management); *observed at cutoff* (the latest "
        "satellite image on or before `as_of_date`); *cumulative to cutoff* (every image on or before "
        "`as_of_date`); *timing* (date arithmetic); *QA*; *identifier*; *target*. For a TPk row, "
        "nothing comes from an image after the site's TPk acquisition.",
        "",
        "Reflectance is the 16-bit value / 10,000. Index statistics are computed per pixel over valid "
        "plot pixels, then summarised. A value is missing when it can't be computed yet (e.g. "
        "`*_previous`, `*_trend` and `*_area_to_date` need two images, so they are empty at TP1).",
        "",
    ]
    if counts:
        lines += ["Column counts: " + ", ".join(f"{k}: {v}" for k, v in counts.items()), ""]
    lines += [
        "## Satellite progressive table",
        "",
        "| Column | Meaning | Availability |",
        "|---|---|---|",
    ]
    for c in cols:
        meaning, avail = describe(c)
        lines.append(f"| `{c}` | {meaning} | {avail} |")
    lines += [
        "",
        "Index means for NDVI, NDRE, GNDVI and EVI appear once, as `<index>_current`; "
        "`cur_<index>_mean` would duplicate them and is not written.",
        "",
        "## UAV columns (`satellite_uav_features.parquet`)",
        "",
        "Joined by flight date: a flight counts for a row only if it was on or before `as_of_date`.",
        "",
        "| Column | Meaning | Availability |",
        "|---|---|---|",
    ]
    for c in uav_columns():
        meaning, avail = describe(c)
        lines.append(f"| `{c}` | {meaning} | {avail} |")
    lines += [
        "",
        "## Per-image table (`satellite_image_features.parquet`)",
        "",
        "One row per TIFF. Besides the identifiers (`path`, `site_id`, `time_point`, `plot_id`, "
        "`experiment`, `range`, `row`, `sha1`, `date`), it has the raw statistics the progressive "
        "table draws on (`<band>_<stat>`, `<index>_<stat>`, `ndvi_cover_frac`, `<index>_core_mean`) and "
        "the masking and format metadata: `height`, `width`, `n_bands`, `dtype`, `layout`, "
        "`compression`, `band_names`, `band_order_source`, `band_order_agrees`, `nodata`, "
        "`pixel_size_x/y`, `epsg`, `centroid_x/y` (map units, valid-pixel centroid), "
        "`reflectance_scale`, `n_pixels_total`, `n_padding`, `n_in_plot`, `n_valid`, `n_invalid`, "
        "`n_saturated`, `n_nonpositive`, `n_near_zero` (valid pixels with a band < 0.001), `n_core`, `valid_fraction`, `valid_fraction_of_plot`, "
        "`<index>_n_out_of_range`, `brightest_band`, `error`, `extractor_version`.",
        "",
        f"Core statistics ({', '.join(CORE_INDICES)}) use a 3x3 erosion of the valid mask.",
        "",
        "Planting-known columns are an allow-list: "
        + ", ".join(f"`{c}`" for c in PLANTING_KNOWN)
        + ". In-season or post-season ground truth (stand count, anthesis dates, GDD to anthesis) "
        "is never copied into the tables.",
        "",
        f"Relative-to-site averages over the season exist for {', '.join(RELATIVE_AVG_INDICES)} only. "
        f"Temporal features per index: {', '.join(TEMPORAL_FEATURES)}.",
    ]
    return "\n".join(lines) + "\n"
