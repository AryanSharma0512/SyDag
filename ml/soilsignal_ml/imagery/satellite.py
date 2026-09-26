"""
One satellite plot image (GeoTIFF) -> band layout, valid-pixel mask, band and index statistics.

Masking rules, in order:
  padding  every band is 0 (or every band equals the GDAL nodata value, or every band is NaN).
           The plot images are clipped to the plot polygon and zero-filled outside it.
  in_plot  not padding.
  invalid  in_plot, but some band is non-finite, <= 0 or above MAX_REFLECTANCE after scaling.
           A single zero band inside the plot is an edge/resampling artefact, not a reflectance.
  valid    in_plot and not invalid. Every statistic uses valid pixels only.

Indices: NDVI, NDRE, GNDVI and EVI come from the backend's compute_indices() (the formulas
the API serves with; per-pixel values outside [-1, 1] become NaN there). SAVI is added here
because the backend has no use for it yet. Each index is computed per pixel, then summarized.
"""

import io
import re
from dataclasses import dataclass, field

import numpy as np
import tifffile
from scipy import ndimage

from app.features.vegetation import compute_indices
from soilsignal_ml.ingest.dataset_adapter import BANDS as DEFAULT_BANDS
from soilsignal_ml.ingest.dataset_adapter import REFLECTANCE_SCALE

# Bump when masking or statistics change: cached per-image results are keyed on it.
EXTRACTOR_VERSION = "sat-1"

MAX_REFLECTANCE = 1.0
NEAR_ZERO_REFLECTANCE = 0.001
SAVI_L = 0.5
INDICES = ("ndvi", "ndre", "gndvi", "evi", "savi")
STATS = ("mean", "median", "std", "p10", "p25", "p75", "p90")
_PERCENTILES = (10, 25, 50, 75, 90)
# Indices whose mean is also taken over the eroded plot core (one pixel in from the edge),
# where alley soil and neighbouring plots contaminate the least.
CORE_INDICES = ("ndvi", "ndre")
# Heuristic soil/canopy split for the canopy-cover proxy (fraction of valid pixels above it).
COVER_NDVI_THRESHOLD = 0.5

GDAL_METADATA_TAG = 42112
GDAL_NODATA_TAG = 42113
# Keyword -> band, checked in order ("deep blue" before "blue", "red edge" before "red").
# Matches plain names ("NIR") and sensor descriptions ("Pleiades NEO Red (0.618 - 0.689) um").
_BAND_KEYWORDS = (
    (("deepblue", "coastal"), "deep_blue"),
    (("rededge",), "red_edge"),
    (("nearinfrared", "nir"), "nir"),
    (("red",), "red"),
    (("green",), "green"),
    (("blue",), "blue"),
)


class UnsupportedLayout(ValueError):
    """The TIFF's array shape can't be mapped to (rows, cols, bands)."""


@dataclass
class Raster:
    pixels: np.ndarray  # (rows, cols, bands), as stored
    band_names: tuple[str, ...] | None  # None when the layout can't be trusted
    band_order_source: str  # "gdal_metadata", "configured", or "unknown"
    meta: dict = field(default_factory=dict)


def _band_descriptions(tags) -> list[str] | None:
    tag = tags.get(GDAL_METADATA_TAG)
    if tag is None:
        return None
    found = re.findall(
        r'<Item name="DESCRIPTION" sample="(\d+)"[^>]*>([^<]*)</Item>', str(tag.value)
    )
    if not found:
        return None
    by_sample = {int(s): d for s, d in found}
    return [by_sample.get(i, "") for i in range(max(by_sample) + 1)]


def _canonical_band(name: str) -> str | None:
    text = re.sub(r"\(.*?\)", "", name.lower())  # drop the wavelength range
    text = re.sub(r"[^a-z]", "", text)
    for keywords, band in _BAND_KEYWORDS:
        if any(k in text for k in keywords):
            return band
    return {"r": "red", "g": "green", "b": "blue", "re": "red_edge"}.get(text)


def _page_pixels(tif: tifffile.TiffFile, page) -> tuple[np.ndarray, str]:
    """(rows, cols, bands) from the IFD the header points to.

    The plot TIFFs have been edited in place (GDAL appends a new IFD and repoints the
    header), so the current image is pages[0]; older IFDs are ignored. Only when every
    page is a full-resolution single band of the same shape are pages read as bands."""
    arr = page.asarray()
    spp = int(page.samplesperpixel)
    if spp > 1:
        if arr.ndim != 3:
            raise UnsupportedLayout(f"array shape {arr.shape} with {spp} samples per pixel")
        if int(page.planarconfig) == 2:  # SEPARATE: (bands, rows, cols)
            return np.moveaxis(arr, 0, -1), "planar"
        return arr, "interleaved"
    if arr.ndim != 2:
        raise UnsupportedLayout(f"array shape {arr.shape}")
    pages = [p for p in tif.pages if not int(getattr(p, "subfiletype", 0))]
    if len(pages) > 1 and all(p.shape == page.shape for p in pages):
        return np.stack([p.asarray() for p in pages], axis=-1), "band_per_page"
    return arr[..., None], "single_band"


def read_raster(data: bytes, band_order: tuple[str, ...] = DEFAULT_BANDS) -> Raster:
    """Decode a plot GeoTIFF and work out which band is which.

    Band names come from the GDAL band descriptions when the file has them, otherwise
    from band_order when the band count matches it. Anything else is left unnamed
    (and flagged), never guessed."""
    with tifffile.TiffFile(io.BytesIO(data)) as tif:
        page = tif.pages[0]
        tags = page.tags
        pixels, layout = _page_pixels(tif, page)
        meta: dict = {
            "height": int(pixels.shape[0]),
            "width": int(pixels.shape[1]),
            "n_bands": int(pixels.shape[2]),
            "dtype": str(pixels.dtype),
            "layout": layout,
            "compression": str(getattr(page.compression, "name", page.compression)),
            "n_pages": len(tif.pages),
        }
        nodata = tags.get(GDAL_NODATA_TAG)
        meta["nodata"] = _float_or_none(str(nodata.value).strip("\x00 ")) if nodata else None
        scale = tags.get("ModelPixelScaleTag")
        tie = tags.get("ModelTiepointTag")
        meta["pixel_size_x"] = float(scale.value[0]) if scale else None
        meta["pixel_size_y"] = float(scale.value[1]) if scale else None
        meta["origin_x"] = float(tie.value[3]) if tie else None
        meta["origin_y"] = float(tie.value[4]) if tie else None
        epsg = None
        if page.is_geotiff and page.geotiff_tags:
            key = page.geotiff_tags.get("ProjectedCSTypeGeoKey") or page.geotiff_tags.get(
                "GeographicTypeGeoKey"
            )
            try:
                epsg = int(key) if key is not None else None
            except (TypeError, ValueError):
                epsg = None
        meta["epsg"] = epsg
        descriptions = _band_descriptions(tags)

    n = pixels.shape[2]
    names: tuple[str, ...] | None = None
    source = "unknown"
    if descriptions and len(descriptions) == n:
        mapped = [_canonical_band(d) for d in descriptions]
        if all(mapped) and len(set(mapped)) == n:
            names, source = tuple(mapped), "gdal_metadata"
    if names is None and len(band_order) == n:
        names, source = tuple(band_order), "configured"
    # False when the file's own band descriptions contradict the configured order.
    agrees = names == tuple(band_order)[: len(names)] if names else None
    meta["band_order_agrees"] = agrees if source == "gdal_metadata" else None
    meta["band_names"] = ",".join(names) if names else None
    return Raster(pixels=pixels, band_names=names, band_order_source=source, meta=meta)


def _float_or_none(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _summary(values: np.ndarray, prefix: str, out: dict) -> None:
    values = values[np.isfinite(values)]
    if values.size == 0:
        for s in STATS:
            out[f"{prefix}_{s}"] = np.nan
        return
    p10, p25, p50, p75, p90 = np.percentile(values, _PERCENTILES)
    out[f"{prefix}_mean"] = float(values.mean())
    out[f"{prefix}_median"] = float(p50)
    out[f"{prefix}_std"] = float(values.std())
    out[f"{prefix}_p10"] = float(p10)
    out[f"{prefix}_p25"] = float(p25)
    out[f"{prefix}_p75"] = float(p75)
    out[f"{prefix}_p90"] = float(p90)


def pixel_indices(bands: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Per-pixel indices for whichever indices the bands support."""
    out = compute_indices(bands)
    if "nir" in bands and "red" in bands:
        with np.errstate(divide="ignore", invalid="ignore"):
            out["savi"] = (
                (1 + SAVI_L)
                * (bands["nir"] - bands["red"])
                / (bands["nir"] + bands["red"] + SAVI_L)
            )
    return out


def masks(raster: Raster, scale: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(in_plot, valid, reflectance) for a raster; reflectance is pixels / scale."""
    px = raster.pixels
    padding = (px == 0).all(axis=2)
    nodata = raster.meta.get("nodata")
    if nodata is not None and np.isfinite(nodata) and nodata != 0:
        padding |= (px == nodata).all(axis=2)
    if np.issubdtype(px.dtype, np.floating):
        padding |= np.isnan(px).all(axis=2)
    in_plot = ~padding
    refl = px.astype(np.float64) / scale
    with np.errstate(invalid="ignore"):
        bad = (~np.isfinite(refl)).any(axis=2) | (refl <= 0).any(axis=2)
        bad |= (refl > MAX_REFLECTANCE).any(axis=2)
    return in_plot, in_plot & ~bad, refl


def infer_scale(raster: Raster, in_plot: np.ndarray) -> float:
    """16-bit data is reflectance x 10,000; float data already in 0-1 stays as it is."""
    px = raster.pixels
    if np.issubdtype(px.dtype, np.integer):
        return float(REFLECTANCE_SCALE)
    values = px[in_plot]
    values = values[np.isfinite(values)]
    if values.size and np.percentile(values, 99) <= 1.5:
        return 1.0
    return float(REFLECTANCE_SCALE)


def raster_stats(raster: Raster, reflectance_scale: float | None = None) -> dict:
    """Every per-image quantity the feature tables and quality report use."""
    out: dict = {**raster.meta, "band_order_source": raster.band_order_source}
    px = raster.pixels
    padding_guess = (px == 0).all(axis=2)
    scale = reflectance_scale or infer_scale(raster, ~padding_guess)
    in_plot, valid, refl = masks(raster, scale)
    n_total = int(in_plot.size)
    n_in_plot = int(in_plot.sum())
    n_valid = int(valid.sum())
    with np.errstate(invalid="ignore"):
        out["n_saturated"] = int((in_plot & (refl > MAX_REFLECTANCE).any(axis=2)).sum())
        out["n_nonpositive"] = int((in_plot & (refl <= 0).any(axis=2)).sum())
        # Valid but implausibly dark (< 0.001 in some band): kept, counted for review.
        out["n_near_zero"] = int((valid & (refl < NEAR_ZERO_REFLECTANCE).any(axis=2)).sum())
    out.update(
        reflectance_scale=scale,
        n_pixels_total=n_total,
        n_padding=n_total - n_in_plot,
        n_in_plot=n_in_plot,
        n_valid=n_valid,
        n_invalid=n_in_plot - n_valid,
        valid_fraction=n_valid / n_total if n_total else np.nan,
        valid_fraction_of_plot=n_valid / n_in_plot if n_in_plot else np.nan,
    )
    names = raster.band_names
    if names is None:
        out["brightest_band"] = None
        return out

    bands = {name: refl[..., i][valid] for i, name in enumerate(names)}
    for name in DEFAULT_BANDS:
        _summary(bands.get(name, np.array([])), name, out)
    medians = {b: out[f"{b}_median"] for b in bands if np.isfinite(out[f"{b}_median"])}
    out["brightest_band"] = max(medians, key=medians.get) if medians else None

    idx = pixel_indices(bands)
    for name in INDICES:
        values = idx.get(name, np.array([]))
        _summary(values, name, out)
        # Valid pixels always have finite, positive bands, so a NaN index value here is
        # one compute_indices() rejected as outside [-1, 1] (or a zero denominator).
        out[f"{name}_n_out_of_range"] = int((~np.isfinite(values)).sum())
    ndvi = idx.get("ndvi")
    out["ndvi_cover_frac"] = (
        float(np.mean(ndvi[np.isfinite(ndvi)] > COVER_NDVI_THRESHOLD))
        if ndvi is not None and np.isfinite(ndvi).any()
        else np.nan
    )

    core = ndimage.binary_erosion(valid, structure=np.ones((3, 3), bool), border_value=0)
    out["n_core"] = int(core.sum())
    core_bands = {name: refl[..., i][core] for i, name in enumerate(names)}
    core_idx = compute_indices(core_bands) if out["n_core"] else {}
    for name in CORE_INDICES:
        v = core_idx.get(name, np.array([]))
        v = v[np.isfinite(v)]
        out[f"{name}_core_mean"] = float(v.mean()) if v.size else np.nan

    rows, cols = np.nonzero(valid)
    if n_valid and out.get("origin_x") is not None and out.get("pixel_size_x"):
        out["centroid_x"] = out["origin_x"] + out["pixel_size_x"] * (cols.mean() + 0.5)
        out["centroid_y"] = out["origin_y"] - out["pixel_size_y"] * (rows.mean() + 0.5)
    else:
        out["centroid_x"] = out["centroid_y"] = np.nan
    return out


def image_stats(
    data: bytes,
    band_order: tuple[str, ...] = DEFAULT_BANDS,
    reflectance_scale: float | None = None,
) -> dict:
    """Read and summarize one TIFF. A file that can't be decoded returns {'error': ...}
    instead of raising, so one corrupt image never stops a batch."""
    try:
        raster = read_raster(data, band_order)
        stats = raster_stats(raster, reflectance_scale)
        stats["error"] = None
    except Exception as exc:  # any decoder failure is a corrupt-image flag
        stats = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    stats["extractor_version"] = EXTRACTOR_VERSION
    return stats


def stat_columns(bands: tuple[str, ...] = DEFAULT_BANDS) -> list[str]:
    """Spectral statistic columns every successfully read 6-band image has."""
    cols = [f"{b}_{s}" for b in bands for s in STATS]
    cols += [f"{i}_{s}" for i in INDICES for s in STATS]
    cols += ["ndvi_cover_frac", *[f"{i}_core_mean" for i in CORE_INDICES]]
    return cols
