"""
Experiment records: every evaluated model is appended to ml/experiments/results.csv,
with its full feature list and parameters in ml/experiments/runs/<run_id>.json.
Nothing depends on notebook memory.
"""

import csv
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from soilsignal_ml import ML_ROOT, REPO_ROOT

EXPERIMENTS = ML_ROOT / "experiments"
RESULTS = EXPERIMENTS / "results.csv"
RUNS = EXPERIMENTS / "runs"
FIELDS = [
    "run_id",
    "timestamp",
    "git_sha",
    "dataset",
    "dataset_version",
    "cutoff",
    "as_of",
    "model",
    "feature_set",
    "n_features",
    "validation",
    "train_groups",
    "test_groups",
    "mae",
    "rmse",
    "r2",
    "relative_mae",
    "mae_fold_std",
    "interval_coverage",
    "interval_lower",
    "interval_upper",
    "train_seconds",
    "seed",
    "params",
]


def git_sha() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "ml", "backend/app"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return f"{sha}{'-dirty' if dirty else ''}"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def dataset_version(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.csv")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def new_run_id(cutoff: str, model: str, feature_set: str, validation: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    slug = f"{cutoff}-{model}-{feature_set}-{validation}".replace(" ", "_").replace("+", "plus")
    return f"{stamp}-{slug}"


def record(row: dict, detail: dict) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    row = {**row, "timestamp": datetime.now(UTC).isoformat(timespec="seconds")}
    new = not RESULTS.exists()
    with RESULTS.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in FIELDS})
    (RUNS / f"{row['run_id']}.json").write_text(
        json.dumps({**row, **detail}, indent=2, default=str) + "\n"
    )
