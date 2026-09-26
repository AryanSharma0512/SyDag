"""
Adapters from a yield model to the outlook's `predict(season_weather) -> bu/ac`.

The outlook only needs a function from a season's daily weather to a yield. Everything
else about the plot stays as it was on the as-of date: its imagery, hybrid, nitrogen,
irrigation and planting date. `artifact_predictor` builds that function from an exported
SoilSignal model and the plot's raw inputs, through the same build_features the API uses.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date

from app.features.build import build_features, visible_inputs
from app.features.inputs import DailyWeather, FieldInputs
from app.model.artifact import ModelArtifact


def artifact_predictor(
    artifact: ModelArtifact, inputs: FieldInputs, as_of: date, feature_date: date
) -> Callable[[Sequence[DailyWeather]], float]:
    """Yield under a given season's weather, with the plot frozen at as_of.

    Imagery and other time-stamped inputs after as_of are dropped (they would not exist
    yet); the weather is replaced by the season passed in (observed through as_of, then a
    trajectory). Features are built as of feature_date, the model's own cutoff, so a model
    trained on end-of-season features sees a whole season of weather."""
    frozen = visible_inputs(inputs, as_of)

    def predict(weather: Sequence[DailyWeather]) -> float:
        season = tuple(d for d in weather if d.day <= feature_date)
        features = build_features(replace(frozen, weather=season), feature_date)
        # As the forecast builder does: the model's own features, missing ones as null
        # (the artifact refuses nulls its schema does not allow).
        row = {name: features.get(name) for name in artifact.schema.names}
        return artifact.predict([row])[0].yield_

    return predict
