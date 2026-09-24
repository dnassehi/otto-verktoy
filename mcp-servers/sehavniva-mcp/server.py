#!/usr/bin/env python3
"""Kartverket "Se havniva" (water level / tide) API MCP server.

Successor to the old sehavniva.no API - the standalone site now redirects
to kartverket.no/til-sjos/se-havniva, and the actual data API moved to
vannstand.kartverket.no/tideapi.php (see the June 2025 protocol revision,
"New URL"). XML-only responses, no authentication key required.

Base URL: https://vannstand.kartverket.no/tideapi.php
Full protocol spec: https://vannstand.kartverket.no/tideapi_en.html
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://vannstand.kartverket.no/tideapi.php"
TIMEOUT = 30

mcp = FastMCP("sehavniva-mcp")


def _xml_to_dict(elem: ET.Element) -> Any:
    d: dict[str, Any] = {}
    if elem.attrib:
        d["@attributes"] = dict(elem.attrib)
    children = list(elem)
    if children:
        for child in children:
            d.setdefault(child.tag, []).append(_xml_to_dict(child))
    elif elem.text and elem.text.strip():
        d["#text"] = elem.text.strip()
    return d


def _get_xml(params: dict) -> str:
    resp = requests.get(BASE, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    return json.dumps(_xml_to_dict(root), ensure_ascii=False, indent=2)


@mcp.tool()
def sehavniva_stationlist() -> str:
    """List all publicly available permanent Norwegian water level/tide
    gauge stations (name, three-letter code, latitude, longitude). Station
    codes are used with sehavniva_locationdata's underlying station model,
    but for most purposes you can just pass lat/lon directly to
    sehavniva_locationdata/sehavniva_locationlevels instead of a station
    code - the API finds the nearest relevant tidal zone automatically."""
    return _get_xml({"tide_request": "stationlist"})


@mcp.tool()
def sehavniva_locationdata(
    lat: float,
    lon: float,
    fromtime: str | None = None,
    totime: str | None = None,
    datatype: str = "all",
    refcode: str = "cd",
    interval: int = 60,
    lang: str = "en",
) -> str:
    """Get water level/tide data for a geographic position (e.g. Bergen
    58.45,5.98 or Sogne/Kristiansand 58.08,7.83) from Kartverket's tidal
    zone model. Returns observed (estimated) water level, tidal
    predictions, and forecast where available.
    fromtime/totime: 'yyyy-mm-ddTHH:MM', default previous day to now. Max
    366 days of data (1000 days if datatype='tab').
    datatype: 'obs' (observed/estimated water level), 'pre' (tidal
    predictions only), 'all' (default, obs+pre+forecast), or 'tab' (high/
    low tide table only, interval is ignored).
    refcode: 'cd' (chart datum, default), 'msl' (mean sea level), or
    'nn2000'.
    interval: 10 or 60 minutes between data points (default 60).
    lang: 'en' (default), 'nb' (bokmal) or 'nn' (nynorsk)."""
    params: dict[str, Any] = {
        "tide_request": "locationdata",
        "lat": lat,
        "lon": lon,
        "datatype": datatype,
        "refcode": refcode,
        "interval": interval,
        "lang": lang,
    }
    if fromtime:
        params["fromtime"] = fromtime
    if totime:
        params["totime"] = totime
    return _get_xml(params)


@mcp.tool()
def sehavniva_locationlevels(
    lat: float,
    lon: float,
    refcode: str = "cd",
    flag: str | None = None,
    lang: str = "en",
) -> str:
    """Get reference water levels for a geographic position: chart datum,
    NN2000, mean sea level, and - if requested via flag - astronomical
    tide levels (HAT/LAT) and statistical storm-surge return levels (e.g.
    '20-years high water', '1000-years high water'). Useful for assessing
    flood/storm-surge risk at a specific coastal point (e.g. a property).
    flag: comma-separated subset of 'obs' (observed min/max), 'astro'
    (tide-related levels), 'astroref' (HAT/MHW), 'return' (statistical
    extreme-water return levels by return period - e.g. storm surge),
    'adm' (currently unavailable). Omit for the default core reference
    levels only.
    refcode: 'cd' (chart datum, default), 'msl' (mean sea level), or
    'nn2000'.
    lang: 'en' (default), 'nb' (bokmal) or 'nn' (nynorsk)."""
    params: dict[str, Any] = {
        "tide_request": "locationlevels",
        "lat": lat,
        "lon": lon,
        "refcode": refcode,
        "lang": lang,
    }
    if flag:
        params["flag"] = flag
    return _get_xml(params)


if __name__ == "__main__":
    mcp.run()
