"""Masking, band layout, indices, discovery, caching, UAV features and the dictionary."""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import tifffile
from PIL import Image

import soilsignal_ml  # noqa: F401  (puts backend/ on the import path)
from soilsignal_ml.imagery import qa
from soilsignal_ml.imagery.dictionary import describe, dictionary_markdown
from soilsignal_ml.imagery.discover import (
    discover_images,
    parse_image_path,
    read_acquisitions,
    read_plots,
)
from soilsignal_ml.imagery.extract import extract_images
from soilsignal_ml.imagery.pipeline import run
from soilsignal_ml.imagery.progressive import build_progressive
from soilsignal_ml.imagery.satellite import image_stats, read_raster
from soilsignal_ml.imagery.synthetic import DESCRIPTIONS, _gdal_metadata, write_synthetic
from soilsignal_ml.imagery.uav import uav_columns, uav_image_stats

# One vegetated pixel spectrum, file band order red, green, blue, nir, red_edge, deep_blue.
VEG = np.array([400, 800, 300, 4500, 2200, 280], dtype=np.uint16)


def _tiff(data: np.ndarray, planar: str = "contig", descriptions=None, nodata=None) -> bytes:
    buf = io.BytesIO()
    extratags = []
    if descriptions:
        items = "".join(
            f'<Item name="DESCRIPTION" sample="{i}" role="description">{d}</Item>'
            for i, d in enumerate(descriptions)
        )
        extratags.append((42112, "s", 0, f"<GDALMetadata>{items}</GDALMetadata>", False))
    if nodata is not None:
        extratags.append((42113, "s", 0, str(nodata), False))
    tifffile.imwrite(buf, data, photometric="minisblack", planarconfig=planar, extratags=extratags)
    return buf.getvalue()


def _plot(values=VEG) -> np.ndarray:
    """4 x 5 box: a 3 x 3 plot of `values`, one partial-zero pixel, one saturated pixel."""
    arr = np.zeros((4, 5, 6), dtype=np.uint16)
    arr[0:3, 0:3] = values
    arr[0, 0, 2] = 0  # blue = 0 inside the plot: invalid, not padding
    arr[2, 2] = 12_000  # reflectance 1.2 everywhere: saturated
    arr[3, 4] = values  # an isolated valid pixel
    return arr


def test_masking_excludes_padding_partial_zeros_and_saturation():
    s = image_stats(_tiff(_plot()))
    assert s["error"] is None
    assert s["n_pixels_total"] == 20
    assert s["n_padding"] == 20 - 10
    assert s["n_in_plot"] == 10
    assert s["n_valid"] == 8
    assert s["n_saturated"] == 1 and s["n_nonpositive"] == 1
    assert s["red_mean"] == pytest.approx(0.04)
    assert s["nir_p90"] == pytest.approx(0.45)
    assert s["red_std"] == pytest.approx(0.0)
    ndvi = (0.45 - 0.04) / (0.45 + 0.04)
    assert s["ndvi_mean"] == pytest.approx(ndvi)
    assert s["ndre_mean"] == pytest.approx((0.45 - 0.22) / (0.45 + 0.22))
    assert s["gndvi_mean"] == pytest.approx((0.45 - 0.08) / (0.45 + 0.08))
    evi = 2.5 * (0.45 - 0.04) / (0.45 + 6 * 0.04 - 7.5 * 0.03 + 1)
    assert s["evi_mean"] == pytest.approx(evi)
    assert s["savi_mean"] == pytest.approx(1.5 * (0.45 - 0.04) / (0.45 + 0.04 + 0.5))
    assert s["brightest_band"] == "nir"
    assert s["ndvi_cover_frac"] == 1.0


def test_core_mean_uses_the_eroded_plot():
    arr = np.zeros((7, 7, 6), dtype=np.uint16)
    arr[1:6, 1:6] = VEG
    arr[1, 1:6] = np.array([1600, 1300, 1000, 2400, 2000, 900], dtype=np.uint16)  # soil edge
    s = image_stats(_tiff(arr))
    assert s["n_core"] == 9
    assert s["ndvi_core_mean"] == pytest.approx((0.45 - 0.04) / (0.45 + 0.04))
    assert s["ndvi_mean"] < s["ndvi_core_mean"]


def test_planar_and_interleaved_layouts_give_the_same_statistics():
    arr = _plot()
    a = image_stats(_tiff(arr))
    b = image_stats(_tiff(np.moveaxis(arr, -1, 0).copy(), planar="separate"))
    assert b["layout"] == "planar" and a["layout"] == "interleaved"
    for key in ("n_valid", "red_mean", "nir_p75", "ndvi_mean", "evi_median"):
        assert a[key] == pytest.approx(b[key])


def test_band_descriptions_override_the_configured_order():
    order = [3, 4, 0, 1, 2, 5]  # the README's order: NIR, red edge, red, green, blue, deep blue
    arr = _plot()[..., order]
    desc = [DESCRIPTIONS[i] for i in order]
    s = image_stats(_tiff(arr, descriptions=desc))
    assert s["band_order_source"] == "gdal_metadata"
    assert s["band_order_agrees"] is False
    assert s["ndvi_mean"] == pytest.approx(image_stats(_tiff(_plot()))["ndvi_mean"])
    real = image_stats(_tiff(_plot(), descriptions=list(DESCRIPTIONS)))
    assert real["band_order_agrees"] is True
    assert real["band_names"] == "red,green,blue,nir,red_edge,deep_blue"


def test_unknown_band_layout_is_flagged_not_guessed():
    s = image_stats(_tiff(_plot()[..., :4]))
    assert s["n_bands"] == 4
    assert s["band_order_source"] == "unknown"
    assert "ndvi_mean" not in s
    named = image_stats(_tiff(_plot()[..., :4], descriptions=list(DESCRIPTIONS[:4])))
    assert named["band_names"] == "red,green,blue,nir"
    assert np.isnan(named["ndre_mean"]) and np.isfinite(named["ndvi_mean"])


def test_corrupt_file_returns_an_error_instead_of_raising():
    s = image_stats(b"II*\x00garbage")
    assert s["error"]


def test_float_reflectance_and_non_zero_nodata():
    arr = _plot().astype(np.float32) / 10_000
    s = image_stats(_tiff(arr))
    assert s["reflectance_scale"] == 1.0
    assert s["ndvi_mean"] == pytest.approx(image_stats(_tiff(_plot()))["ndvi_mean"], rel=1e-5)
    padded = _plot()
    padded[(padded == 0).all(axis=2)] = 65535
    s = image_stats(_tiff(padded, nodata=65535))
    assert s["n_in_plot"] == 10


def test_index_values_outside_minus_one_to_one_become_nan_and_are_counted():
    arr = np.zeros((1, 2, 6), dtype=np.uint16)
    arr[0, 0] = VEG
    # NIR + 6 Red - 7.5 Blue + 1 is ~0 here, so EVI is huge
    arr[0, 1] = np.array([200, 500, 1893, 3000, 1500, 150], dtype=np.uint16)
    s = image_stats(_tiff(arr))
    assert s["evi_n_out_of_range"] == 1
    assert np.isfinite(s["evi_mean"])


def test_real_file_geotiff_tags_are_read(tmp_path):
    write_synthetic(tmp_path / "d", plots_per_site=1, defects=False, uav=False)
    path = next((tmp_path / "d" / "Satellite").rglob("*.TIF"))
    raster = read_raster(path.read_bytes())
    assert raster.meta["epsg"] == 32615
    assert raster.meta["pixel_size_x"] == pytest.approx(0.3)
    assert raster.meta["nodata"] == 0
    assert raster.meta["compression"] == "LZW"
    assert raster.band_order_source == "gdal_metadata"
    assert "Pleiades NEO NIR" in _gdal_metadata(6)


@pytest.mark.parametrize(
    "path, site, tp, exp, rng, row, modality",
    [
        ("Satellite/Ames/TP5/Ames-TP5-4231_11_3.TIF", "Ames", 5, "4231", 11, 3, "satellite"),
        (
            "UAV/Crawfordsville/TP1/Crawfordsville-TP1-4351_3_15.PNG",
            "Crawfordsville",
            1,
            "4351",
            3,
            15,
            "uav",
        ),
        (
            "Satellite/Lincoln/TP1/Lincoln-TP1-hybirds_2_2.TIF",
            "Lincoln",
            1,
            "hybirds",
            2,
            2,
            "satellite",
        ),
    ],
)
def test_file_names_parse(path, site, tp, exp, rng, row, modality, tmp_path):
    parsed = parse_image_path(Path(path))
    assert (parsed["site_id"], parsed["time_point"], parsed["experiment"]) == (site, tp, exp)
    assert (parsed["range"], parsed["row"]) == (rng, row)
    assert parsed["plot_id"] == f"{site}-{exp.lower()}-{rng}-{row}"
    f = tmp_path / path
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    assert discover_images(tmp_path)["modality"].tolist() == [modality]


def test_folder_fallback_when_the_file_name_does_not_parse():
    parsed = parse_image_path(Path("Satellite/Ames/TP3/plot_017.tif"))
    assert parsed["site_id"] == "Ames" and parsed["time_point"] == 3
    assert parsed["plot_id"] == "Ames-plot_017" and parsed["parse_method"] == "folders"


def test_date_sheet_and_ground_truth(tmp_path):
    sheet = pd.DataFrame(
        {
            "Location": ["Missouri Valley", "Ames", "Ames"],
            "Date": ["07/13/22", "07/15/22", "07/12/22"],
            "Image": ["Satellite", "Satellite", "UAV"],
            "time": ["TP1", "TP1", "TP1"],
        }
    )
    sheet.to_excel(tmp_path / "DateofCollection.xlsx", index=False)
    acq = read_acquisitions(tmp_path / "DateofCollection.xlsx")
    assert set(acq["site_id"]) == {"MOValley", "Ames"}
    assert acq.loc[acq["modality"] == "uav", "date"].iloc[0] == pd.Timestamp("2022-07-12")

    truth = pd.DataFrame(
        {
            "location": ["Ames", "Ames"],
            "experiment": ["4231", "4231"],
            "range": [11, 11],
            "row": [3, 4],
            "plantingDate": ["2022-05-10", None],
            "yieldPerAcre": [190.5, 170.0],
            "genotype": ["A", "B"],
            "poundsOfNitrogenPerAcre": [150, 150],
            "irrigationProvided": [0, 0],
            "totalStandCount": [60, 61],
            "daysToAnthesis": [70, 71],
        }
    )
    truth.to_csv(tmp_path / "gt.csv", index=False)
    plots = read_plots(tmp_path / "gt.csv")
    assert plots["plot_id"].tolist() == ["Ames-4231-11-3", "Ames-4231-11-4"]
    assert plots["planting_date"].notna().all()  # site mode fills the missing date
    assert not {"totalStandCount", "daysToAnthesis", "stand_count"} & set(plots.columns)


def test_cache_resumes_and_re_extracts_changed_files(tmp_path):
    root = tmp_path / "d"
    write_synthetic(root, plots_per_site=2, defects=False, uav=False)
    images = discover_images(root)
    cache = tmp_path / "cache.jsonl"
    first, t1 = extract_images(images, root, cache, workers=1, progress=lambda m: None)
    again, t2 = extract_images(images, root, cache, workers=1, progress=lambda m: None)
    assert t1["extracted"] == len(images) and t2["extracted"] == 0
    pd.testing.assert_frame_equal(first, again)
    path = root / images["path"].iloc[0]
    data = tifffile.imread(path)
    tifffile.imwrite(path, (data // 2).astype(np.uint16), photometric="minisblack")
    third, t3 = extract_images(images, root, cache, workers=1, progress=lambda m: None)
    assert t3["extracted"] == 1
    assert third["red_mean"].iloc[0] != first["red_mean"].iloc[0]


def test_uav_features():
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb[:3, :3] = (40, 120, 30)  # green canopy
    rgb[3, 3] = (150, 120, 90)  # soil
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    s = uav_image_stats(buf.getvalue())
    assert s["n_valid"] == 10 and s["error"] is None
    assert s["green_frac"] == pytest.approx(0.9)
    assert s["exg_mean"] > 0
    g = 120 / 190
    assert s["exg_median"] == pytest.approx(2 * g - 40 / 190 - 30 / 190)
    rgba = np.dstack([rgb, np.where((rgb > 0).any(axis=2), 255, 0).astype(np.uint8)])
    rgba[0, 0, 3] = 0
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    assert uav_image_stats(buf.getvalue())["n_valid"] == 9
    assert uav_image_stats(b"not a png")["error"]


@pytest.fixture(scope="module")
def pipeline_out(tmp_path_factory):
    root = tmp_path_factory.mktemp("pipe") / "data"
    info = write_synthetic(root, plots_per_site=6, defects=True, uav=True)
    out = tmp_path_factory.mktemp("pipe_out")
    summary = run(root, out, workers=2, visual_qa=True, progress=lambda m: None)
    return root, out, summary, info


def test_pipeline_writes_every_output(pipeline_out):
    _, out, summary, _ = pipeline_out
    for name in (
        "satellite_image_features.parquet",
        "satellite_features.parquet",
        "satellite_uav_features.parquet",
        "uav_image_features.parquet",
        "canonical_observations.csv",
        "quality_flags.csv",
        "reports/feature_quality_report.md",
        "reports/feature_dictionary.md",
        "visual_qa/sample.csv",
        "visual_qa/contact_sheet_01.png",
        "run_summary.json",
    ):
        assert (out / name).exists(), name
    assert summary["cutoffs"] == ["records_only", "TP1", "TP2", "TP3", "TP4", "TP5", "TP6"]
    for cutoff in summary["cutoffs"]:
        part = pd.read_parquet(out / "progressive" / f"{cutoff}.parquet")
        assert set(part["cutoff"]) == {cutoff}


def test_every_planted_defect_is_flagged(pipeline_out):
    root, out, _, info = pipeline_out
    flags = pd.read_csv(out / "quality_flags.csv")
    by_path = flags.groupby("path")["flag"].apply(set)
    rel = {k: str(Path(v).relative_to(root)) for k, v in info["defects"].items()}
    assert "corrupt" in by_path[rel["corrupt"]]
    assert "unexpected_band_count" in by_path[rel["four_band"]]
    assert "duplicate_content" in by_path[rel["duplicate"]]
    assert "saturated_pixels" in by_path[rel["saturated"]]
    assert "small_footprint" in by_path[rel["low_valid"]]
    assert "implausible_change" in by_path[rel["jump"]]
    missing = flags[flags["flag"] == "missing_tp"]
    assert ((missing["plot_id"] == "Lincoln-hybrids-1-1") & (missing["time_point"] == 4)).any()
    table = pd.read_parquet(out / "satellite_features.parquet")
    row = table[(table["plot_id"] == "Lincoln-hybrids-1-1") & (table["cutoff"] == "TP4")]
    assert row["latest_image_tp"].iloc[0] == 3 and row["days_since_latest_image"].iloc[0] > 0
    images = pd.read_parquet(out / "satellite_image_features.parquet")
    assert len(images) == len(discover_images(root).query("modality == 'satellite'"))


def test_dictionary_covers_every_column(pipeline_out):
    _, out, _, _ = pipeline_out
    joined = pd.read_parquet(out / "satellite_uav_features.parquet")
    for column in joined.columns:
        meaning, availability = describe(column)
        assert meaning and availability
    assert set(uav_columns()) <= set(joined.columns)
    text = dictionary_markdown()
    assert "`ndvi_trend`" in text and "`final_yield`" in text


def test_quality_report_mentions_band_check(pipeline_out):
    _, out, _, _ = pipeline_out
    report = (out / "reports" / "feature_quality_report.md").read_text()
    assert "brightest band" in report and "## Flags" in report
    assert qa.FLAG_TEXT.keys() >= set(pd.read_csv(out / "quality_flags.csv")["flag"])


def test_every_cutoff_describes_the_same_imaged_plots(pipeline_out):
    root, out, _, _ = pipeline_out
    table = pd.read_parquet(out / "satellite_features.parquet")
    per_cutoff = table.groupby("cutoff")["plot_id"].apply(frozenset)
    assert per_cutoff.nunique() == 1
    images = pd.read_parquet(out / "satellite_image_features.parquet")
    plots = read_plots(root / "GroundTruth" / "HYBRID_HIPS_V3.5_ALLPLOTS.csv")
    extra = pd.DataFrame(
        {"plot_id": ["Ames-other-9-9"], "site_id": ["Ames"], "final_yield": [150.0]}
    )
    rebuilt = build_progressive(images, pd.concat([plots, extra]), None)
    assert "Ames-other-9-9" not in set(rebuilt["plot_id"])
    assert set(rebuilt["plot_id"]) == set(per_cutoff.iloc[0])
