"""
FieldForecast from raw inputs and exported models.

For every model cutoff in the season, the snapshot is:

    build_features(inputs, cutoff)  ->  registry.for_date(cutoff).predict()
                                    ->  yield, 90% range, confidence, this forecast's drivers

so a July 31 snapshot sees only images and weather up to July 31, scored by a model
trained only on what was knowable by July 31. Weather, soil, events and history are
the same inputs, summarized. Nothing on the page is typed in by hand.
"""

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np

from app.context.soil import water_class
from app.features import thresholds as t
from app.features.build import build_features, season_status
from app.features.catalog import info
from app.features.weather import DailySeries, hargreaves_et0_mm
from app.forecast.bundle import Bundle, ShowcaseField
from app.model.artifact import Driver, ModelArtifact, ModelRegistry, Prediction
from app.schemas import (
    Bounds,
    DataSource,
    EventMarker,
    FeatureImportanceItem,
    FieldForecast,
    FieldMeta,
    ForecastMetadata,
    ForecastSnapshot,
    HistoricalContext,
    ModelExplanation,
    PlotDecision,
    SoilContext,
    SpatialContext,
    SpatialZone,
    VegetationObservation,
    WeatherContext,
    YearlyYield,
)

INFLUENCE_LABELS = {
    "positive": "Positive influence",
    "negative": "Negative influence",
    "neutral": "Neutral / buffering influence",
}
# Display thresholds for "deficit" / "surplus" against the 30-year normal.
RAIN_STATUS_PCT = 25
PLOT_AREA_ACRES = 0.004  # 4 rows x 30 in x 17.5 ft trial plots
EVENT_LIMIT = {"rain": 4, "heat": 3, "dry": 2}
HEAT_RUN_DAYS = 2
DRY_RUN_DAYS = 14


def _display(d: date) -> str:
    return f"{d:%b} {d.day}"


def _slug(plot_id: str) -> str:
    return plot_id.lower().replace(" ", "-")


def _fmt(name: str, value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "not available"
    if isinstance(value, str):
        return value
    units = (("_lb_ac", " lb/ac"), ("_mm", " mm"), ("_f", " °F"), ("_pct", "%"), ("_cm", " cm"))
    unit = next((u for suffix, u in units if name.endswith(suffix)), "")
    counted = "days" in name or name.endswith(("_to_date", "_images")) and float(value).is_integer()
    if "days" in name:
        unit = " days"
    digits = (
        0 if counted or abs(value) >= 100 else 3 if abs(value) < 0.1 else 2 if abs(value) < 2 else 1
    )
    return f"{value:,.{digits}f}{unit}"


def stage_note(gdd: float, stage: str) -> str:
    """Growth stage estimated from heat units (ISU PMR 1009 milestones; ~84 GDD per leaf)."""
    heat = f"{gdd:,.0f} GDD since planting"
    if stage == "Emergence":
        return f"VE, emergence (estimated) · {heat}"
    if stage == "Vegetative":
        leaves = max(1, int((gdd - t.GDD_EMERGENCE) / 84) + 1)
        return f"About V{leaves} (estimated from heat units) · {heat}"
    if stage == "Reproductive":
        return f"Silking to blister, R1–R2 (estimated) · {heat}"
    if stage == "Grain Fill":
        return f"Milk to dent, R3–R5 (estimated) · {heat}"
    return f"Black layer, R6 (estimated) · {heat}"


class ForecastBuilder:
    def __init__(self, bundle: Bundle, registry: ModelRegistry) -> None:
        self.bundle = bundle
        self.registry = registry
        year = bundle.season_year
        dated = [a for a in registry.artifacts if a.metadata.as_of is not None]
        self.dates = sorted({date(year, *map(int, a.metadata.as_of.split("-"))) for a in dated})
        # Every bundled plot sits in some showcase field's 4 x 4 block; that block is its map.
        self._blocks = {
            pid: f.neighbours for f in bundle.fields for row in f.neighbours for pid in row
        }
        self._predictions: dict[date, list[Prediction]] = {}

    # ---- fields -----------------------------------------------------------------

    def field_id(self, field: ShowcaseField) -> str:
        return _slug(field.plot_id)

    def plot_field(self, plot_id: str) -> ShowcaseField:
        """Any bundled plot as a field: the showcase fields are listed, the rest are reachable
        from the scouting queue."""
        return ShowcaseField(plot_id, self._blocks.get(plot_id, []))

    def _short_plot_id(self, plot_id: str) -> str:
        return plot_id.removeprefix(self.bundle.site["id"]).strip("-")

    def _plot_name(self, plot_id: str) -> str:
        return f"{self.bundle.site['name']} plot {self._short_plot_id(plot_id)}"

    def field_meta(self, field: ShowcaseField) -> FieldMeta:
        b, p = self.bundle, self.bundle.plots[field.plot_id]
        soil = p.soil or {}
        if b.site["irrigated"]:
            raise ValueError("irrigation method unknown for this dataset; add it to the bundle")
        texture = (soil.get("texture") or "").lower()
        nitrogen = p.management.get("nitrogen_lb_ac")
        return FieldMeta(
            id=self.field_id(field),
            name=self._plot_name(field.plot_id),
            crop="Corn (Maize)",
            season=b.season_year,
            latitude=p.latitude,
            longitude=p.longitude,
            location=f"{b.site['county']}, {b.site['state']} (trial site held out of training)",
            acreage=PLOT_AREA_ACRES,
            regional_baseline=round(self._five_year_average() or 0.0, 1),
            soil_classification=" ".join(x for x in (soil.get("series"), texture) if x)
            or "Unknown",
            irrigation_status="Dryland",
            plot_id=self._short_plot_id(field.plot_id),
            site=b.site["name"],
            hybrid=p.management.get("genotype"),
            nitrogen_lb_ac=float(nitrogen) if nitrogen is not None else None,
            planting_date=p.planting_date.isoformat(),
        )

    def _five_year_average(self) -> float | None:
        past = sorted(self.bundle.county_yields.items())[-5:]
        return float(np.mean([v for _, v in past])) if len(past) >= 3 else None

    # ---- predictions --------------------------------------------------------------

    def _rows(self, artifact: ModelArtifact, plot_ids: list[str], as_of: date) -> list[dict]:
        rows = []
        for pid in plot_ids:
            features = build_features(self.bundle.inputs(pid), as_of)
            rows.append({name: features.get(name) for name in artifact.schema.names})
        return rows

    def _snapshot(self, i: int, field: ShowcaseField, as_of: date) -> ForecastSnapshot | None:
        artifact = self.registry.for_date(as_of.isoformat())
        if artifact is None:
            return None
        [pred] = artifact.predict(self._rows(artifact, [field.plot_id], as_of))
        inputs = self.bundle.inputs(field.plot_id)
        status = season_status(inputs, as_of)
        features = build_features(inputs, as_of)
        return ForecastSnapshot(
            id=f"snap-{i + 1}",
            date=as_of.isoformat(),
            display_date=_display(as_of),
            stage=status.stage,
            stage_subtext=stage_note(status.gdd_since_planting, status.stage),
            yield_=pred.yield_,
            unit=artifact.metadata.unit,
            lower_bound=pred.lower_bound,
            upper_bound=pred.upper_bound,
            confidence=pred.confidence,
            confidence_rating=pred.confidence_rating,
            generated_at=f"As of {_display(as_of)}, {as_of.year} · {artifact.metadata.model_id}",
            weather=self._weather(features, as_of),
            soil=self._soil(field.plot_id),
            explanations=self._explanations(pred.drivers, artifact),
            feature_importance=[
                FeatureImportanceItem(
                    name=d.label, weight=d.weight, category=d.category, direction=d.direction
                )
                for d in _unique(pred.drivers)
            ],
            spatial=self._spatial(field, artifact, as_of),
        )

    # ---- context ----------------------------------------------------------------

    def _weather(self, f: dict[str, Any], as_of: date) -> WeatherContext:
        normals = self.bundle.normals.get(as_of.isoformat(), {})
        rain = float(f.get("rain_30d_mm") or 0.0)
        rain_normal = normals.get("rain_30d_normal_mm")
        gdd = float(f.get("gdd_since_planting") or 0.0)
        pace = normals.get("gdd_since_planting_pace")
        if not rain_normal or not pace:
            raise ValueError(f"bundle has no climate normals for {as_of}")
        rain_pct = round(100 * (rain / rain_normal - 1))
        status = (
            "deficit"
            if rain_pct < -RAIN_STATUS_PCT
            else "surplus"
            if rain_pct > RAIN_STATUS_PCT
            else "normal"
        )
        series = DailySeries(
            self.bundle.weather,
            as_of - timedelta(29),
            as_of,
            self.bundle.site["latitude"],
        )
        et0 = np.array(_reference_et(series, self.bundle.site["latitude"]))
        return WeatherContext(
            rainfall_30_day=round(rain),
            rainfall_comparison=rain_pct,
            rainfall_status=status,
            gdd_accumulated=round(gdd),
            gdd_comparison=round(100 * (gdd / pace - 1)),
            heat_exposure_days=int(f.get("heat_days_since_planting") or 0),
            dry_spell_days=int(f.get("longest_dry_spell_days") or 0),
            updated_ago=f"NOAA observations through {_display(as_of)}, {as_of.year}",
            avg_temperature_f=round(float(f.get("tmean_30d_f") or 0.0), 1),
            et0_demand_mm=round(float(np.nansum(et0))),
        )

    def _soil(self, plot_id: str) -> SoilContext:
        s = self.bundle.plots[plot_id].soil or {}
        return SoilContext(
            awc=water_class(s.get("available_water_storage_cm")) or "Moderate",
            drainage=s.get("drainage") or "Unknown",
            organic_matter=round(float(s.get("organic_matter") or 0.0), 1),
            ph=round(float(s.get("ph") or 0.0), 1),
            dominant_texture=s.get("texture") or "Unknown",
            cation_exchange_capacity=None,
            root_zone_depth_cm=round(float(s.get("root_zone_depth_cm") or 0.0)),
            source="USDA NRCS SSURGO",
        )

    def _explanations(
        self, drivers: list[Driver], artifact: ModelArtifact
    ) -> list[ModelExplanation]:
        if not drivers:
            return [
                ModelExplanation(
                    id="exp-1",
                    title="No crop signal yet: the forecast is the trial average",
                    influence="neutral",
                    influence_label=INFLUENCE_LABELS["neutral"],
                    description=(
                        "Before the first satellite image, no available input beat the average "
                        "yield of the training sites when tested on sites the model had not seen, "
                        "so this forecast is that average. The range shows how much sites differ."
                    ),
                    metric_reference=f"Model: {artifact.metadata.algorithm}",
                )
            ]
        out = []
        for i, d in enumerate(_unique(drivers)[:3]):
            higher = "higher" if d.direction == "positive" else "lower"
            name = d.feature or ""
            what = info(name).label if name else d.label
            if d.value is not None and isinstance(d.value, str):
                detail = f"{what}: {d.value}."
            else:
                detail = (
                    f"{what}: {_fmt(name, d.value)} for this plot, against {_fmt(name, d.typical)} "
                    "typical in training."
                )
            out.append(
                ModelExplanation(
                    id=f"exp-{i + 1}",
                    title=d.label,
                    influence=d.direction,
                    influence_label=INFLUENCE_LABELS[d.direction],
                    description=(
                        f"{detail} The model associates this with a {higher} forecast; it carries "
                        f"{d.weight:.0f}% of this forecast's driver weight. "
                        "An association the model "
                        "learned, not a proven cause."
                    ),
                    metric_reference=f"{d.category} · {artifact.metadata.model_id}",
                )
            )
        return out

    def _spatial(self, field: ShowcaseField, artifact: ModelArtifact, as_of: date):
        ids = [pid for row in field.neighbours for pid in row]
        if not ids:
            return None
        plots = [self.bundle.plots[pid] for pid in ids]
        images = [d for d in plots[0].nir if d <= as_of]
        if not images:
            return None
        preds = artifact.predict(self._rows(artifact, ids, as_of))
        weather = build_features(self.bundle.inputs(field.plot_id), as_of)
        rain = round(float(weather.get("rain_30d_mm") or 0.0))
        days = max(1, int(weather.get("days_since_planting") or 1) + 1)
        heat_share = round(float(weather.get("heat_days_since_planting") or 0) / days, 3)
        zones = []
        for k, (pid, plot, pred) in enumerate(zip(ids, plots, preds, strict=True)):
            latest = max((o for o in plot.canopy if o.day <= as_of), key=lambda o: o.day)
            soil = plot.soil or {}
            zones.append(
                SpatialZone(
                    id=f"z-{k + 1}",
                    name=self._plot_name(pid) + (" (this plot)" if pid == field.plot_id else ""),
                    grid_row=k // 4,
                    grid_col=k % 4,
                    predicted_yield=pred.yield_,
                    ndvi=round(float(latest.values.get("ndvi", 0.0)), 3),
                    rainfall_30_day=rain,
                    soil=" ".join(x for x in (soil.get("series"), soil.get("texture")) if x)
                    or "Unknown",
                    heat_stress_index=heat_share,
                    satellite_reflectance=round(float(plot.nir.get(latest.day) or 0.0), 3),
                )
            )
        lats, lons = [p.latitude for p in plots], [p.longitude for p in plots]
        return SpatialContext(
            zones=zones,
            resolution_meters=0.3,
            tile_date=max(images).isoformat(),
            satellite_platform="Pléiades Neo",
            bounds=Bounds(north=max(lats), south=min(lats), east=max(lons), west=min(lons)),
            description=(
                "16 neighbouring trial plots, each forecast by the same model from its own "
                "images. Heat stress is the share of days since planting at 95 °F or hotter."
            ),
            provenance="model",
        )

    # ---- season-level ------------------------------------------------------------

    def _vegetation(self, plot_id: str) -> list[VegetationObservation]:
        reference = {o.day: o.values for o in self.bundle.reference}
        out = []
        for o in self.bundle.plots[plot_id].canopy:
            v = o.values
            out.append(
                VegetationObservation(
                    date=o.day.isoformat(),
                    display_date=_display(o.day),
                    ndvi=round(v["ndvi"], 3),
                    ndre=round(v["ndre"], 3),
                    regional_baseline_ndvi=round(
                        reference.get(o.day, {}).get("ndvi", v["ndvi"]), 3
                    ),
                    gndvi=round(v["gndvi"], 3) if "gndvi" in v else None,
                    evi=round(v["evi"], 3) if "evi" in v else None,
                )
            )
        return out

    def _events(self, plot_id: str, until: date) -> list[EventMarker]:
        p = self.bundle.plots[plot_id]
        m = p.management
        events = [
            EventMarker(
                date=p.planting_date.isoformat(),
                display_date=_display(p.planting_date),
                title="Planted",
                type="management",
                summary=f"{m.get('nitrogen_lb_ac', 0):.0f} lb N/ac",
                hover_detail=(
                    f"Hybrid {m.get('genotype')} planted at "
                    f"{m.get('nitrogen_lb_ac', 0):.0f} lb N/ac."
                ),
            )
        ]
        days = [d for d in self.bundle.weather if p.planting_date <= d.day <= until]
        heavy = sorted(
            (d for d in days if (d.prcp_mm or 0) >= t.VERY_HEAVY_RAIN_MM),
            key=lambda d: -(d.prcp_mm or 0),
        )[: EVENT_LIMIT["rain"]]
        for d in heavy:
            events.append(
                EventMarker(
                    date=d.day.isoformat(),
                    display_date=_display(d.day),
                    title="Very heavy rain",
                    type="rain",
                    summary=f"{d.prcp_mm:.0f} mm in a day",
                    hover_detail=(
                        f"{d.prcp_mm:.0f} mm fell on {_display(d.day)} (NOAA). "
                        "Days with 20 mm or more "
                        "can saturate poorly drained soil."
                    ),
                )
            )
        for kind, test, min_len, title in (
            (
                "heat",
                lambda d: d.tmax_f is not None and d.tmax_f >= t.HEAT_STRESS_F,
                HEAT_RUN_DAYS,
                "Heat stress",
            ),
            (
                "dry",
                lambda d: d.prcp_mm is not None and d.prcp_mm < t.DRY_DAY_MM,
                DRY_RUN_DAYS,
                "Dry spell",
            ),
        ):
            runs = sorted(_runs(days, test), key=lambda r: -len(r))
            for run in [r for r in runs if len(r) >= min_len][: EVENT_LIMIT[kind]]:
                start = run[0].day
                summary = (
                    f"{len(run)} days at 95 °F or hotter"
                    if kind == "heat"
                    else f"{len(run)} days under 1 mm"
                )
                events.append(
                    EventMarker(
                        date=start.isoformat(),
                        display_date=_display(start),
                        title=title,
                        type=kind,
                        summary=summary,
                        hover_detail=(
                            f"{summary}, from {_display(start)} to {_display(run[-1].day)} (NOAA)."
                        ),
                    )
                )
        return sorted(events, key=lambda e: e.date)

    def _historical(self, forecast_yield: float) -> HistoricalContext:
        years = sorted(self.bundle.county_yields.items())[-5:]
        avg = self._five_year_average() or forecast_yield
        yearly = [YearlyYield(year=y, yield_=round(v, 1), type="historical") for y, v in years]
        yearly.append(
            YearlyYield(year=self.bundle.season_year, yield_=forecast_yield, type="forecast")
        )
        return HistoricalContext(
            regional_5_year_avg=round(avg, 1),
            regional_delta_pct=round(100 * (forecast_yield / avg - 1), 1),
            yearly_yields=yearly,
        )

    def _sources(self) -> list[DataSource]:
        b, s = self.bundle, self.bundle.site
        models = [a.metadata for a in self.registry.artifacts if a.metadata.as_of]
        holdout = models[-1].holdout if models else None
        held_out = (
            f" Held-out accuracy at the last cutoff: MAE {holdout.metrics.mae:.0f} bu/ac."
            if holdout
            else ""
        )
        return [
            DataSource(
                id="practice-trials",
                name=b.source["name"],
                short_name=b.source["short_name"],
                purpose="Satellite images, management and harvested yields",
                role="practice",
                status_label="Practice data (public)",
                detail=(
                    f"{b.source['detail']} The plots shown are from {s['name']}, {s['state']}, "
                    "a site the models never trained on."
                ),
            ),
            DataSource(
                id="noaa-ghcn",
                name="NOAA NCEI GHCN-Daily",
                short_name="NOAA",
                purpose="Weather",
                role="public",
                status_label="Connected",
                detail=(
                    f"Daily rain and temperature from {s['weather_station']} "
                    f"({s['station_distance_km']:.0f} km away), gaps filled from nearby stations. "
                    "Normals: the same station's 1991–2020 record."
                ),
            ),
            DataSource(
                id="ssurgo",
                name="USDA NRCS SSURGO",
                short_name="SSURGO",
                purpose="Soil",
                role="public",
                status_label="Connected",
                detail="Dominant soil component at each plot, via Soil Data Access.",
            ),
            DataSource(
                id="nass",
                name="USDA NASS Quick Stats",
                short_name="NASS",
                purpose="County yield history",
                role="public",
                status_label="Connected",
                detail=f"{s['county']} corn yields for the years before {b.season_year}.",
            ),
            DataSource(
                id="soilsignal-models",
                name="SoilSignal forecast models",
                short_name="Model",
                purpose="Forecasts, ranges and drivers",
                role="model",
                status_label="Model-derived",
                detail=(
                    "One model per forecast date, trained on other sites and validated "
                    "leave-one-site-out." + held_out
                ).strip(),
            ),
        ]

    # ---- decision support ---------------------------------------------------------

    def _predict_all(self, as_of: date) -> list[Prediction]:
        """Every bundled plot at one forecast date: the same features and model as that
        date's snapshot, scored in one batch."""
        if as_of not in self._predictions:
            artifact = self.registry.for_date(as_of.isoformat())
            ids = list(self.bundle.plots)
            self._predictions[as_of] = artifact.predict(self._rows(artifact, ids, as_of))
        return self._predictions[as_of]

    def decisions(self, as_of: date) -> list[PlotDecision]:
        """Each plot's forecast as of a date: the latest forecast date on or before it, and
        the change from the forecast date before that. Empty before the first forecast."""
        eligible = [d for d in self.dates if d <= as_of]
        if not eligible:
            return []
        current = eligible[-1]
        previous = eligible[-2] if len(eligible) > 1 else None
        now = self._predict_all(current)
        before = self._predict_all(previous) if previous else [None] * len(now)
        out = []
        for pid, pred, prior in zip(self.bundle.plots, now, before, strict=True):
            meta = self.field_meta(self.plot_field(pid))
            negative = next((d for d in _unique(pred.drivers) if d.direction == "negative"), None)
            out.append(
                PlotDecision(
                    field_id=meta.id,
                    plot_id=meta.plot_id,
                    name=meta.name,
                    site=meta.site,
                    season=meta.season,
                    hybrid=meta.hybrid,
                    nitrogen_lb_ac=meta.nitrogen_lb_ac,
                    irrigation_status=meta.irrigation_status,
                    forecast_date=current.isoformat(),
                    predicted_yield=pred.yield_,
                    lower_bound=pred.lower_bound,
                    upper_bound=pred.upper_bound,
                    confidence=pred.confidence,
                    confidence_rating=pred.confidence_rating,
                    previous_forecast_date=previous.isoformat() if previous else None,
                    previous_yield=prior.yield_ if prior else None,
                    change_since_previous=round(pred.yield_ - prior.yield_, 1) if prior else None,
                    top_negative_driver=negative.label if negative else None,
                )
            )
        return out

    # ---- assemble -------------------------------------------------------------------

    def forecast(self, field: ShowcaseField) -> FieldForecast:
        snapshots = [
            s for i, d in enumerate(self.dates) if (s := self._snapshot(i, field, d)) is not None
        ]
        if not snapshots:
            raise ValueError("no model covers any forecast date in this season")
        last = snapshots[-1]
        m = self.bundle.plots[field.plot_id].management
        s = self.bundle.site
        images = [o.day for o in self.bundle.plots[field.plot_id].canopy]
        return FieldForecast(
            field=self.field_meta(field),
            story_description=(
                f"Hybrid {m.get('genotype')} at {m.get('nitrogen_lb_ac', 0):.0f} lb N/ac in the "
                f"{s['name']}, {s['state']} trial ({self.bundle.season_year}). "
                "This site was held out of "
                "model training, so every forecast here is out-of-sample, and each date uses only "
                "the images and weather available by then."
            ),
            snapshots=snapshots,
            full_vegetation_series=self._vegetation(field.plot_id),
            events=self._events(field.plot_id, date.fromisoformat(last.date)),
            historical=self._historical(last.yield_),
            sources=self._sources(),
            metadata=ForecastMetadata(
                forecast_generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
                dataset_version=f"{self.bundle.dataset} · "
                + ", ".join(a.metadata.model_id for a in self.registry.artifacts),
                last_satellite_pass=max(images).isoformat() if images else None,
            ),
        )


def _unique(drivers: list[Driver]) -> list[Driver]:
    """Drivers with distinct labels (labels are list keys on the dashboard)."""
    seen, out = set(), []
    for d in drivers:
        if d.label not in seen:
            seen.add(d.label)
            out.append(d)
    return out


def _runs(days, test) -> list[list]:
    runs, current = [], []
    for d in days:
        if test(d):
            current.append(d)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def _reference_et(series: DailySeries, latitude: float) -> list[float]:
    """Daily reference evapotranspiration (Hargreaves, FAO-56 eq. 52) for the series."""
    return [
        hargreaves_et0_mm(d, latitude, hi, lo)
        if not (math.isnan(hi) or math.isnan(lo))
        else math.nan
        for d, hi, lo in zip(series.dates, series.tmax, series.tmin, strict=True)
    ]
