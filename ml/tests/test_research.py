"""The research record and the code agree."""

import yaml

from app.features import thresholds
from app.features.catalog import CATALOG
from soilsignal_ml import ML_ROOT

DOC = yaml.safe_load((ML_ROOT / "research" / "agronomy_thresholds.yaml").read_text())


def test_every_documented_threshold_matches_the_code():
    for entry in DOC["thresholds"]:
        assert getattr(thresholds, entry["code_constant"]) == entry["value"], entry["id"]
        assert entry["source"] and entry["url"].startswith("http"), entry["id"]


def test_every_numeric_threshold_in_code_is_documented():
    documented = {e["code_constant"] for e in DOC["thresholds"]}
    constants = {
        k
        for k, v in vars(thresholds).items()
        if k.isupper() and isinstance(v, int | float) and not isinstance(v, bool)
    }
    assert constants <= documented, f"undocumented: {sorted(constants - documented)}"


def test_sensitivity_expectations_name_real_features():
    for entry in DOC["sensitivity_expectations"]:
        assert entry["feature"] in CATALOG
        assert entry["expected"] in {"increase", "decrease", "context"}
