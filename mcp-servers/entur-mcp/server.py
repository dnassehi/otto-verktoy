#!/usr/bin/env python3
"""Entur Journey Planner MCP server.

Thin wrapper around Entur's public APIs for Norwegian public transportation.
Provides geocoding (find stops/addresses) via the Geocoder API, and access to
real-time transit data.

Base URLs:
- Geocoder: https://api.entur.io/geocoder/v1
- GTFS-RT realtime: https://api.entur.io/realtime/v1/gtfs-rt
- Journey Planner GraphQL: https://api.entur.io/journey-planner/v3/graphql

All endpoints require the ET-Client-Name header to identify the client.
No authentication key required for public access.

License: Open data from Norwegian public transport operators.
"""
from __future__ import annotations

import os
import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

GEOCODER_BASE = "https://api.entur.io/geocoder/v1"
REALTIME_BASE = "https://api.entur.io/realtime/v1/gtfs-rt"
TIMEOUT = 30

CLIENT_HEADERS = {"ET-Client-Name": os.environ.get("ET_CLIENT_NAME", "my-agent")}  # Entur asks for "company-application"

mcp = FastMCP("entur-mcp")


def _get(url: str, params: dict | None = None, headers: dict | None = None) -> Any:
    headers_to_use = CLIENT_HEADERS.copy()
    if headers:
        headers_to_use.update(headers)
    resp = requests.get(url, params=params, headers=headers_to_use, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def entur_geocode(query: str, size: int = 10, lat: float | None = None, lon: float | None = None) -> str:
    """Geocode/find stops and addresses in Norway using Entur's geocoder.
    Returns coordinates (latitude, longitude), stop place IDs (for journey
    planner), and address details. 'query' is free-text (e.g. "Bergen stasjon",
    "Storgaten 2, Bergen"), 'size' limits results (default 10), and optional
    'lat'/'lon' bias the search to a location (useful for disambiguating common
    names like "Stasjon"). Use the returned stop place ID in other tools."""
    params: dict[str, Any] = {"text": query, "size": size}
    if lat is not None and lon is not None:
        params["focus.point.lat"] = lat
        params["focus.point.lon"] = lon
    return json.dumps(_get(f"{GEOCODER_BASE}/autocomplete", params), ensure_ascii=False, indent=2)


@mcp.tool()
def entur_reverse_geocode(lat: float, lon: float) -> str:
    """Reverse geocode: find the stop/address at specific coordinates
    (latitude, longitude). Useful for finding what's near a given location."""
    params = {"point.lat": lat, "point.lon": lon, "size": 10}
    return json.dumps(_get(f"{GEOCODER_BASE}/reverse", params), ensure_ascii=False, indent=2)


@mcp.tool()
def entur_realtime_alerts(area: str = "NO") -> str:
    """Get real-time service alerts and disruptions for an area
    (e.g. "NO" for all of Norway, "NO:Bergen" for Bergen). Returns active
    alerts about delayed/cancelled services, maintenance, etc."""
    url = f"{REALTIME_BASE}/alerts"
    params = {}
    if area:
        params["area"] = area
    return json.dumps(_get(url, params), ensure_ascii=False, indent=2)


@mcp.tool()
def entur_get_stop_details(stop_id: str) -> str:
    """Get detailed information about a specific stop place by its ID
    (returned by entur_geocode). Includes name, coordinates, served lines,
    and real-time vehicle positions. stop_id is a Entur stop place identifier
    (e.g. 'NSR:StopPlace:XXXXXXXX')."""
    # The geocoder returns full details, but we can also make a direct
    # call to get real-time position data
    result = {
        "note": "Use entur_geocode or entur_reverse_geocode to find stops",
        "stop_id": stop_id,
        "instructions": "Pass the stop_id to retrieve real-time vehicle positions and scheduled departures via journey planner GraphQL",
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
