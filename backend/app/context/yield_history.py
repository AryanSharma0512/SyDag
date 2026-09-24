"""County corn yields from USDA NASS Quick Stats (needs a free API key)."""

from datetime import UTC, datetime

import httpx2 as httpx

from app.context.http import NoData, request_json
from app.schemas import County, YieldHistory, YieldYear

QUICKSTATS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
SERVICE = "USDA NASS Quick Stats"
YEARS_SHOWN = 10


def _bushels(raw: object) -> float | None:
    """'191.3' or '1,191.3' -> float. NASS marks withheld values like '(D)' or '(NA)'."""
    text = str(raw).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def fetch_yield_history(
    client: httpx.Client, api_key: str, county: County, through_year: int
) -> YieldHistory:
    county_code = county.fips[2:]
    payload = request_json(
        client,
        SERVICE,
        "GET",
        QUICKSTATS_URL,
        params={
            "key": api_key,
            "source_desc": "SURVEY",
            "commodity_desc": "CORN",
            "statisticcat_desc": "YIELD",
            "short_desc": "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE",
            "agg_level_desc": "COUNTY",
            "reference_period_desc": "YEAR",
            "state_alpha": county.state_code,
            "county_ansi": county_code,
            "year__GE": through_year - YEARS_SHOWN + 1,
            "year__LE": through_year,
            "format": "JSON",
        },
    )
    by_year: dict[int, float] = {}
    for row in payload.get("data", []) if isinstance(payload, dict) else []:
        if str(row.get("county_ansi", "")).zfill(3) != county_code:
            continue  # skip "other (combined) counties" rows
        value = _bushels(row.get("Value"))
        year = int(row["year"]) if str(row.get("year", "")).isdigit() else None
        if value is not None and year is not None:
            by_year.setdefault(year, value)
    if not by_year:
        raise NoData(f"NASS has no published corn yields for {county.name}")
    years = [YieldYear(year=y, yield_=by_year[y]) for y in sorted(by_year)]
    recent = [y.yield_ for y in years[-5:]]
    return YieldHistory(
        county=county,
        years=years,
        five_year_average=round(sum(recent) / len(recent), 1) if len(recent) >= 3 else None,
        unit="bu/ac",
        source=SERVICE,
        retrieved_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
