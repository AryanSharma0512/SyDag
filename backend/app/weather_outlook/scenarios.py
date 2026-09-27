"""
Historical weather outlook: what followed this point of the season in comparable
historical seasons, as a weighted ensemble of real weather trajectories.

    outlook = WeatherOutlook(library).generate("Ames", date(2023, 6, 1), 60)
    outlook.probabilities          # favorable / typical / adverse, weighted by similarity
    for trajectory in outlook.trajectories:
        trajectory.season          # the historical year this weather comes from
        trajectory.weight          # its analog weight
        trajectory.weather         # its days as DailyWeather, dated in the outlook's season
        outlook.season_weather(trajectory)   # observed season to date + this trajectory

The outlook's own season is never an analog, and nothing observed after as_of is read
for it: only the library's other seasons contribute future weather.
"""

import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Any, Literal

import numpy as np

from app.features.inputs import DailyWeather
from app.weather_outlook import analogs
from app.weather_outlook.analogs import CATEGORIES, Weights
from app.weather_outlook.features import (
    DailyArrays,
    descriptors,
    from_daily_weather,
    from_record,
    horizon_outcomes,
    stage_outcomes,
)
from app.weather_outlook.history import SiteInfo, WeatherLibrary, month_day
from app.weather_outlook.stress import depletion_through, score_trajectory

Horizon = int | Literal["season"]


class OutlookError(ValueError):
    """The request cannot be answered from this library (unknown site, date outside the
    record, horizon past the checked window, too few seasons)."""


@dataclass(frozen=True)
class OutlookSettings:
    season_start: str = "04-01"
    season_end: str = "10-15"
    analog_features: tuple[str, ...] = (
        "gdd_to_date",
        "rain_to_date_mm",
        "rain_30d_mm",
        "tmean_30d_c",
    )
    bandwidth: float = 1.0
    min_ess_fraction: float = 0.4
    min_days_observed: int = 21
    bootstrap_samples: int = 500
    interval_level: float = 0.8
    robust_min_seasons: int = 20
    # Horizons may not run past this month-day (the library's quality window).
    latest_end: str = "11-30"
    min_seasons: int = 3

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "OutlookSettings":
        known = {f for f in cls.__dataclass_fields__}
        values = {k: v for k, v in raw.items() if k in known}
        if "analog_features" in values:
            values["analog_features"] = tuple(values["analog_features"])
        return cls(**values)


@dataclass(frozen=True)
class CategoryBasis:
    scorer: str
    description: str
    provisional: bool


WATER_BASIS = CategoryBasis(
    "fao_water_stress",
    "Relative maize yield from water supply over the horizon (FAO-33 yield response by "
    "growth period, FAO-56 root-zone water balance on SoilSignal's crop water demand). "
    "Rain beyond what the root zone holds is not rewarded; heat is counted only through "
    "crop water demand.",
    provisional=True,
)
HEAT_BASIS = CategoryBasis(
    "stage_weighted_heat",
    "Degree days above 29 C over the horizon, weighted by each growth period's FAO-33 "
    "sensitivity. Used for irrigated sites, where water supply is managed.",
    provisional=True,
)
YIELD_BASIS = CategoryBasis(
    "yield_model",
    "SoilSignal yield model prediction with management and crop status held fixed and "
    "only the future weather changed.",
    provisional=False,
)


@dataclass(frozen=True)
class Trajectory:
    season: int  # historical year the weather comes from
    weight: float
    distance: float
    score: float
    score_details: dict[str, float]
    outcomes: dict[str, float]
    stage_outcomes: dict[str, float]
    future: DailyArrays  # the horizon's days, dated in the outlook's season
    category: str | None = None

    @property
    def weather(self) -> list[DailyWeather]:
        return self.future.daily_weather()


@dataclass(frozen=True)
class CategoryOutlook:
    basis: CategoryBasis
    available: bool
    reason: str | None
    scores: np.ndarray
    categories: np.ndarray  # per trajectory: 0 adverse, 1 typical, 2 favorable
    probabilities: np.ndarray  # weighted
    climatology: np.ndarray  # unweighted
    intervals: np.ndarray  # (3, 2) bootstrap interval per category

    def probability(self, name: str) -> float:
        return float(self.probabilities[CATEGORIES.index(name)])


@dataclass
class Outlook:
    site: SiteInfo
    library: str
    library_label: str
    as_of: date
    horizon: Horizon
    end: date
    planting: date
    season_start: date
    settings: OutlookSettings
    seasons: tuple[int, ...]
    left_out: dict[int, str]
    weights: Weights
    current: dict[str, float]
    library_descriptors: np.ndarray  # (seasons, analog features)
    observed: DailyArrays  # the outlook's season from its first day through as_of
    trajectories: list[Trajectory]
    categories: CategoryOutlook
    adjusted_to_site: bool
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def n_seasons(self) -> int:
        return len(self.seasons)

    @property
    def exploratory(self) -> bool:
        return self.n_seasons < self.settings.robust_min_seasons

    @property
    def probabilities(self) -> dict[str, float] | None:
        if not self.categories.available:
            return None
        rounded = analogs.round_probabilities(self.categories.probabilities)
        return dict(zip(CATEGORIES, rounded, strict=True))

    def weight_array(self) -> np.ndarray:
        return np.array([tr.weight for tr in self.trajectories])

    def outcome_array(self, name: str) -> np.ndarray:
        return np.array([tr.outcomes.get(name, math.nan) for tr in self.trajectories])

    def season_weather(self, trajectory: Trajectory) -> list[DailyWeather]:
        """The outlook's season as the yield model would see it if this trajectory
        happened: observations through as_of, then the trajectory through the horizon."""
        return self.observed.concat(trajectory.future).daily_weather()

    def with_categories(self, categories: CategoryOutlook) -> "Outlook":
        names = [CATEGORIES[int(c)] for c in categories.categories]
        trajectories = [
            Trajectory(**{**tr.__dict__, "category": name})
            for tr, name in zip(self.trajectories, names, strict=True)
        ]
        return Outlook(**{**self.__dict__, "trajectories": trajectories, "categories": categories})


class WeatherOutlook:
    def __init__(self, library: WeatherLibrary, settings: OutlookSettings | None = None) -> None:
        self.library = library
        self.settings = settings or OutlookSettings.from_dict(library.settings)
        self._descriptor_cache = lru_cache(maxsize=4096)(self._library_descriptors)

    # -- descriptors ------------------------------------------------------------------

    def _dates(self, year: int, as_of_md: str, planting_md: str) -> tuple[date, date, date, date]:
        as_of = month_day(year, as_of_md)
        planting = month_day(year, planting_md)
        start = month_day(year, self.settings.season_start)
        return as_of, planting, start, min(start, planting)

    def _library_descriptors(
        self, site: str, year: int, as_of_md: str, planting_md: str
    ) -> tuple[tuple[str, float], ...]:
        record = self.library.record(site)
        as_of, planting, start, first = self._dates(year, as_of_md, planting_md)
        season = from_record(record, first, as_of)
        return tuple(sorted(self._describe(season, record, as_of, start, planting).items()))

    def _describe(
        self, season: DailyArrays, record, as_of: date, start: date, planting: date
    ) -> dict[str, float]:
        out = descriptors(record, as_of, start, planting, current=season)
        capacity = record.info.root_zone_water_mm
        out["root_zone_depletion_mm"] = depletion_through(season, as_of, planting, capacity)
        return out

    # -- outlook ----------------------------------------------------------------------

    def generate(
        self,
        site: str,
        as_of: date,
        horizon: Horizon,
        planting: date | None = None,
        current_weather: Sequence[DailyWeather] | None = None,
        exclude_seasons: Sequence[int] = (),
        bootstrap: bool = True,
        stages: bool = True,
        weighting: Literal["site", "analog", "equal"] = "site",
    ) -> Outlook:
        """`weighting`: the site's setting from the library manifest (default), or force
        analog / equal weights (the backtest compares the two)."""
        try:
            info = self.library.site(site)
        except KeyError as err:
            known = ", ".join(self.library.sites)
            raise OutlookError(f"unknown site '{site}' (known: {known})") from err
        record = self.library.record(info.name)
        s = self.settings
        year = as_of.year
        planting = planting or info.planting(year)
        start = month_day(year, s.season_start)
        first = min(start, planting)
        end = self._horizon_end(as_of, horizon)
        stage_end = max(end, month_day(year, s.season_end))

        left_out = {year: "the outlook's own season"} | {
            y: "excluded by request" for y in exclude_seasons if y != year
        }
        seasons = tuple(y for y in info.seasons if y not in left_out)
        if len(seasons) < s.min_seasons:
            raise OutlookError(
                f"{info.name}: {len(seasons)} historical seasons available, need {s.min_seasons}"
            )

        # The outlook's own season: only days through as_of, from the plot's weather if
        # given, else from the library station.
        if current_weather is not None:
            visible = [d for d in current_weather if d.day <= as_of]
            observed = from_daily_weather(visible, first, as_of, info.latitude)
        else:
            if as_of > info.observed_through:
                raise OutlookError(
                    f"{info.name}: observations end {info.observed_through}, after which "
                    f"the season to date is unknown"
                )
            observed = from_record(record, first, as_of)
        current = self._describe(observed, record, as_of, start, planting)

        md = f"{as_of.month:02d}-{as_of.day:02d}"
        pmd = f"{planting.month:02d}-{planting.day:02d}"
        features = s.analog_features
        lib = np.array(
            [
                [
                    dict(self._descriptor_cache(info.name, y, md, pmd)).get(f, math.nan)
                    for f in features
                ]
                for y in seasons
            ]
        )
        cur = np.array([current.get(f, math.nan) for f in features])
        days_observed = (as_of - start).days + 1
        use_analogs = info.analog_weighting if weighting == "site" else weighting == "analog"
        if not use_analogs:
            weights = analogs.equal_weights(len(seasons))
            reason = (
                "Every season weighs the same: in the backtest, weighting by similarity to the "
                "season so far did not beat equal weights at this site."
            )
        elif days_observed < s.min_days_observed:
            weights = analogs.equal_weights(len(seasons))
            reason = (
                f"Every season weighs the same: fewer than {s.min_days_observed} days of the "
                "season have been observed."
            )
        else:
            weights = analogs.analog_weights(cur, lib, s.bandwidth, s.min_ess_fraction)
            reason = (
                "Seasons that resembled this one so far weigh more."
                if weights.method == "historical_analogs"
                else "Every season weighs the same: the season so far does not separate them."
            )

        adjust = current_weather is not None and bool(info.temperature_adjustment)
        trajectories = []
        for k, y in enumerate(seasons):
            as_of_y = month_day(y, md)
            length = (stage_end - as_of).days
            future = from_record(record, as_of_y + timedelta(1), as_of_y + timedelta(length))
            future = future.redate(as_of + timedelta(1))
            if adjust:
                future = _adjust_temperatures(future, info)
            season = observed.concat(future)
            score = score_trajectory(
                season, as_of, end, planting, info.root_zone_water_mm, info.irrigated
            )
            trajectories.append(
                Trajectory(
                    season=y,
                    weight=float(weights.weights[k]),
                    distance=float(weights.distances[k]),
                    score=score.score,
                    score_details=score.details,
                    outcomes=horizon_outcomes(season, as_of, end, planting),
                    stage_outcomes=stage_outcomes(season, end, planting)
                    if stages and horizon == "season"
                    else {},
                    future=_head(future, (end - as_of).days),
                )
            )

        outlook = Outlook(
            site=info,
            library=self.library.name,
            library_label=self.library.label,
            as_of=as_of,
            horizon=horizon,
            end=end,
            planting=planting,
            season_start=start,
            settings=s,
            seasons=seasons,
            left_out=left_out,
            weights=weights,
            current=current,
            library_descriptors=lib,
            observed=observed,
            trajectories=trajectories,
            categories=None,  # type: ignore[arg-type]
            adjusted_to_site=adjust,
            extra={"method_reason": reason},
        )
        basis = HEAT_BASIS if info.irrigated else WATER_BASIS
        scores = np.array([tr.score for tr in trajectories])
        return outlook.with_categories(classify(outlook, scores, basis, bootstrap=bootstrap))

    def _horizon_end(self, as_of: date, horizon: Horizon) -> date:
        s = self.settings
        if horizon == "season":
            end = month_day(as_of.year, s.season_end)
        elif isinstance(horizon, int) and horizon > 0:
            end = as_of + timedelta(horizon)
        else:
            raise OutlookError(
                f"horizon must be a positive number of days or 'season', not {horizon!r}"
            )
        if end <= as_of:
            raise OutlookError(f"the season ends {end}, on or before {as_of}")
        latest = month_day(as_of.year, s.latest_end)
        if end > latest:
            raise OutlookError(
                f"the horizon ends {end}, after {latest}, the end of the checked season window"
            )
        return end


def _head(arrays: DailyArrays, n: int) -> DailyArrays:
    return DailyArrays(
        arrays.first,
        *(getattr(arrays, f)[:n] for f in ("tmax_c", "tmin_c", "precip_mm", "gdd", "kdd", "et0")),
    )


def _adjust_temperatures(arrays: DailyArrays, info: SiteInfo) -> DailyArrays:
    """Express a proxy station's trajectory at the site: add the monthly mean temperature
    difference measured where both stations overlap. Rain is not changed."""
    dates = arrays.dates()
    dmax = np.array([info.temperature_adjustment.get(d.month, (0.0, 0.0))[0] for d in dates])
    dmin = np.array([info.temperature_adjustment.get(d.month, (0.0, 0.0))[1] for d in dates])
    days = [
        DailyWeather(
            day=d,
            tmax_f=None if math.isnan(hi) else float((hi + a) * 9 / 5 + 32),
            tmin_f=None if math.isnan(lo) else float((lo + b) * 9 / 5 + 32),
            prcp_mm=None if math.isnan(p) else float(p),
        )
        for d, hi, lo, p, a, b in zip(
            dates, arrays.tmax_c, arrays.tmin_c, arrays.precip_mm, dmax, dmin, strict=True
        )
    ]
    return from_daily_weather(days, dates[0], dates[-1], info.latitude)


# -- categories and their uncertainty --------------------------------------------------


def _seed(outlook: Outlook, basis: CategoryBasis) -> int:
    key = f"{outlook.library}|{outlook.site.name}|{outlook.as_of}|{outlook.horizon}|{basis.scorer}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def classify(
    outlook: Outlook, scores: np.ndarray, basis: CategoryBasis, bootstrap: bool = True
) -> CategoryOutlook:
    """Fixed tercile categories from the unweighted historical scores, probabilities from
    the analog weights, and a bootstrap interval that resamples the historical seasons
    (descriptor scaling, weights and category boundaries all recomputed each time)."""
    weights = outlook.weights.weights
    cats, probs = analogs.category_probabilities(scores, weights)
    clim = np.array([np.mean(cats == k) for k in range(3)])
    available, reason = True, None
    if np.ptp(scores) == 0:
        available = False
        reason = "every historical trajectory scores the same for this window (no separation)"
    elif clim.min() < 1 / 6:
        available = False
        reason = "too many historical trajectories tie for the categories to be formed"
    intervals = np.full((3, 2), np.nan)
    s = outlook.settings
    if bootstrap and available and s.bootstrap_samples > 0:
        rng = np.random.default_rng(_seed(outlook, basis))
        n = len(scores)
        draws = np.empty((s.bootstrap_samples, 3))
        cur = np.array([outlook.current.get(f, math.nan) for f in s.analog_features])
        for b in range(s.bootstrap_samples):
            idx = rng.integers(0, n, n)
            if outlook.weights.method == "climatology":
                w = np.full(n, 1.0 / n)
            else:
                w = analogs.analog_weights(
                    cur, outlook.library_descriptors[idx], s.bandwidth, s.min_ess_fraction
                ).weights
            _, draws[b] = analogs.category_probabilities(scores[idx], w)
        tail = (1 - s.interval_level) / 2 * 100
        intervals = np.percentile(draws, [tail, 100 - tail], axis=0).T
    return CategoryOutlook(basis, available, reason, scores, cats, probs, clim, intervals)


# -- the yield model's view --------------------------------------------------------------


@dataclass(frozen=True)
class YieldOutlook:
    outlook: Outlook  # categories now defined by yield
    yields: np.ndarray  # per trajectory, bu/ac

    def distribution(self) -> dict[str, float]:
        w = self.outlook.weight_array()
        return {
            "p10": analogs.weighted_quantile(self.yields, w, 0.1),
            "p50": analogs.weighted_quantile(self.yields, w, 0.5),
            "p90": analogs.weighted_quantile(self.yields, w, 0.9),
            "mean": float(np.sum(w * self.yields)),
        }

    def by_category(self) -> dict[str, float]:
        """Weighted mean yield of the trajectories in each category."""
        w = self.outlook.weight_array()
        cats = self.outlook.categories.categories
        out = {}
        for k, name in enumerate(CATEGORIES):
            mask = cats == k
            if w[mask].sum() > 0:
                out[name] = float(np.sum(w[mask] * self.yields[mask]) / w[mask].sum())
        return out


def couple_yield(
    outlook: Outlook,
    predict: Callable[[list[DailyWeather]], float],
    bootstrap: bool = True,
) -> YieldOutlook:
    """Run every trajectory through a yield model and let yield define the categories.

    `predict` receives the season's daily weather (observed through as_of, then one
    trajectory through the horizon end) and returns bu/ac; everything else about the plot
    (imagery to date, hybrid, nitrogen, irrigation, planting) is the caller's to hold
    fixed. Use horizon "season" for end-of-season yield."""
    yields = np.array([float(predict(outlook.season_weather(tr))) for tr in outlook.trajectories])
    categories = classify(outlook, yields, YIELD_BASIS, bootstrap=bootstrap)
    if np.ptp(yields) == 0:
        categories = CategoryOutlook(
            **{
                **categories.__dict__,
                "available": False,
                "reason": "the yield model returns the same yield under every trajectory: "
                "it does not respond to future weather",
            }
        )
    return YieldOutlook(outlook.with_categories(categories), yields)
