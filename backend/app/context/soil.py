"""Soil profile from USDA NRCS SSURGO through Soil Data Access (no API key needed)."""

from datetime import UTC, datetime
from typing import Any

import httpx2 as httpx

from app.context.http import NoData, UpstreamError, request_json
from app.schemas import SoilProfile

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
SERVICE = "USDA Soil Data Access"
SOURCE = "USDA NRCS SSURGO"

# Components that are land cover rather than soil (e.g. "Urban land", "Water").
MISC_KIND = "Miscellaneous area"

MAP_UNIT_QUERY = """
SELECT mu.mukey, mu.muname, c.cokey, c.compname, c.comppct_r, c.compkind, c.drainagecl,
       c.hydgrp, c.taxclname, ma.aws0100wta, ma.slopegraddcp
FROM mapunit mu
INNER JOIN component c ON c.mukey = mu.mukey
LEFT JOIN muaggatt ma ON ma.mukey = mu.mukey
WHERE mu.mukey IN (
  SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon:.6f} {lat:.6f})'))
ORDER BY c.comppct_r DESC
"""

HORIZON_QUERY = """
SELECT h.hzdept_r, h.hzdepb_r, h.awc_r, h.om_r, h.ph1to1h2o_r,
       (SELECT TOP 1 tg.texdesc FROM chtexturegrp tg
         WHERE tg.chkey = h.chkey AND tg.rvindicator = 'Yes') AS texdesc,
       (SELECT MIN(r.resdept_r) FROM corestrictions r WHERE r.cokey = h.cokey) AS restriction_depth
FROM chorizon h
WHERE h.cokey = '{cokey}'
ORDER BY h.hzdept_r
"""

ROOT_ZONE_CM = 100  # depth over which available water is summarized


def _query(client: httpx.Client, sql: str) -> list[dict[str, Any]]:
    payload = request_json(
        client, SERVICE, "POST", SDA_URL, json={"query": sql, "format": "JSON+COLUMNNAME"}
    )
    if not isinstance(payload, dict):
        raise UpstreamError(SERVICE, "unexpected response shape")
    table = payload.get("Table") or []  # Soil Data Access returns {} when nothing matches
    if not table:
        return []
    columns, *rows = table
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def water_class(storage_cm: float | None) -> str | None:
    """Plant-available water in the top 100 cm. The Soil Survey Manual's classes
    (low under 15 cm, high from 22.5 cm) are for 150 cm, so they're scaled to 100 cm."""
    if storage_cm is None:
        return None
    return "Low" if storage_cm < 10 else "Moderate" if storage_cm < 15 else "High"


def _water_in_top(
    horizons: list[dict[str, Any]], depth_cm: float
) -> tuple[float | None, float | None]:
    """Thickness-weighted available water capacity (cm/cm) and total storage (cm)
    over the top `depth_cm` of the profile."""
    water = thickness = 0.0
    for h in horizons:
        top, bottom, awc = _num(h["hzdept_r"]), _num(h["hzdepb_r"]), _num(h["awc_r"])
        if top is None or bottom is None or awc is None:
            continue
        overlap = max(0.0, min(bottom, depth_cm) - top)
        water += awc * overlap
        thickness += overlap
    if thickness == 0:
        return None, None
    return round(water / thickness, 3), round(water, 1)


def parse_profile(
    components: list[dict[str, Any]], horizons: list[dict[str, Any]], retrieved_at: datetime
) -> SoilProfile:
    soil = _dominant_component(components)
    surface = horizons[0] if horizons else {}
    awc, storage = _water_in_top(horizons, ROOT_ZONE_CM)
    if storage is None:
        storage = _num(soil.get("aws0100wta"))
    restriction = _num(surface.get("restriction_depth"))
    deepest = max((_num(h["hzdepb_r"]) or 0 for h in horizons), default=None)
    texture = next((h["texdesc"] for h in horizons if h.get("texdesc")), None)
    return SoilProfile(
        map_unit_key=str(soil["mukey"]),
        map_unit_name=soil["muname"],
        series=soil["compname"],
        component_percent=_num(soil["comppct_r"]) or 0,
        taxonomic_class=soil.get("taxclname"),
        texture=texture,
        drainage=soil.get("drainagecl"),
        hydrologic_group=soil.get("hydgrp"),
        available_water_capacity=awc,
        available_water_storage_cm=storage,
        available_water_class=water_class(storage),
        organic_matter=_num(surface.get("om_r")),
        ph=_num(surface.get("ph1to1h2o_r")),
        root_zone_depth_cm=restriction if restriction is not None else deepest or None,
        slope_percent=_num(soil.get("slopegraddcp")),
        source=SOURCE,
        retrieved_at=retrieved_at.isoformat(timespec="seconds"),
    )


def _dominant_component(components: list[dict[str, Any]]) -> dict[str, Any]:
    if not components:
        raise NoData("SSURGO has no soil survey for this location")
    soils = [c for c in components if c.get("compkind") != MISC_KIND]
    if not soils:
        land = components[0]["compname"]
        raise NoData(f"SSURGO maps this location as {land.lower()}, not soil")
    return max(soils, key=lambda c: _num(c["comppct_r"]) or 0)


def fetch_soil_profile(client: httpx.Client, lat: float, lon: float) -> SoilProfile:
    components = _query(client, MAP_UNIT_QUERY.format(lat=lat, lon=lon))
    soil = _dominant_component(components)
    cokey = str(soil["cokey"])
    if not cokey.isdigit():
        raise UpstreamError(SERVICE, "unexpected component key")
    horizons = _query(client, HORIZON_QUERY.format(cokey=cokey))
    return parse_profile(components, horizons, datetime.now(UTC))
