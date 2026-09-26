"""The API's view of the weather outlook: libraries loaded once, requests validated."""

from datetime import date
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.weather_outlook.contract import to_contract
from app.weather_outlook.history import LibraryError, WeatherLibrary
from app.weather_outlook.scenarios import OutlookError, WeatherOutlook


class OutlookRequestError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status


@lru_cache(maxsize=8)
def get_engine(name: str) -> WeatherOutlook:
    directory = get_settings().weather_history_dir / name
    return WeatherOutlook(WeatherLibrary(directory))


def weather_outlook(
    site: str,
    as_of: date,
    horizon: str,
    planting: date | None = None,
    library: str | None = None,
) -> dict[str, Any]:
    name = library or get_settings().weather_outlook_library
    if not name.isidentifier():
        raise OutlookRequestError(404, f"Unknown weather library '{name}'")
    try:
        engine = get_engine(name)
    except LibraryError as err:
        raise OutlookRequestError(503, f"The weather outlook is unavailable: {err}") from err
    if horizon == "season":
        span: int | str = "season"
    elif horizon.isdigit() and int(horizon) > 0:
        span = int(horizon)
    else:
        raise OutlookRequestError(422, "horizonDays must be a positive number of days or 'season'")
    if site.lower() not in {s.lower() for s in engine.library.sites}:
        known = ", ".join(engine.library.sites)
        raise OutlookRequestError(404, f"Unknown site '{site}' (known: {known})")
    try:
        return to_contract(engine.generate(site, as_of, span, planting=planting))
    except OutlookError as err:
        raise OutlookRequestError(422, str(err)) from err
