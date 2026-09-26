"""
The outlook's output contract: a JSON document for the API and dashboard, and a long
table of every trajectory's days for the yield model (written as Parquet by the ML side).

Probabilities are whole percentages. Every document says how many historical seasons it
rests on, how many of them effectively count after weighting, and whether it is
exploratory.
"""

import math
from typing import Any

import numpy as np
import pandas as pd

from app.weather_outlook import analogs
from app.weather_outlook.analogs import CATEGORIES, TERCILES
from app.weather_outlook.features import OUTCOMES, STAGE_OUTCOMES
from app.weather_outlook.scenarios import Outlook, YieldOutlook

CONTRACT_VERSION = 1
METHOD_NOTE = (
    "Historical analog outlook: the weather that followed this date in past seasons at "
    "this station, weighted by how closely each season so far resembled this one. It is "
    "not a meteorological forecast."
)
CAMEL = {
    "precip_mm": "precipitationMm",
    "gdd": "gdd",
    "heat_days": "heatDays",
    "kdd_29c": "killingDegreeDays29c",
    "warm_nights": "warmNights",
    "longest_dry_spell_days": "longestDrySpellDays",
    "very_heavy_rain_days": "veryHeavyRainDays",
    "water_deficit_mm": "waterDeficitMm",
    "tmean_c": "meanTemperatureC",
    "rain_around_silking_mm": "rainAroundSilkingMm",
    "heat_days_around_silking": "heatDaysAroundSilking",
    "water_deficit_around_silking_mm": "waterDeficitAroundSilkingMm",
    "rain_grain_fill_mm": "rainGrainFillMm",
    "heat_days_grain_fill": "heatDaysGrainFill",
    "warm_nights_grain_fill": "warmNightsGrainFill",
    "water_deficit_grain_fill_mm": "waterDeficitGrainFillMm",
    "gdd_to_date": "gddToDate",
    "rain_to_date_mm": "rainToDateMm",
    "rain_14d_mm": "rain14dMm",
    "rain_30d_mm": "rain30dMm",
    "rain_60d_mm": "rain60dMm",
    "heat_days_to_date": "heatDaysToDate",
    "kdd_to_date": "killingDegreeDaysToDate",
    "warm_nights_to_date": "warmNightsToDate",
    "current_dry_spell_days": "currentDrySpellDays",
    "tmean_30d_c": "meanTemperature30dC",
    "root_zone_depletion_mm": "rootZoneDepletionMm",
}


def _r(value: float, digits: int = 1) -> float | None:
    return None if value is None or math.isnan(value) else round(float(value), digits)


def _pct(values: np.ndarray) -> dict[str, float]:
    rounded = analogs.round_probabilities(values)
    return dict(zip(CATEGORIES, rounded, strict=True))


def reliability_label(outlook: Outlook) -> str:
    n = outlook.n_seasons
    if outlook.exploratory:
        return f"Exploratory, based on {n} historical seasons"
    return f"Based on {n} historical seasons"


def _variable_summary(outlook: Outlook, name: str, stage: bool = False) -> dict[str, Any]:
    w = outlook.weight_array()
    source = "stage_outcomes" if stage else "outcomes"
    values = np.array([getattr(tr, source).get(name, math.nan) for tr in outlook.trajectories])
    keep = ~np.isnan(values)
    if not keep.any():
        return {}
    v, wk = values[keep], w[keep] / w[keep].sum()
    digits = 0 if name.endswith(("_mm", "gdd")) or name in ("gdd",) else 1
    out: dict[str, Any] = {
        "mean": _r(float(np.sum(v * wk)), digits),
        "p20": _r(analogs.weighted_quantile(v, wk, 0.2), digits),
        "median": _r(analogs.weighted_quantile(v, wk, 0.5), digits),
        "p80": _r(analogs.weighted_quantile(v, wk, 0.8), digits),
        "climatologyMedian": _r(float(np.median(v)), digits),
    }
    if np.ptp(v) > 0:
        terciles = np.array([analogs.tercile(x, v) for x in v])
        probs = np.array([wk[terciles == k].sum() for k in range(3)])
        out["terciles"] = dict(zip(TERCILES, analogs.round_probabilities(probs), strict=True))
    return out


def _events(outlook: Outlook) -> dict[str, Any]:
    w = outlook.weight_array()
    out = {}
    for key, name in (("heat_days", "anyHeatDay"), ("very_heavy_rain_days", "anyVeryHeavyRainDay")):
        hit = outlook.outcome_array(key) >= 1
        out[name] = {
            "probability": round(float(w[hit].sum()), 2),
            "climatology": round(float(hit.mean()), 2),
        }
    return out


def _representative(outlook: Outlook) -> dict[str, Any]:
    """Per category, the most similar historical season whose trajectory fell in it."""
    out: dict[str, Any] = {}
    for name in CATEGORIES:
        members = [tr for tr in outlook.trajectories if tr.category == name]
        if not members or not outlook.categories.available:
            out[name] = None
            continue
        best = max(members, key=lambda tr: (tr.weight, -tr.distance))
        out[name] = {
            "season": best.season,
            "weight": round(best.weight, 3),
            "outcomes": {CAMEL[k2]: _r(v) for k2, v in best.outcomes.items()},
            "score": _r(best.score, 4),
        }
    return out


def to_contract(outlook: Outlook, yield_outlook: YieldOutlook | None = None) -> dict[str, Any]:
    cat = outlook.categories
    percentile = {}
    for j, f in enumerate(outlook.settings.analog_features):
        column = outlook.library_descriptors[:, j]
        value = outlook.current.get(f, math.nan)
        if not math.isnan(value) and not np.isnan(column).all():
            percentile[CAMEL[f]] = round(
                analogs.percentile_rank(value, column[~np.isnan(column)]) * 100
            )
    doc: dict[str, Any] = {
        "contractVersion": CONTRACT_VERSION,
        "site": outlook.site.name,
        "asOfDate": outlook.as_of.isoformat(),
        "horizonDays": outlook.horizon,
        "horizonEnd": outlook.end.isoformat(),
        "plantingDate": outlook.planting.isoformat(),
        "method": outlook.weights.method,
        "methodNote": METHOD_NOTE,
        "weighting": outlook.extra.get("method_reason"),
        "library": outlook.library,
        "libraryLabel": outlook.library_label,
        "station": {
            "id": outlook.site.station.get("id"),
            "name": outlook.site.station.get("name"),
            "source": outlook.site.station.get("source"),
        },
        "historicalSeasons": outlook.n_seasons,
        "seasonsUsed": list(outlook.seasons),
        "effectiveSampleSize": round(outlook.weights.ess, 1),
        "exploratory": outlook.exploratory,
        "reliability": reliability_label(outlook),
        "conditionsThrough": outlook.as_of.isoformat(),
        "seasonToDate": {CAMEL[k]: _r(v) for k, v in sorted(outlook.current.items()) if k in CAMEL},
        "seasonToDatePercentile": percentile,
        "categoryBasis": {
            "scorer": cat.basis.scorer,
            "description": cat.basis.description,
            "provisional": cat.basis.provisional,
            "available": cat.available,
            "reason": cat.reason,
        },
        "probabilities": _pct(cat.probabilities) if cat.available else None,
        "probabilityIntervals": (
            {
                name: [round(float(cat.intervals[k, 0]), 2), round(float(cat.intervals[k, 1]), 2)]
                for k, name in enumerate(CATEGORIES)
            }
            if cat.available and not np.isnan(cat.intervals).any()
            else None
        ),
        "intervalLevel": outlook.settings.interval_level,
        "climatology": _pct(cat.climatology) if cat.available else None,
        "weatherSummary": {CAMEL[name]: _variable_summary(outlook, name) for name in OUTCOMES},
        "events": _events(outlook),
        "representativeScenarios": _representative(outlook),
        "analogs": [
            {
                "season": tr.season,
                "weight": round(tr.weight, 3),
                "distance": _r(tr.distance, 2),
                "category": tr.category,
            }
            for tr in sorted(outlook.trajectories, key=lambda tr: -tr.weight)
        ],
    }
    if outlook.horizon == "season":
        doc["stageSummary"] = {
            CAMEL[name]: _variable_summary(outlook, name, stage=True) for name in STAGE_OUTCOMES
        }
    if outlook.adjusted_to_site:
        doc["notes"] = [
            "Trajectories come from a proxy station and were shifted by its measured monthly "
            "temperature difference from the site."
        ]
    if yield_outlook is not None:
        doc["yield"] = {
            "unit": "bu/ac",
            "distribution": {k: _r(v) for k, v in yield_outlook.distribution().items()},
            "byCategory": {k: _r(v) for k, v in yield_outlook.by_category().items()},
            "perSeason": {
                str(tr.season): _r(y)
                for tr, y in zip(
                    yield_outlook.outlook.trajectories, yield_outlook.yields, strict=True
                )
            },
        }
    return doc


def trajectories_frame(outlook: Outlook) -> pd.DataFrame:
    """One row per trajectory day: the yield model's input table."""
    frames = []
    for tr in outlook.trajectories:
        f = tr.future
        frames.append(
            pd.DataFrame(
                {
                    "site": outlook.site.name,
                    "as_of": outlook.as_of,
                    "horizon": str(outlook.horizon),
                    "source_season": tr.season,
                    "weight": tr.weight,
                    "category": tr.category,
                    "date": f.dates(),
                    "day": np.arange(1, len(f) + 1),
                    "tmax_c": f.tmax_c,
                    "tmin_c": f.tmin_c,
                    "precip_mm": f.precip_mm,
                    "gdd_f": f.gdd,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
