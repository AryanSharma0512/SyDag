"""Challenge ingestion on a small synthetic copy of the organizers' folder layout."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
import tifffile
from PIL import Image

from soilsignal_ml.ingest import challenge

UTM15N = 32615
ORIGIN = (446_000.0, 4_651_000.0)  # near Ames, IA
PIXEL = 0.3


def _geotiff(path, bands=6, offset=(0.0, 0.0), zero_border=2, value=1000):
    h, w = 12, 30
    data = np.zeros((h, w, bands), dtype=np.uint16)
    data[zero_border : h - zero_border, zero_border : w - zero_border, :] = value
    data[..., 3][data[..., 3] > 0] = 4 * value  # NIR brightest over canopy
    x0, y0 = ORIGIN[0] + offset[0], ORIGIN[1] + offset[1]
    geokeys = (1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, UTM15N)
    tifffile.imwrite(
        path,
        data,
        photometric="minisblack",
        planarconfig="contig",
        extratags=[
            (33550, "d", 3, (PIXEL, PIXEL, 0.0), False),
            (33922, "d", 6, (0.0, 0.0, 0.0, x0, y0, 0.0), False),
            (34735, "H", len(geokeys), geokeys, False),
        ],
    )


def _png(path, seed=0):
    rng = np.random.default_rng(seed)
    data = np.zeros((20, 40, 3), dtype=np.uint8)
    data[3:17, 3:37] = rng.integers(20, 200, (14, 34, 3))
    Image.fromarray(data).save(path)


@pytest.fixture
def raw(tmp_path):
    root = tmp_path / "raw"
    (root / "Documentation").mkdir(parents=True)
    (root / "Documentation" / "README.md").write_text("organizer readme")
    gt = root / "GroundTruth"
    gt.mkdir()
    pd.DataFrame(
        {
            "location": ["Ames", "Ames", "Ames", "MOValley", "MOValley"],
            "experiment": ["Hyrbrids", "Hybrids", "Hybrids", "Hybrids", "Hybrids"],
            "range": [1, 1, 2, 1, 1],
            "row": [1, 2, 1, 1, 1],
            "genotype": ["H1", "H2", "H1", "H3", "H3"],
            "poundsOfNitrogenPerAcre": [75, 150, 150, 175, 175],
            "plantingDate": ["2023-05-10", "2023-05-10", None, "2023-05-01", "2023-05-01"],
            "irrigationProvided": [0, 0, 0, 0, 0],
            "yieldPerAcre": [150.0, 160.0, None, 170.0, 171.0],
        }
    ).to_csv(gt / "HYBRID_HIPS_TEST_ALLPLOTS.csv", index=False)
    pd.DataFrame(
        {
            "Location": ["Ames", "Ames", "Ames", "Missouri Valley", "Missouri Valley"],
            "Date": pd.to_datetime(
                ["2023-07-15", "2023-07-30", "2023-07-16", "2023-07-20", "2023-08-01"]
            ),
            "Image": ["Satellite", "Satellite", "UAV", "Satellite", "UAV"],
            "time": ["TP1", "TP2", "TP1", "TP1", "TP1"],
        }
    ).to_excel(gt / "DateofCollection.xlsx", index=False)

    for tp in (1, 2):
        folder = root / "Satellite" / "Ames" / f"TP{tp}"
        folder.mkdir(parents=True)
        _geotiff(folder / f"Ames-TP{tp}-Hybrids_1_1.TIF")
        _geotiff(folder / f"Ames-TP{tp}-Hybrids_1_2.TIF", offset=(0.0, -5.0))
    _geotiff(root / "Satellite" / "Ames" / "TP1" / "Ames-TP1-Hybrids_9_9.TIF")
    (root / "Satellite" / "Ames" / "TP1" / "notes.txt").write_text("stray file")
    mo = root / "Satellite" / "MOValley" / "TP1"
    mo.mkdir(parents=True)
    _geotiff(mo / "MOValley-TP1-Hybrids_1_1.TIF", offset=(-400_000.0, 0.0))

    uav = root / "UAV" / "Ames" / "TP1"
    uav.mkdir(parents=True)
    _png(uav / "Ames-TP1-Hybrids_1_1.png", seed=1)
    _png(uav / "Ames-TP1-Hybrids_1_2.png", seed=1)
    _png(uav / "Ames-TP1-badname.png", seed=2)
    return root


@pytest.fixture
def built(raw, tmp_path):
    out = tmp_path / "out"
    manifest = challenge.build(raw, out, workers=1, cache=tmp_path / "cache.parquet")
    return manifest, out


def test_ground_truth_join_and_plot_ids(built):
    manifest, out = built
    plots = pd.read_parquet(out / "plots.parquet")
    assert "Ames-2023-hybrids-1-1" in set(plots["plot_id"])  # 'Hyrbrids' typo normalized
    assert all(p.startswith(s) for p, s in zip(plots["plot_id"], plots["site_id"], strict=True))
    assert manifest["counts"]["duplicate_plot_id_rows"] == 2  # MOValley 1/1 twice
    assert manifest["counts"]["plots_with_final_yield"] == 4
    assert manifest["counts"]["unique_hybrids"] == 3


def test_dates_come_from_the_workbook_not_the_time_point(built):
    _, out = built
    sat = pd.read_parquet(out / "satellite_manifest.parquet")
    ames = sat[(sat["site_id"] == "Ames") & (sat["match_status"] == "matched")]
    assert set(zip(ames["time_point"], ames["acq_date"], strict=True)) == {
        (1, date(2023, 7, 15)),
        (2, date(2023, 7, 30)),
    }
    mo = sat[sat["site_id"] == "MOValley"]
    assert mo["acq_date"].iloc[0] == date(2023, 7, 20)  # 'Missouri Valley' in the workbook


def test_nothing_is_dropped_and_exceptions_are_labelled(built, raw):
    manifest, out = built
    sat = pd.read_parquet(out / "satellite_manifest.parquet")
    uav = pd.read_parquet(out / "uav_manifest.parquet")
    files = pd.read_parquet(out / "file_inventory.parquet")
    assert len(sat) == 6 and len(uav) == 3
    assert len(files) == len([p for p in raw.rglob("*") if p.is_file()])
    status = dict(zip(sat["file_name"], sat["match_status"], strict=True))
    assert status["Ames-TP1-Hybrids_9_9.TIF"] == "no_ground_truth_plot"
    assert (
        dict(zip(uav["file_name"], uav["match_status"], strict=True))["Ames-TP1-badname.png"]
        == "unparsed_name"
    )
    assert uav["duplicate_content"].sum() == 2  # two identical PNGs under different names
    assert files.loc[files["name"] == "notes.txt", "role"].iloc[0] == "other"
    json.loads((out / "challenge_manifest.json").read_text())


def test_bands_padding_and_centroid(built):
    _, out = built
    sat = pd.read_parquet(out / "satellite_manifest.parquet")
    first = sat[sat["file_name"] == "Ames-TP1-Hybrids_1_1.TIF"].iloc[0]
    assert first["n_bands"] == 6 and first["epsg"] == UTM15N
    assert first["n_valid_pixels"] == 8 * 26 and first["n_zero_pixels"] == 12 * 30 - 8 * 26
    assert first["b4_valid_mean"] > first["b1_valid_mean"]
    assert first["centroid_x"] == pytest.approx(ORIGIN[0] + 15 * PIXEL)
    assert first["centroid_y"] == pytest.approx(ORIGIN[1] - 6 * PIXEL)
    plots = pd.read_parquet(out / "plots.parquet").set_index("plot_id")
    ames = plots.loc["Ames-2023-hybrids-1-1"]
    assert 41.5 < ames["latitude"] < 42.5 and -94.5 < ames["longitude"] < -93
    assert ames["centroid_spread_m"] == pytest.approx(0.0)
    assert ames["footprint_wkt"].startswith("POLYGON((")
    assert pd.isna(plots.loc["Ames-2023-hybrids-2-1", "latitude"])  # no image, no coordinate


def test_observations_cover_matched_images_only(built):
    _, out = built
    obs = pd.read_parquet(out / "observations.parquet")
    assert set(obs["source"]) == {"satellite", "uav"}
    assert obs[["plot_id", "date", "source", "time_point", "image_path"]].notna().all().all()
    assert len(obs[obs["source"] == "satellite"]) == 5
