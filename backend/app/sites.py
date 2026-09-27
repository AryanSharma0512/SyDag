"""
The trial sites, for the website's map and location selector (GET /api/sites).

The static inventory (location, seasons, plots, which imagery exists) is
data/trial_sites.json, written from the challenge inventory by
scripts/export_trial_sites.py. Each request adds what is live on this deployment:
the weather history behind /api/weather-outlook, and how many plots have forecasts
from the deployed models and from the published final results.

Mirrored by src/types/sites.ts.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field

from app.schemas import ApiModel


class ImageryInventory(ApiModel):
    acquisitions: int  # scheduled passes or flights in the acquisition calendar
    acquisition_dates: list[str] = Field(default_factory=list)
    plot_images: int  # usable plot images in the challenge set; 0 = no imagery here
    plots_imaged: int


class TrialSeason(ApiModel):
    year: int
    planting_dates: list[str] = Field(default_factory=list)
    plots: int
    plots_with_yield: int
    hybrids: int
    satellite: ImageryInventory
    uav: ImageryInventory


class SiteWeather(ApiModel):
    library_site: str  # the site's key in the weather library (?site= of the outlook)
    seasons: int  # historical seasons that passed quality control
    first_season: int
    last_season: int
    station: str | None = None
    analog_weighting: bool  # False: every historical season weighs the same


class SiteForecasts(ApiModel):
    live_plots: int = 0  # plots the deployed models forecast (/api/fields?site=)
    final_plots: int = 0  # plots in the published final results (/api/results/plots)
    final_site_forecast: bool = False  # the final results carry a whole-site forecast
    seasons: list[int] = Field(default_factory=list)


class TrialSite(ApiModel):
    id: str  # the data's spelling, e.g. "MOValley"
    name: str  # for people, e.g. "Missouri Valley"
    state: str
    state_name: str
    latitude: float
    longitude: float
    coordinate_source: str
    crop: str
    irrigated: bool
    seasons: list[TrialSeason]
    weather: SiteWeather | None = None
    forecasts: SiteForecasts = Field(default_factory=SiteForecasts)


@lru_cache(maxsize=2)
def load_sites(path: Path) -> tuple[TrialSite, ...]:
    """The static registry; empty if the file is missing (the map then shows no sites)."""
    if not path.is_file():
        return ()
    raw = json.loads(path.read_text())
    return tuple(TrialSite.model_validate(s) for s in raw["sites"])
