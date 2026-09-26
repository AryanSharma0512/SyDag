"""
Point-in-time integrity of the progressive imagery features.

A TP2 row must not change when TP3..TP6 imagery is deleted or altered, when later
acquisition dates are changed (even moved earlier than TP2), when later UAV flights change,
or when yields change. Each test runs the full pipeline on a synthetic dataset in the
challenge layout and compares the records_only, TP1 and TP2 rows exactly.
"""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import tifffile
from PIL import Image

import soilsignal_ml  # noqa: F401  (puts backend/ on the import path)
from soilsignal_ml.imagery.pipeline import run
from soilsignal_ml.imagery.progressive import (
    LeakageError,
    build_progressive,
    cutoff_rows,
    usable_images,
)
from soilsignal_ml.imagery.synthetic import PLANTING, write_synthetic

LATER = (3, 4, 5, 6)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("imagery") / "data"
    write_synthetic(root, plots_per_site=8, defects=True, uav=True)
    return root


def _run(root: Path, out: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    run(root, out, workers=1, visual_qa=False, progress=lambda m: None)
    return (
        pd.read_parquet(out / "satellite_features.parquet"),
        pd.read_parquet(out / "satellite_uav_features.parquet"),
        pd.read_parquet(out / "satellite_image_features.parquet"),
    )


def _early(table: pd.DataFrame, drop: tuple[str, ...] = ()) -> pd.DataFrame:
    t = table[table["cutoff_tp"] <= 2].drop(columns=list(drop))
    return t.sort_values(["cutoff_tp", "plot_id"]).reset_index(drop=True)


@pytest.fixture(scope="module")
def baseline(dataset, tmp_path_factory):
    return _run(dataset, tmp_path_factory.mktemp("baseline"))


def _copy(dataset: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "data"
    shutil.copytree(dataset, dst)
    return dst


def test_deleting_later_satellite_imagery_changes_nothing_through_tp2(baseline, dataset, tmp_path):
    root = _copy(dataset, tmp_path)
    for site in PLANTING:
        for tp in LATER:
            shutil.rmtree(root / "Satellite" / site / f"TP{tp}")
    table, joined, _ = _run(root, tmp_path / "out")
    assert set(table["cutoff_tp"]) >= {0, 1, 2}
    pd.testing.assert_frame_equal(_early(baseline[0]), _early(table))
    pd.testing.assert_frame_equal(_early(baseline[1]), _early(joined))


def test_altering_later_imagery_dates_uav_and_yield_changes_nothing_through_tp2(
    baseline, dataset, tmp_path
):
    root = _copy(dataset, tmp_path)
    rng = np.random.default_rng(1)
    for path in (root / "Satellite").rglob("*.TIF"):
        if int(path.parent.name[2:]) in LATER:
            try:
                data = tifffile.imread(path)
            except Exception:
                continue
            noisy = np.where(data > 0, rng.integers(1, 9000, data.shape), 0).astype(np.uint16)
            tifffile.imwrite(path, noisy, photometric="minisblack")
    for path in (root / "UAV").rglob("*.png"):
        if path.parent.name in ("TP2", "TP3"):  # flights after the TP2 satellite date
            arr = np.asarray(Image.open(path)).copy()
            arr[arr > 0] = 255 - arr[arr > 0]
            Image.fromarray(arr).save(path)
    dates_path = root / "GroundTruth" / "DateofCollection.xlsx"
    dates = pd.read_excel(dates_path)
    later = dates["Image"].eq("Satellite") & dates["time"].isin([f"TP{k}" for k in LATER])
    # Move every later acquisition before TP1: only TP numbering may decide what a TP2 row sees.
    dates.loc[later, "Date"] = pd.to_datetime(dates.loc[later, "Date"]) - pd.Timedelta(days=90)
    dates.to_excel(dates_path, index=False)
    truth_path = root / "GroundTruth" / "HYBRID_HIPS_V3.5_ALLPLOTS.csv"
    truth = pd.read_csv(truth_path)
    truth["yieldPerAcre"] = truth["yieldPerAcre"] * 2 + 7
    truth.to_csv(truth_path, index=False)

    table, joined, _ = _run(root, tmp_path / "out")
    base = _early(baseline[0], drop=("final_yield",))
    pd.testing.assert_frame_equal(base, _early(table, drop=("final_yield",)))
    pd.testing.assert_frame_equal(
        _early(baseline[1], drop=("final_yield",)), _early(joined, drop=("final_yield",))
    )
    # The yield did change, so the comparison above is not vacuous.
    assert not np.allclose(
        _early(baseline[0])["final_yield"].to_numpy(), _early(table)["final_yield"].to_numpy()
    )


def test_every_cutoff_equals_a_build_from_truncated_imagery(baseline):
    table, _, images = baseline
    for k in range(1, 7):
        truncated = build_progressive(images[images["time_point"] <= k], _plots(images), None)
        full = build_progressive(images, _plots(images), None)
        a = full[full["cutoff_tp"] == k].reset_index(drop=True)
        b = truncated[truncated["cutoff_tp"] == k].reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)


def _plots(images: pd.DataFrame) -> pd.DataFrame:
    p = images[["plot_id", "site_id"]].drop_duplicates("plot_id").copy()
    p["planting_date"] = p["site_id"].map(lambda s: pd.Timestamp(PLANTING[s]))
    p["final_yield"] = 100.0
    return p


def test_latest_image_never_after_as_of_date(baseline):
    table = baseline[0]
    dated = table.dropna(subset=["latest_image_date", "as_of_date"])
    assert len(dated)
    assert (dated["latest_image_date"] <= dated["as_of_date"]).all()
    assert (dated["latest_image_tp"] <= dated["cutoff_tp"]).all()
    joined = baseline[1].dropna(subset=["uav_latest_date"])
    assert len(joined)
    assert (joined["uav_latest_date"] <= joined["as_of_date"]).all()


def test_an_image_dated_after_the_cutoff_is_not_used(baseline):
    """A file labelled TP2 but acquired after the TP2 date (mislabelled) is excluded."""
    _, _, images = baseline
    img = images.copy()
    img["date"] = pd.to_datetime(img["date"])
    target = img[(img["time_point"] == 2) & img["error"].isna()].index[0]
    img.loc[target, "date"] = img.loc[target, "date"] + pd.Timedelta(days=30)
    img.loc[target, "ndvi_mean"] = -0.9
    table = build_progressive(img, _plots(img), None)
    row = table[(table["cutoff_tp"] == 2) & (table["plot_id"] == img.loc[target, "plot_id"])]
    assert row["latest_image_tp"].iloc[0] == 1
    assert (row["ndvi_current"] > 0).all()


def test_cutoff_rows_refuse_later_images(baseline):
    _, _, images = baseline
    usable = usable_images(images, None)
    with pytest.raises(LeakageError):
        cutoff_rows(
            usable[usable["time_point"] <= 3], None, 2, dict.fromkeys(usable["site_id"], pd.NaT)
        )


def test_target_and_in_season_ground_truth_are_not_features(baseline):
    table = baseline[0]
    assert table.columns[-1] == "final_yield"
    lowered = [c.lower() for c in table.columns]
    for leaked in ("stand", "anthesis", "yieldperacre", "gdd"):
        assert not [c for c in lowered if leaked in c]
    assert not [c for c in table.columns if "yield" in c and c != "final_yield"]


def test_control_altering_tp2_imagery_does_change_tp2_rows(baseline, dataset, tmp_path):
    """The comparisons above would pass trivially if rows ignored imagery. They don't."""
    root = _copy(dataset, tmp_path)
    for path in (root / "Satellite").rglob("TP2/*.TIF"):
        try:
            data = tifffile.imread(path)
        except Exception:
            continue
        tifffile.imwrite(path, (data // 2).astype(np.uint16), photometric="minisblack")
    table, _, _ = _run(root, tmp_path / "out")
    early = _early(table)
    base = _early(baseline[0])
    tp1 = early["cutoff_tp"] <= 1
    pd.testing.assert_frame_equal(base[tp1], early[tp1])
    assert not base.loc[~tp1, "cur_red_mean"].equals(early.loc[~tp1, "cur_red_mean"])
