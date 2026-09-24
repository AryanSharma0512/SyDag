"""County for a coordinate, from the FCC Area API (no API key needed)."""

import httpx2 as httpx

from app.context.http import NoData, request_json
from app.schemas import County

FCC_URL = "https://geo.fcc.gov/api/census/block/find"
SERVICE = "FCC Area API"


def fetch_county(client: httpx.Client, lat: float, lon: float) -> County:
    data = request_json(
        client,
        SERVICE,
        "GET",
        FCC_URL,
        params={"latitude": lat, "longitude": lon, "censusYear": 2020, "format": "json"},
    )
    county, state = data.get("County") or {}, data.get("State") or {}
    if not county.get("FIPS") or not state.get("code"):
        raise NoData("this location is outside US counties")
    return County(
        name=county["name"], state_code=state["code"], state_name=state["name"], fips=county["FIPS"]
    )
