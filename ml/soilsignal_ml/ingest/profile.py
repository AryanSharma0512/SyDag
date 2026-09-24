"""
Dataset profile: ml/experiments/reports/dataset_profile.md. Counts, yield by site and
nitrogen rate, image dates, canopy trajectories, weather, soil and missingness, plus a
check of the GDD-to-silking assumption against anthesis observed in the data.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.features import thresholds as t
from app.features.weather import modified_gdd
from soilsignal_ml import ML_ROOT
from soilsignal_ml.ingest.canonical import CanonicalDataset
from soilsignal_ml.ingest.validate import validate

REPORTS = ML_ROOT / "experiments" / "reports"


def _md(frame: pd.DataFrame, digits: int = 1) -> str:
    frame = frame.copy()
    for c in frame.columns:
        if pd.api.types.is_float_dtype(frame[c]):
            frame[c] = frame[c].map(lambda v: "–" if pd.isna(v) else f"{v:,.{digits}f}")
    header = "| " + " | ".join(map(str, frame.columns)) + " |"
    rule = "|" + "|".join("---" for _ in frame.columns) + "|"
    rows = ["| " + " | ".join(map(str, r)) + " |" for r in frame.itertuples(index=False)]
    return "\n".join([header, rule, *rows])


def season_weather(ds: CanonicalDataset) -> pd.DataFrame:
    rows = []
    w = ds.weather.copy()
    for site, g in w.groupby("site_id"):
        planting = ds.plots.loc[ds.plots["site_id"] == site, "planting_date"].mode().iloc[0]
        season = g[(g["date"] >= planting) & (g["date"] <= date(planting.year, 9, 30))]
        temps = season.dropna(subset=["tmax_f", "tmin_f"])
        rows.append(
            {
                "Site": site,
                "Planted": planting.isoformat(),
                "Rain, planting-Sep 30 (mm)": season["prcp_mm"].sum(),
                "GDD, planting-Sep 30": sum(
                    modified_gdd(a, b)
                    for a, b in zip(temps["tmax_f"], temps["tmin_f"], strict=True)
                ),
                "Days ≥ 95 °F": int((season["tmax_f"] >= t.HEAT_STRESS_F).sum()),
                "Nights ≥ 70 °F": int((season["tmin_f"] >= t.WARM_NIGHT_F).sum()),
                "Filled from other stations (days)": int(
                    (season["tmax_f_station"] != season["tmax_f_station"].mode().iloc[0]).sum()
                )
                if "tmax_f_station" in season
                else 0,
            }
        )
    return pd.DataFrame(rows)


def silking_check(ds: CanonicalDataset) -> pd.DataFrame:
    """Observed GDD to anthesis (dataset) vs the 1,300 GDD silking milestone used by features."""
    p = ds.plots.dropna(subset=["days_to_anthesis"])
    rows = []
    for site, g in p.groupby("site_id"):
        w = ds.weather[ds.weather["site_id"] == site].set_index("date")
        planting = g["planting_date"].mode().iloc[0]
        gdd = []
        for days in g["days_to_anthesis"]:
            span = [planting + timedelta(int(i)) for i in range(int(days) + 1)]
            gdd.append(
                sum(
                    modified_gdd(w.at[d, "tmax_f"], w.at[d, "tmin_f"])
                    for d in span
                    if d in w.index and pd.notna(w.at[d, "tmax_f"]) and pd.notna(w.at[d, "tmin_f"])
                )
            )
        rows.append(
            {
                "Site": site,
                "Plots": len(g),
                "Days to anthesis (median)": float(g["days_to_anthesis"].median()),
                "GDD to anthesis, NOAA weather (median)": float(np.median(gdd)),
                "GDD to anthesis, as recorded (median)": float(g["gdd_to_anthesis"].median()),
                "Feature milestone (GDD)": t.GDD_SILKING,
            }
        )
    return pd.DataFrame(rows)


def build_profile(ds: CanonicalDataset) -> str:
    p, o = ds.plots, ds.observations
    y = p.dropna(subset=["final_yield"])
    by_site = (
        y.groupby("site_id")
        .agg(
            Plots=("plot_id", "size"),
            Hybrids=("genotype", "nunique"),
            Mean=("final_yield", "mean"),
            SD=("final_yield", "std"),
            Min=("final_yield", "min"),
            Max=("final_yield", "max"),
        )
        .reset_index()
        .rename(columns={"site_id": "Site"})
    )
    by_site.insert(1, "Irrigated", by_site["Site"].map(p.groupby("site_id")["irrigated"].first()))
    n_response = y.pivot_table(
        index="site_id", columns="nitrogen_lb_ac", values="final_yield", aggfunc="mean"
    )
    n_response.columns = [f"{int(c)} lb N" for c in n_response.columns]
    n_response = n_response.reset_index().rename(columns={"site_id": "Site"})

    obs = o.merge(p[["plot_id", "site_id"]], on="plot_id")
    dates = obs.groupby("site_id")["date"].agg(
        lambda s: ", ".join(d.strftime("%b %d") for d in sorted(set(s)))
    )
    ndvi = obs.pivot_table(index="site_id", columns="time_point", values="ndvi", aggfunc="median")
    ndvi.columns = [f"Image {c}" for c in ndvi.columns]
    ndvi = ndvi.reset_index().rename(columns={"site_id": "Site"})
    ndvi.insert(1, "Image dates", ndvi["Site"].map(dates))

    corr = []
    for site, g in obs.merge(y[["plot_id", "final_yield"]], on="plot_id").groupby(
        ["site_id", "time_point"]
    ):
        corr.append({"site": site[0], "tp": site[1], "r": g["ndvi"].corr(g["final_yield"])})
    corr = pd.DataFrame(corr).pivot(index="site", columns="tp", values="r")
    corr.columns = [f"Image {c}" for c in corr.columns]
    corr = corr.reset_index().rename(columns={"site": "Site"})

    soil = (
        ds.soil.merge(p[["plot_id", "site_id"]], on="plot_id")
        .groupby("site_id")
        .agg(
            Series=(
                "series",
                lambda s: ", ".join(f"{k} ({v})" for k, v in s.value_counts().items()),
            ),
            Drainage=("drainage", lambda s: s.mode().iloc[0] if len(s.mode()) else "–"),
            AWS_cm=("available_water_storage_cm", "mean"),
            OM_pct=("organic_matter", "mean"),
            pH=("ph", "mean"),
        )
        .reset_index()
        .rename(
            columns={
                "site_id": "Site",
                "AWS_cm": "Available water, 100 cm (cm)",
                "OM_pct": "Organic matter (%)",
            }
        )
    )
    county = ds.county_yields.pivot(index="year", columns="site_id", values="yield").reset_index()
    county = county[county["year"] >= 2012].rename(columns={"year": "Year"})
    missing = pd.DataFrame(
        {
            "Column": [
                "final_yield",
                "genotype",
                "planting_date",
                "latitude",
                "stand_count",
                "days_to_anthesis",
            ],
            "Missing (plots)": [
                int(p[c].isna().sum())
                for c in [
                    "final_yield",
                    "genotype",
                    "planting_date",
                    "latitude",
                    "stand_count",
                    "days_to_anthesis",
                ]
            ],
        }
    )
    problems = validate(ds)
    sites = ds.sites[
        [
            "site_id",
            "county",
            "state",
            "latitude",
            "longitude",
            "weather_station",
            "station_distance_km",
        ]
    ].rename(columns=str.capitalize)

    return (
        "\n".join(
            [
                f"# Dataset profile: {ds.name}",
                "",
                f"{ds.provenance.get('citation', '')}",
                "",
                f"- {len(p)} plots with imagery, {len(y)} with a harvested yield; {len(o)} plot images "
                f"on {o['date'].nunique()} dates; {p['genotype'].nunique()} hybrids.",
                f"- Data checks: {'all passed' if not problems else '; '.join(problems)}.",
                *[f"- {n}" for n in ds.provenance.get("notes", [])],
                "",
                "## Sites",
                "",
                _md(sites, 3),
                "",
                "## Yield (bu/ac at 15.5% moisture)",
                "",
                _md(by_site),
                "",
                "Between-site differences dwarf within-site ones: Lincoln (rainfed, 2022 drought) averages about a "
                "quarter of Crawfordsville. Leave-one-site-out validation is hard for exactly this reason.",
                "",
                "### Mean yield by nitrogen rate",
                "",
                _md(n_response),
                "",
                "## Canopy: median NDVI by image",
                "",
                _md(ndvi, 2),
                "",
                "### Correlation of NDVI with final yield, within each site",
                "",
                _md(corr, 2),
                "",
                "## Weather, planting to Sep 30 (NOAA GHCN-Daily)",
                "",
                _md(season_weather(ds), 0),
                "",
                "## Growth stage check",
                "",
                "Features place silking at 1,300 GDD after planting (ISU PMR 1009). Two sites recorded anthesis:",
                "",
                _md(silking_check(ds), 0),
                "",
                "## Soil (SSURGO dominant component at each plot)",
                "",
                _md(soil, 1),
                "",
                "## County corn yield history (USDA NASS, bu/ac)",
                "",
                _md(county, 1),
                "",
                "## Missing values",
                "",
                _md(missing),
                "",
                "Stand counts and anthesis dates exist at only some sites and have no reliable measurement date, "
                "so they are profiled here but never used as features.",
            ]
        )
        + "\n"
    )


def write_profile(name: str) -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "dataset_profile.md"
    path.write_text(build_profile(CanonicalDataset.load(name)))
    return str(path)
