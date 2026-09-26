"""
Weather history for the outlook: the supplied challenge file and the long-record library.

Each library holds exactly one station per site for every season. Neighbouring stations
are read only to flag doubtful seasons (a gauge that reported zeros while broken, a
thermometer that drifted); a flagged season is left out, never filled from another
station. What was kept, left out and why is written to the library's manifest.

    supplied  the challenge file as delivered (IEM computed daily summaries, 2018-2023)
    long      NOAA GHCN-Daily for the same airport stations (the official daily record, which
              IEM's computed summaries do not match in every year), and a documented proxy
              station for Crawfordsville, whose on-site station starts in December 2013
"""

import io
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2 as httpx
import numpy as np
import pandas as pd
import yaml

from app.weather_outlook.history import DAILY_FILE, MANIFEST_FILE
from soilsignal_ml import BACKEND_ROOT, ML_ROOT

CONFIG_PATH = ML_ROOT / "configs" / "weather_outlook.yaml"
RAW_DIR = ML_ROOT / "data" / "raw" / "weather"
PUBLISH_DIR = BACKEND_ROOT / "data" / "weather_history"
REPORT_DIR = ML_ROOT / "experiments" / "weather_outlook"

GHCN_URL = "https://www.ncei.noaa.gov/access/services/data/v1"
ISUSM_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/isusm.py"
USER_AGENT = "SoilSignal/0.1 (IoT4Ag hackathon project; weather outlook research)"
CORE = ("tmax_c", "tmin_c", "precip_mm")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


# --- sources ---------------------------------------------------------------------------


def _get(client: httpx.Client, url: str, params: dict[str, Any], tries: int = 4) -> str:
    for attempt in range(tries):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


def fetch_ghcn(
    station: str, start: date, end: date, cache: Path = RAW_DIR / "ghcn", refresh: bool = False
) -> pd.DataFrame:
    """GHCN-Daily TMAX/TMIN/PRCP (metric) with observation time. Values that failed NOAA's
    quality checks (a non-blank QFLAG) are set to missing."""
    path = cache / f"{station}_{start}_{end}.csv"
    if refresh or not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=180, headers={"User-Agent": USER_AGENT}) as client:
            text = _get(
                client,
                GHCN_URL,
                {
                    "dataset": "daily-summaries",
                    "stations": station,
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "dataTypes": "TMAX,TMIN,PRCP",
                    "units": "metric",
                    "format": "csv",
                    "includeAttributes": "true",
                },
            )
        path.write_text(text)
    raw = pd.read_csv(path, dtype=str)
    out = pd.DataFrame({"date": pd.to_datetime(raw["DATE"])})
    for code, column in (("TMAX", "tmax_c"), ("TMIN", "tmin_c"), ("PRCP", "precip_mm")):
        values = pd.to_numeric(raw.get(code), errors="coerce")
        attrs = raw.get(f"{code}_ATTRIBUTES", pd.Series("", index=raw.index)).fillna("")
        qflag = attrs.str.split(",").str[1].fillna("")
        out[column] = values.where(qflag == "")
        if code == "PRCP":
            out["obs_time"] = attrs.str.split(",").str[3].fillna("")
    return out


def fetch_isusm(
    station: str, start: date, end: date, cache: Path = RAW_DIR / "isusm", refresh: bool = False
) -> pd.DataFrame:
    """ISU Soil Moisture Network daily summaries (local calendar day)."""
    path = cache / f"{station}_{start}_{end}.csv"
    if refresh or not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=180, headers={"User-Agent": USER_AGENT}) as client:
            text = _get(
                client,
                ISUSM_URL,
                {
                    "station": station,
                    "mode": "daily",
                    "sts": f"{start.isoformat()}T06:00Z",
                    "ets": f"{(end + timedelta(1)).isoformat()}T06:00Z",
                    "format": "comma",
                    "tz": "America/Chicago",
                    "vars": "high,low,precip",
                },
            )
        path.write_text(text)
    raw = pd.read_csv(path)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(raw["valid"]),
            "tmax_c": (pd.to_numeric(raw["high"], errors="coerce") - 32) * 5 / 9,
            "tmin_c": (pd.to_numeric(raw["low"], errors="coerce") - 32) * 5 / 9,
            "precip_mm": pd.to_numeric(raw["precip"], errors="coerce") * 25.4,
        }
    )


def align_observation_day(frame: pd.DataFrame, shift_days: int) -> pd.DataFrame:
    """Move every value by shift_days (−1: a 07:00 observation dated D describes D−1)."""
    if not shift_days:
        return frame
    out = frame.copy()
    out["date"] = out["date"] + pd.Timedelta(days=shift_days)
    return out


def load_supplied(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The challenge file, normalized columns only, and its station metadata."""
    daily = pd.read_csv(ML_ROOT / cfg["supplied"]["file"], low_memory=False)
    meta = pd.read_csv(ML_ROOT / cfg["supplied"]["metadata"])
    daily = daily.rename(columns={"site_name": "site"})
    daily["date"] = pd.to_datetime(daily["date"])
    keep = ["site", "date", "station_id", *CORE, "avg_rh", "avg_wind_speed_mps", "qc_status"]
    return daily[keep].sort_values(["site", "date"]).reset_index(drop=True), meta


# --- season QC -----------------------------------------------------------------------


def _window(frame: pd.DataFrame, year: int, window: tuple[str, str]) -> pd.DataFrame:
    first = pd.Timestamp(f"{year}-{window[0]}")
    last = pd.Timestamp(f"{year}-{window[1]}")
    return frame[(frame["date"] >= first) & (frame["date"] <= last)]


def season_table(frame: pd.DataFrame, years: range, window: tuple[str, str]) -> pd.DataFrame:
    """Per season: completeness of each core variable over the QC window, precipitation
    total and mean temperatures."""
    length = (pd.Timestamp(f"2001-{window[1]}") - pd.Timestamp(f"2001-{window[0]}")).days + 1
    rows = []
    for year in years:
        w = _window(frame, year, window).drop_duplicates("date")
        row: dict[str, Any] = {"season": year}
        for column in CORE:
            row[f"{column}_complete"] = round(w[column].notna().sum() / length, 3) if len(w) else 0
        row["precip_total_mm"] = round(float(w["precip_mm"].sum()), 1) if len(w) else math.nan
        row["tmax_mean_c"] = round(float(w["tmax_c"].mean()), 2) if len(w) else math.nan
        row["tmin_mean_c"] = round(float(w["tmin_c"].mean()), 2) if len(w) else math.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("season")


def fill_temperature_gaps(frame: pd.DataFrame, max_gap: int) -> pd.DataFrame:
    """Interpolate runs of at most max_gap missing days in tmax and tmin, within this
    station's own record, on a continuous calendar. Adds `temp_filled` (True where either
    temperature was interpolated). Precipitation is never filled."""
    frame = frame.drop_duplicates("date").set_index("date").sort_index()
    frame = frame.reindex(pd.date_range(frame.index.min(), frame.index.max(), freq="D"))
    filled = pd.Series(False, index=frame.index)
    for column in ("tmax_c", "tmin_c"):
        missing = frame[column].isna()
        run_id = (missing != missing.shift()).cumsum()
        run_length = missing.groupby(run_id).transform("sum")
        short = missing & (run_length <= max_gap)
        interpolated = frame[column].interpolate(limit_area="inside")
        frame.loc[short, column] = interpolated[short]
        filled |= short & frame[column].notna()
    frame["temp_filled"] = filled
    return frame.rename_axis("date").reset_index()


def _usual(values: pd.Series, usable: pd.Series, year: int, window: int) -> float:
    """Median of a pair statistic over the `window` usable seasons nearest `year`
    (excluding it), so a step change at either station only shifts nearby seasons."""
    candidates = values[usable & (values.index != year)]
    if candidates.empty:
        return math.nan
    nearest = (candidates.index.to_series() - year).abs().sort_values(kind="stable")
    return float(candidates.loc[nearest.index[:window]].median())


def qc_seasons(
    primary: pd.DataFrame,
    neighbors: dict[str, pd.DataFrame],
    years: range,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """One row per season: completeness, the neighbour comparisons and the decision.

    A neighbour comparison uses only seasons in which both stations are complete. The
    usual ratio (precipitation) and difference (temperature) between the pair are medians
    over the nearest seasons, so a steady offset between two sites is not a flag, and
    neither is a station change at the neighbour. A season is left out when it is
    incomplete, or when every neighbour able to check it flags it."""
    window = tuple(cfg["seasons"]["qc_window"])
    need = cfg["seasons"]["min_completeness"]
    ratio_tol = math.log(cfg["seasons"]["precip_ratio_tolerance"])
    temp_tol = cfg["seasons"]["temperature_tolerance_c"]
    span = cfg["seasons"].get("usual_window_seasons", 11)
    table = season_table(primary, years, window)
    if "temp_filled" in primary:
        table["temp_days_filled"] = [
            int(_window(primary, y, window)["temp_filled"].sum()) for y in years
        ]
    complete = table[[f"{c}_complete" for c in CORE]].min(axis=1) >= need
    table["complete"] = complete
    reasons: dict[int, list[str]] = {y: [] for y in years}
    flags: dict[int, list[str]] = {y: [] for y in years}
    checked: dict[int, int] = {y: 0 for y in years}
    for year in years:
        if not complete[year]:
            worst = {c: table.loc[year, f"{c}_complete"] for c in CORE}
            reasons[year].append(
                "incomplete: " + ", ".join(f"{c} {v:.0%}" for c, v in worst.items() if v < need)
            )
    temp_need = cfg["seasons"].get("neighbour_temperature_completeness", need)
    for station, frame in neighbors.items():
        other = season_table(frame, years, window)
        both_p = complete & (other["precip_mm_complete"] >= need)
        both_t = complete & (other[["tmax_c_complete", "tmin_c_complete"]].min(axis=1) >= temp_need)
        both = both_p | both_t
        with np.errstate(divide="ignore", invalid="ignore"):
            log_ratio = np.log(table["precip_total_mm"] / other["precip_total_mm"])
        d_tmax = table["tmax_mean_c"] - other["tmax_mean_c"]
        d_tmin = table["tmin_mean_c"] - other["tmin_mean_c"]
        table[f"precip_ratio_vs_{station}"] = np.exp(log_ratio).round(2).where(both_p)
        table[f"tmax_diff_vs_{station}"] = d_tmax.round(2).where(both_t)
        table[f"tmin_diff_vs_{station}"] = d_tmin.round(2).where(both_t)
        use_p, use_t = both_p.sum() >= 5, both_t.sum() >= 5
        for year in table.index[both]:
            if not ((use_p and both_p[year]) or (use_t and both_t[year])):
                continue
            checked[year] += 1
            found = []
            if use_p and both_p[year]:
                usual = _usual(log_ratio, both_p, year, span)
                if abs(log_ratio[year] - usual) > ratio_tol:
                    found.append(
                        f"precipitation {math.exp(log_ratio[year]):.2f}x {station} "
                        f"(usual {math.exp(usual):.2f}x)"
                    )
            for name, diff in (("tmax", d_tmax), ("tmin", d_tmin)):
                if not (use_t and both_t[year]):
                    continue
                usual_diff = _usual(diff, both_t, year, span)
                if abs(diff[year] - usual_diff) > temp_tol:
                    found.append(
                        f"mean {name} {diff[year]:+.1f} C vs {station} (usual {usual_diff:+.1f} C)"
                    )
            if found:
                flags[year].append("; ".join(found))
    table["neighbours_checked"] = [checked[y] for y in years]
    table["neighbour_flags"] = ["; ".join(flags[y]) for y in years]
    for year in years:
        if checked[year] and len(flags[year]) == checked[year]:
            reasons[year].append("disagrees with every neighbour: " + " | ".join(flags[year]))
    table["included"] = [not reasons[y] for y in table.index]
    table["reason"] = ["; ".join(reasons[y]) for y in table.index]
    return table


def overlap_stats(proxy: pd.DataFrame, reference: pd.DataFrame) -> dict[str, Any]:
    """How a proxy station compares with the on-site station where both exist:
    daily correlations, mean biases and the monthly temperature differences used to adjust
    exported trajectories. Growing-season months (April-October) only for the summaries."""
    merged = proxy.merge(reference, on="date", suffixes=("_proxy", "_site")).dropna(
        subset=[f"{c}_{s}" for c in CORE for s in ("proxy", "site")]
    )
    season = merged[merged["date"].dt.month.between(4, 10)]
    monthly = merged.groupby(merged["date"].dt.month)
    by_year = season.groupby(season["date"].dt.year)
    totals = by_year[["precip_mm_proxy", "precip_mm_site"]].sum()
    return {
        "days": int(len(merged)),
        "first": merged["date"].min().date().isoformat(),
        "last": merged["date"].max().date().isoformat(),
        "daily_correlation": {
            c: round(float(season[f"{c}_proxy"].corr(season[f"{c}_site"])), 3) for c in CORE
        },
        "mean_difference_c": {
            c: round(float((season[f"{c}_proxy"] - season[f"{c}_site"]).mean()), 2)
            for c in ("tmax_c", "tmin_c")
        },
        "season_precip_ratio": round(
            float(totals["precip_mm_proxy"].sum() / totals["precip_mm_site"].sum()), 3
        ),
        "season_precip_correlation": round(
            float(totals["precip_mm_proxy"].corr(totals["precip_mm_site"])), 3
        ),
        # site minus proxy, by calendar month: added to a proxy trajectory's temperatures.
        "monthly_temperature_adjustment_c": {
            c: {
                int(m): round(float(-(g[f"{c}_proxy"] - g[f"{c}_site"]).mean()), 2)
                for m, g in monthly
            }
            for c in ("tmax_c", "tmin_c")
        },
    }


# --- libraries -----------------------------------------------------------------------


@dataclass
class SiteHistory:
    site: str
    station: dict[str, Any]
    daily: pd.DataFrame  # date + CORE
    qc: pd.DataFrame


def _site_record(cfg: dict[str, Any], site: str, library: str) -> dict[str, Any]:
    s = cfg["sites"][site]
    weighting = (
        cfg["supplied"]["analog_weighting"] if library == "supplied" else s["analog_weighting"]
    )
    return {
        "analog_weighting": bool(weighting),
        "latitude": s["latitude"],
        "longitude": s["longitude"],
        "irrigated": s["irrigated"],
        "reference_planting": s["reference_planting"],
        "root_zone_water_mm": s["root_zone_water_mm"],
    }


def build_supplied(cfg: dict[str, Any]) -> list[SiteHistory]:
    daily, meta = load_supplied(cfg)
    years = range(2018, 2024)
    out = []
    for site, frame in daily.groupby("site"):
        row = meta.loc[meta["site_name"] == site].iloc[0]
        qc = qc_seasons(frame, {}, years, cfg)
        station = {
            "id": row["station_id"],
            "name": row["station_name"],
            "network": row["station_network"],
            "source": f"{row['source_dataset']} (challenge weather file)",
            "latitude": float(row["station_latitude"]),
            "longitude": float(row["station_longitude"]),
            "distance_km": round(float(row["station_distance_km"]), 1),
            "tobs_shift_days": 0,
        }
        out.append(SiteHistory(str(site), station, frame[["date", *CORE]], qc))
    return out


def build_long(cfg: dict[str, Any], end: date, refresh: bool = False) -> list[SiteHistory]:
    first = cfg["seasons"]["long_first_season"]
    last = cfg["seasons"]["long_last_season"]
    start = date(first - 1, 10, 1)
    years = range(first, last + 1)
    out = []
    for site, s in cfg["sites"].items():
        spec = s["long"]
        primary = fetch_ghcn(spec["station"], start, end, refresh=refresh)
        primary = align_observation_day(primary, spec["tobs_shift_days"])
        primary = primary[primary["date"].dt.date <= end]
        primary = fill_temperature_gaps(primary, cfg["seasons"]["max_temperature_gap_days"])
        neighbors = {
            n: fetch_neighbor(n, start, end, refresh) for n in spec.get("qc_neighbors", [])
        }
        qc = qc_seasons(primary, neighbors, years, cfg)
        station: dict[str, Any] = {
            "id": spec["station"],
            "name": spec["name"],
            "network": "GHCN-Daily",
            "source": "NOAA NCEI GHCN-Daily (daily-summaries)",
            "same_as_supplied": spec["same_as_supplied"],
            "tobs_shift_days": spec["tobs_shift_days"],
            "observation_time": sorted(set(primary["obs_time"].dropna()) - {""}),
            "qc_neighbors": spec.get("qc_neighbors", []),
        }
        if spec.get("overlap_reference"):
            ref = fetch_isusm(spec["overlap_reference"], date(2013, 12, 17), end, refresh=refresh)
            stats = overlap_stats(primary[["date", *CORE]], ref)
            stats["reference_station"] = spec["overlap_reference"]
            station["overlap"] = stats
        out.append(SiteHistory(site, station, primary[["date", *CORE, "temp_filled"]], qc))
    return out


def fetch_neighbor(name: str, start: date, end: date, refresh: bool) -> pd.DataFrame:
    """A QC neighbour: a GHCN-Daily id, or "isusm:<id>" for an ISU Soil Moisture station."""
    if name.startswith("isusm:"):
        return fetch_isusm(name.split(":", 1)[1], date(2013, 12, 17), end, refresh=refresh)
    return fetch_ghcn(name, start, end, refresh=refresh)


def publish(
    name: str,
    label: str,
    sites: list[SiteHistory],
    cfg: dict[str, Any],
    out_dir: Path = PUBLISH_DIR,
    report_dir: Path = REPORT_DIR,
) -> Path:
    """Write <out_dir>/<name>/daily.csv.gz (every day of every site, including incomplete
    seasons and the current partial one, which can be a 'current season' but never an
    analog) and manifest.json (stations, seasons used and left out, site parameters)."""
    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    manifest_sites = {}
    for h in sites:
        daily = h.daily.drop_duplicates("date").sort_values("date").copy()
        daily.insert(0, "site", h.site)
        daily.insert(2, "station_id", h.station["id"])
        frames.append(daily)
        included = [int(y) for y in h.qc.index[h.qc["included"]]]
        excluded = {int(y): r for y, r in h.qc.loc[~h.qc["included"], "reason"].items()}
        manifest_sites[h.site] = {
            **_site_record(cfg, h.site, name),
            "station": h.station,
            "seasons": included,
            "excluded_seasons": excluded,
            "observed_through": daily["date"].max().date().isoformat(),
        }
        h.qc.to_csv(report_dir / f"qc_{name}_{h.site}.csv")
    table = pd.concat(frames, ignore_index=True)
    if "temp_filled" in table:
        table["temp_filled"] = table["temp_filled"].fillna(False).astype(int)
    table["date"] = table["date"].dt.strftime("%Y-%m-%d")
    for column in CORE:
        table[column] = table[column].round(2)
    buffer = io.BytesIO()
    table.to_csv(buffer, index=False, compression={"method": "gzip", "mtime": 0})
    (target / DAILY_FILE).write_bytes(buffer.getvalue())
    manifest = {
        "library": name,
        "label": label,
        "created": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "variables": {
            "tmax_c": "daily maximum air temperature, C",
            "tmin_c": "daily minimum air temperature, C",
            "precip_mm": "daily precipitation, mm",
        },
        "qc": {
            "window": cfg["seasons"]["qc_window"],
            "min_completeness": cfg["seasons"]["min_completeness"],
            "precip_ratio_tolerance": cfg["seasons"]["precip_ratio_tolerance"],
            "temperature_tolerance_c": cfg["seasons"]["temperature_tolerance_c"],
            "max_temperature_gap_days": cfg["seasons"]["max_temperature_gap_days"],
            "rule": "one station per site; neighbours flag seasons, never fill them; "
            "temperature gaps of at most max_temperature_gap_days are interpolated within "
            "the station (temp_filled = 1); precipitation is never filled",
        },
        "outlook": cfg["outlook"],
        "sites": manifest_sites,
    }
    (target / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n")
    return target
