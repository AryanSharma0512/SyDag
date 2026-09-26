"""
SyDAg26 challenge data: file inventory, image manifests, acquisition dates and the
ground-truth join, written to ml/data/challenge/.

Reads the organizers' Drive folder as mirrored by `soilsignal_ml.ingest.gdrive`:

    <raw>/Documentation/                      README and example script
    <raw>/GroundTruth/                        DateofCollection.xlsx, plot-level CSV
    <raw>/Satellite/<location>/TP<n>/<image>.tif
    <raw>/UAV/<location>/TP<n>/<image>.png

Outputs (ml/data/challenge/):

    challenge_manifest.json     counts, anomalies, band-order evidence, provenance
    file_inventory.parquet      every file under <raw>: size, MD5, role, what it became
    plots.parquet               one row per ground-truth plot, image coverage, centroid
    ground_truth.parquet        the plot CSV unchanged, plus plot_id
    acquisition_dates.parquet   one row per location x source x time point
    satellite_manifest.parquet  one row per satellite image
    uav_manifest.parquet        one row per UAV image
    observations.parquet        plot_id, date, source, time_point, image_path per matched image

Nothing is dropped: an image that matches no plot stays in its manifest with the reason.
Time points are never used as dates; every date comes from DateofCollection.xlsx.

    cd ml && uv run --project ../backend --group ml python -m soilsignal_ml challenge
"""

import hashlib
import json
import re
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile
from PIL import Image
from pyproj import Transformer

from soilsignal_ml import ML_ROOT

RAW = ML_ROOT / "data" / "raw" / "sydag26"
OUT = ML_ROOT / "data" / "challenge"
CACHE = ML_ROOT / "data" / "interim" / "challenge_scan_cache.parquet"

SOURCES = {"Satellite": "satellite", "UAV": "uav"}
IMAGE_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
IMAGE_NAME = re.compile(
    r"^(?P<site>[^-]+)-TP(?P<tp>\d+)-(?P<exp>.+?)_(?P<range>\d+)_(?P<row>\d+)$", re.I
)
TP_FOLDER = re.compile(r"^TP\s*(\d+)$", re.I)
EXPERIMENT_ALIASES = {"hyrbrids": "hybrids"}
SITE_ALIASES = {"missourivalley": "movalley"}

GT_COLUMNS = {
    "location": ("location", "site", "loc"),
    "experiment": ("experiment", "exp"),
    "range": ("range",),
    "row": ("row",),
    "year": ("year", "yr", "season"),
    "genotype": ("genotype", "hybrid", "pedigree"),
    "nitrogen_lb_ac": ("poundsofnitrogenperacre", "nitrogen_lb_ac", "nrate"),
    "planting_date": ("plantingdate", "planting_date"),
    "irrigation_provided": ("irrigationprovided", "irrigation"),
    "final_yield": ("yieldperacre", "yield_bu_ac", "yield"),
    "stand_count": ("totalstandcount", "standcount"),
    "days_to_anthesis": ("daystoanthesis",),
    "gdd_to_anthesis": ("gddtoanthesis",),
    "days_to_silk": ("daystosilk",),
    "gdd_to_silk": ("gddtosilk",),
    "plot_number": ("plotnumber", "plot"),
    "block": ("block",),
    "replicate": ("rep", "replicate"),
}


def _key(text: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def experiment_key(value: object) -> str:
    text = str(value).strip().lower()
    return EXPERIMENT_ALIASES.get(text, text)


def site_key(value: object) -> str:
    key = _key(value)
    return SITE_ALIASES.get(key, key)


def make_plot_id(site: str, year: int, experiment: str, rng: int, row: int) -> str:
    """Site first: the API labels plots by removing the site prefix."""
    return f"{site}-{int(year)}-{experiment_key(experiment)}-{int(rng)}-{int(row)}"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ---- per-image readers (run in worker processes) --------------------------------------


def _valid_extent(valid: np.ndarray) -> dict:
    rows, cols = np.nonzero(valid)
    if not rows.size:
        return {
            "valid_row_min": None,
            "valid_row_max": None,
            "valid_col_min": None,
            "valid_col_max": None,
            "valid_row_mean": None,
            "valid_col_mean": None,
        }
    return {
        "valid_row_min": int(rows.min()),
        "valid_row_max": int(rows.max()),
        "valid_col_min": int(cols.min()),
        "valid_col_max": int(cols.max()),
        "valid_row_mean": float(rows.mean()),
        "valid_col_mean": float(cols.mean()),
    }


def _gdal_band_descriptions(xml: str | None) -> list[str]:
    if not xml:
        return []
    found = re.findall(r'<Item name="DESCRIPTION" sample="(\d+)"[^>]*>([^<]*)</Item>', xml)
    return [d for _, d in sorted(found, key=lambda x: int(x[0]))]


def read_tiff(path: Path) -> dict:
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        n_pages = len(tif.pages)
        pixels = page.asarray()
        axes = page.axes
        geo = page.geotiff_tags or {}
        nodata = page.tags.valueof(42113)
        gdal_xml = page.tags.valueof(42112)
        info = {
            "n_pages": n_pages,
            "axes": axes,
            "dtype": str(pixels.dtype),
            "photometric": str(page.photometric.name),
            "planar_config": str(page.planarconfig.name),
            "compression": str(page.compression.name),
            "bits_per_sample": int(np.atleast_1d(page.bitspersample)[0]),
            "extra_samples": len(page.extrasamples or ()),
            "nodata": None if nodata is None else str(nodata).strip("\x00 "),
            "band_descriptions": "|".join(_gdal_band_descriptions(gdal_xml)),
            "is_geotiff": bool(page.is_geotiff),
        }
    if "S" in axes:
        pixels = np.moveaxis(pixels, axes.index("S"), -1)
    elif pixels.ndim == 2:
        pixels = pixels[..., None]
    height, width, bands = pixels.shape
    data = pixels.astype(float)
    finite = np.isfinite(data).all(axis=2)
    zero = (data == 0).all(axis=2)
    missing = ~finite | zero
    if info["nodata"] not in (None, ""):
        try:
            missing |= (data == float(info["nodata"])).all(axis=2)
        except ValueError:
            pass
    valid = ~missing & (data != 0).all(axis=2)
    partial = ~missing & ~valid
    info |= {
        "height": height,
        "width": width,
        "n_bands": bands,
        "n_pixels": height * width,
        "n_valid_pixels": int(valid.sum()),
        "n_zero_pixels": int(zero.sum()),
        "n_partial_zero_pixels": int(partial.sum()),
        "n_nonfinite_pixels": int((~finite).sum()),
        "pixel_md5": hashlib.md5(
            np.ascontiguousarray(pixels).tobytes() + str(pixels.shape).encode()
        ).hexdigest(),
        **_valid_extent(valid),
    }
    for b in range(bands):
        v = data[..., b][valid]
        info[f"b{b + 1}_valid_mean"] = float(v.mean()) if v.size else None
        info[f"b{b + 1}_max"] = float(np.nanmax(data[..., b])) if finite.any() else None
    info |= _georeference(geo, height, width, info)
    return info


def _georeference(geo: dict, height: int, width: int, info: dict) -> dict:
    epsg = geo.get("ProjectedCSTypeGeoKey") or geo.get("GeographicTypeGeoKey")
    out = {
        "epsg": None,
        "raster_type": str(geo.get("GTRasterTypeGeoKey", "")) or None,
        "pixel_size_x": None,
        "pixel_size_y": None,
        "min_x": None,
        "min_y": None,
        "max_x": None,
        "max_y": None,
        "centroid_x": None,
        "centroid_y": None,
    }
    try:
        out["epsg"] = int(epsg) if epsg is not None else None
    except (TypeError, ValueError):
        out["epsg"] = None
    if out["epsg"] == 32767:
        out["epsg"] = None
    scale, tie = geo.get("ModelPixelScale"), geo.get("ModelTiepoint")
    matrix = geo.get("ModelTransformation")
    if scale and tie and not isinstance(tie[0], list):
        sx, sy = float(scale[0]), float(scale[1])
        i, j, x, y = float(tie[0]), float(tie[1]), float(tie[3]), float(tie[4])

        def to_map(col: float, row: float) -> tuple[float, float]:
            return x + (col - i) * sx, y - (row - j) * sy

    elif matrix:
        m = np.array(matrix, dtype=float).reshape(4, 4)
        sx, sy = float(abs(m[0, 0])), float(abs(m[1, 1]))

        def to_map(col: float, row: float) -> tuple[float, float]:
            return m[0, 0] * col + m[0, 1] * row + m[0, 3], m[1, 0] * col + m[1, 1] * row + m[1, 3]

    else:
        return out
    corners = [to_map(c, r) for c, r in ((0, 0), (width, 0), (0, height), (width, height))]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    out |= {
        "pixel_size_x": sx,
        "pixel_size_y": sy,
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
    }
    if info.get("valid_col_mean") is not None:
        cx, cy = to_map(info["valid_col_mean"] + 0.5, info["valid_row_mean"] + 0.5)
        out |= {"centroid_x": cx, "centroid_y": cy}
    return out


def read_png(path: Path) -> dict:
    with Image.open(path) as im:
        mode, (width, height) = im.mode, im.size
        meta = {k: v for k, v in im.info.items() if isinstance(v, str | int | float)}
        pixels = np.asarray(im)
    if pixels.ndim == 2:
        pixels = pixels[..., None]
    channels = pixels.shape[2]
    color = pixels[..., :3] if channels >= 3 else pixels
    zero = (color == 0).all(axis=2)
    valid = ~zero
    if mode in ("RGBA", "LA"):
        valid &= pixels[..., -1] > 0
    info = {
        "mode": mode,
        "dtype": str(pixels.dtype),
        "height": height,
        "width": width,
        "n_bands": channels,
        "n_pixels": height * width,
        "n_valid_pixels": int(valid.sum()),
        "n_zero_pixels": int(zero.sum()),
        "has_alpha": mode in ("RGBA", "LA"),
        "png_info": json.dumps(meta, default=str)[:500] if meta else None,
        "pixel_md5": hashlib.md5(
            np.ascontiguousarray(pixels).tobytes() + str(pixels.shape).encode()
        ).hexdigest(),
        **_valid_extent(valid),
    }
    for b in range(min(channels, 3)):
        v = pixels[..., b][valid]
        info[f"b{b + 1}_valid_mean"] = float(v.mean()) if v.size else None
    return info


def _scan_one(args: tuple[str, str]) -> dict:
    raw, rel = args
    path = Path(raw) / rel
    row = {"image_path": rel, "file_md5": md5(path), "read_error": None}
    try:
        reader = read_png if path.suffix.lower() == ".png" else read_tiff
        row |= reader(path)
    except Exception as error:
        row["read_error"] = f"{type(error).__name__}: {error}"[:300]
    return row


# ---- inventory and manifests -----------------------------------------------------------


def inventory(raw: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(p for p in raw.rglob("*") if p.is_file()):
        rel = path.relative_to(raw).as_posix()
        if rel == "drive_listing.json" or rel.endswith(".part"):
            continue
        stat = path.stat()
        top = rel.split("/", 1)[0]
        rows.append(
            {
                "path": rel,
                "top_folder": top,
                "name": path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return pd.DataFrame(rows)


def _parse_location(rel: str) -> dict:
    parts = rel.split("/")
    out = {"folder_location": None, "folder_tp": None, "folder_depth_ok": False}
    if len(parts) == 4:
        tp = TP_FOLDER.match(parts[2])
        out |= {
            "folder_location": parts[1],
            "folder_tp": int(tp[1]) if tp else None,
            "folder_depth_ok": bool(tp),
        }
    elif len(parts) >= 3:
        out["folder_location"] = parts[1]
    return out


def parse_image_name(stem: str) -> dict:
    m = IMAGE_NAME.match(stem)
    if not m:
        return {"name_site": None, "name_tp": None, "experiment": None, "range": None, "row": None}
    return {
        "name_site": m["site"],
        "name_tp": int(m["tp"]),
        "experiment": experiment_key(m["exp"]),
        "range": int(m["range"]),
        "row": int(m["row"]),
    }


def scan_images(raw: Path, files: pd.DataFrame, workers: int, cache: Path = CACHE) -> pd.DataFrame:
    images = files[files["top_folder"].isin(SOURCES) & files["suffix"].isin(IMAGE_SUFFIXES)].copy()
    cached = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    if len(cached):
        merged = images[["path", "size_bytes", "mtime_ns"]].merge(
            cached,
            left_on=["path", "size_bytes", "mtime_ns"],
            right_on=["image_path", "size_bytes", "mtime_ns"],
            how="inner",
        )
        done = set(merged["path"])
    else:
        merged, done = pd.DataFrame(), set()
    todo = [p for p in images["path"] if p not in done]
    print(f"{len(images)} images, {len(done)} cached, reading {len(todo)}", flush=True)
    with ProcessPoolExecutor(workers) as pool:
        fresh = list(pool.map(_scan_one, [(str(raw), p) for p in todo], chunksize=16))
    scanned = pd.DataFrame(fresh)
    if len(scanned):
        scanned = scanned.merge(
            images[["path", "size_bytes", "mtime_ns"]], left_on="image_path", right_on="path"
        ).drop(columns="path")
    if len(merged):
        merged = merged.drop(columns="path")
    result = pd.concat([d for d in (merged, scanned) if len(d)], ignore_index=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache, index=False)
    return result


# ---- ground truth and dates ------------------------------------------------------------


def _pick(frame: pd.DataFrame, names: Iterable[str]) -> str | None:
    lookup = {_key(c): c for c in frame.columns}
    for name in names:
        if _key(name) in lookup:
            return lookup[_key(name)]
    return None


def find_ground_truth(raw: Path) -> tuple[Path, Path]:
    gt = raw / "GroundTruth"
    csvs = sorted(gt.glob("*.csv"))
    xlsx = sorted(p for p in gt.glob("*.xls*") if "date" in p.name.lower())
    if len(csvs) != 1 or len(xlsx) != 1:
        raise ValueError(
            f"expected one plot CSV and one dates workbook in {gt}, "
            f"found {[p.name for p in csvs]} and {[p.name for p in xlsx]}"
        )
    return csvs[0], xlsx[0]


def read_dates(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """One row per location x source x time point. Each row of the workbook is read for
    a location, a date, a source (Satellite/UAV) and a TP token, wherever they sit."""
    notes: list[str] = []
    rows = []
    sheets = pd.read_excel(path, sheet_name=None, header=None)
    for sheet, frame in sheets.items():
        header_row = None
        for i in range(min(len(frame), 10)):
            cells = [_key(v) for v in frame.iloc[i].tolist()]
            if any(c in ("location", "site") for c in cells) and any("date" in c for c in cells):
                header_row = i
                break
        if header_row is None:
            notes.append(f"sheet '{sheet}': no header row with Location and Date; skipped")
            continue
        header = [_key(v) for v in frame.iloc[header_row].tolist()]
        loc_col = next(i for i, c in enumerate(header) if c in ("location", "site"))
        date_col = next(i for i, c in enumerate(header) if "date" in c)
        for r in range(header_row + 1, len(frame)):
            values = frame.iloc[r].tolist()
            if all(pd.isna(v) for v in values):
                continue
            text = " ".join(
                str(v) for i, v in enumerate(values) if i not in (loc_col, date_col) and pd.notna(v)
            )
            source = re.search(r"satellite|uav|drone", text, re.I)
            tp = re.search(r"TP\s*(\d+)", text, re.I)
            raw_date = values[date_col]
            parsed = pd.to_datetime(raw_date, errors="coerce")
            rows.append(
                {
                    "sheet": sheet,
                    "sheet_row": r + 1,
                    "location_raw": None if pd.isna(values[loc_col]) else str(values[loc_col]),
                    "source": None
                    if not source
                    else ("satellite" if source[0].lower() == "satellite" else "uav"),
                    "time_point": int(tp[1]) if tp else None,
                    "date": None if pd.isna(parsed) else parsed.date(),
                    "date_raw": str(raw_date),
                    "row_text": text,
                }
            )
    dates = pd.DataFrame(rows)
    if dates.empty:
        raise ValueError(f"no acquisition dates parsed from {path.name}")
    bad = dates[dates[["location_raw", "source", "time_point", "date"]].isna().any(axis=1)]
    for r in bad.itertuples():
        notes.append(f"{r.sheet} row {r.sheet_row}: incomplete date row ({r.row_text!r})")
    return dates, notes


def read_ground_truth(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raw = pd.read_csv(path, low_memory=False)
    mapping = {canon: _pick(raw, names) for canon, names in GT_COLUMNS.items()}
    required = ("location", "experiment", "range", "row")
    missing = [c for c in required if mapping[c] is None]
    if missing:
        raise ValueError(f"ground truth has no column for {missing}; columns: {list(raw.columns)}")
    t = pd.DataFrame({canon: raw[col] for canon, col in mapping.items() if col is not None})
    t["location_raw"] = t["location"].astype("string").str.strip()
    t["experiment_raw"] = t["experiment"].astype("string").str.strip()
    t["experiment"] = t["experiment_raw"].map(experiment_key)
    for c in ("range", "row"):
        t[c] = pd.to_numeric(t[c], errors="coerce").astype("Int64")
    for c in (
        "nitrogen_lb_ac",
        "final_yield",
        "stand_count",
        "days_to_anthesis",
        "gdd_to_anthesis",
        "days_to_silk",
        "gdd_to_silk",
        "irrigation_provided",
    ):
        if c in t:
            t[c] = pd.to_numeric(t[c], errors="coerce")
    if "planting_date" in t:
        t["planting_date"] = pd.to_datetime(t["planting_date"], errors="coerce").dt.date
    if "genotype" in t:
        t["genotype"] = t["genotype"].astype("string").str.strip()
    if "irrigation_provided" in t:
        t["irrigated"] = (t["irrigation_provided"] > 0).where(t["irrigation_provided"].notna())
    return t, raw, {k: v for k, v in mapping.items() if v is not None}


# ---- joins -----------------------------------------------------------------------------


class SiteResolver:
    """Maps any spelling of a location (folder, file name, dates workbook) onto the
    ground truth's own location value."""

    def __init__(self, gt_locations: Iterable[str]) -> None:
        self.by_key = {site_key(v): v for v in gt_locations}

    def __call__(self, name: object) -> str | None:
        if name is None or (isinstance(name, float) and np.isnan(name)):
            return None
        return self.by_key.get(site_key(name))


def to_lonlat(frame: pd.DataFrame, x: str, y: str, epsg: str = "epsg") -> tuple[list, list]:
    lon, lat = [np.nan] * len(frame), [np.nan] * len(frame)
    for code, idx in frame.groupby(epsg).groups.items():
        tr = Transformer.from_crs(f"EPSG:{int(code)}", "EPSG:4326", always_xy=True)
        pos = [frame.index.get_loc(i) for i in idx]
        lo, la = tr.transform(frame.loc[idx, x].to_numpy(float), frame.loc[idx, y].to_numpy(float))
        for p, a, b in zip(pos, lo, la, strict=True):
            lon[p], lat[p] = a, b
    return lon, lat


def _bbox_wkt(frame: pd.DataFrame) -> list[str | None]:
    out: list[str | None] = [None] * len(frame)
    for code, idx in frame.dropna(subset=["epsg", "min_x"]).groupby("epsg").groups.items():
        tr = Transformer.from_crs(f"EPSG:{int(code)}", "EPSG:4326", always_xy=True)
        for i in idx:
            r = frame.loc[i]
            ring = [
                (r.min_x, r.min_y),
                (r.max_x, r.min_y),
                (r.max_x, r.max_y),
                (r.min_x, r.max_y),
                (r.min_x, r.min_y),
            ]
            pts = [tr.transform(a, b) for a, b in ring]
            out[frame.index.get_loc(i)] = (
                "POLYGON((" + ", ".join(f"{a:.8f} {b:.8f}" for a, b in pts) + "))"
            )
    return out


def build(raw: Path = RAW, out: Path = OUT, workers: int = 4, cache: Path = CACHE) -> dict:
    anomalies: list[str] = []
    files = inventory(raw)
    if files.empty:
        raise SystemExit(f"no files under {raw}; mirror the Drive folder first")
    listing_path = raw / "drive_listing.json"
    listing = json.loads(listing_path.read_text()) if listing_path.exists() else None

    gt_csv, dates_xlsx = find_ground_truth(raw)
    truth, truth_raw, gt_mapping = read_ground_truth(gt_csv)
    resolve = SiteResolver(truth["location_raw"].dropna().unique())
    truth["site_id"] = truth["location_raw"]

    dates, date_notes = read_dates(dates_xlsx)
    anomalies += date_notes
    dates["site_id"] = dates["location_raw"].map(resolve)
    for loc in sorted(dates.loc[dates["site_id"].isna(), "location_raw"].dropna().unique()):
        anomalies.append(f"dates workbook location {loc!r} matches no ground-truth location")
    dates["year"] = pd.to_datetime(dates["date"]).dt.year.astype("Int64")
    dup_dates = dates.dropna(subset=["site_id", "source", "time_point"]).duplicated(
        ["site_id", "source", "time_point"], keep=False
    )
    for r in dates[dup_dates].itertuples():
        anomalies.append(
            f"more than one date for {r.site_id} {r.source} TP{r.time_point}: {r.date}"
        )

    if "year" in truth and truth["year"].notna().any():
        truth["year"] = pd.to_numeric(truth["year"], errors="coerce").astype("Int64")
        truth["year_source"] = "ground_truth"
    else:
        site_year = (
            dates.dropna(subset=["site_id", "year"])
            .groupby("site_id")["year"]
            .agg(lambda s: sorted(set(s)))
        )
        multi = {s: y for s, y in site_year.items() if len(y) > 1}
        if multi:
            anomalies.append(f"acquisition dates span several years at {multi}")
        truth["year"] = truth["site_id"].map(lambda s: site_year.get(s, [None])[0]).astype("Int64")
        truth["year_source"] = "acquisition_dates"
        if truth["year"].isna().any() and "planting_date" in truth:
            fill = pd.to_datetime(truth["planting_date"]).dt.year.astype("Int64")
            truth.loc[truth["year"].isna(), "year_source"] = "planting_date"
            truth["year"] = truth["year"].fillna(fill)

    keyed = truth.dropna(subset=["site_id", "year", "experiment", "range", "row"])
    if len(keyed) < len(truth):
        anomalies.append(f"{len(truth) - len(keyed)} ground-truth rows lack site/exp/range/row")
    truth["plot_id"] = [
        make_plot_id(s, y, e, rg, rw) if i in keyed.index else None
        for i, s, y, e, rg, rw in zip(
            truth.index,
            truth["site_id"],
            truth["year"],
            truth["experiment"],
            truth["range"],
            truth["row"],
            strict=True,
        )
    ]
    dup_plot = truth["plot_id"].notna() & truth["plot_id"].duplicated(keep=False)
    truth["duplicate_plot_id"] = dup_plot

    scanned = scan_images(raw, files, workers, cache)
    manifests = {}
    for folder, source in SOURCES.items():
        m = scanned[scanned["image_path"].str.startswith(folder + "/")].copy()
        if m.empty:
            anomalies.append(f"no {folder} images found")
            manifests[source] = m
            continue
        loc = pd.DataFrame([_parse_location(p) for p in m["image_path"]], index=m.index)
        names = pd.DataFrame(
            [parse_image_name(Path(p).stem) for p in m["image_path"]], index=m.index
        )
        m = pd.concat([m, loc, names], axis=1)
        m.insert(0, "source", source)
        m["file_name"] = m["image_path"].map(lambda p: Path(p).name)
        m["file_type"] = m["file_name"].map(lambda n: Path(n).suffix.lower().lstrip("."))
        m["site_id"] = m["folder_location"].map(resolve)
        m["name_site_id"] = m["name_site"].map(resolve)
        m["time_point"] = m["folder_tp"]
        m["site_matches_name"] = m["site_id"].notna() & (m["site_id"] == m["name_site_id"])
        m["tp_matches_name"] = m["folder_tp"].notna() & (m["folder_tp"] == m["name_tp"])

        d = dates[dates["source"] == source].drop_duplicates(["site_id", "time_point"])
        m = m.merge(
            d[["site_id", "time_point", "date", "year"]].rename(columns={"date": "acq_date"}),
            on=["site_id", "time_point"],
            how="left",
        )
        key_cols = ["site_id", "year", "experiment", "range", "row"]
        gt_keys = truth.dropna(subset=["plot_id"]).drop_duplicates("plot_id")
        m["plot_id"] = [
            make_plot_id(*k) if all(pd.notna(v) for v in k) else None
            for k in m[key_cols].itertuples(index=False)
        ]
        known = set(gt_keys["plot_id"])
        m["in_ground_truth"] = m["plot_id"].isin(known)
        swapped = [
            make_plot_id(s, y, e, rw, rg) if all(pd.notna(v) for v in (s, y, e, rg, rw)) else None
            for s, y, e, rg, rw in m[key_cols].itertuples(index=False)
        ]
        m["matches_if_range_row_swapped"] = [
            (not hit) and (p in known) for hit, p in zip(m["in_ground_truth"], swapped, strict=True)
        ]
        m["match_status"] = np.select(
            [
                m["read_error"].notna(),
                m["experiment"].isna(),
                m["site_id"].isna(),
                m["time_point"].isna(),
                m["acq_date"].isna(),
                ~m["in_ground_truth"],
            ],
            [
                "unreadable",
                "unparsed_name",
                "unknown_site",
                "no_time_point",
                "no_date",
                "no_ground_truth_plot",
            ],
            default="matched",
        )
        m["duplicate_key"] = m["plot_id"].notna() & m.duplicated(
            ["plot_id", "time_point"], keep=False
        )
        content = m.groupby("file_md5")["image_path"].transform("count")
        m["duplicate_content"] = content > 1
        manifests[source] = m
        if m["matches_if_range_row_swapped"].sum() > m["in_ground_truth"].sum():
            anomalies.append(
                f"{source}: names line up with ground truth only with range/row "
                "swapped; check the orientation"
            )

    sat = manifests["satellite"]
    plots = truth.copy()
    if len(sat) and "centroid_x" in sat:
        ok = sat[
            (sat["match_status"] == "matched") & sat["centroid_x"].notna() & sat["epsg"].notna()
        ].copy()
        cent = ok.groupby("plot_id").agg(
            epsg=("epsg", lambda s: int(s.mode().iloc[0])),
            n_epsg=("epsg", "nunique"),
            centroid_x=("centroid_x", "median"),
            centroid_y=("centroid_y", "median"),
            centroid_spread_m=("centroid_x", lambda s: 0.0),
            min_x=("min_x", "min"),
            min_y=("min_y", "min"),
            max_x=("max_x", "max"),
            max_y=("max_y", "max"),
        )
        spread = ok.groupby("plot_id").apply(
            lambda g: float(
                np.hypot(
                    g["centroid_x"] - g["centroid_x"].median(),
                    g["centroid_y"] - g["centroid_y"].median(),
                ).max()
            ),
            include_groups=False,
        )
        cent["centroid_spread_m"] = spread
        cent = cent.reset_index()
        lon, lat = to_lonlat(cent, "centroid_x", "centroid_y")
        cent["longitude"], cent["latitude"] = lon, lat
        cent["footprint_wkt"] = _bbox_wkt(cent)
        plots = plots.merge(cent, on="plot_id", how="left")
        plots["coordinate_source"] = np.where(
            plots["latitude"].notna(), "satellite_valid_pixel_centroid", None
        )
    for source, m in manifests.items():
        if len(m):
            counts = m[m["match_status"] == "matched"].groupby("plot_id")["time_point"].nunique()
            plots[f"n_{source}_time_points"] = plots["plot_id"].map(counts).fillna(0).astype(int)

    obs = (
        pd.concat(
            [
                m.loc[
                    m["match_status"] == "matched",
                    [
                        "plot_id",
                        "acq_date",
                        "source",
                        "time_point",
                        "image_path",
                        "n_valid_pixels",
                        "duplicate_key",
                    ],
                ]
                for m in manifests.values()
                if len(m)
            ],
            ignore_index=True,
        )
        .rename(columns={"acq_date": "date"})
        .sort_values(["plot_id", "source", "date"])
    )

    files["role"] = np.select(
        [
            files["top_folder"].isin(SOURCES) & files["suffix"].isin(IMAGE_SUFFIXES),
            files["path"].isin([gt_csv.relative_to(raw).as_posix()]),
            files["path"].isin([dates_xlsx.relative_to(raw).as_posix()]),
            files["top_folder"] == "Documentation",
        ],
        ["image", "ground_truth_plots", "acquisition_dates", "documentation"],
        default="other",
    )
    status = pd.concat([m[["image_path", "match_status"]] for m in manifests.values() if len(m)])
    files = files.merge(status.rename(columns={"image_path": "path"}), on="path", how="left")
    if listing:
        drive = pd.DataFrame(listing["files"])[["path", "id", "md5Checksum"]].rename(
            columns={"id": "drive_file_id", "md5Checksum": "drive_md5"}
        )
        files = files.merge(drive, on="path", how="left")

    out.mkdir(parents=True, exist_ok=True)
    manifest = summarize(files, truth, plots, dates, manifests, obs, anomalies, gt_mapping)
    manifest["provenance"] = {
        "dataset": "sydag26",
        "raw_root": str(raw.relative_to(ML_ROOT)) if raw.is_relative_to(ML_ROOT) else str(raw),
        "drive_folder_id": listing["folder_id"] if listing else None,
        "drive_retrieved": listing["retrieved"] if listing else None,
        "ground_truth_file": gt_csv.relative_to(raw).as_posix(),
        "dates_file": dates_xlsx.relative_to(raw).as_posix(),
        "built": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_outputs(out, files, truth_raw, truth, plots, dates, manifests, obs, manifest)
    return manifest


def summarize(files, truth, plots, dates, manifests, obs, anomalies, gt_mapping) -> dict:
    per_tp = []
    for source, m in manifests.items():
        if not len(m):
            continue
        for (site, tp), g in m.groupby(["folder_location", "time_point"], dropna=False):
            dims = g.groupby(["height", "width"]).size().sort_values(ascending=False)
            per_tp.append(
                {
                    "source": source,
                    "location_folder": site,
                    "site_id": g["site_id"].iloc[0],
                    "time_point": None if pd.isna(tp) else int(tp),
                    "acq_date": None if g["acq_date"].isna().all() else str(g["acq_date"].iloc[0]),
                    "year": None if g["year"].isna().all() else int(g["year"].iloc[0]),
                    "file_types": sorted(g["file_type"].unique().tolist()),
                    "n_images": int(len(g)),
                    "n_matched": int((g["match_status"] == "matched").sum()),
                    "n_bands": sorted(g["n_bands"].dropna().astype(int).unique().tolist()),
                    "dtypes": sorted(g["dtype"].dropna().unique().tolist()),
                    "most_common_size_hw": [int(v) for v in dims.index[0]] if len(dims) else None,
                    "n_distinct_sizes": int(len(dims)),
                    "height_range": [int(g["height"].min()), int(g["height"].max())],
                    "width_range": [int(g["width"].min()), int(g["width"].max())],
                    "bytes_total": int(g["size_bytes"].sum()),
                    "median_valid_pixels": float(g["n_valid_pixels"].median()),
                    "n_no_valid_pixels": int((g["n_valid_pixels"] == 0).sum()),
                }
            )
    status = {
        source: m["match_status"].value_counts().to_dict()
        for source, m in manifests.items()
        if len(m)
    }
    unmatched = {
        source: m.loc[m["match_status"] != "matched", ["image_path", "match_status"]]
        .head(200)
        .to_dict("records")
        for source, m in manifests.items()
        if len(m)
    }
    by_site = []
    for site, g in truth.groupby("site_id", dropna=False):
        by_site.append(
            {
                "site_id": site,
                "year": None if g["year"].isna().all() else int(g["year"].mode().iloc[0]),
                "n_plots": int(len(g)),
                "n_with_final_yield": int(g["final_yield"].notna().sum())
                if "final_yield" in g
                else 0,
                "n_hybrids": int(g["genotype"].nunique()) if "genotype" in g else None,
                "experiments": sorted(g["experiment"].dropna().unique().tolist()),
                "n_with_satellite": int((plots.loc[g.index, "n_satellite_time_points"] > 0).sum())
                if "n_satellite_time_points" in plots
                else 0,
                "n_with_uav": int((plots.loc[g.index, "n_uav_time_points"] > 0).sum())
                if "n_uav_time_points" in plots
                else 0,
            }
        )
    missing = {c: int(truth[c].isna().sum()) for c in truth.columns if truth[c].isna().any()}
    return {
        "counts": {
            "files": int(len(files)),
            "files_by_top_folder": files["top_folder"].value_counts().to_dict(),
            "ground_truth_rows": int(len(truth)),
            "unique_plot_ids": int(truth["plot_id"].nunique()),
            "plots_with_final_yield": int(truth["final_yield"].notna().sum())
            if "final_yield" in truth
            else 0,
            "unique_hybrids": int(truth["genotype"].nunique()) if "genotype" in truth else None,
            "duplicate_plot_id_rows": int(truth["duplicate_plot_id"].sum()),
            "observations": int(len(obs)),
            "image_match_status": status,
            "duplicate_images_by_key": {
                s: int(m["duplicate_key"].sum()) for s, m in manifests.items() if len(m)
            },
            "duplicate_images_by_content": {
                s: int(m["duplicate_content"].sum()) for s, m in manifests.items() if len(m)
            },
        },
        "ground_truth_columns_used": gt_mapping,
        "ground_truth_missing_values": missing,
        "sites": by_site,
        "acquisitions": per_tp,
        "acquisition_dates": [
            {k: (str(v) if k == "date" else v) for k, v in r.items()}
            for r in dates.drop(columns=["row_text"])
            .astype(object)
            .where(dates.drop(columns=["row_text"]).notna(), None)
            .to_dict("records")
        ],
        "unmatched_images_first_200": unmatched,
        "anomalies": anomalies,
    }


def write_outputs(out, files, truth_raw, truth, plots, dates, manifests, obs, manifest) -> None:
    files.to_parquet(out / "file_inventory.parquet", index=False)
    gt = truth_raw.copy()
    gt.insert(0, "plot_id", truth["plot_id"])
    gt.to_parquet(out / "ground_truth.parquet", index=False)
    plots.to_parquet(out / "plots.parquet", index=False)
    dates.to_parquet(out / "acquisition_dates.parquet", index=False)
    for source, m in manifests.items():
        m.to_parquet(out / f"{source}_manifest.parquet", index=False)
    obs.to_parquet(out / "observations.parquet", index=False)
    (out / "challenge_manifest.json").write_text(json.dumps(manifest, indent=1, default=str) + "\n")
