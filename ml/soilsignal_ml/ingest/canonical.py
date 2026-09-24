"""
The canonical dataset every adapter produces, so training never depends on a
source's own column names.

    plots         one row per plot: ids, location, management, final_yield (bu/ac)
    observations  one row per plot image: date, band reflectances, vegetation indices
    weather       one row per site-day: tmax_f, tmin_f, prcp_mm
    soil          one row per plot: SSURGO properties at the plot
    county_yields one row per site-year: published county yield (bu/ac)
    sites         one row per site: name, state, county, weather station

Stored as CSV under ml/data/processed/<name>/.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from app.features.inputs import CanopyObservation, DailyWeather, FieldInputs, SoilInputs
from app.features.vegetation import INDEX_NAMES
from soilsignal_ml import ML_ROOT

PROCESSED = ML_ROOT / "data" / "processed"

PLOT_COLUMNS = [
    "plot_id",
    "field_id",
    "site_id",
    "year",
    "planting_date",
    "latitude",
    "longitude",
    "genotype",
    "nitrogen_lb_ac",
    "irrigated",
    "final_yield",
]
OBSERVATION_COLUMNS = ["plot_id", "date", "source", *INDEX_NAMES]
WEATHER_COLUMNS = ["site_id", "date", "tmax_f", "tmin_f", "prcp_mm"]
SOIL_COLUMNS = [
    "plot_id",
    "available_water_storage_cm",
    "organic_matter",
    "ph",
    "root_zone_depth_cm",
    "drainage",
    "slope_percent",
]
# Management columns passed to the model when present (known at planting).
MANAGEMENT_COLUMNS = ["genotype", "nitrogen_lb_ac", "irrigated"]
TABLES = ("plots", "observations", "weather", "soil", "county_yields", "sites")


def _none(value):
    return None if pd.isna(value) else value


@dataclass
class CanonicalDataset:
    name: str
    plots: pd.DataFrame
    observations: pd.DataFrame
    weather: pd.DataFrame
    soil: pd.DataFrame
    county_yields: pd.DataFrame
    sites: pd.DataFrame
    provenance: dict = field(default_factory=dict)

    # ---- storage -----------------------------------------------------------------

    def save(self, root: Path = PROCESSED) -> Path:
        out = root / self.name
        out.mkdir(parents=True, exist_ok=True)
        for table in TABLES:
            getattr(self, table).to_csv(out / f"{table}.csv", index=False)
        (out / "provenance.json").write_text(json.dumps(self.provenance, indent=2) + "\n")
        return out

    @classmethod
    def load(cls, name: str, root: Path = PROCESSED) -> "CanonicalDataset":
        src = root / name
        tables = {
            t: pd.read_csv(src / f"{t}.csv", dtype={"plot_id": str, "site_id": str}) for t in TABLES
        }
        for t in ("observations", "weather"):
            tables[t]["date"] = pd.to_datetime(tables[t]["date"]).dt.date
        tables["plots"]["planting_date"] = pd.to_datetime(tables["plots"]["planting_date"]).dt.date
        provenance = json.loads((src / "provenance.json").read_text())
        return cls(name=name, provenance=provenance, **tables)

    # ---- per-plot inputs for feature engineering -----------------------------------

    def indices(self) -> list[str]:
        return [
            i for i in INDEX_NAMES if i in self.observations and self.observations[i].notna().any()
        ]

    def _index_maps(self) -> None:
        if hasattr(self, "_obs_by_plot"):
            return
        idx = self.indices()
        self._obs_by_plot = {
            pid: tuple(
                CanopyObservation(
                    day=r.date,
                    values={i: float(getattr(r, i)) for i in idx if pd.notna(getattr(r, i))},
                )
                for r in g.itertuples()
            )
            for pid, g in self.observations.sort_values("date").groupby("plot_id")
        }
        obs = self.observations.merge(self.plots[["plot_id", "site_id"]], on="plot_id")
        means = obs.groupby(["site_id", "date"])[idx].mean().reset_index()
        self._reference_by_site = {
            sid: tuple(
                CanopyObservation(day=r.date, values={i: float(getattr(r, i)) for i in idx})
                for r in g.itertuples()
            )
            for sid, g in means.groupby("site_id")
        }
        self._weather_by_site = {
            sid: tuple(
                DailyWeather(r.date, _none(r.tmax_f), _none(r.tmin_f), _none(r.prcp_mm))
                for r in g.sort_values("date").itertuples()
            )
            for sid, g in self.weather.groupby("site_id")
        }
        self._soil_by_plot = {
            r.plot_id: SoilInputs(
                available_water_storage_cm=_none(r.available_water_storage_cm),
                organic_matter=_none(r.organic_matter),
                ph=_none(r.ph),
                root_zone_depth_cm=_none(r.root_zone_depth_cm),
                drainage=_none(r.drainage),
                slope_percent=_none(r.slope_percent),
            )
            for r in self.soil.itertuples()
        }
        self._county_by_site = {
            sid: {int(r.year): float(r["yield"]) for _, r in g.iterrows()}
            for sid, g in self.county_yields.groupby("site_id")
        }

    def field_inputs(self, plot: pd.Series) -> FieldInputs:
        self._index_maps()
        management = {c: _none(plot[c]) for c in MANAGEMENT_COLUMNS if c in plot.index}
        if management.get("irrigated") is not None:
            management["irrigated"] = bool(management["irrigated"])
        planting: date = plot["planting_date"]
        return FieldInputs(
            season_year=int(plot["year"]),
            planting_date=planting,
            latitude=float(plot["latitude"]),
            management=management,
            canopy=self._obs_by_plot.get(plot["plot_id"], ()),
            canopy_reference=self._reference_by_site.get(plot["site_id"], ()),
            weather=self._weather_by_site.get(plot["site_id"], ()),
            soil=self._soil_by_plot.get(plot["plot_id"]),
            county_yields=self._county_by_site.get(plot["site_id"], {}),
        )
