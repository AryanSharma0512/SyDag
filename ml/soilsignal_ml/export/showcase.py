"""
Showcase bundle: the raw inputs the API needs to serve forecasts for a few plots of
the held-out site, written to backend/data/practice/<dataset>.json.

The bundle holds inputs only (images, daily weather, soil, management, county
history, climate normals), never a yield or a forecast. The API turns them into
forecasts with build_features() and the exported models, exactly as for new data.
"""

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.context.http import get_http_client
from app.context.weather import MM_PER_INCH, fetch_daily
from app.features.weather import modified_gdd
from soilsignal_ml import BACKEND_ROOT
from soilsignal_ml.features.build import cutoff_date
from soilsignal_ml.ingest.canonical import MANAGEMENT_COLUMNS, CanonicalDataset
from soilsignal_ml.ingest.context import GAP_FILL_MAX_STATIONS, _nearby_stations
from soilsignal_ml.models.train import load_cutoffs, load_project

OUT = BACKEND_ROOT / "data" / "practice"
QUANTILES = (0.1, 0.3, 0.5, 0.7, 0.9)  # spread of outcomes shown on the dashboard
NEIGHBOURS = 16  # 4 x 4 block of plots around each showcased plot
RAIN_NORMAL_YEARS = range(1991, 2021)  # NOAA's current 30-year normal period
GDD_PACE_YEARS = 10
SOURCE_LABELS = {
    "shrestha2024": {
        "name": "Multistate maize yield trials (Shrestha et al. 2024)",
        "short_name": "Practice data",
        "detail": (
            "Public research dataset used for practice until the challenge data is released: "
            "84 hybrids at five US Corn Belt sites in 2022, six Pléiades Neo satellite images per "
            "plot, harvested plot yields. CC0."
        ),
    }
}


def _none(value):
    return None if pd.isna(value) else value


def fully_imaged(ds: CanonicalDataset) -> set[str]:
    """Plots with every image of the season and a known hybrid."""
    images = ds.observations.groupby("plot_id").size()
    full = set(images[images == images.max()].index)
    return full & set(ds.plots.loc[ds.plots["genotype"].notna(), "plot_id"])


def showcase_plots(ds: CanonicalDataset, site: str) -> pd.DataFrame:
    """Plots at the held-out site nearest to fixed quantiles of harvested yield, so the
    dashboard shows a spread of outcomes. Only fully imaged plots with a hybrid."""
    p = ds.plots[
        (ds.plots["site_id"] == site)
        & ds.plots["plot_id"].isin(fully_imaged(ds))
        & ds.plots["final_yield"].notna()
    ].sort_values("plot_id")
    chosen = []
    for q in QUANTILES:
        target = p["final_yield"].quantile(q)
        pool = p[~p["plot_id"].isin(chosen)]
        chosen.append(pool.iloc[(pool["final_yield"] - target).abs().argsort().iloc[0]]["plot_id"])
    return p.set_index("plot_id").loc[chosen].reset_index()


def neighbour_block(ds: CanonicalDataset, plot: pd.Series) -> list[list[str]]:
    """The 16 plots nearest to `plot` (itself included) as a 4 x 4 grid: rows by latitude
    (north first), columns by longitude (west first)."""
    same = ds.plots[
        (ds.plots["site_id"] == plot["site_id"]) & ds.plots["plot_id"].isin(fully_imaged(ds))
    ].copy()
    km_lat = 111.0
    km_lon = 111.0 * np.cos(np.radians(plot["latitude"]))
    same["d"] = np.hypot(
        (same["latitude"] - plot["latitude"]) * km_lat,
        (same["longitude"] - plot["longitude"]) * km_lon,
    )
    block = same.nsmallest(NEIGHBOURS, "d").sort_values("latitude", ascending=False)
    rows = [block.iloc[i : i + 4].sort_values("longitude") for i in range(0, NEIGHBOURS, 4)]
    return [list(r["plot_id"]) for r in rows]


def _plot_inputs(ds: CanonicalDataset, plot_id: str) -> dict:
    p = ds.plots.set_index("plot_id").loc[plot_id]
    obs = ds.observations[ds.observations["plot_id"] == plot_id].sort_values("date")
    soil = ds.soil.set_index("plot_id").loc[plot_id] if plot_id in set(ds.soil["plot_id"]) else None
    return {
        "plot_id": plot_id,
        "latitude": round(float(p["latitude"]), 6),
        "longitude": round(float(p["longitude"]), 6),
        "planting_date": p["planting_date"].isoformat(),
        "management": {
            c: (bool(p[c]) if c == "irrigated" else _none(p[c]))
            for c in MANAGEMENT_COLUMNS
            if c in p.index
        },
        "canopy": [
            {
                "date": r.date.isoformat(),
                **{i: round(float(getattr(r, i)), 5) for i in ds.indices()},
                "nir": round(float(r.nir), 5),
            }
            for r in obs.itertuples()
        ],
        "soil": None
        if soil is None
        else {
            "series": _none(soil["series"]),
            "map_unit_name": _none(soil["map_unit_name"]),
            "texture": _none(soil["texture"]),
            "drainage": _none(soil["drainage"]),
            "available_water_storage_cm": _none(soil["available_water_storage_cm"]),
            "organic_matter": _none(soil["organic_matter"]),
            "ph": _none(soil["ph"]),
            "root_zone_depth_cm": _none(soil["root_zone_depth_cm"]),
            "slope_percent": _none(soil["slope_percent"]),
        },
    }


def climate_normals(site: pd.Series, planting: date, dates: list[date]) -> dict:
    """For each forecast date: the 1991-2020 mean rain over the same 30 days, and the mean
    GDD from the planting day to that day over the previous 10 years. Same station rule as
    the season's weather: the site's station, gaps filled from the next-nearest stations."""
    client = get_http_client()
    first_gdd_year = planting.year - GDD_PACE_YEARS
    years = sorted(set(RAIN_NORMAL_YEARS) | set(range(first_gdd_year, planting.year)))
    nearby = _nearby_stations(
        client, site["latitude"], site["longitude"], date(years[0], 3, 1), date(years[-1], 10, 31)
    )
    stations = [site["weather_station_id"]] + [
        s.id for s in nearby if s.id != site["weather_station_id"]
    ][: GAP_FILL_MAX_STATIONS - 1]
    daily: dict[date, list] = {}
    for year in years:
        for station in stations:
            for d in fetch_daily(client, station, date(year, 3, 1), date(year, 10, 31)):
                row = daily.setdefault(d.day, [None, None, None])
                for k, v in enumerate((d.prcp_in, d.tmax_f, d.tmin_f)):
                    if row[k] is None and v is not None:
                        row[k] = v
            season = [daily.get(date(year, 3, 1) + timedelta(i)) for i in range(245)]
            if all(r is not None and None not in r for r in season):
                break

    def shifted(day: date, year: int) -> date:
        return day.replace(year=year)

    out = {}
    for d in dates:
        rain = []
        for y in RAIN_NORMAL_YEARS:
            window = [shifted(d, y) - timedelta(i) for i in range(30)]
            values = [daily.get(w, (None,))[0] for w in window]
            if sum(v is not None for v in values) >= 27:
                rain.append(sum(v for v in values if v is not None) * MM_PER_INCH)
        gdd = []
        for y in range(first_gdd_year, planting.year):
            span = (shifted(d, y) - shifted(planting, y)).days + 1
            days = [shifted(planting, y) + timedelta(i) for i in range(span)]
            temps = [daily.get(x) for x in days]
            ok = [t for t in temps if t and t[1] is not None and t[2] is not None]
            if len(ok) >= 0.95 * span:
                gdd.append(sum(modified_gdd(t[1], t[2]) for t in ok) * span / len(ok))
        out[d.isoformat()] = {
            "rain_30d_normal_mm": round(float(np.mean(rain)), 1) if len(rain) >= 20 else None,
            "rain_normal_years": len(rain),
            "gdd_since_planting_pace": round(float(np.mean(gdd))) if len(gdd) >= 7 else None,
            "gdd_pace_years": len(gdd),
            "stations": stations,
        }
    return out


def build_bundle(dataset: str) -> dict:
    project = load_project()
    ds = CanonicalDataset.load(dataset)
    site = project["holdout_site"]
    site_row = ds.sites.set_index("site_id").loc[site]
    fields = showcase_plots(ds, site)
    year = int(fields["year"].iloc[0])
    dates = [cutoff_date(year, c["as_of"]) for c in load_cutoffs()]
    planting = fields["planting_date"].iloc[0]

    blocks = {pid: neighbour_block(ds, row) for pid, row in fields.set_index("plot_id").iterrows()}
    needed = sorted({pid for b in blocks.values() for r in b for pid in r} | set(fields["plot_id"]))

    obs = ds.observations.merge(ds.plots[["plot_id", "site_id"]], on="plot_id")
    obs = obs[obs["site_id"] == site]
    reference = obs.groupby("date")[ds.indices()].mean().reset_index().sort_values("date")
    weather = ds.weather[ds.weather["site_id"] == site].sort_values("date")
    county = ds.county_yields[
        (ds.county_yields["site_id"] == site) & (ds.county_yields["year"] < year)
    ]

    return {
        "dataset": dataset,
        "source": SOURCE_LABELS.get(
            dataset, {"name": dataset, "short_name": dataset, "detail": ""}
        ),
        "citation": ds.provenance.get("citation"),
        "license": ds.provenance.get("license"),
        "season_year": year,
        "forecast_dates": [d.isoformat() for d in dates],
        "held_out_site": True,
        "site": {
            "id": site,
            "name": str(site_row["name"]),
            "state": str(site_row["state"]),
            "county": str(site_row["county"]),
            "fips": str(site_row["fips"]).zfill(5),
            "latitude": round(float(site_row["latitude"]), 6),
            "longitude": round(float(site_row["longitude"]), 6),
            "weather_station": str(site_row["weather_station"]),
            "weather_station_id": str(site_row["weather_station_id"]),
            "station_distance_km": float(site_row["station_distance_km"]),
            "irrigated": bool(fields["irrigated"].iloc[0]),
        },
        "weather": [
            {
                "date": r.date.isoformat(),
                "tmax_f": _none(r.tmax_f),
                "tmin_f": _none(r.tmin_f),
                "prcp_mm": _none(r.prcp_mm),
            }
            for r in weather.itertuples()
        ],
        "climate_normals": climate_normals(site_row, planting, dates),
        "county_yields": {str(int(r.year)): float(r["yield"]) for _, r in county.iterrows()},
        "canopy_reference": [
            {
                "date": r.date.isoformat(),
                **{i: round(float(getattr(r, i)), 5) for i in ds.indices()},
            }
            for r in reference.itertuples()
        ],
        "fields": [{"plot_id": pid, "neighbours": blocks[pid]} for pid in fields["plot_id"]],
        "plots": {pid: _plot_inputs(ds, pid) for pid in needed},
    }


def write_bundle(dataset: str) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{dataset}.json"
    path.write_text(json.dumps(build_bundle(dataset), indent=1) + "\n")
    return str(path)
