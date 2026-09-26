"""
Challenge dataset (SyDAg26 IoT4Ag hackathon): ground truth, acquisition dates and a
manifest of every satellite and UAV plot image, joined on one plot key.

    year + site + experiment + range + row  ->  plot_id  ->  ground truth, dates, images

Inputs, a local copy of the organizers' shared folder (default ml/data/raw/challenge/):

    GroundTruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv   one row per plot (authoritative key + target)
    GroundTruth/DateofCollection.xlsx           location + sensor + TPn -> acquisition date
    Satellite/<Location>/TP1..TP6/<Location>-TPn-<experiment>_<range>_<row>.TIF
    UAV/<Location>/TP1..TP3/<Location>-TPn-<experiment>_<range>_<row>.PNG

When the images are not on disk (tonight they were only reachable through the Drive
connector), the file list can come from a Drive listing instead: every name and size is
then inventoried and joined, and the per-file raster metadata is filled in later by the
same command once the files are local. Nothing is dropped: files that do not parse, match
no plot, or duplicate another file stay in the manifest with a status saying so.

Outputs (default ml/data/challenge/, see write_outputs):

    plots.parquet, acquisition_dates.parquet, sites.parquet,
    satellite_manifest.parquet, uav_manifest.parquet, observations.parquet,
    drive_inventory.parquet, challenge_manifest.json
"""

import json
import re
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from soilsignal_ml import ML_ROOT
from soilsignal_ml.ingest.imagery import read_metadata

RAW_ROOT = ML_ROOT / "data" / "raw" / "challenge"
OUT_ROOT = ML_ROOT / "data" / "challenge"
GROUND_TRUTH_CSV = "GroundTruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv"
DATES_XLSX = "GroundTruth/DateofCollection.xlsx"

Progress = Callable[[str], None]

# Folder name -> sensor, and the image format each sensor uses.
SENSOR_FOLDERS = {"Satellite": "satellite", "UAV": "uav"}
SENSOR_EXTENSIONS = {"satellite": {"tif", "tiff"}, "uav": {"png"}}
SENSOR_TIME_POINTS = {"satellite": 6, "uav": 3}

# <Location>-<TPn>-<experiment>_<range>_<row>.<ext>, e.g. Ames-TP3-4231_17_3.TIF. The
# experiment code may itself contain "_" only if followed by the two numeric fields, so the
# last two "_" fields are always range and row (the organizers' notebook splits the same way).
FILENAME = re.compile(
    r"^(?P<location>[^-]+)-(?P<time_point>TP\d+)-(?P<experiment>.+)"
    r"_(?P<range>\d+)_(?P<row>\d+)\.(?P<ext>[A-Za-z]+)$"
)

# Location names in DateofCollection.xlsx (and its second sheet's typos) -> site_id, which
# is the ground-truth `location` value (also the image folder and file name prefix).
SITE_ALIASES = {
    "Missouri Valley": "MOValley",
    "Crawfordville": "Crawfordsville",
    "ScottsBluff": "Scottsbluff",
    "North Platte": "NorthPlatte",
}
# Site facts that are not in the files: state from the organizers' site names; the reference
# coordinates are the mean satellite plot centroid per site from the practice run on the
# same imagery (ml/experiments/reports/dataset_profile.md). Plot coordinates are always
# computed from this run's own images; these only locate a site for public weather/soil
# when its images are not local yet.
SITE_FACTS = {
    "Ames": {"state": "IA", "ref_latitude": 42.014, "ref_longitude": -93.734},
    "Crawfordsville": {"state": "IA", "ref_latitude": 41.199, "ref_longitude": -91.487},
    "Lincoln": {"state": "NE", "ref_latitude": 40.852, "ref_longitude": -96.615},
    "MOValley": {"state": "IA", "ref_latitude": 41.671, "ref_longitude": -95.942},
    "Scottsbluff": {"state": "NE", "ref_latitude": 41.950, "ref_longitude": -103.703},
    "NorthPlatte": {"state": "NE", "ref_latitude": None, "ref_longitude": None},
}


def site_id(name: str) -> str:
    name = str(name).strip()
    return SITE_ALIASES.get(name, name)


def make_plot_id(year: int, site: str, experiment: str | None, rng: int, row: int) -> str:
    """2022-Ames-4231-17-3. Experiment missing in the ground truth becomes "NA"."""
    exp = "NA" if experiment is None or pd.isna(experiment) else str(experiment)
    return f"{int(year)}-{site}-{exp}-{int(rng)}-{int(row)}"


def practice_plot_id(site: str, experiment: str | None, rng: int, row: int) -> str:
    """The id the practice pipeline (shrestha2024) gave the same physical plot."""
    exp = "NA" if experiment is None or pd.isna(experiment) else str(experiment)
    return f"{site}-{exp}-{int(rng)}-{int(row)}"


# ---- ground truth --------------------------------------------------------------------


def load_plots(csv_path: Path) -> pd.DataFrame:
    """One row per ground-truth plot, every source row kept, with the challenge plot key.

    - nitrogen: poundsOfNitrogenPerAcre is 0 on every row without a genotype (fill/border
      plots) and never a real treatment in this trial, so a 0 on a plot without a genotype
      or treatment becomes null (nitrogen_placeholder_zero records it).
    - irrigated: irrigationProvided > 0 (Scottsbluff 16.9, else 0); null when missing.
    - planting_date stays as recorded; planting_date_filled adds the one date shared by the
      plot's site + experiment for the fill plots that have none (planting_date_source).
    - year: planting year (2022); fill plots take their site's single year.
    """
    raw = pd.read_csv(csv_path, dtype={"experiment": "string", "qrCode": "string"})
    df = pd.DataFrame(
        {
            "gt_row": np.arange(len(raw)),  # position in the CSV (the notebook's record id)
            "gt_index": raw["index"].astype("Int64"),  # the CSV's own index; not unique
            "qr_code": raw["qrCode"],
            "site_id": raw["location"].map(site_id).astype("string"),
            "experiment": raw["experiment"],
            "range": raw["range"].astype(int),
            "row": raw["row"].astype(int),
            "block": raw["block"].astype("Int64"),
            "plot_number": raw["plotNumber"].astype("Int64"),
            "genotype": raw["genotype"].astype("string"),
            "nitrogen_treatment": raw["nitrogenTreatment"].astype("string"),
            "nitrogen_lb_ac_raw": raw["poundsOfNitrogenPerAcre"].astype(float),
            "irrigation_provided": raw["irrigationProvided"].astype(float),
            "plot_length_ft": raw["plotLength"].astype(float),
            "planting_date": pd.to_datetime(raw["plantingDate"], errors="coerce").dt.date,
            "total_stand_count": raw["totalStandCount"].astype(float),
            "days_to_anthesis": raw["daysToAnthesis"].astype(float),
            "gdd_to_anthesis": raw["GDDToAnthesis"].astype(float),
            "final_yield": raw["yieldPerAcre"].astype(float),
        }
    )
    placeholder = (df["nitrogen_lb_ac_raw"] == 0) & (
        df["genotype"].isna() | df["nitrogen_treatment"].isna()
    )
    df["nitrogen_placeholder_zero"] = placeholder
    df["nitrogen_lb_ac"] = df["nitrogen_lb_ac_raw"].where(~placeholder)
    df["irrigated"] = (df["irrigation_provided"] > 0).astype("boolean")
    df.loc[df["irrigation_provided"].isna(), "irrigated"] = pd.NA
    df["is_hybrid_plot"] = df["genotype"].notna()

    planted = pd.to_datetime(df["planting_date"])
    shared = (
        df.assign(_p=planted)
        .dropna(subset=["_p"])
        .groupby(["site_id", "experiment"], dropna=False)["_p"]
        .agg(lambda s: s.iloc[0] if s.nunique() == 1 else pd.NaT)
    )
    fill = [
        shared.get((s, e), pd.NaT) if pd.isna(p) else p
        for s, e, p in zip(df["site_id"], df["experiment"], planted, strict=True)
    ]
    df["planting_date_filled"] = pd.to_datetime(pd.Series(fill, index=df.index)).dt.date
    df["planting_date_source"] = np.where(
        planted.notna(),
        "ground_truth",
        np.where(pd.Series(fill).notna(), "site_experiment_date", "missing"),
    )
    years = planted.dt.year.groupby(df["site_id"]).agg(lambda s: sorted(s.dropna().unique()))
    multi = {s: y for s, y in years.items() if len(y) != 1}
    if multi:
        raise ValueError(f"expected one season per site, found {multi}")
    df["year"] = df["site_id"].map({s: int(y[0]) for s, y in years.items()}).astype(int)

    df["plot_id"] = [
        make_plot_id(y, s, e, r, w)
        for y, s, e, r, w in zip(
            df["year"], df["site_id"], df["experiment"], df["range"], df["row"], strict=True
        )
    ]
    df["practice_plot_id"] = [
        practice_plot_id(s, e, r, w)
        for s, e, r, w in zip(df["site_id"], df["experiment"], df["range"], df["row"], strict=True)
    ]
    # One trial block per site + experiment code: a single nitrogen rate at Ames and
    # Crawfordsville, all three rates at Lincoln.
    df["field_id"] = [
        f"{y}-{s}-{'NA' if pd.isna(e) else e}"
        for y, s, e in zip(df["year"], df["site_id"], df["experiment"], strict=True)
    ]
    dup = df["plot_id"].duplicated(keep=False)
    if dup.any():
        raise ValueError(
            f"duplicate plot keys in the ground truth: {df.loc[dup, 'plot_id'].tolist()}"
        )
    first = ["plot_id", "year", "site_id", "field_id", "experiment", "range", "row"]
    return df[first + [c for c in df.columns if c not in first]]


# ---- acquisition dates ---------------------------------------------------------------


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%m/%d/%y").date()


def load_acquisition_dates(xlsx_path: Path) -> pd.DataFrame:
    """Sheet1 of DateofCollection.xlsx: Location, Date, Image (Satellite/UAV), time (TPn).
    TP numbers are per site and sensor; the same TP is a different date elsewhere."""
    from openpyxl import load_workbook

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    rows = list(wb["Sheet1"].iter_rows(values_only=True))
    header = [str(h).strip() for h in rows[0]]
    need = ["Location", "Date", "Image", "time"]
    if header[:4] != need:
        raise ValueError(f"unexpected DateofCollection header {header}, expected {need}")
    out = []
    for loc, day, image, tp in (r[:4] for r in rows[1:]):
        if loc is None:
            continue
        sensor = SENSOR_FOLDERS.get(str(image).strip())
        if sensor is None:
            raise ValueError(f"unknown image type {image!r} in DateofCollection.xlsx")
        d = _as_date(day)
        out.append(
            {
                "site_id": site_id(loc),
                "location_label": str(loc).strip(),
                "sensor": sensor,
                "time_point": str(tp).strip().upper(),
                "date": d,
                "year": d.year,
                "day_of_year": d.timetuple().tm_yday,
            }
        )
    df = pd.DataFrame(out)
    df["tp_index"] = df["time_point"].str.removeprefix("TP").astype(int)
    if df.duplicated(["site_id", "sensor", "time_point"]).any():
        raise ValueError("DateofCollection.xlsx lists a site/sensor/time point twice")
    # TP order must be chronological within a site and sensor.
    for (s, sensor), g in df.groupby(["site_id", "sensor"]):
        g = g.sort_values("tp_index")
        if not g["date"].is_monotonic_increasing:
            raise ValueError(f"{s} {sensor}: time points are not in date order")
    return df.sort_values(["site_id", "sensor", "tp_index"]).reset_index(drop=True)


# ---- image files -----------------------------------------------------------------------

FILE_COLUMNS = [
    "rel_path",
    "sensor_folder",
    "location_folder",
    "tp_folder",
    "filename",
    "size_bytes",
    "file_source",
    "local_path",
    "drive_id",
    "drive_created_time",
    "drive_modified_time",
]


def _split_rel(rel: str) -> tuple[str, str, str, str]:
    parts = rel.split("/")
    if len(parts) != 4:
        return (parts[0] if parts else "", "", "", parts[-1] if parts else "")
    return parts[0], parts[1], parts[2], parts[3]


def local_files(root: Path) -> pd.DataFrame:
    """Every file under Satellite/ and UAV/ (any depth, so misplaced files show up)."""
    rows = []
    for top in SENSOR_FOLDERS:
        base = root / top
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = p.relative_to(root).as_posix()
            sensor_folder, loc, tp, name = _split_rel(rel)
            rows.append(
                {
                    "rel_path": rel,
                    "sensor_folder": sensor_folder,
                    "location_folder": loc,
                    "tp_folder": tp,
                    "filename": name,
                    "size_bytes": p.stat().st_size,
                    "file_source": "local",
                    "local_path": str(p),
                }
            )
    return pd.DataFrame(rows, columns=FILE_COLUMNS)


def drive_listing_files(listing_dir: Path) -> tuple[pd.DataFrame, dict]:
    """Files from saved Drive listings (JSON {"files": [...]}, as the Drive connector returns
    them) plus folders.json (folder id -> "Satellite/Ames/TP1"). The same Drive file listed
    twice is kept once; two uploads of the same name are two files."""
    folders = json.loads((listing_dir / "folders.json").read_text())
    rows, seen, relisted = [], set(), 0
    for fn in sorted(listing_dir.glob("*.json")):
        if fn.name == "folders.json":
            continue
        for f in json.loads(fn.read_text())["files"]:
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            if f["id"] in seen:
                relisted += 1
                continue
            seen.add(f["id"])
            folder = folders.get(f["parentId"])
            rel = f"{folder}/{f['title']}" if folder else f"?/{f['title']}"
            sensor_folder, loc, tp, name = _split_rel(rel)
            rows.append(
                {
                    "rel_path": rel,
                    "sensor_folder": sensor_folder,
                    "location_folder": loc,
                    "tp_folder": tp,
                    "filename": name,
                    "size_bytes": int(f.get("fileSize", 0)),
                    "file_source": "drive_listing",
                    "drive_id": f["id"],
                    "drive_created_time": f.get("createdTime"),
                    "drive_modified_time": f.get("modifiedTime"),
                }
            )
    df = pd.DataFrame(rows, columns=FILE_COLUMNS)
    parents = {
        f
        for fn in listing_dir.glob("*.json")
        if fn.name != "folders.json"
        for f in (x["parentId"] for x in json.loads(fn.read_text())["files"])
    }
    empty = sorted(
        path for fid, path in folders.items() if not fid.startswith("_") and fid not in parents
    )
    return df, {"drive_listing_repeats_dropped": relisted, "empty_drive_folders": empty}


def inventory_files(inventory: Path) -> pd.DataFrame:
    """A saved drive_inventory.parquet (this module's own output) as the file list."""
    df = pd.read_parquet(inventory)
    df["file_source"] = "drive_inventory"
    for c in FILE_COLUMNS:
        if c not in df:
            df[c] = None
    return df[FILE_COLUMNS]


def combine_file_sources(local: pd.DataFrame, listed: pd.DataFrame) -> pd.DataFrame:
    """Local files win; listed files not on disk are kept (metadata pending). A listing with
    two uploads of one name keeps both only if the disk also has both (it cannot)."""
    if listed.empty:
        return local.reset_index(drop=True)
    if local.empty:
        return listed.reset_index(drop=True)
    on_disk = set(local["rel_path"])
    extra = listed[~listed["rel_path"].isin(on_disk)]
    # Drive fields for files that are also local (first listed copy).
    drive_cols = ["drive_id", "drive_created_time", "drive_modified_time"]
    first = listed.drop_duplicates("rel_path").set_index("rel_path")[drive_cols + ["size_bytes"]]
    local = local.copy()
    for c in drive_cols:
        local[c] = local["rel_path"].map(first[c])
    local["drive_size_bytes"] = local["rel_path"].map(first["size_bytes"])
    return pd.concat([local, extra], ignore_index=True)


# ---- manifests -------------------------------------------------------------------------


def parse_filenames(files: pd.DataFrame) -> pd.DataFrame:
    parsed = files["filename"].str.extract(FILENAME)
    out = files.copy()
    out["name_location"] = parsed["location"]
    out["time_point"] = parsed["time_point"].str.upper()
    out["experiment"] = parsed["experiment"]
    out["range"] = pd.to_numeric(parsed["range"]).astype("Int64")
    out["row"] = pd.to_numeric(parsed["row"]).astype("Int64")
    out["extension"] = parsed["ext"].str.lower()
    out["name_parsed"] = parsed["location"].notna()
    return out


def build_manifest(
    files: pd.DataFrame, plots: pd.DataFrame, dates: pd.DataFrame, sensor: str
) -> pd.DataFrame:
    """One row per file of one sensor, joined to its plot and acquisition date."""
    folder = next(k for k, v in SENSOR_FOLDERS.items() if v == sensor)
    df = parse_filenames(files[files["sensor_folder"] == folder]).reset_index(drop=True)
    df.insert(0, "sensor", sensor)
    df["site_id"] = df["name_location"].map(lambda s: site_id(s) if isinstance(s, str) else None)

    status = pd.Series("ok", index=df.index, dtype="string")
    status[~df["name_parsed"]] = "unparseable_name"
    ok = status == "ok"
    bad_ext = ok & ~df["extension"].isin(SENSOR_EXTENSIONS[sensor])
    status[bad_ext] = "wrong_file_type"
    ok = status == "ok"
    folder_mismatch = ok & (
        (df["name_location"] != df["location_folder"]) | (df["time_point"] != df["tp_folder"])
    )
    status[folder_mismatch] = "folder_name_mismatch"

    d = dates[dates["sensor"] == sensor][["site_id", "time_point", "date", "tp_index"]]
    df = df.merge(d, on=["site_id", "time_point"], how="left")
    status[(status == "ok") & df["date"].isna()] = "no_acquisition_date"

    key = ["site_id", "experiment", "range", "row"]
    p = plots[
        key
        + [
            "plot_id",
            "year",
            "field_id",
            "genotype",
            "final_yield",
            "planting_date_filled",
            "is_hybrid_plot",
        ]
    ].rename(columns={"planting_date_filled": "planting_date"})
    p = p.astype({"experiment": "string", "range": "Int64", "row": "Int64"})
    df = df.astype({"experiment": "string"}).merge(p, on=key, how="left")
    status[(status == "ok") & df["plot_id"].isna()] = "not_in_ground_truth"
    df["match_status"] = status

    # Duplicates: the same sensor + site + time point + plot more than once. The first
    # (by Drive upload time, then path) is kept for use; identical copies are expected.
    parts = [
        df[c].astype("string").fillna("?")
        for c in ("site_id", "time_point", "experiment", "range", "row")
    ]
    df["image_key"] = pd.Series(sensor, index=df.index, dtype="string").str.cat(parts, sep="|")
    order = df.sort_values(["image_key", "drive_created_time", "rel_path"], na_position="last")
    df["copy_index"] = order.groupby("image_key").cumcount().reindex(df.index)
    df["copies"] = df.groupby("image_key")["image_key"].transform("size")
    df["is_duplicate"] = df["copy_index"] > 0
    df["use"] = (df["match_status"] == "ok") & ~df["is_duplicate"]

    df["days_after_planting"] = [
        (a - b).days if pd.notna(a) and pd.notna(b) else pd.NA
        for a, b in zip(df["date"], df["planting_date"], strict=True)
    ]
    df["days_after_planting"] = df["days_after_planting"].astype("Int64")
    df["image_path"] = df["rel_path"]
    df["image_id"] = pd.Series(
        [
            k.replace("|", "-") + (f"-copy{int(c)}" if c > 0 else "")
            for k, c in zip(df["image_key"], df["copy_index"], strict=True)
        ],
        index=df.index,
        dtype="string",
    )
    first = [
        "image_id",
        "sensor",
        "plot_id",
        "site_id",
        "year",
        "time_point",
        "tp_index",
        "date",
        "days_after_planting",
        "experiment",
        "range",
        "row",
        "match_status",
        "is_duplicate",
        "use",
        "image_path",
        "size_bytes",
    ]
    return df[first + [c for c in df.columns if c not in first]]


# ---- raster metadata (restartable) ---------------------------------------------------


def _meta_job(args: tuple[str, str]) -> dict:
    path, sensor = args
    return {"local_path": path, **read_metadata(Path(path), sensor)}


def raster_metadata(
    manifest: pd.DataFrame,
    cache_path: Path,
    workers: int = 4,
    limit: int | None = None,
    progress: Progress = print,
    checkpoint_every: int = 200,
) -> pd.DataFrame:
    """Read every local image once. Results are cached by (path, size, mtime), saved every
    `checkpoint_every` files, so an interrupted run resumes where it stopped."""
    local = manifest.dropna(subset=["local_path"])[["local_path", "sensor"]].drop_duplicates()
    stamps = {p: (Path(p).stat().st_size, Path(p).stat().st_mtime_ns) for p in local["local_path"]}
    cache = pd.read_parquet(cache_path) if cache_path.exists() else pd.DataFrame()
    if len(cache):
        fresh = [
            stamps.get(p) == (s, m)
            for p, s, m in zip(cache["local_path"], cache["_size"], cache["_mtime_ns"], strict=True)
        ]
        cache = cache[fresh]
    done = set(cache["local_path"]) if len(cache) else set()
    todo = [(p, s) for p, s in local.itertuples(index=False) if p not in done]
    if limit is not None:
        todo = todo[:limit]
    progress(f"raster metadata: {len(done)} cached, {len(todo)} to read")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    batch: list[dict] = []

    def flush() -> None:
        nonlocal cache, batch
        if not batch:
            return
        new = pd.DataFrame(batch)
        new["_size"] = new["local_path"].map(lambda p: stamps[p][0])
        new["_mtime_ns"] = new["local_path"].map(lambda p: stamps[p][1])
        cache = pd.concat([cache, new], ignore_index=True) if len(cache) else new
        cache.to_parquet(cache_path, index=False)
        batch = []

    if todo:
        with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
            for i, meta in enumerate(pool.map(_meta_job, todo, chunksize=16), 1):
                batch.append(meta)
                if i % checkpoint_every == 0:
                    flush()
                    progress(f"  {i}/{len(todo)}")
        flush()
    return cache


def attach_metadata(manifest: pd.DataFrame, cache: pd.DataFrame) -> pd.DataFrame:
    if not len(cache):
        manifest = manifest.copy()
        manifest["metadata_status"] = np.where(
            manifest["local_path"].notna(), "pending", "not_local"
        )
        return manifest
    meta = cache.drop(columns=["_size", "_mtime_ns"], errors="ignore")
    # Only this sensor's images, and only the fields its reader produces.
    meta = meta[meta["local_path"].isin(manifest["local_path"])].dropna(axis=1, how="all")
    if "local_path" not in meta:
        meta = pd.DataFrame(columns=["local_path", "read_ok"])
    out = manifest.merge(meta, on="local_path", how="left")
    out["metadata_status"] = np.select(
        [out["local_path"].isna(), out["read_ok"].isna(), out["read_ok"].eq(True)],
        ["not_local", "pending", "read"],
        default="read_error",
    )
    if "sha256" in out:
        # Identical bytes under two names or places.
        h = out["sha256"].dropna()
        out["content_copies"] = out["sha256"].map(h.value_counts()).astype("Int64")
    return out


# ---- plot coordinates -----------------------------------------------------------------


def plot_coordinates(sat: pd.DataFrame) -> pd.DataFrame:
    """Plot centre = median over its satellite images of the valid-pixel centroid.
    Spread (m) across images is reported: they come from different acquisitions."""
    cols = {"centroid_lat", "centroid_lon", "centroid_x", "centroid_y", "crs_epsg"}
    if not cols <= set(sat.columns):
        return pd.DataFrame(columns=["plot_id", "latitude", "longitude"])
    s = sat[sat["use"] & sat["centroid_lat"].notna()]
    if s.empty:
        return pd.DataFrame(columns=["plot_id", "latitude", "longitude"])
    g = s.groupby("plot_id")
    out = pd.DataFrame(
        {
            "latitude": g["centroid_lat"].median(),
            "longitude": g["centroid_lon"].median(),
            "utm_epsg": g["crs_epsg"].agg(lambda v: int(v.mode().iloc[0])),
            "utm_x": g["centroid_x"].median(),
            "utm_y": g["centroid_y"].median(),
            "coord_images": g.size(),
            "coord_spread_m": g.apply(
                lambda d: float(
                    np.hypot(
                        d["centroid_x"] - d["centroid_x"].median(),
                        d["centroid_y"] - d["centroid_y"].median(),
                    ).max()
                ),
                include_groups=False,
            ).round(2),
        }
    ).reset_index()
    out["coord_source"] = "satellite_centroid"
    return out


# ---- build -------------------------------------------------------------------------------


@dataclass
class ChallengeTables:
    plots: pd.DataFrame
    acquisition_dates: pd.DataFrame
    sites: pd.DataFrame
    satellite: pd.DataFrame
    uav: pd.DataFrame
    files: pd.DataFrame
    listed: pd.DataFrame  # the Drive listing / inventory as given, before local files win
    notes: dict = field(default_factory=dict)

    def observations(self) -> pd.DataFrame:
        """Canonical observation rows: every usable, matched plot image of either sensor."""
        cols = [
            "plot_id",
            "date",
            "source",
            "time_point",
            "image_path",
            "image_id",
            "days_after_planting",
        ]
        parts = []
        for df in (self.satellite, self.uav):
            if len(df):
                parts.append(df[df["use"]].assign(source=df["sensor"])[cols])
        if not parts:
            return pd.DataFrame(columns=cols)
        return pd.concat(parts, ignore_index=True).sort_values(["plot_id", "date", "source"])


def build(
    raw_root: Path = RAW_ROOT,
    drive_listing: Path | None = None,
    inventory: Path | None = None,
    out_root: Path = OUT_ROOT,
    read_rasters: bool = True,
    workers: int = 4,
    limit: int | None = None,
    progress: Progress = print,
) -> ChallengeTables:
    progress(f"ground truth: {raw_root / GROUND_TRUTH_CSV}")
    plots = load_plots(raw_root / GROUND_TRUTH_CSV)
    dates = load_acquisition_dates(raw_root / DATES_XLSX)

    local = local_files(raw_root)
    notes: dict = {"local_files": len(local)}
    listed = pd.DataFrame(columns=FILE_COLUMNS)
    if drive_listing is not None:
        listed, extra = drive_listing_files(drive_listing)
        notes.update(extra)
    elif inventory is not None and inventory.exists():
        listed = inventory_files(inventory)
    notes["listed_files"] = len(listed)
    files = combine_file_sources(local, listed)
    progress(f"files: {len(local)} on disk, {len(listed)} listed, {len(files)} in total")

    sat = build_manifest(files, plots, dates, "satellite")
    uav = build_manifest(files, plots, dates, "uav")
    unknown = files[~files["sensor_folder"].isin(SENSOR_FOLDERS)]
    notes["files_outside_sensor_folders"] = unknown["rel_path"].tolist()

    cache = pd.DataFrame()
    if read_rasters:
        cache = raster_metadata(
            pd.concat([sat, uav]),
            out_root / "cache" / "raster_metadata.parquet",
            workers=workers,
            limit=limit,
            progress=progress,
        )
    sat = attach_metadata(sat, cache)
    uav = attach_metadata(uav, cache)

    coords = plot_coordinates(sat)
    plots = plots.merge(coords, on="plot_id", how="left")
    for c in ("utm_epsg", "coord_images"):
        if c in plots:
            plots[c] = plots[c].astype("Int64")
    if "coord_source" not in plots:
        plots["latitude"] = np.nan
        plots["longitude"] = np.nan
        plots["coord_source"] = pd.NA
    for sensor, df in (("satellite", sat), ("uav", uav)):
        used = df[df["use"]]
        plots[f"{sensor}_images"] = plots["plot_id"].map(used.groupby("plot_id").size())
        plots[f"{sensor}_images"] = plots[f"{sensor}_images"].fillna(0).astype(int)
        plots[f"{sensor}_time_points"] = plots["plot_id"].map(
            used.groupby("plot_id")["time_point"].agg(lambda s: ",".join(sorted(s)))
        )

    sites = build_sites(plots, dates)
    return ChallengeTables(plots, dates, sites, sat, uav, files, listed, notes)


def build_sites(plots: pd.DataFrame, dates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for s, g in plots.groupby("site_id"):
        facts = SITE_FACTS.get(s, {})
        lat = g["latitude"].mean() if g["latitude"].notna().any() else facts.get("ref_latitude")
        lon = g["longitude"].mean() if g["longitude"].notna().any() else facts.get("ref_longitude")
        planted = sorted({d for d in g["planting_date"].dropna()})
        d = dates[dates["site_id"] == s]
        rows.append(
            {
                "site_id": s,
                "name": s,
                "state": facts.get("state"),
                "latitude": lat,
                "longitude": lon,
                "coord_source": "plot_centroids"
                if g["latitude"].notna().any()
                else ("practice_site_reference" if lat is not None else None),
                "year": int(g["year"].iloc[0]),
                "irrigated": bool(g["irrigated"].fillna(False).any()),
                "planting_dates": ",".join(str(p) for p in planted),
                "plots": len(g),
                "hybrid_plots": int(g["is_hybrid_plot"].sum()),
                "yield_plots": int(g["final_yield"].notna().sum()),
                "hybrids": int(g["genotype"].nunique()),
                "satellite_dates": ",".join(str(x) for x in d[d["sensor"] == "satellite"]["date"]),
                "uav_dates": ",".join(str(x) for x in d[d["sensor"] == "uav"]["date"]),
            }
        )
    return pd.DataFrame(rows)
