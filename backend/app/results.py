"""
The frozen final results: one versioned file the ML team publishes after the final run,
which the website reads instead of re-running training or inference.

    backend/artifacts/final_results.json      (next to the model artifacts; mounted, so
                                              copying it in and restarting deploys it)

Written by the ML side in snake_case (camelCase is accepted too); served camelCase by
GET /api/results (everything except plots) and GET /api/results/plots?site=&season=.
Until the file exists the API reports `pending` and the website shows placeholders; it
never fills in numbers. A malformed file is a 503 that names the problem, so a typo
shows up at deploy time rather than as a quietly missing chart. Check a file with

    cd backend && uv run python -m app.results path/to/final_results.json

Contract (contract_version 1). Required: `results_version`, `model`, `performance`.
The numbers below only illustrate the shape.

    {
      "contract_version": 1,
      "results_version": "final-2026-09-27",
      "generated_at": "2026-09-27T03:00:00Z",
      "dataset_label": "Challenge data (SyDAg26)",
      "model": {"name": "Random Forest", "validation": "leave-one-site-out, 3 sites",
                "description": "...", "features": ["ndvi_tp1", "..."]},
      "interval": {"level": 0.9, "coverage": 0.86, "method": "split conformal"},
      "performance": [{"dap": 57, "label": "TP1", "mae": 30.1, "rmse": 38.0, "r2": 0.21,
                       "n": 900}, ...],
      "earliest_useful_dap": 82,
      "earliest_useful_rule": "first stage whose MAE ...",
      "sites": [{"site": "Ames", "season": 2022, "plots": 256,
                 "forecasts": [{"date": "2022-08-12", "dap": 82, "yield": 181.0,
                                "lower": 160.0, "upper": 199.0}]}],
      "plots": [{"plot_id": "4231-17-3", "site": "Ames", "season": 2022,
                 "hybrid": "B73 X MO17", "nitrogen_lb_ac": 150, "planting_date": "2022-05-22",
                 "irrigated": false,
                 "forecasts": [{"date": "2022-08-12", "dap": 82, "yield": 184.0,
                                "lower": 166.0, "upper": 194.0}],
                 "uav": {"dap": 80, "satellite_only": 184.0, "satellite_plus_uav": 181.0}}],
      "maturity": [{"site": "Ames", "season": 2022, "plot_id": null, "as_of": "2022-08-12",
                    "gdd_since_planting": 1940, "gdd_to_maturity": 2700,
                    "window_start": "2022-09-18", "window_end": "2022-09-24",
                    "method": "..."}],
      "uav": {"matched": true, "sites": ["Ames"], "plots": 160, "dap": 80,
              "validation": "leave-one-...", "framework": "Random Forest, same features",
              "satellite_only": {"mae": 20.0, "r2": 0.6},
              "satellite_plus_uav": {"mae": 19.0, "r2": 0.62},
              "note": "..."}
    }

`lower`/`upper` are the prediction range; `interval.coverage` is the share of validation
yields inside it, which is what the website quotes (never a nominal level on its own).
The UAV panels fill only when `uav.matched` is true: the same plots, dates, validation
split and model framework with and without UAV.
"""

import json
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from app.schemas import ApiModel

RESULTS_FILE = "final_results.json"
CONTRACT_VERSION = 1


class ResultsError(Exception):
    """final_results.json exists but does not match the contract."""


class ResultsModel(ApiModel):
    name: str
    validation: str
    description: str | None = None
    features: list[str] | None = None


class IntervalInfo(ApiModel):
    level: float | None = Field(default=None, gt=0, lt=1)  # nominal, e.g. 0.9
    coverage: float | None = Field(default=None, ge=0, le=1)  # observed in validation
    method: str | None = None


class StagePerformance(ApiModel):
    dap: int = Field(ge=0)  # days after planting of the latest data the stage can use
    label: str | None = None  # e.g. "TP1-TP3"
    mae: float | None = Field(default=None, ge=0)
    rmse: float | None = Field(default=None, ge=0)
    r2: float | None = None
    n: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _has_a_metric(self) -> "StagePerformance":
        if self.mae is None and self.r2 is None:
            raise ValueError(f"performance at DAP {self.dap} needs mae or r2")
        return self


class ForecastPoint(ApiModel):
    date: date
    dap: int = Field(ge=0)
    yield_: float = Field(ge=0)
    lower: float | None = None
    upper: float | None = None

    @model_validator(mode="after")
    def _ordered(self) -> "ForecastPoint":
        if (self.lower is None) != (self.upper is None):
            raise ValueError(f"forecast on {self.date}: give both lower and upper, or neither")
        if self.lower is not None and not (self.lower <= self.yield_ <= self.upper):
            raise ValueError(f"forecast on {self.date}: needs lower <= yield <= upper")
        return self


def _chronological(points: list[ForecastPoint], where: str) -> list[ForecastPoint]:
    dates = [p.date for p in points]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError(f"{where}: forecasts must be in date order, one per date")
    return points


class SiteForecast(ApiModel):
    site: str
    season: int
    plots: int | None = Field(default=None, ge=1)
    forecasts: list[ForecastPoint] = Field(min_length=1)

    @model_validator(mode="after")
    def _order(self) -> "SiteForecast":
        _chronological(self.forecasts, f"site {self.site} {self.season}")
        return self


class PlotUav(ApiModel):
    dap: int | None = Field(default=None, ge=0)
    satellite_only: float = Field(ge=0)
    satellite_plus_uav: float = Field(ge=0)


class PlotForecast(ApiModel):
    plot_id: str
    site: str
    season: int
    hybrid: str | None = None
    nitrogen_lb_ac: float | None = None
    planting_date: date | None = None
    irrigated: bool | None = None
    forecasts: list[ForecastPoint] = Field(min_length=1)
    uav: PlotUav | None = None

    @model_validator(mode="after")
    def _order(self) -> "PlotForecast":
        _chronological(self.forecasts, f"plot {self.plot_id}")
        return self


class MaturityEstimate(ApiModel):
    site: str
    season: int
    plot_id: str | None = None  # None: the estimate for the whole site
    as_of: date
    gdd_since_planting: float | None = Field(default=None, ge=0)
    gdd_to_maturity: float | None = Field(default=None, gt=0)
    window_start: date | None = None
    window_end: date | None = None
    method: str | None = None

    @model_validator(mode="after")
    def _window(self) -> "MaturityEstimate":
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("maturity window needs both window_start and window_end")
        if self.window_start and self.window_start > self.window_end:
            raise ValueError("maturity window_start is after window_end")
        return self


class UavVariant(ApiModel):
    mae: float = Field(ge=0)
    rmse: float | None = Field(default=None, ge=0)
    r2: float | None = None


class UavComparison(ApiModel):
    # True only for a matched experiment: the same plots, dates, validation split and
    # model framework with and without UAV. The website shows numbers only when true.
    matched: bool
    sites: list[str] = Field(default_factory=list)
    plots: int | None = Field(default=None, ge=1)
    dap: int | None = Field(default=None, ge=0)
    validation: str | None = None
    framework: str | None = None
    satellite_only: UavVariant
    satellite_plus_uav: UavVariant
    note: str | None = None


class _ResultsFile(ApiModel):
    contract_version: Literal[1]
    results_version: str
    generated_at: str | None = None
    dataset_label: str | None = None
    unit: str = "bu/ac"
    model: ResultsModel
    interval: IntervalInfo | None = None
    performance: list[StagePerformance] = Field(min_length=1)
    earliest_useful_dap: int | None = Field(default=None, ge=0)
    earliest_useful_rule: str | None = None
    sites: list[SiteForecast] = Field(default_factory=list)
    plots: list[PlotForecast] = Field(default_factory=list)
    maturity: list[MaturityEstimate] = Field(default_factory=list)
    uav: UavComparison | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "_ResultsFile":
        daps = [p.dap for p in self.performance]
        if daps != sorted(daps) or len(set(daps)) != len(daps):
            raise ValueError("performance rows must be in DAP order, one per DAP")
        keys = [(p.site.lower(), p.season, p.plot_id) for p in self.plots]
        if len(set(keys)) != len(keys):
            raise ValueError("plots: each (site, season, plot_id) must appear once")
        return self


class PlotCount(ApiModel):
    site: str
    season: int
    plots: int


class FinalResults(ApiModel):
    """GET /api/results: everything but the per-plot forecasts."""

    status: Literal["pending", "ready"]
    contract_version: int = CONTRACT_VERSION
    results_version: str | None = None
    generated_at: str | None = None
    dataset_label: str | None = None
    unit: str = "bu/ac"
    model: ResultsModel | None = None
    interval: IntervalInfo | None = None
    performance: list[StagePerformance] = Field(default_factory=list)
    earliest_useful_dap: int | None = None
    earliest_useful_rule: str | None = None
    sites: list[SiteForecast] = Field(default_factory=list)
    plot_counts: list[PlotCount] = Field(default_factory=list)
    maturity: list[MaturityEstimate] = Field(default_factory=list)
    uav: UavComparison | None = None


class LoadedResults:
    def __init__(self, parsed: _ResultsFile) -> None:
        self.parsed = parsed
        counts: dict[tuple[str, int], int] = {}
        for p in parsed.plots:
            counts[(p.site, p.season)] = counts.get((p.site, p.season), 0) + 1
        self.summary = FinalResults(
            status="ready",
            **parsed.model_dump(exclude={"plots"}),
            plot_counts=[
                PlotCount(site=s, season=y, plots=n) for (s, y), n in sorted(counts.items())
            ],
        )

    def plots(self, site: str, season: int | None = None) -> list[PlotForecast]:
        return [
            p
            for p in self.parsed.plots
            if p.site.lower() == site.lower() and (season is None or p.season == season)
        ]


def parse(text: str) -> _ResultsFile:
    try:
        return _ResultsFile.model_validate_json(text)
    except ValidationError as err:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}" for e in err.errors()[:8]
        )
        raise ResultsError(
            f"{RESULTS_FILE} does not match contract v{CONTRACT_VERSION}: {problems}"
        ) from err


@lru_cache(maxsize=4)
def _load(path: Path, mtime_ns: int) -> LoadedResults:
    return LoadedResults(parse(path.read_text()))


def load_results(model_dir: Path) -> LoadedResults | None:
    """The published results, or None while pending. Re-read when the file changes, so
    copying a new file in takes effect without a restart."""
    path = model_dir / RESULTS_FILE
    if not path.is_file():
        return None
    return _load(path, path.stat().st_mtime_ns)


PENDING = FinalResults(status="pending")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.results path/to/final_results.json")
        return 2
    try:
        loaded = LoadedResults(parse(Path(argv[0]).read_text()))
    except (ResultsError, OSError, json.JSONDecodeError) as err:
        print(f"INVALID: {err}")
        return 1
    s = loaded.summary
    print(f"OK: {s.results_version} ({s.model.name}, {s.model.validation})")
    print(f"  performance at DAP {[p.dap for p in s.performance]}")
    print(f"  earliest useful DAP {s.earliest_useful_dap}")
    print(f"  plots by site: {[(c.site, c.season, c.plots) for c in s.plot_counts]}")
    print(f"  site forecasts {len(s.sites)}, maturity estimates {len(s.maturity)}")
    uav = "none" if s.uav is None else "matched" if s.uav.matched else "not matched"
    print(f"  UAV comparison: {uav}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
