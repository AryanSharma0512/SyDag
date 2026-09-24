"""
Writing model artifacts. The ML pipeline calls save_artifact() after training, so
anything it exports is guaranteed to load in the API.
"""

import shutil
from pathlib import Path
from typing import Any

import joblib

from app.model.artifact import ModelArtifact
from app.model.contract import METADATA_FILE, MODEL_FILE, SCHEMA_FILE, FeatureSchema, ModelMetadata


def save_artifact(
    estimator: Any, metadata: ModelMetadata, schema: FeatureSchema, root: Path
) -> Path:
    """Write <root>/<model_id>/ and verify it loads back. Returns the artifact directory."""
    # Validate before touching disk (raises ArtifactError on inconsistency).
    ModelArtifact(metadata, schema, estimator)

    out = root / metadata.model_id
    tmp = root / f".{metadata.model_id}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    joblib.dump(estimator, tmp / MODEL_FILE)
    (tmp / METADATA_FILE).write_text(metadata.model_dump_json(indent=2) + "\n")
    (tmp / SCHEMA_FILE).write_text(schema.model_dump_json(indent=2) + "\n")
    ModelArtifact.load(tmp)

    # Swap in only after the new artifact is known to load.
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    return out
