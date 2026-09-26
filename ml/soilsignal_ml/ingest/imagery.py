"""
Per-file metadata for the challenge plot images, read from the files themselves.

    satellite  6-band uint16 GeoTIFF (Pleiades NEO), one plot per file, cropped to the
               plot's minimum bounding box; pixels outside the plot are 0 in every band
               (GDAL_NODATA = 0)
    uav        RGBA PNG, one plot per file, alpha = 0 outside the plot; not georeferenced

Band order is read from each GeoTIFF's GDAL band descriptions and checked against
SATELLITE_BANDS: Red, Green, Blue, NIR, Red Edge, Deep Blue. (The organizers' README lists
the bands as "near infrared, red edge, red, green, blue, deep blue"; the files and the
organizers' notebook both use the order below.)

Only compact numbers are returned: sizes, geometry, valid-pixel counts and per-band means
for QA. Spectral features are built downstream from the manifest's image_path.
"""

import hashlib
import re
from pathlib import Path

import numpy as np

SATELLITE_BANDS = ("red", "green", "blue", "nir", "red_edge", "deep_blue")
# Words in the GDAL band description that identify each band. Order matters: "deep blue"
# and "red edge" are matched before "blue" and "red".
_BAND_WORDS = (
    ("deep_blue", "deep blue"),
    ("red_edge", "red edge"),
    ("nir", "nir"),
    ("green", "green"),
    ("blue", "blue"),
    ("red", "red"),
)
UAV_BANDS = ("red", "green", "blue")
# Pleiades NEO products store reflectance x 10 000 (NIR ~4 400 over a July canopy).
SATELLITE_REFLECTANCE_SCALE = 1e-4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _band_names_from_gdal(xml: str | None, count: int) -> list[str | None]:
    names: list[str | None] = [None] * count
    if not xml:
        return names
    for sample, text in re.findall(
        r'<Item name="(?:DESCRIPTION|BandName)" sample="(\d+)"[^>]*>([^<]*)</Item>', xml
    ):
        i = int(sample)
        if i < count and names[i] is None:
            lowered = text.lower()
            names[i] = next((band for band, word in _BAND_WORDS if word in lowered), None)
    return names


def satellite_metadata(path: Path) -> dict:
    """Geometry, band order and valid pixels of one plot GeoTIFF."""
    import tifffile
    from pyproj import Transformer

    out: dict = {"read_ok": False}
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        arr = page.asarray()
        tags = page.tags
        gdal = tags["GDAL_METADATA"].value if "GDAL_METADATA" in tags else None
        nodata = tags["GDAL_NODATA"].value if "GDAL_NODATA" in tags else None
        geo = tif.geotiff_metadata if tif.is_geotiff else {}
        out.update(
            height=int(page.imagelength),
            width=int(page.imagewidth),
            bands=int(page.samplesperpixel),
            dtype=str(page.dtype),
            compression=page.compression.name,
            nodata=None if nodata is None else str(nodata).strip("\x00 "),
            is_geotiff=bool(tif.is_geotiff),
        )
    cube = arr if arr.ndim == 3 else arr[..., None]  # (rows, cols, bands)
    names = _band_names_from_gdal(gdal, out["bands"])
    out["band_names"] = ",".join(n or "?" for n in names)
    out["band_order_ok"] = tuple(names) == SATELLITE_BANDS

    zero = cube == 0
    valid = ~zero.any(axis=-1)  # a plot pixel has data in every band
    out["pixels"] = int(valid.size)
    out["valid_pixels"] = int(valid.sum())
    out["padding_pixels"] = int(zero.all(axis=-1).sum())
    # Zero in some bands but not all: not padding, not usable. Expected to be 0.
    out["partial_zero_pixels"] = int((zero.any(axis=-1) & ~zero.all(axis=-1)).sum())
    out["valid_fraction"] = round(out["valid_pixels"] / out["pixels"], 4)
    if out["valid_pixels"]:
        for i, name in enumerate(SATELLITE_BANDS[: out["bands"]]):
            out[f"mean_{name}"] = round(float(cube[..., i][valid].mean()), 3)

    scale = geo.get("ModelPixelScale")
    tie = geo.get("ModelTiepoint")
    epsg = geo.get("ProjectedCSTypeGeoKey")
    if scale and tie and epsg is not None:
        epsg = int(getattr(epsg, "value", epsg))
        dx, dy = float(scale[0]), float(scale[1])
        # Tiepoint maps raster (i, j) to model (x, y); RasterPixelIsArea: (0, 0) is the
        # outer corner of the top-left pixel.
        x0 = float(tie[3]) - float(tie[0]) * dx
        y0 = float(tie[4]) + float(tie[1]) * dy
        out.update(
            crs_epsg=epsg,
            pixel_size_x_m=round(dx, 4),
            pixel_size_y_m=round(dy, 4),
            bbox_minx=round(x0, 3),
            bbox_maxx=round(x0 + dx * out["width"], 3),
            bbox_maxy=round(y0, 3),
            bbox_miny=round(y0 - dy * out["height"], 3),
            plot_area_m2=round(out["valid_pixels"] * dx * dy, 2),
        )
        to_wgs84 = Transformer.from_crs(epsg, 4326, always_xy=True)
        # Bounding-box centre: what the practice pipeline used for plot coordinates.
        lon, lat = to_wgs84.transform(x0 + dx * out["width"] / 2, y0 - dy * out["height"] / 2)
        out.update(bbox_center_lat=round(float(lat), 7), bbox_center_lon=round(float(lon), 7))
        if out["valid_pixels"]:
            # Centroid of the plot's own pixels (padding excluded): the plot coordinate.
            rows, cols = np.nonzero(valid)
            cx = x0 + (cols.mean() + 0.5) * dx
            cy = y0 - (rows.mean() + 0.5) * dy
            lon, lat = to_wgs84.transform(cx, cy)
            out.update(
                centroid_x=round(float(cx), 3),
                centroid_y=round(float(cy), 3),
                centroid_lat=round(float(lat), 7),
                centroid_lon=round(float(lon), 7),
            )
    out["read_ok"] = True
    return out


def uav_metadata(path: Path) -> dict:
    """Size and valid pixels of one plot PNG. Alpha (when present) marks the plot."""
    from PIL import Image

    out: dict = {"read_ok": False}
    with Image.open(path) as im:
        out.update(width=im.width, height=im.height, mode=im.mode, bands=len(im.getbands()))
        arr = np.asarray(im)
    out["dtype"] = str(arr.dtype)
    rgb = arr[..., :3] if arr.ndim == 3 else np.repeat(arr[..., None], 3, axis=-1)
    padding = (rgb == 0).all(axis=-1)
    valid = arr[..., 3] > 0 if arr.ndim == 3 and arr.shape[-1] == 4 else ~padding
    out["has_alpha"] = bool(arr.ndim == 3 and arr.shape[-1] == 4)
    out["pixels"] = int(valid.size)
    out["valid_pixels"] = int(valid.sum())
    out["padding_pixels"] = int(padding.sum())
    # Alpha and zero-RGB should mark the same padding; disagreement means a black plot pixel
    # or a transparent non-black one.
    out["alpha_rgb_disagree_pixels"] = int((valid == padding).sum()) if out["has_alpha"] else 0
    out["valid_fraction"] = round(out["valid_pixels"] / out["pixels"], 4)
    if out["valid_pixels"]:
        for i, name in enumerate(UAV_BANDS):
            out[f"mean_{name}"] = round(float(rgb[..., i][valid].mean()), 3)
    out["read_ok"] = True
    return out


def read_metadata(path: Path, sensor: str) -> dict:
    """Metadata for one image; a file that cannot be read is reported, never skipped."""
    try:
        meta = satellite_metadata(path) if sensor == "satellite" else uav_metadata(path)
    except Exception as exc:  # corrupt or truncated file: keep the row, record why
        meta = {"read_ok": False, "read_error": f"{type(exc).__name__}: {exc}"[:300]}
    meta["sha256"] = sha256(path)
    return meta
