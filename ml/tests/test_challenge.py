"""
Challenge ingestion: plot key, ground-truth cleaning, acquisition dates, the image manifest
(matching, unmatched and duplicate files) and per-file raster metadata, on a small synthetic
copy of the organizers' folder layout. The last tests use the real files when present.
"""

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from soilsignal_ml.ingest import challenge as ch
from soilsignal_ml.ingest.challenge_report import write_outputs
from soilsignal_ml.ingest.imagery import SATELLITE_BANDS, read_metadata

GT_HEADER = (
    "index,qrCode,location,irrigationProvided,nitrogenTreatment,poundsOfNitrogenPerAcre,"
    "experiment,plotLength,block,row,range,plotNumber,genotype,plantingDate,totalStandCount,"
    "daysToAnthesis,GDDToAnthesis,yieldPerAcre"
)
GT_ROWS = [
    "0,22-A-1,Ames,0,High,250,4231,17.5,1,3,17,101,B73 X MO17,2022-05-22,60,NA,NA,150.5",
    "1,22-A-2,Ames,0,High,250,4231,17.5,1,4,17,102,LH82 X PHK56,2022-05-22,58,NA,NA,NA",
    "0,NA,Ames,NA,NA,0,4231,NA,NA,2,23,NA,NA,NA,NA,NA,NA,NA",  # fill plot, CSV index repeats
    "2,22-A-3,Ames,0,Low,75,4233,17.5,2,5,3,103,B73 X MO17,2022-05-23,61,NA,NA,120.0",
    "0,22-L-1,Lincoln,0,Medium,150,hybrids,17.5,1,2,2,201,PHW52 X PHZ51,2022-05-22,62,59,1346,40.2",
]
DATES = [
    ("Ames", datetime(2022, 7, 15), "Satellite", "TP1"),
    ("Ames", datetime(2022, 7, 23), "Satellite", "TP2"),
    ("Ames", datetime(2022, 7, 12), "UAV", "TP1"),
    ("Lincoln", datetime(2022, 7, 18), "Satellite", "TP1"),
    ("Missouri Valley", datetime(2022, 7, 13), "Satellite", "TP1"),
]
# Plot footprint inside the 6 x 4 bounding box (1 = plot, 0 = padding).
MASK = np.array(
    [[0, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 0]],
    dtype=bool,
)
ORIGIN = (439387.2, 4651653.6)  # top-left corner, UTM 15N (Ames)


def write_geotiff(path: Path, mask: np.ndarray = MASK, bands=SATELLITE_BANDS) -> None:
    import tifffile

    rows, cols = mask.shape
    values = np.array([500, 680, 470, 4400, 2200, 430], dtype=np.uint16)
    cube = np.where(mask[..., None], values, 0).astype(np.uint16)
    labels = {
        "red": "Red (0.618 - 0.689)",
        "green": "Green (0.533 - 0.59)",
        "blue": "Blue (0.446 - 0.52)",
        "nir": "NIR (0.768 - 0.888)",
        "red_edge": "Red Edge (0.696 - 0.749)",
        "deep_blue": "Deep Blue (0.416 - 0.456)",
    }
    gdal = (
        "<GDALMetadata>\n"
        + "".join(
            f'  <Item name="DESCRIPTION" sample="{i}" role="description">Pleiades NEO '
            f"{labels[b]} um</Item>\n"
            for i, b in enumerate(bands)
        )
        + "</GDALMetadata>\n"
    )
    geokeys = [1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, 32615]
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        path,
        cube,
        photometric="minisblack",
        planarconfig="contig",
        extratags=[
            (33550, "d", 3, (0.3, 0.3, 0.0), True),
            (33922, "d", 6, (0.0, 0.0, 0.0, ORIGIN[0], ORIGIN[1], 0.0), True),
            (34735, "H", len(geokeys), geokeys, True),
            (42112, "s", 0, gdal, True),
            (42113, "s", 0, "0", True),
        ],
    )
    assert rows and cols


def write_png(path: Path) -> None:
    from PIL import Image

    arr = np.zeros((8, 5, 4), dtype=np.uint8)
    arr[1:7, 1:4] = (40, 90, 50, 255)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path)


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    from openpyxl import Workbook

    root = tmp_path / "raw"
    gt = root / ch.GROUND_TRUTH_CSV
    gt.parent.mkdir(parents=True)
    gt.write_text("\n".join([GT_HEADER, *GT_ROWS]) + "\n")
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Location", "Date", "Image", "time"])
    for r in DATES:
        ws.append(list(r))
    wb.save(root / ch.DATES_XLSX)

    sat = root / "Satellite"
    write_geotiff(sat / "Ames/TP1/Ames-TP1-4231_17_3.TIF")
    write_geotiff(sat / "Ames/TP2/Ames-TP2-4231_17_3.TIF")
    write_geotiff(sat / "Ames/TP1/Ames-TP1-4231_1_3.TIF")  # border plot: not in ground truth
    write_geotiff(sat / "Ames/TP1/Ames-TP2-4231_17_4.TIF")  # name says TP2, folder TP1
    write_geotiff(sat / "Lincoln/TP1/Lincoln-TP1-hybrids_2_2.TIF")
    (sat / "Ames/TP1/notes.txt").write_text("not an image")
    write_png(root / "UAV/Ames/TP1/Ames-TP1-4231_17_3.PNG")
    return root


def test_plot_key_and_ground_truth_cleaning(raw: Path) -> None:
    p = ch.load_plots(raw / ch.GROUND_TRUTH_CSV).set_index("plot_id")
    assert list(p.index) == [
        "2022-Ames-4231-17-3",
        "2022-Ames-4231-17-4",
        "2022-Ames-4231-23-2",
        "2022-Ames-4233-3-5",
        "2022-Lincoln-hybrids-2-2",
    ]
    fill = p.loc["2022-Ames-4231-23-2"]
    # 0 lb N on a plot without genotype or treatment is a placeholder, not a treatment.
    assert fill["nitrogen_placeholder_zero"] and pd.isna(fill["nitrogen_lb_ac"])
    assert pd.isna(fill["planting_date"])
    assert str(fill["planting_date_filled"]) == "2022-05-22"
    assert fill["planting_date_source"] == "site_experiment_date"
    assert fill["year"] == 2022 and not fill["is_hybrid_plot"]
    assert p.loc["2022-Ames-4231-17-3", "nitrogen_lb_ac"] == 250
    assert p.loc["2022-Ames-4231-17-3", "practice_plot_id"] == "Ames-4231-17-3"
    assert p.loc["2022-Ames-4231-17-3", "field_id"] == "2022-Ames-4231"
    assert pd.isna(p.loc["2022-Ames-4231-17-4", "final_yield"])
    assert not p["gt_index"].is_unique  # the CSV's own index repeats; gt_row does not
    assert p["gt_row"].is_unique


def test_duplicate_plot_keys_are_rejected(raw: Path) -> None:
    gt = raw / ch.GROUND_TRUTH_CSV
    gt.write_text(gt.read_text() + GT_ROWS[0] + "\n")
    with pytest.raises(ValueError, match="duplicate plot keys"):
        ch.load_plots(gt)


def test_acquisition_dates_are_per_site_and_sensor(raw: Path) -> None:
    d = ch.load_acquisition_dates(raw / ch.DATES_XLSX)
    got = {(r.site_id, r.sensor, r.time_point): str(r.date) for r in d.itertuples()}
    assert got[("Ames", "satellite", "TP1")] == "2022-07-15"
    assert got[("Ames", "uav", "TP1")] == "2022-07-12"
    assert got[("Lincoln", "satellite", "TP1")] == "2022-07-18"
    assert ("MOValley", "satellite", "TP1") in got  # "Missouri Valley" aliased


def test_filename_parsing() -> None:
    files = pd.DataFrame(
        {
            "filename": [
                "Ames-TP3-4231_17_3.TIF",
                "Lincoln-TP1-hybrids_15_33.TIF",
                "Crawfordsville-TP1-4351_3_15.PNG",
                "Ames-TP3-4231-17-3.TIF",
            ]
        }
    )
    p = ch.parse_filenames(files)
    assert p.loc[0, ["name_location", "time_point", "experiment"]].tolist() == [
        "Ames",
        "TP3",
        "4231",
    ]
    assert (p.loc[0, "range"], p.loc[0, "row"]) == (17, 3)
    assert (p.loc[1, "experiment"], p.loc[1, "range"], p.loc[1, "row"]) == ("hybrids", 15, 33)
    assert p.loc[2, "extension"] == "png"
    assert not p.loc[3, "name_parsed"]


def test_manifest_joins_flags_and_metadata(raw: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    t = ch.build(raw_root=raw, out_root=out, workers=1, progress=lambda _: None)
    sat = t.satellite.set_index("image_path")
    ok = sat.loc["Satellite/Ames/TP1/Ames-TP1-4231_17_3.TIF"]
    assert ok["match_status"] == "ok" and ok["use"]
    assert ok["plot_id"] == "2022-Ames-4231-17-3"
    assert str(ok["date"]) == "2022-07-15" and ok["days_after_planting"] == 54
    assert sat.loc["Satellite/Ames/TP1/Ames-TP1-4231_1_3.TIF", "match_status"] == (
        "not_in_ground_truth"
    )
    assert sat.loc["Satellite/Ames/TP1/Ames-TP2-4231_17_4.TIF", "match_status"] == (
        "folder_name_mismatch"
    )
    assert sat.loc["Satellite/Ames/TP1/notes.txt", "match_status"] == "unparseable_name"
    # Metadata read from the file: 4 padding pixels of 24, centroid of the plot pixels.
    assert ok["metadata_status"] == "read" and ok["band_order_ok"]
    assert (ok["valid_pixels"], ok["padding_pixels"], ok["partial_zero_pixels"]) == (22, 2, 0)
    rows, cols = np.nonzero(MASK)
    assert ok["centroid_x"] == pytest.approx(ORIGIN[0] + (cols.mean() + 0.5) * 0.3, abs=1e-3)
    assert ok["centroid_y"] == pytest.approx(ORIGIN[1] - (rows.mean() + 0.5) * 0.3, abs=1e-3)
    assert ok["centroid_lat"] == pytest.approx(42.0145, abs=1e-3)
    # Plot coordinates come from its satellite images.
    plot = t.plots.set_index("plot_id").loc["2022-Ames-4231-17-3"]
    assert plot["satellite_images"] == 2 and plot["satellite_time_points"] == "TP1,TP2"
    assert plot["latitude"] == pytest.approx(ok["centroid_lat"])
    assert plot["coord_spread_m"] == 0
    uav = t.uav.iloc[0]
    assert uav["use"] and uav["valid_pixels"] == 18 and uav["alpha_rgb_disagree_pixels"] == 0
    obs = t.observations()
    assert set(obs["source"]) == {"satellite", "uav"} and obs["image_path"].notna().all()
    assert len(obs) == int(t.satellite["use"].sum() + t.uav["use"].sum())


def test_duplicates_from_a_listing_are_kept_but_not_used(raw: Path, tmp_path: Path) -> None:
    listing = tmp_path / "listing"
    listing.mkdir()
    (listing / "folders.json").write_text(
        json.dumps({"f1": "Satellite/Lincoln/TP1", "f2": "Satellite/Lincoln/TP1"})
    )
    files = [
        {
            "id": "a",
            "parentId": "f1",
            "title": "Lincoln-TP1-hybrids_2_2.TIF",
            "fileSize": "10",
            "createdTime": "2026-09-26T06:53:23Z",
        },
        {
            "id": "b",
            "parentId": "f1",
            "title": "Lincoln-TP1-hybrids_2_2.TIF",
            "fileSize": "10",
            "createdTime": "2026-09-26T06:53:26Z",
        },
        {
            "id": "a",
            "parentId": "f1",
            "title": "Lincoln-TP1-hybrids_2_2.TIF",
            "fileSize": "10",
            "createdTime": "2026-09-26T06:53:23Z",
        },  # the same Drive file listed twice
    ]
    (listing / "sat.json").write_text(json.dumps({"files": files}))
    empty = raw.parent / "empty"
    (empty / "GroundTruth").mkdir(parents=True)
    for rel in (ch.GROUND_TRUTH_CSV, ch.DATES_XLSX):
        (empty / rel).write_bytes((raw / rel).read_bytes())
    t = ch.build(
        raw_root=empty, drive_listing=listing, out_root=tmp_path / "o", progress=lambda _: None
    )
    assert t.notes["drive_listing_repeats_dropped"] == 1
    assert t.notes["empty_drive_folders"] == ["Satellite/Lincoln/TP1"]
    s = t.satellite.sort_values("copy_index")
    assert s["copies"].tolist() == [2, 2]
    assert s["use"].tolist() == [True, False] and s["is_duplicate"].tolist() == [False, True]
    assert (s["metadata_status"] == "not_local").all()


def test_raster_metadata_is_restartable(raw: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    log: list[str] = []
    ch.build(raw_root=raw, out_root=out, workers=1, limit=2, progress=log.append)
    ch.build(raw_root=raw, out_root=out, workers=1, progress=log.append)
    reads = [line for line in log if line.startswith("raster metadata")]
    assert reads[0].endswith("2 to read") and "2 cached" in reads[1]
    ch.build(raw_root=raw, out_root=out, workers=1, progress=log.append)
    assert log[-1].endswith("0 to read")


def test_outputs_hold_no_private_fields(raw: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    t = ch.build(raw_root=raw, out_root=out, workers=1, progress=lambda _: None)
    manifest = write_outputs(t, out, raw)
    for name in ("satellite_manifest", "uav_manifest", "plots", "observations"):
        cols = pd.read_parquet(out / f"{name}.parquet").columns
        assert "drive_id" not in cols and "local_path" not in cols
    assert manifest["ground_truth"]["duplicate_plot_ids"] == 0
    assert json.loads((out / "challenge_manifest.json").read_text())["dataset"] == "challenge2022"


def test_wrong_band_order_is_flagged(tmp_path: Path) -> None:
    path = tmp_path / "x.TIF"
    write_geotiff(path, bands=("nir", "red_edge", "red", "green", "blue", "deep_blue"))
    meta = read_metadata(path, "satellite")
    assert meta["band_names"] == "nir,red_edge,red,green,blue,deep_blue"
    assert not meta["band_order_ok"]


def test_unreadable_image_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "broken.TIF"
    path.write_bytes(b"II*\x00garbage")
    meta = read_metadata(path, "satellite")
    assert meta["read_ok"] is False and meta["read_error"]


# ---- the real challenge files, when present -----------------------------------------

REAL = ch.RAW_ROOT


@pytest.mark.skipif(not (REAL / ch.GROUND_TRUTH_CSV).exists(), reason="challenge data absent")
def test_real_ground_truth_keys() -> None:
    p = ch.load_plots(REAL / ch.GROUND_TRUTH_CSV)
    assert p["plot_id"].is_unique
    assert set(p["year"]) == {2022}
    # Every zero N rate is a placeholder on a plot without genotype.
    assert (p.loc[p["nitrogen_lb_ac_raw"] == 0, "genotype"]).isna().all()
    d = ch.load_acquisition_dates(REAL / ch.DATES_XLSX)
    assert len(d[d["sensor"] == "satellite"].groupby("site_id")) == 6


REAL_TIF = REAL / "Satellite/Crawfordsville/TP2/Crawfordsville-TP2-4353_9_42.TIF"


@pytest.mark.skipif(not REAL_TIF.exists(), reason="sample GeoTIFF absent")
def test_real_geotiff_matches_practice_coordinates() -> None:
    m = read_metadata(REAL_TIF, "satellite")
    assert m["band_order_ok"] and m["bands"] == 6 and m["crs_epsg"] == 32615
    # The practice pipeline placed Crawfordsville-4353-9-42 at 41.198262, -91.486475.
    d = math.hypot(
        (m["centroid_lat"] - 41.198262) * 111_320,
        (m["centroid_lon"] + 91.486475) * 111_320 * math.cos(math.radians(41.2)),
    )
    assert d < 0.5


def test_canonical_adapter_builds_training_tables(raw: Path, tmp_path: Path) -> None:
    from soilsignal_ml.ingest.canonical import PLOT_COLUMNS, CanonicalDataset
    from soilsignal_ml.ingest.challenge_adapter import ChallengeDatasetAdapter
    from soilsignal_ml.ingest.validate import validate

    out = tmp_path / "out"
    write_outputs(
        ch.build(raw_root=raw, out_root=out, workers=1, progress=lambda _: None), out, raw
    )
    ds = ChallengeDatasetAdapter(out_root=out, raw_root=raw).build()
    # Plots with a usable satellite image and coordinates; UAV-only plots are not kept.
    assert set(ds.plots["plot_id"]) == {"2022-Ames-4231-17-3", "2022-Lincoln-hybrids-2-2"}
    assert set(PLOT_COLUMNS) <= set(ds.plots.columns)
    assert set(ds.observations["source"]) == {"satellite"}
    ndvi = (4400 - 500) / (4400 + 500)  # the synthetic plot's pixels
    assert ds.observations["ndvi"].to_numpy() == pytest.approx(ndvi)
    assert ds.observations["nir"].to_numpy() == pytest.approx(0.44)
    assert set(ds.sites["site_id"]) == {"Ames", "Lincoln"}
    # Only the public-context tables are missing until `ingest` fetches them.
    assert validate(ds) == ["no weather data"]
    saved = ds.save(tmp_path / "processed")
    back = CanonicalDataset.load(ds.name, root=saved.parent)
    assert len(back.observations) == len(ds.observations)


def test_canonical_adapter_prefers_spectral_features(raw: Path, tmp_path: Path) -> None:
    from soilsignal_ml.ingest.challenge_adapter import ChallengeDatasetAdapter

    out = tmp_path / "out"
    t = ch.build(raw_root=raw, out_root=out, workers=1, progress=lambda _: None)
    write_outputs(t, out, raw)
    used = t.satellite[t.satellite["use"]]
    pd.DataFrame({"image_id": used["image_id"], "ndvi": 0.5, "ndre": 0.3}).to_parquet(
        out / "satellite_features.parquet"
    )
    ds = ChallengeDatasetAdapter(out_root=out, raw_root=tmp_path / "nowhere").build()
    assert (ds.observations["ndvi"] == 0.5).all() and ds.observations["evi"].isna().all()


@pytest.mark.skipif(not REAL_TIF.exists(), reason="sample GeoTIFF absent")
def test_real_indices_match_the_practice_pipeline() -> None:
    from soilsignal_ml.ingest.challenge_adapter import image_indices

    # backend/data/practice/shrestha2024.json, Crawfordsville-4353-9-42 on 2022-07-20.
    practice = {"ndvi": 0.82918, "ndre": 0.37175, "gndvi": 0.76413, "evi": 0.78364, "nir": 0.50254}
    got = image_indices(REAL_TIF)
    assert {k: round(got[k], 5) for k in practice} == practice
