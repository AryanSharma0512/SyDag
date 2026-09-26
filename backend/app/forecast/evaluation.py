"""
Evaluation results the ML team publishes next to the models.

`<model_dir>/imagery_ablation.json` compares validation error with and without satellite
imagery. It is written by the ML pipeline (snake_case, like metadata.json):

    {
      "dataset_label": "Challenge data",
      "validation": "leave-one-site-out",
      "as_of": "07-31",
      "variants": [
        {"id": "records", "label": "Field records only", "uses_imagery": false, "mae": 31.4},
        {"id": "imagery", "label": "+ Satellite imagery", "uses_imagery": true, "mae": 18.7}
      ]
    }

Until the file exists the API reports `pending`; nothing is estimated in its place.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import AblationVariant, ImageryAblation

IMAGERY_ABLATION_FILE = "imagery_ablation.json"


class _Variant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    uses_imagery: bool
    mae: float = Field(ge=0)
    rmse: float | None = Field(default=None, ge=0)
    r2: float | None = None


class _AblationFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_label: str
    validation: str | None = None
    as_of: str | None = Field(default=None, pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
    variants: list[_Variant] = Field(min_length=2)


def imagery_ablation(model_dir: Path) -> ImageryAblation:
    """The published comparison, or `pending`. Raises ValueError if the file is malformed."""
    path = model_dir / IMAGERY_ABLATION_FILE
    if not path.is_file():
        return ImageryAblation(status="pending")
    result = _AblationFile.model_validate_json(path.read_text())
    return ImageryAblation(
        status="ready",
        dataset_label=result.dataset_label,
        validation=result.validation,
        as_of=result.as_of,
        variants=[AblationVariant(**v.model_dump()) for v in result.variants],
    )
