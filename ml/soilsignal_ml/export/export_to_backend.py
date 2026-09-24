"""
Export each season cutoff's selected model to backend/artifacts/<model_id>/ with the
backend's own save_artifact(), which refuses to write anything the API couldn't load.
"""

import json
from datetime import UTC, datetime

import joblib

from app.features.catalog import info
from app.model.contract import (
    FeatureSchema,
    FeatureSpec,
    HoldoutEvaluation,
    Metrics,
    ModelMetadata,
    PredictionInterval,
)
from app.model.export import save_artifact
from soilsignal_ml import BACKEND_ROOT
from soilsignal_ml.ingest.canonical import CanonicalDataset
from soilsignal_ml.models.train import CANDIDATES, load_cutoffs, load_project

ARTIFACTS = BACKEND_ROOT / "artifacts"
DATASET_LABELS = {
    "shrestha2024": "Practice data: Shrestha et al. (2024) multistate maize trials (public, CC0)",
}


def _r(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def feature_schema(summary: dict) -> FeatureSchema:
    specs = []
    for name in summary["features"]:
        meta = info(name)
        categorical = name in summary["categorical"]
        low, high = summary["ranges"].get(name, (None, None))
        typical = summary["typical"].get(name)
        specs.append(
            FeatureSpec(
                name=name,
                dtype="category" if categorical else "float",
                # Crop images, weather windows and soil can be missing for a field; every
                # numeric model here accepts NaN. Categories (the hybrid) must be sent.
                nullable=not categorical,
                label=meta.label,
                category=meta.category,
                importance=_r(max(0.0, summary["importance"].get(name, 0.0)), 4),
                direction=summary["direction"].get(name, "neutral"),
                typical=typical if categorical or typical is None else _r(typical, 4),
                train_low=None if low is None else _r(low, 4),
                train_high=None if high is None else _r(high, 4),
                high_label=meta.high,
                low_label=meta.low,
            )
        )
    return FeatureSchema(features=specs)


def metadata(summary: dict, dataset_label: str) -> ModelMetadata:
    cfg, cv, holdout = summary["config"], summary["cv"], summary["holdout"]
    sites = summary["dev_sites"]
    return ModelMetadata(
        model_id=cfg["model_id"],
        algorithm=summary["algorithm"],
        target="grain yield at 15.5% moisture",
        unit="bu/ac",
        metrics=Metrics(rmse=_r(cv["cv_rmse"], 2), mae=_r(cv["cv_mae"], 2), r2=_r(cv["cv_r2"])),
        validation=(
            f"leave-one-site-out CV over {len(sites)} sites ({', '.join(sites)}); "
            f"features: {summary['feature_set']}; "
            f"final test on held-out site {summary['holdout_site']}"
        ),
        feature_count=len(summary["features"]),
        trained_at=datetime.now(UTC).isoformat(timespec="seconds"),
        as_of=cfg["as_of"],
        interval=PredictionInterval(
            level=summary["interval"]["level"],
            lower_offset=_r(summary["interval"]["lower_offset"], 2),
            upper_offset=_r(summary["interval"]["upper_offset"], 2),
        ),
        dataset=dataset_label,
        holdout=HoldoutEvaluation(
            group=f"site: {summary['holdout_site']}",
            metrics=Metrics(
                rmse=_r(holdout["rmse"], 2), mae=_r(holdout["mae"], 2), r2=_r(holdout["r2"])
            ),
            interval_coverage=_r(holdout["interval_coverage"]),
            n=int(holdout["n"]),
        ),
    )


def export(dataset: str) -> list[str]:
    project = load_project()
    ds = CanonicalDataset.load(dataset)
    label = DATASET_LABELS.get(ds.name, ds.name)
    written, libraries = [], set()
    for cfg in load_cutoffs():
        folder = CANDIDATES / cfg["name"]
        summary = json.loads((folder / "summary.json").read_text())
        if summary["holdout_site"] != project["holdout_site"]:
            raise ValueError(f"{cfg['name']}: candidate was trained with a different held-out site")
        model = joblib.load(folder / "model.joblib")
        path = save_artifact(model, metadata(summary, label), feature_schema(summary), ARTIFACTS)
        libraries.add(summary["library"])
        written.append(str(path))
        print(f"wrote {path.relative_to(BACKEND_ROOT.parent)} ({summary['algorithm']})")
    extra = sorted(libraries - {"scikit-learn"})
    if extra:
        print(f"note: the backend must depend on {', '.join(extra)} to load these models")
    return written
