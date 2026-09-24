"""
SoilSignal ML pipeline: ingest a dataset, build point-in-time features, train and
validate progressive (as-of-date) yield models, and export them as backend artifacts.

Feature engineering, the artifact contract and export live in the backend
(`backend/app/features`, `backend/app/model`) so training and serving share one
implementation. This package puts `backend/` on the import path to use them.
"""

import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ML_ROOT.parent
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
