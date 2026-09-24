#!/usr/bin/env python3
"""WHO Global Health Observatory (GHO) OData API MCP server.

Thin wrapper around WHO's public GHO OData API, which exposes ~2000 health
indicators (life expectancy, disease incidence, nutrition, health-system
capacity, etc.) per country and year.

Base URL: https://ghoapi.azureedge.net/api
No authentication key required.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://ghoapi.azureedge.net/api"
TIMEOUT = 30

mcp = FastMCP("who-mcp")


def _get(url: str, params: dict | None = None) -> Any:
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def who_search_indicators(query: str, limit: int = 20) -> str:
    """Search WHO GHO indicator names for a keyword (e.g. "life expectancy",
    "diabetes", "maternal mortality"). Returns matching IndicatorCode values
    to use with who_get_data. Case-insensitive substring match on the
    indicator name."""
    data = _get(f"{BASE}/Indicator")
    values = data.get("value", [])
    q = query.lower()
    matches = [v for v in values if q in (v.get("IndicatorName") or "").lower()]
    return json.dumps(matches[:limit], ensure_ascii=False, indent=2)


@mcp.tool()
def who_get_data(indicator_code: str, country_code: str | None = None, year: int | None = None, limit: int = 50) -> str:
    """Fetch data for a WHO GHO indicator (use who_search_indicators to find
    the code, e.g. "WHOSIS_000001" for life expectancy at birth).
    country_code is an optional ISO3 code (e.g. "NOR", "DNK") to filter to one
    country. year is an optional 4-digit year to filter to one time period.
    Returns raw OData records including SpatialDim (country), TimeDim (year),
    and NumericValue."""
    filters = []
    if country_code:
        filters.append(f"SpatialDim eq '{country_code.upper()}'")
    if year:
        filters.append(f"TimeDim eq {year}")
    params: dict[str, Any] = {"$top": limit}
    if filters:
        params["$filter"] = " and ".join(filters)
    data = _get(f"{BASE}/{indicator_code}", params)
    return json.dumps(data.get("value", data), ensure_ascii=False, indent=2)


@mcp.tool()
def who_list_dimension_values(dimension: str = "COUNTRY", limit: int = 300) -> str:
    """List valid values for a WHO GHO dimension, most commonly "COUNTRY"
    (returns ISO3 codes and names) or "REGION". Useful for finding the right
    country_code to pass to who_get_data."""
    data = _get(f"{BASE}/DIMENSION/{dimension}/DimensionValues")
    return json.dumps(data.get("value", data)[:limit], ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
