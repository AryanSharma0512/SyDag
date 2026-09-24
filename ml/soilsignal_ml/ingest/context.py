"""
Public context for every site and plot, fetched with the same backend code the API
uses, so the model trains on the data sources it is served with:

    weather        NOAA NCEI GHCN-Daily, nearest station with rain and temperature
    soil           USDA NRCS SSURGO dominant component at each plot (Soil Data Access)
    county_yields  USDA NASS Quick Stats county corn yields (needs the NASS key)
"""

from datetime import UTC, date, datetime

import pandas as pd

from app.config import Settings
from app.context.geo import fetch_county
from app.context.http import NoData, get_http_client, request_json
from app.context.soil import (
    HORIZON_QUERY,
    MAP_UNIT_QUERY,
    _dominant_component,
    _query,
    parse_profile,
)
from app.context.weather import (
    MM_PER_INCH,
    REQUIRED_TYPES,
    SEARCH_URL,
    SERVICE,
    WeatherStation,
    _km,
    _station_name,
    fetch_daily,
    find_station,
)
from app.context.yield_history import fetch_yield_history
from soilsignal_ml import BACKEND_ROOT
from soilsignal_ml.ingest.canonical import CanonicalDataset
from soilsignal_ml.ingest.dataset_adapter import Progress

# Plots are grouped onto a ~50 m grid for soil lookups: SSURGO map units are far larger.
SOIL_GRID_DEG = 0.0005
# Gaps in the nearest station's record are filled from the next-nearest stations.
GAP_FILL_RADIUS_DEG = 0.5  # ~50 km
GAP_FILL_MAX_STATIONS = 4


def _nearby_stations(
    client, lat: float, lon: float, start: date, end: date
) -> list[WeatherStation]:
    """Stations reporting rain and temperature within the window, nearest first."""
    r = GAP_FILL_RADIUS_DEG
    data = request_json(
        client,
        SERVICE,
        "GET",
        SEARCH_URL,
        params={
            "dataset": "daily-summaries",
            "bbox": f"{lat + r:.4f},{lon - r:.4f},{lat - r:.4f},{lon + r:.4f}",
            "startDate": f"{start.isoformat()}T00:00:00",
            "endDate": f"{end.isoformat()}T23:59:59",
            "dataTypes": ",".join(sorted(REQUIRED_TYPES)),
            "limit": 50,
        },
    )
    out = []
    for result in data.get("results", []):
        types = {t.get("id") for t in result.get("dataTypes", [])}
        stations = result.get("stations") or []
        coords = (result.get("location") or {}).get("coordinates")
        if not REQUIRED_TYPES <= types or not stations or not coords:
            continue
        slon, slat = float(coords[0]), float(coords[1])
        out.append(
            WeatherStation(
                id=stations[0]["id"],
                name=_station_name(stations[0].get("name", stations[0]["id"])),
                latitude=slat,
                longitude=slon,
                distance_km=round(_km(lat, lon, slat, slon), 1),
            )
        )
    return sorted(out, key=lambda s: s.distance_km)


def _weather(dataset: CanonicalDataset, progress: Progress) -> tuple[pd.DataFrame, dict]:
    """Daily weather per site: the nearest station the backend would choose, with any
    missing day filled from the next-nearest stations (the station is kept per row)."""
    client = get_http_client()
    rows, stations = [], {}
    for site in dataset.sites.itertuples():
        year = int(dataset.plots.loc[dataset.plots["site_id"] == site.site_id, "year"].iloc[0])
        start, end = date(year, 3, 1), date(year, 10, 31)
        primary = find_station(client, site.latitude, site.longitude, start, end)
        stations[site.site_id] = primary
        candidates = [primary] + [
            s
            for s in _nearby_stations(client, site.latitude, site.longitude, start, end)
            if s.id != primary.id
        ][: GAP_FILL_MAX_STATIONS - 1]
        days = pd.date_range(start, end).date
        filled: dict[date, dict] = {}
        for station in candidates:
            got = {d.day: d for d in fetch_daily(client, station.id, start, end)}
            for day in days:
                obs = got.get(day)
                if obs is None:
                    continue
                row = filled.setdefault(day, {"site_id": site.site_id, "date": day})
                for key, value in (
                    ("tmax_f", obs.tmax_f),
                    ("tmin_f", obs.tmin_f),
                    (
                        "prcp_mm",
                        None if obs.prcp_in is None else round(obs.prcp_in * MM_PER_INCH, 1),
                    ),
                ):
                    if row.get(key) is None and value is not None:
                        row[key] = value
                        row[f"{key}_station"] = station.id
            if all(
                filled.get(d, {}).get(k) is not None
                for d in days
                for k in ("tmax_f", "tmin_f", "prcp_mm")
            ):
                break
        site_rows = [filled[d] for d in days if d in filled]
        from_primary = sum(r.get("tmax_f_station") == primary.id for r in site_rows)
        progress(
            f"  weather {site.site_id}: {primary.name} ({primary.distance_km} km) for "
            f"{from_primary}/{len(days)} days; "
            f"{len(site_rows) - from_primary} filled from nearby stations"
        )
        rows += site_rows
    return pd.DataFrame(rows), stations


def _soil(dataset: CanonicalDataset, progress: Progress) -> pd.DataFrame:
    client = get_http_client()
    plots = dataset.plots.dropna(subset=["latitude", "longitude"]).copy()
    plots["cell"] = list(
        zip(
            (plots["latitude"] / SOIL_GRID_DEG).round().astype(int),
            (plots["longitude"] / SOIL_GRID_DEG).round().astype(int),
            strict=True,
        )
    )
    horizons: dict[str, list] = {}
    by_cell = {}
    cells = plots.groupby("cell")[["latitude", "longitude"]].mean()
    progress(f"  soil: {len(cells)} grid cells")
    for cell, (lat, lon) in cells.iterrows():
        try:
            components = _query(client, MAP_UNIT_QUERY.format(lat=lat, lon=lon))
            soil = _dominant_component(components)
        except NoData:
            continue
        cokey = str(soil["cokey"])
        if cokey not in horizons:
            horizons[cokey] = _query(client, HORIZON_QUERY.format(cokey=cokey))
        profile = parse_profile(components, horizons[cokey], datetime.now(UTC))
        by_cell[cell] = profile
    rows = []
    for plot in plots.itertuples():
        p = by_cell.get(plot.cell)
        if p is None:
            continue
        rows.append(
            {
                "plot_id": plot.plot_id,
                "map_unit_key": p.map_unit_key,
                "map_unit_name": p.map_unit_name,
                "series": p.series,
                "texture": p.texture,
                "drainage": p.drainage,
                "hydrologic_group": p.hydrologic_group,
                "available_water_storage_cm": p.available_water_storage_cm,
                "organic_matter": p.organic_matter,
                "ph": p.ph,
                "root_zone_depth_cm": p.root_zone_depth_cm,
                "slope_percent": p.slope_percent,
            }
        )
    return pd.DataFrame(rows)


def _county(dataset: CanonicalDataset, progress: Progress) -> tuple[pd.DataFrame, dict]:
    client = get_http_client()
    settings = Settings(_env_file=BACKEND_ROOT / ".env")
    key = settings.nass_api_key.get_secret_value() if settings.nass_api_key else None
    rows, counties = [], {}
    for site in dataset.sites.itertuples():
        county = fetch_county(client, site.latitude, site.longitude)
        counties[site.site_id] = county
        if key is None:
            progress("  county yields skipped: SOILSIGNAL_NASS_API_KEY is not set")
            continue
        year = int(dataset.plots.loc[dataset.plots["site_id"] == site.site_id, "year"].iloc[0])
        history = fetch_yield_history(client, key, county, through_year=year)
        progress(
            f"  county {site.site_id}: {county.name}, {county.state_code} "
            f"({len(history.years)} years)"
        )
        rows += [
            {"site_id": site.site_id, "year": y.year, "yield": y.yield_} for y in history.years
        ]
    return pd.DataFrame(rows, columns=["site_id", "year", "yield"]), counties


def add_public_context(dataset: CanonicalDataset, progress: Progress = print) -> CanonicalDataset:
    progress("fetching public context")
    dataset.weather, stations = _weather(dataset, progress)
    dataset.soil = _soil(dataset, progress)
    dataset.county_yields, counties = _county(dataset, progress)
    sites = dataset.sites.copy()
    sites["county"] = sites["site_id"].map(lambda s: counties[s].name)
    sites["fips"] = sites["site_id"].map(lambda s: counties[s].fips)
    sites["weather_station"] = sites["site_id"].map(lambda s: stations[s].name)
    sites["weather_station_id"] = sites["site_id"].map(lambda s: stations[s].id)
    sites["station_distance_km"] = sites["site_id"].map(lambda s: stations[s].distance_km)
    weather = dataset.weather
    sites["weather_days_from_primary"] = sites["site_id"].map(
        lambda s: int(
            (weather.loc[weather["site_id"] == s, "tmax_f_station"] == stations[s].id).sum()
        )
    )
    dataset.sites = sites
    dataset.provenance["context"] = {
        "weather": "NOAA NCEI GHCN-Daily: nearest station with rain and temperature; missing days "
        "filled from the next-nearest stations within ~50 km (station recorded per value)",
        "soil": "USDA NRCS SSURGO via Soil Data Access (dominant component per ~50 m cell)",
        "county_yields": "USDA NASS Quick Stats, county corn grain yield",
        "retrieved": date.today().isoformat(),
    }
    return dataset
