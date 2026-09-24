"""
Model artifact contract.

Every trained model is exported as a directory:

    artifacts/<model_id>/
        model.joblib         fitted estimator (anything with .predict(DataFrame))
        metadata.json        ModelMetadata
        feature_schema.json  FeatureSchema

These files are written by the ML pipeline in Python, so they use snake_case,
unlike the camelCase API responses in app/schemas.py.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

FeatureCategory = Literal["Vegetation", "Weather", "Soil", "Temporal", "Management", "History"]
Direction = Literal["positive", "negative", "neutral"]

MODEL_FILE = "model.joblib"
METADATA_FILE = "metadata.json"
SCHEMA_FILE = "feature_schema.json"


class Metrics(BaseModel):
    rmse: float
    mae: float
    r2: float


class PredictionInterval(BaseModel):
    """Offsets added to the point prediction to form the interval, typically the
    validation residual quantiles (e.g. 5th and 95th percentile for a 90% interval)."""

    level: float = Field(gt=0, lt=1)
    lower_offset: float = Field(le=0)
    upper_offset: float = Field(ge=0)


class HoldoutEvaluation(BaseModel):
    """Accuracy on data the model never saw during training, tuning or interval fitting."""

    group: str  # e.g. "site: Crawfordsville"
    metrics: Metrics
    interval_coverage: float = Field(ge=0, le=1)  # share of held-out yields inside the interval
    n: int


class ModelMetadata(BaseModel):
    model_id: str
    algorithm: str
    target: str
    unit: str = "bu/ac"
    metrics: Metrics
    validation: str  # e.g. "leave-field-out"
    feature_count: int
    trained_at: str
    # Season cutoff as "MM-DD": the model only uses information available by this
    # date. None means the model uses the full season.
    as_of: str | None = None
    interval: PredictionInterval
    dataset: str | None = None  # e.g. "shrestha2024 (public practice data)"
    holdout: HoldoutEvaluation | None = None

    @field_validator("model_id")
    @classmethod
    def _safe_model_id(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", v):
            raise ValueError("model_id may only contain letters, digits, '.', '_' and '-'")
        return v

    @field_validator("as_of")
    @classmethod
    def _valid_as_of(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", v):
            raise ValueError("as_of must be 'MM-DD'")
        return v


class FeatureSpec(BaseModel):
    name: str
    dtype: Literal["float", "int", "category"] = "float"
    # Nullable features may be sent as null; they reach the model as NaN.
    nullable: bool = False
    # Human-readable name shown in the dashboard's "Model Signals" list.
    label: str | None = None
    category: FeatureCategory
    # Global importance (any non-negative scale; normalized to % for display).
    # If omitted, the estimator's feature_importances_ is used when available.
    importance: float | None = Field(default=None, ge=0)
    direction: Direction = "neutral"
    # Typical training value (median, or most common category). Enables per-prediction
    # drivers: how far the forecast moves if this feature alone were typical.
    typical: float | str | None = None
    # Central 98% of training values; inputs outside it lower the confidence score.
    train_low: float | None = None
    train_high: float | None = None
    # Driver phrases for values above / below typical, e.g. "Rainfall deficit, last 30 days".
    high_label: str | None = None
    low_label: str | None = None


class FeatureSchema(BaseModel):
    features: list[FeatureSpec]

    @model_validator(mode="after")
    def _unique_names(self) -> "FeatureSchema":
        names = [f.name for f in self.features]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate feature names: {dupes}")
        if not names:
            raise ValueError("feature schema is empty")
        return self

    @property
    def names(self) -> list[str]:
        return [f.name for f in self.features]
