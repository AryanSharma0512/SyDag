"""
Training tables: one row per plot, features as of a season cutoff.

Every value comes from the backend's build_features(), the same function the API
calls when it serves a forecast, so training and serving cannot drift apart.
"""

from datetime import date

import pandas as pd

from app.features.build import build_features
from app.features.catalog import info
from soilsignal_ml.ingest.canonical import CanonicalDataset

ID_COLUMNS = ["plot_id", "field_id", "site_id", "year", "final_yield"]
# Ablation groups, in the order they are added.
GROUPS = ("management", "temporal", "crop", "weather", "soil", "soil_weather", "history")


def cutoff_date(year: int, as_of: str) -> date:
    month, day = (int(p) for p in as_of.split("-"))
    return date(year, month, day)


def feature_table(dataset: CanonicalDataset, as_of: str) -> pd.DataFrame:
    """Features for every plot with a harvested yield, as known on as_of ('MM-DD')."""
    plots = dataset.plots[dataset.plots["final_yield"].notna()]
    rows = []
    for _, plot in plots.iterrows():
        features = build_features(dataset.field_inputs(plot), cutoff_date(int(plot["year"]), as_of))
        rows.append({**{c: plot[c] for c in ID_COLUMNS}, **features})
    return pd.DataFrame(rows)


def feature_columns(table: pd.DataFrame) -> list[str]:
    return [c for c in table.columns if c not in ID_COLUMNS]


def group_of(name: str) -> str:
    return info(name).group


def select_groups(columns: list[str], groups: set[str]) -> list[str]:
    """Columns whose group is included. Soil-weather interactions need both parents."""
    if {"soil", "weather"} <= groups:
        groups = groups | {"soil_weather"}
    return [c for c in columns if group_of(c) in groups]
