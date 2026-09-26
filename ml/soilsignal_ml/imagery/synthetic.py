"""
A small synthetic dataset laid out like the real one, for tests and benchmarks only.

Plot images are 6-band uint16 GeoTIFFs (reflectance x 10,000, zero outside a slanted plot
footprint), UAV images are RGB PNGs with black padding, and the ground truth and
acquisition dates use the publication's column names. Canopy cover follows a logistic
curve whose height tracks the plot's yield, so features carry some signal, but none of
these numbers describe real maize. Optional defects exercise every quality check.
"""

import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile
from PIL import Image

from soilsignal_ml.ingest.dataset_adapter import BANDS

PLANTING = {
    "Ames": date(2022, 5, 5),
    "Crawfordsville": date(2022, 5, 10),
    "Lincoln": date(2022, 5, 2),
}
SAT_DAP = (36, 52, 68, 86, 104, 128)  # days after planting of TP1..TP6
UAV_DAP = (48, 70, 92)
VEG = np.array([0.035, 0.080, 0.030, 0.480, 0.220, 0.028])  # BANDS order
SOIL = np.array([0.160, 0.130, 0.100, 0.240, 0.200, 0.090])
DEFECTS = ("corrupt", "four_band", "duplicate", "saturated", "low_valid", "missing", "jump")


# How the real plot TIFFs describe their bands (GDAL metadata, file order).
DESCRIPTIONS = (
    "Pleiades NEO Red (0.618 - 0.689) um",
    "Pleiades NEO Green (0.533 - 0.59) um",
    "Pleiades NEO Blue (0.446 - 0.52) um",
    "Pleiades NEO NIR (0.768 - 0.888) um",
    "Pleiades NEO Red Edge (0.696 - 0.749) um",
    "Pleiades NEO Deep Blue (0.416 - 0.456) um",
)


def _gdal_metadata(n_bands: int) -> str:
    items = "".join(
        f'  <Item name="DESCRIPTION" sample="{i}" role="description">{d}</Item>\n'
        for i, d in enumerate(DESCRIPTIONS[:n_bands])
    )
    return f"<GDALMetadata>\n{items}</GDALMetadata>\n"


def _geotiff(path: Path, data: np.ndarray, x0: float, y0: float, pixel: float = 0.3) -> None:
    """Written like the real plot images: 16-bit, LZW, 0.3 m pixels, UTM 15N, nodata 0,
    and GDAL band descriptions."""
    geokeys = [1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, 32615]
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        path,
        data,
        photometric="minisblack",
        planarconfig="contig",
        compression="lzw",
        extratags=[
            (33550, 12, 3, (pixel, pixel, 0.0), False),
            (33922, 12, 6, (0, 0, 0, x0, y0, 0), False),
            (34735, 3, len(geokeys), geokeys, False),
            (42112, "s", 0, _gdal_metadata(data.shape[-1]), False),
            (42113, "s", 0, "0", False),
        ],
    )


def footprint(shape: tuple[int, int]) -> np.ndarray:
    """A slanted plot inside its bounding box, like a clipped, slightly rotated polygon."""
    h, w = shape
    rows, cols = np.mgrid[0:h, 0:w]
    shift = rows / max(h, 1) * (w * 0.2)
    return (cols >= 1 + shift) & (cols <= w - 2 - (w * 0.2) + shift) & (rows >= 1) & (rows <= h - 2)


def cover(dap: float, fmax: float, t50: float) -> float:
    grow = fmax / (1 + np.exp(-(dap - t50) / 7))
    return float(grow * (np.exp(-(dap - 100) / 45) if dap > 100 else 1.0))


def write_synthetic(
    root: Path,
    plots_per_site: int = 12,
    shape: tuple[int, int] = (21, 12),
    seed: int = 0,
    defects: bool = True,
    uav: bool = True,
    uav_scale: int = 3,
) -> dict:
    """Write the dataset under root and return what was planted (defects by path)."""
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    rng = np.random.default_rng(seed)
    mask = footprint(shape)
    truth, dates, planted = [], [], {}
    for s, (site, planting) in enumerate(PLANTING.items()):
        for k, dap in enumerate(SAT_DAP, 1):
            day = planting + timedelta(days=dap + s)
            dates.append({"Location": site, "Date": day, "Image": "Satellite", "time": f"TP{k}"})
        for j, dap in enumerate(UAV_DAP, 1):
            day = planting + timedelta(days=dap + s)
            dates.append({"Location": site, "Date": day, "Image": "UAV", "time": f"TP{j}"})
        for p in range(plots_per_site):
            rng_, row = 1 + p // 4, 1 + p % 4
            z = rng.normal()
            fmax = float(np.clip(0.8 + 0.08 * z, 0.35, 0.97))
            t50 = 50 - 3 * z + 2 * s
            truth.append(
                {
                    "location": site,
                    "experiment": "Hybrids",
                    "range": rng_,
                    "row": row,
                    "plantingDate": planting.isoformat(),
                    "yieldPerAcre": round(170 + 35 * z + 10 * s + rng.normal(0, 8), 1),
                    "genotype": f"H{p % 5}",
                    "poundsOfNitrogenPerAcre": [75, 150, 225][p % 3],
                    "irrigationProvided": 0,
                    "totalStandCount": int(60 + 5 * z),  # in-season: must never be a feature
                }
            )
            for k, dap in enumerate(SAT_DAP, 1):
                f = cover(dap + s, fmax, t50)
                cov = np.clip(f + rng.normal(0, 0.05, shape), 0, 1)[..., None]
                refl = cov * VEG + (1 - cov) * SOIL + rng.normal(0, 0.004, (*shape, 6))
                dn = np.clip(np.round(refl * 10_000), 1, 65535).astype(np.uint16)
                dn[~mask] = 0
                name = f"{site}-TP{k}-Hybrids_{rng_}_{row}.TIF"
                _geotiff(
                    root / "Satellite" / site / f"TP{k}" / name,
                    dn,
                    400_000 + 50_000 * s + 12 * rng_,
                    4_650_000 - 6 * row,
                )
            if uav:
                for j, dap in enumerate(UAV_DAP, 1):
                    f = cover(dap + s, fmax, t50)
                    h, w = shape[0] * uav_scale, shape[1] * uav_scale
                    cov = np.clip(f + rng.normal(0, 0.15, (h, w)), 0, 1)[..., None]
                    rgb = cov * np.array([45, 115, 40]) + (1 - cov) * np.array([150, 122, 92])
                    rgb = np.clip(rgb + rng.normal(0, 6, (h, w, 3)), 1, 255).astype(np.uint8)
                    rgb[~footprint((h, w))] = 0
                    path = root / "UAV" / site / f"TP{j}" / f"{site}-TP{j}-Hybrids_{rng_}_{row}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(rgb).save(path)
    gt = root / "GroundTruth"
    gt.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(truth).to_csv(gt / "HYBRID_HIPS_V3.5_ALLPLOTS.csv", index=False)
    pd.DataFrame(dates).to_excel(gt / "DateofCollection.xlsx", index=False)
    if defects:
        if plots_per_site < 6:
            raise ValueError("defects need at least 6 plots per site")
        planted = _plant_defects(root, shape, mask)
    return {"root": root, "plots": len(truth), "defects": planted}


def _sat(root: Path, site: str, tp: int, rng_: int, row: int) -> Path:
    return root / "Satellite" / site / f"TP{tp}" / f"{site}-TP{tp}-Hybrids_{rng_}_{row}.TIF"


def _plant_defects(root: Path, shape: tuple[int, int], mask: np.ndarray) -> dict:
    planted = {}
    p = _sat(root, "Ames", 2, 1, 2)
    p.write_bytes(p.read_bytes()[:200] + b"\x00garbage")
    planted["corrupt"] = p
    p = _sat(root, "Ames", 3, 1, 3)
    data = tifffile.imread(p)[..., :4]
    _geotiff(p, np.ascontiguousarray(data), 400_000, 4_650_000)
    planted["four_band"] = p
    src, dst = _sat(root, "Crawfordsville", 3, 1, 1), _sat(root, "Crawfordsville", 3, 1, 2)
    dst.write_bytes(src.read_bytes())
    planted["duplicate"] = dst
    p = _sat(root, "Crawfordsville", 4, 2, 1)
    data = tifffile.imread(p)
    data[mask] = np.where(np.arange(data[mask].shape[0])[:, None] % 5 == 0, 12_000, data[mask])
    _geotiff(p, data, 450_012, 4_649_994)
    planted["saturated"] = p
    p = _sat(root, "Lincoln", 3, 2, 2)
    data = tifffile.imread(p)
    data[: shape[0] - 4] = 0
    _geotiff(p, data, 500_024, 4_649_988)
    planted["low_valid"] = p
    p = _sat(root, "Lincoln", 4, 1, 1)
    p.unlink()
    planted["missing"] = p
    p = _sat(root, "Lincoln", 5, 1, 3)
    data = tifffile.imread(p)
    soil = np.round(SOIL * 10_000).astype(np.uint16)
    data[mask] = soil
    _geotiff(p, data, 500_012, 4_649_982)
    planted["jump"] = p
    return planted


if __name__ == "__main__":
    import sys

    out = write_synthetic(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("synthetic"))
    print(out)
    print(f"bands: {BANDS}")
