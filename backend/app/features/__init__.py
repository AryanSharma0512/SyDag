"""
Feature engineering shared by training (ml/) and serving (the forecast provider).

    build_features(FieldInputs, as_of) -> {feature name: value}

Thresholds and their sources: app/features/thresholds.py and
ml/research/agronomy_thresholds.md.
"""
