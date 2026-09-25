"""
Showcase bundles: raw inputs for a few fields, written by the ML pipeline
(ml/soilsignal_ml/export/showcase.py). A bundle holds inputs only (images, daily
weather, soil, management, county yields, climate normals), never a yield.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.features.inputs import CanopyObservation, DailyWeather, FieldInputs, SoilInputs


@dataclass(frozen=True)
class Plot:
    plot_id: str
    latitude: float
    longitude: float
    planting_date: date
    management: dict[str, Any]
    canopy: tuple[CanopyObservation, ...]
    nir: dict[date, float]  # mean near-infrared reflectance per image
    soil: dict[str, Any] | None


@dataclass(frozen=True)
class ShowcaseField:
    plot_id: str
    neighbours: list[list[str]]  # 4 x 4 block of plot ids, north row first


class Bundle:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.dataset: str = raw["dataset"]
        self.source: dict[str, str] = raw["source"]
        self.citation: str | None = raw.get("citation")
        self.license: str | None = raw.get("license")
        self.season_year: int = raw["season_year"]
        self.site: dict[str, Any] = raw["site"]
        self.weather = tuple(
            DailyWeather(date.fromisoformat(d["date"]), d["tmax_f"], d["tmin_f"], d["prcp_mm"])
            for d in raw["weather"]
        )
        self.normals: dict[str, dict[str, Any]] = raw["climate_normals"]
        self.county_yields = {int(y): v for y, v in raw["county_yields"].items()}
        self.reference = tuple(
            CanopyObservation(
                date.fromisoformat(r["date"]), {k: v for k, v in r.items() if k != "date"}
            )
            for r in raw["canopy_reference"]
        )
        self.fields = [ShowcaseField(f["plot_id"], f["neighbours"]) for f in raw["fields"]]
        self.plots = {pid: self._plot(p) for pid, p in raw["plots"].items()}

    @staticmethod
    def _plot(p: dict[str, Any]) -> Plot:
        canopy, nir = [], {}
        for obs in p["canopy"]:
            day = date.fromisoformat(obs["date"])
            nir[day] = obs.get("nir")
            values = {k: v for k, v in obs.items() if k not in ("date", "nir") and v is not None}
            canopy.append(CanopyObservation(day, values))
        return Plot(
            plot_id=p["plot_id"],
            latitude=p["latitude"],
            longitude=p["longitude"],
            planting_date=date.fromisoformat(p["planting_date"]),
            management=p["management"],
            canopy=tuple(canopy),
            nir=nir,
            soil=p["soil"],
        )

    @classmethod
    def load(cls, path: Path) -> "Bundle":
        return cls(json.loads(path.read_text()))

    def inputs(self, plot_id: str) -> FieldInputs:
        p = self.plots[plot_id]
        s = p.soil or {}
        soil = (
            SoilInputs(
                available_water_storage_cm=s.get("available_water_storage_cm"),
                organic_matter=s.get("organic_matter"),
                ph=s.get("ph"),
                root_zone_depth_cm=s.get("root_zone_depth_cm"),
                drainage=s.get("drainage"),
                slope_percent=s.get("slope_percent"),
            )
            if p.soil
            else None
        )
        return FieldInputs(
            season_year=self.season_year,
            planting_date=p.planting_date,
            latitude=p.latitude,
            management=dict(p.management),
            canopy=p.canopy,
            canopy_reference=self.reference,
            weather=self.weather,
            soil=soil,
            county_yields=self.county_yields,
        )
