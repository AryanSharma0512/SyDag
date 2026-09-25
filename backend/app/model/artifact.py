"""
Loading and running exported model artifacts.

Only load artifacts the team produced: joblib files are pickles and execute code
when loaded.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.model.contract import (
    METADATA_FILE,
    MODEL_FILE,
    SCHEMA_FILE,
    Direction,
    FeatureCategory,
    FeatureSchema,
    ModelMetadata,
)
from app.model.explain import baseline_contributions

FeatureValue = float | int | str | None


class ArtifactError(Exception):
    """An artifact directory is missing files or is internally inconsistent."""


class FeatureValidationError(ValueError):
    """Prediction input doesn't match the model's feature schema."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Driver:
    label: str
    weight: float  # percent of total importance, 0-100
    category: FeatureCategory
    direction: Direction
    # Set for per-prediction drivers: which feature, this field's value, the typical value.
    feature: str | None = None
    value: FeatureValue = None
    typical: FeatureValue = None


@dataclass(frozen=True)
class Prediction:
    yield_: float
    lower_bound: float
    upper_bound: float
    confidence: float  # 0-100
    confidence_rating: str
    # Share of the model's numeric inputs inside their training range (1.0 = none outside).
    in_domain_share: float
    # This prediction's own drivers when the schema supports them, else the model's global ones.
    drivers: list[Driver]


# Driver weights below this share of the total are not shown.
MIN_DRIVER_WEIGHT = 1.0
MAX_DRIVERS = 8


def confidence_from_interval(
    point: float, lower: float, upper: float, in_domain_share: float = 1.0
) -> tuple[float, str]:
    """Confidence = interval precision x in-domain share.

    Interval precision is 1 - (interval width / forecast): the model's validated error
    at this point in the season, relative to the forecast. In-domain share is the
    fraction of numeric inputs inside the central 98% of training values; each input
    outside it means the model is extrapolating. A display score, not a probability:
    the interval's coverage level is fixed by the model's metadata.
    """
    if point <= 0:
        return 0.0, "LOW"
    precision = max(0.0, min(1.0, 1 - (upper - lower) / point))
    score = 100 * precision * max(0.0, min(1.0, in_domain_share))
    rating = "HIGH" if score >= 80 else "MODERATE" if score >= 60 else "LOW"
    return round(score), rating


class ModelArtifact:
    def __init__(self, metadata: ModelMetadata, schema: FeatureSchema, estimator: Any) -> None:
        self.metadata = metadata
        self.schema = schema
        self.estimator = estimator
        self._check_consistency()
        self.drivers = self._compute_drivers()

    @classmethod
    def load(cls, directory: Path) -> "ModelArtifact":
        missing = [
            f for f in (MODEL_FILE, METADATA_FILE, SCHEMA_FILE) if not (directory / f).is_file()
        ]
        if missing:
            raise ArtifactError(f"{directory.name}: missing {', '.join(missing)}")
        try:
            metadata = ModelMetadata.model_validate(
                json.loads((directory / METADATA_FILE).read_text())
            )
            schema = FeatureSchema.model_validate(json.loads((directory / SCHEMA_FILE).read_text()))
        except ValueError as err:
            raise ArtifactError(f"{directory.name}: {err}") from err
        estimator = joblib.load(directory / MODEL_FILE)
        return cls(metadata, schema, estimator)

    def _check_consistency(self) -> None:
        mid = self.metadata.model_id
        names = self.schema.names
        if self.metadata.feature_count != len(names):
            raise ArtifactError(
                f"{mid}: metadata.feature_count={self.metadata.feature_count} "
                f"but feature_schema has {len(names)} features"
            )
        if not callable(getattr(self.estimator, "predict", None)):
            raise ArtifactError(f"{mid}: estimator has no predict()")
        fitted_names = getattr(self.estimator, "feature_names_in_", None)
        if fitted_names is None:
            fitted_names = getattr(self.estimator, "feature_names_", None)  # CatBoost
        if fitted_names is not None and list(fitted_names) != names:
            raise ArtifactError(
                f"{mid}: estimator was fitted on columns {list(fitted_names)}, "
                f"but feature_schema lists {names} (names and order must match)"
            )
        # CatBoost reports n_features_in_ = 0 after unpickling; its feature_names_ above
        # is the authoritative check for it.
        n_in = getattr(self.estimator, "n_features_in_", None)
        if n_in and n_in != len(names):
            raise ArtifactError(
                f"{mid}: estimator expects {n_in} features, schema has {len(names)}"
            )

    def _compute_drivers(self) -> list[Driver]:
        features = self.schema.features
        if all(f.importance is not None for f in features):
            raw = [float(f.importance) for f in features]
        elif hasattr(self.estimator, "feature_importances_"):
            raw = [float(v) for v in self.estimator.feature_importances_]
        else:
            return []
        total = sum(raw)
        if total <= 0:
            return []
        drivers = [
            Driver(
                label=f.label or f.name,
                weight=round(100 * value / total, 1),
                category=f.category,
                direction=f.direction,
            )
            for f, value in zip(features, raw, strict=True)
        ]
        return sorted(drivers, key=lambda d: d.weight, reverse=True)

    def _to_frame(self, rows: list[dict[str, FeatureValue]]) -> pd.DataFrame:
        specs = {f.name: f for f in self.schema.features}
        problems: list[str] = []
        records = []
        for i, row in enumerate(rows):
            prefix = f"row {i}: " if len(rows) > 1 else ""
            missing = [n for n in specs if n not in row]
            unknown = sorted(set(row) - set(specs))
            if missing:
                problems.append(f"{prefix}missing features {missing}")
            if unknown:
                problems.append(f"{prefix}unknown features {unknown}")
            record: dict[str, FeatureValue] = {}
            for name, spec in specs.items():
                value = row.get(name)
                if value is None:
                    if name in row and not spec.nullable:
                        problems.append(f"{prefix}'{name}' may not be null")
                    record[name] = math.nan if spec.dtype != "category" else None
                elif spec.dtype == "category":
                    record[name] = str(value)
                elif isinstance(value, bool) or not isinstance(value, int | float):
                    problems.append(f"{prefix}'{name}' must be a number, got {value!r}")
                elif not math.isfinite(value) and not spec.nullable:
                    problems.append(f"{prefix}'{name}' must be finite")
                else:
                    record[name] = value
            records.append(record)
        if problems:
            raise FeatureValidationError(problems)
        return pd.DataFrame.from_records(records, columns=self.schema.names)

    def _in_domain_share(self, frame: pd.DataFrame) -> list[float]:
        ranged = [
            f for f in self.schema.features if f.train_low is not None and f.train_high is not None
        ]
        shares = []
        for _, row in frame.iterrows():
            checked = [f for f in ranged if pd.notna(row[f.name])]
            inside = [f for f in checked if f.train_low <= row[f.name] <= f.train_high]
            shares.append(len(inside) / len(checked) if checked else 1.0)
        return shares

    def _local_drivers(self, frame: pd.DataFrame) -> list[list[Driver]] | None:
        specs = [f for f in self.schema.features if f.typical is not None]
        if not specs:
            return None
        typical = {
            f.name: (str(f.typical) if f.dtype == "category" else float(f.typical)) for f in specs
        }
        contributions = baseline_contributions(self.estimator, frame, typical)
        out = []
        for i, (_, row) in enumerate(frame.iterrows()):
            c = contributions.iloc[i]
            total = float(c.abs().sum())
            drivers = []
            for f in specs:
                value, delta = row[f.name], float(c[f.name])
                weight = 100 * abs(delta) / total if total > 0 else 0.0
                if weight < MIN_DRIVER_WEIGHT:
                    continue
                if f.dtype == "category":
                    label = f"{f.label or f.name}: {value}"
                elif pd.isna(value):
                    label = f"{f.label or f.name} (not available)"
                elif value >= float(f.typical):
                    label = f.high_label or f.label or f.name
                else:
                    label = f.low_label or f.label or f.name
                direction: Direction = (
                    "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
                )
                drivers.append(
                    Driver(
                        label,
                        round(weight, 1),
                        f.category,
                        direction,
                        feature=f.name,
                        value=None if pd.isna(value) else value,
                        typical=f.typical,
                    )
                )
            out.append(sorted(drivers, key=lambda d: d.weight, reverse=True)[:MAX_DRIVERS])
        return out

    def predict(self, rows: list[dict[str, FeatureValue]]) -> list[Prediction]:
        frame = self._to_frame(rows)
        interval = self.metadata.interval
        shares = self._in_domain_share(frame)
        local = self._local_drivers(frame)
        results = []
        for i, point in enumerate(self.estimator.predict(frame)):
            point = float(point)
            # Yield can't be negative; wide early-season ranges are cut at zero.
            lower = max(0.0, point + interval.lower_offset)
            upper = point + interval.upper_offset
            confidence, rating = confidence_from_interval(point, lower, upper, shares[i])
            results.append(
                Prediction(
                    yield_=round(point, 1),
                    lower_bound=round(lower, 1),
                    upper_bound=round(upper, 1),
                    confidence=confidence,
                    confidence_rating=rating,
                    in_domain_share=round(shares[i], 3),
                    drivers=local[i] if local is not None else self.drivers,
                )
            )
        return results


class ModelRegistry:
    """All artifacts under a directory, one subdirectory per model."""

    def __init__(self, artifacts: list[ModelArtifact]) -> None:
        ids = [a.metadata.model_id for a in artifacts]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ArtifactError(f"duplicate model_id across artifacts: {dupes}")
        # Sorted by season cutoff; full-season models (as_of=None) last.
        self.artifacts = sorted(artifacts, key=lambda a: a.metadata.as_of or "99-99")

    @classmethod
    def load(cls, root: Path) -> "ModelRegistry":
        if not root.is_dir():
            return cls([])
        # Hidden directories are in-progress exports (see export.save_artifact).
        dirs = sorted(
            d
            for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(".") and (d / METADATA_FILE).exists()
        )
        artifacts = [ModelArtifact.load(d) for d in dirs]
        for d, artifact in zip(dirs, artifacts, strict=True):
            if artifact.metadata.model_id != d.name:
                raise ArtifactError(
                    f"directory '{d.name}' holds model_id '{artifact.metadata.model_id}'; "
                    "they must match"
                )
        return cls(artifacts)

    def get(self, model_id: str) -> ModelArtifact | None:
        return next((a for a in self.artifacts if a.metadata.model_id == model_id), None)

    def for_date(self, iso_date: str) -> ModelArtifact | None:
        """The model with the latest cutoff on or before the date (ISO 'YYYY-MM-DD'),
        so a forecast never uses a model trained on information from after that date.
        Full-season models only apply when no cutoff model exists."""
        month_day = iso_date[5:10]
        dated = [a for a in self.artifacts if a.metadata.as_of is not None]
        if dated:
            eligible = [a for a in dated if a.metadata.as_of <= month_day]
            return eligible[-1] if eligible else None
        return self.artifacts[-1] if self.artifacts else None
