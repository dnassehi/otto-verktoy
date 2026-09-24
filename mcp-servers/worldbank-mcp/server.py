#!/usr/bin/env python3
"""World Bank Indicators API MCP server.

Thin wrapper around the World Bank's open Indicators API: ~16,000 development
indicators (population, GDP, poverty, education, health, climate, etc.) for
every country and region.

Base URL: https://api.worldbank.org/v2
No authentication key required.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://api.worldbank.org/v2"
TIMEOUT = 30

mcp = FastMCP("worldbank-mcp")


def _get(url: str, params: dict | None = None) -> Any:
    params = dict(params or {})
    params["format"] = "json"
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def worldbank_search_indicators(query: str, limit: int = 20) -> str:
    """Search World Bank indicator names for a keyword (e.g. "population",
    "life expectancy", "unemployment", "CO2"). Returns matching indicator IDs
    (e.g. "SP.POP.TOTL") to use with worldbank_get_data. Case-insensitive
    substring match. Note: searches the ~16,000-indicator catalog and may
    take a few seconds."""
    data = _get(f"{BASE}/indicator", {"per_page": 20000})
    values = data[1] if isinstance(data, list) and len(data) > 1 else []
    q = query.lower()
    matches = [
        {"id": v.get("id"), "name": v.get("name"), "sourceNote": v.get("sourceNote")}
        for v in values
        if q in (v.get("name") or "").lower()
    ]
    return json.dumps(matches[:limit], ensure_ascii=False, indent=2)


@mcp.tool()
def worldbank_get_data(country: str, indicator: str, date_range: str | None = None, limit: int = 50) -> str:
    """Fetch time-series data for a World Bank indicator and country.
    country is an ISO2/ISO3 code (e.g. "NO"/"NOR" for Norway, "all" for all
    countries) or region code. indicator is the indicator ID from
    worldbank_search_indicators (e.g. "SP.POP.TOTL" for total population).
    date_range is optional, e.g. "2015:2025" or a single year "2024"."""
    params: dict[str, Any] = {"per_page": limit}
    if date_range:
        params["date"] = date_range
    data = _get(f"{BASE}/country/{country}/indicator/{indicator}", params)
    records = data[1] if isinstance(data, list) and len(data) > 1 else data
    return json.dumps(records, ensure_ascii=False, indent=2)


@mcp.tool()
def worldbank_list_countries(query: str | None = None, limit: int = 50) -> str:
    """List World Bank country/region codes and names. Optional query filters
    by substring match on country name (case-insensitive)."""
    data = _get(f"{BASE}/country", {"per_page": 400})
    values = data[1] if isinstance(data, list) and len(data) > 1 else []
    if query:
        q = query.lower()
        values = [v for v in values if q in (v.get("name") or "").lower()]
    simplified = [
        {"id": v.get("id"), "iso2Code": v.get("iso2Code"), "name": v.get("name"), "region": (v.get("region") or {}).get("value")}
        for v in values
    ]
    return json.dumps(simplified[:limit], ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
