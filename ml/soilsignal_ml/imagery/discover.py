"""
Find the plot images and the tables that give them meaning.

    images        one row per image file: modality, site, time point, plot id, path
    plots         one row per plot: planting date, final yield, and what was known at planting
    acquisitions  one row per site x modality x time point: the acquisition date

Every table can come from Agent 1's canonical outputs (a manifest, plots table and
acquisition table) or, as a fallback, straight from a data root laid out like the
Shrestha et al. (2024) publication the challenge data is drawn from:

    Satellite/<Site>/TP<n>/<Site>-TP<n>-<Experiment>_<range>_<row>.TIF
    UAV/<Site>/TP<n>/<...>.png
    GroundTruth/HYBRID_HIPS_V3.5_ALLPLOTS.csv
    GroundTruth/DateofCollection.xlsx

Folder names beyond the file name are only used when the file name alone doesn't parse.
"""

import re
from pathlib import Path

import pandas as pd

from soilsignal_ml.ingest.dataset_adapter import SITES, plot_id

SATELLITE_EXTS = {".tif", ".tiff"}
UAV_EXTS = {".png", ".jpg", ".jpeg"}
IMAGE_NAME = re.compile(
    r"(?P<site>[A-Za-z]+)[-_ ]TP[-_ ]?(?P<tp>\d+)[-_ ](?P<exp>.+?)_(?P<range>\d+)_(?P<row>\d+)$",
    re.I,
)
TP_DIR = re.compile(r"^TP[-_ ]?(\d+)$", re.I)

# Management and design columns known at planting. Nothing else from a plots table is
# passed through: stand counts, anthesis dates and yield components are in-season or
# post-season measurements and would leak.
PLANTING_KNOWN = ("field_id", "experiment", "genotype", "nitrogen_lb_ac", "irrigated")
IMAGE_COLUMNS = [
    "path",
    "modality",
    "site_id",
    "time_point",
    "plot_id",
    "experiment",
    "range",
    "row",
    "parse_method",
]


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


_SITE_ALIASES = {_key(k): k for k in SITES} | {_key(v[0]): k for k, v in SITES.items()}
_SITE_ALIASES |= {"northplatte": "NorthPlatte", "missourivalley": "MOValley"}


def canonical_site(name: str) -> str:
    """Site id as the practice pipeline spells it ('Missouri Valley' -> 'MOValley')."""
    return _SITE_ALIASES.get(_key(name), re.sub(r"[^A-Za-z0-9]", "", str(name)))


def modality_of(path: Path) -> str | None:
    parts = {_key(p) for p in path.parts[:-1]}
    ext = path.suffix.lower()
    if ext in SATELLITE_EXTS:
        return "satellite"
    if ext in UAV_EXTS:
        return "uav" if not parts & {"satellite"} else None
    return None


def parse_image_path(rel: Path) -> dict:
    """Site, time point and plot id from a path relative to the data root."""
    m = IMAGE_NAME.search(rel.stem)
    if m:
        site = canonical_site(m["site"])
        return {
            "site_id": site,
            "time_point": int(m["tp"]),
            "experiment": m["exp"],
            "range": int(m["range"]),
            "row": int(m["row"]),
            "plot_id": plot_id(site, m["exp"], int(m["range"]), int(m["row"])),
            "parse_method": "file_name",
        }
    # Fallback: TP from a TPn folder, site from the folder above it, plot from the stem.
    parts = list(rel.parts[:-1])
    tp_i = next((i for i, p in enumerate(parts) if TP_DIR.match(p)), None)
    tp = int(TP_DIR.match(parts[tp_i])[1]) if tp_i is not None else None
    site = None
    for p in reversed(parts[: tp_i if tp_i is not None else len(parts)]):
        if _key(p) in _SITE_ALIASES or _key(p) not in {"satellite", "uav", "images", "data"}:
            site = canonical_site(p)
            break
    return {
        "site_id": site,
        "time_point": tp,
        "experiment": None,
        "range": None,
        "row": None,
        "plot_id": f"{site}-{rel.stem}" if site else None,
        "parse_method": "folders" if site and tp else "unparsed",
    }


def discover_images(root: Path) -> pd.DataFrame:
    """Every satellite TIFF and UAV image under root, parsed. Paths are relative to root."""
    root = Path(root)
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(root)
        modality = modality_of(rel)
        if modality is None:
            continue
        rows.append({"path": rel.as_posix(), "modality": modality, **parse_image_path(rel)})
    return pd.DataFrame(rows, columns=IMAGE_COLUMNS)


def load_manifest(path: Path, root: Path | None = None) -> pd.DataFrame:
    """Agent 1's image manifest. Needs `path`; `modality`, `site_id`, `time_point`,
    `plot_id` and `date` override whatever the file name says when present."""
    path = Path(path)
    m = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    if "path" not in m:
        raise ValueError(f"{path} has no 'path' column")
    parsed = pd.DataFrame([parse_image_path(Path(p)) for p in m["path"]])
    for col in parsed:
        if col not in m:
            m[col] = parsed[col]
    if "modality" not in m:
        m["modality"] = [modality_of(Path(p)) for p in m["path"]]
    m["site_id"] = m["site_id"].map(lambda s: canonical_site(s) if pd.notna(s) else s)
    m["parse_method"] = m.get("parse_method", pd.Series(index=m.index)).fillna("manifest")
    if root is not None:
        m["path"] = [
            Path(p).relative_to(root).as_posix() if Path(p).is_absolute() else p for p in m["path"]
        ]
    return m


# ---- ground truth ---------------------------------------------------------------------


def find_file(root: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        hits = sorted(Path(root).rglob(pattern))
        if hits:
            return hits[0]
    return None


def find_ground_truth(root: Path) -> Path | None:
    return find_file(root, ("*ALLPLOTS*.csv", "*GroundTruth*.csv", "*ground_truth*.csv"))


def find_dates(root: Path) -> Path | None:
    return find_file(root, ("*DateofCollection*.xlsx", "*DateofCollection*.csv", "*acquisition*"))


def read_acquisitions(path: Path) -> pd.DataFrame:
    """Acquisition dates as site_id, modality, time_point, date.

    Accepts a tidy table with those columns, or the publication's DateofCollection sheet
    (Location, Date, and 'Satellite'/'UAV' + 'TPn' spread over the remaining columns)."""
    path = Path(path)
    if path.suffix == ".parquet":
        raw = pd.read_parquet(path)
    elif path.suffix in {".xlsx", ".xls"}:
        raw = pd.read_excel(path)
    else:
        raw = pd.read_csv(path)
    cols = {_key(c): c for c in raw.columns}
    if {"siteid", "modality", "timepoint", "date"} <= set(cols):
        out = raw.rename(columns={cols["siteid"]: "site_id", cols["timepoint"]: "time_point"})
        out = out.rename(columns={cols["modality"]: "modality", cols["date"]: "date"})
    else:
        loc = cols.get("location", raw.columns[0])
        day = cols.get("date", raw.columns[1])
        rows = []
        for _, r in raw.iterrows():
            text = " ".join(str(v) for k, v in r.items() if k not in (loc, day) and pd.notna(v))
            m = re.search(r"(Satellite|UAV|Drone)\s*[-_ ]?\s*TP\s*[-_ ]?(\d+)", text, re.I)
            if m is None or pd.isna(r[loc]) or pd.isna(r[day]):
                continue
            kind = "satellite" if m[1].lower() == "satellite" else "uav"
            rows.append(
                {"site_id": r[loc], "modality": kind, "time_point": int(m[2]), "date": r[day]}
            )
        out = pd.DataFrame(rows, columns=["site_id", "modality", "time_point", "date"])
    out = out[["site_id", "modality", "time_point", "date"]].copy()
    out["site_id"] = out["site_id"].map(canonical_site)
    out["modality"] = out["modality"].str.lower()
    out["time_point"] = out["time_point"].astype(int)
    out["date"] = pd.to_datetime(out["date"], format="mixed").dt.normalize()
    return out.drop_duplicates().sort_values(
        ["site_id", "modality", "time_point"], ignore_index=True
    )


def read_plots(path: Path) -> pd.DataFrame:
    """Plot records: plot_id, site_id, planting_date, final_yield plus PLANTING_KNOWN columns.

    Accepts Agent 1's canonical plots table (already has plot_id) or the publication's
    ground-truth CSV (location, experiment, range, row, plantingDate, yieldPerAcre, ...)."""
    path = Path(path)
    t = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, low_memory=False)
    if "plot_id" not in t:
        t = t.copy()
        t["experiment"] = t["experiment"].astype(str).str.strip()
        t["plot_id"] = [
            plot_id(canonical_site(s), e, r, w)
            for s, e, r, w in zip(t["location"], t["experiment"], t["range"], t["row"], strict=True)
        ]
        t["site_id"] = t["location"].map(canonical_site)
        t["field_id"] = t["plot_id"].str.rsplit("-", n=2).str[0]
        t["planting_date"] = pd.to_datetime(t.get("plantingDate"), errors="coerce")
        t["final_yield"] = pd.to_numeric(t.get("yieldPerAcre"), errors="coerce")
        if "poundsOfNitrogenPerAcre" in t:
            t["nitrogen_lb_ac"] = pd.to_numeric(t["poundsOfNitrogenPerAcre"], errors="coerce")
        if "irrigationProvided" in t:
            irrigation = pd.to_numeric(t["irrigationProvided"], errors="coerce")
            t["irrigated"] = t["site_id"].map(irrigation.groupby(t["site_id"]).max()).fillna(0) > 0
        if "genotype" in t:
            t["genotype"] = t["genotype"].astype("string").str.strip()
    t["planting_date"] = pd.to_datetime(t["planting_date"], errors="coerce").dt.normalize()
    # A plot with no recorded planting date takes its site's most common one.
    site_mode = t.groupby("site_id")["planting_date"].agg(
        lambda s: s.dropna().mode().iloc[0] if s.notna().any() else pd.NaT
    )
    t["planting_date"] = t["planting_date"].fillna(t["site_id"].map(site_mode))
    keep = ["plot_id", "site_id", "planting_date", *[c for c in PLANTING_KNOWN if c in t]]
    keep.append("final_yield")
    out = t[keep].drop_duplicates("plot_id").reset_index(drop=True)
    out["final_yield"] = pd.to_numeric(out["final_yield"], errors="coerce")
    return out
