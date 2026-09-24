#!/usr/bin/env python3
"""MET Norway (Norwegian Meteorological Institute) weather API MCP server.

Thin wrapper around api.met.no, the same data source behind Yr. Covers
land weather forecasts, ocean/wave forecasts for Northwestern Europe, and
official weather/marine alerts.

Base URL: https://api.met.no/weatherapi
No authentication key required, but a unique identifying User-Agent header
is mandatory (generic/missing User-Agents get a 403).
"""
from __future__ import annotations

import os
import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://api.met.no/weatherapi"
TIMEOUT = 30
HEADERS = {"User-Agent": f"my-agent/1.0 (contact: {os.environ.get('CONTACT_EMAIL', 'you@example.org')})"}  # MET requires an identifying User-Agent; set CONTACT_EMAIL

mcp = FastMCP("met-mcp")


def _get(url: str, params: dict | None = None) -> Any:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def met_locationforecast(lat: float, lon: float, altitude: int | None = None) -> str:
    """Get a weather forecast (temperature, wind, precipitation, cloud cover,
    humidity) for the next 9 days at a given coordinate, anywhere on earth
    (most accurate for the Nordic region). altitude is the ground height in
    meters above sea level (optional but improves temperature accuracy in
    hilly terrain)."""
    params: dict[str, Any] = {"lat": lat, "lon": lon}
    if altitude is not None:
        params["altitude"] = altitude
    data = _get(f"{BASE}/locationforecast/2.0/compact", params)
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def met_oceanforecast(lat: float, lon: float) -> str:
    """Get wave and sea forecast (wave height/direction/period, sea
    temperature, currents) for a point at sea in Northwestern Europe.
    Coordinates on land near the coast are automatically snapped to the
    nearest ocean point. Returns 422 for locations outside the model's
    coverage area (far from Northwestern Europe)."""
    data = _get(f"{BASE}/oceanforecast/2.0/complete", {"lat": lat, "lon": lon})
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def met_alerts(lat: float | None = None, lon: float | None = None, county: str | None = None,
               geographic_domain: str | None = None, include_inactive: bool = False, lang: str = "no") -> str:
    """Get official Norwegian weather/marine warnings (storm, wind, rain,
    snow, ice, etc.) from MET Norway, in CAP-derived GeoJSON.
    Filter by lat/lon (returns alerts covering that exact point - most
    precise for a specific property/location), or by county (2-digit
    Norwegian fylke number, e.g. "42" for Agder, "11" for Rogaland), and/or
    geographic_domain ("land" or "marine"). include_inactive=True also
    returns alerts issued in the last 30 days that have since expired.
    Alert levels are Yellow (less severe), Orange (severe), Red (extreme)."""
    method = "all" if include_inactive else "current"
    params: dict[str, Any] = {"lang": lang}
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon
    if county:
        params["county"] = county
    if geographic_domain:
        params["geographicDomain"] = geographic_domain
    data = _get(f"{BASE}/metalerts/2.0/{method}.json", params)
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def met_nowcast(lat: float, lon: float) -> str:
    """Get an immediate/short-term precipitation forecast (updated every 5
    minutes) for a location in the Nordic area. More precise than
    locationforecast for the next couple of hours, but only covers a
    limited geographic area."""
    data = _get(f"{BASE}/nowcast/2.0/complete", {"lat": lat, "lon": lon})
    return json.dumps(data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
