#!/usr/bin/env python3
"""Kartverket (Norwegian Mapping Authority) MCP server.

Provides access to Kartverket's public place name and geocoding API
(Stedsnavn-API). Allows looking up Norwegian place names, their geographic
coordinates, and administrative context.

Base URL: https://ws.geonorge.no/stedsnavn/v1
API documentation: https://ws.geonorge.no/stedsnavn/v1/

No authentication required for public access.

License: Kartverket public data / CC0.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

STEDSNAVN_BASE = "https://ws.geonorge.no/stedsnavn/v1"
TIMEOUT = 30

mcp = FastMCP("kartverket-mcp")


def _get(url: str, params: dict | None = None) -> Any:
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def kartverket_search_place(query: str, limit: int = 10, fuzzy: bool = False) -> str:
    """Search for Norwegian place names (cities, municipalities, geographic
    features, landmarks). Returns places with their names, type (By/Tettstad/Elv/
    Fjell/etc.), coordinates (nord/øst = latitude/longitude), municipalities,
    counties, and status. 'query' is free-text (e.g. "Bergen", "Bergen*" for
    wildcard, "Vøringsfossen"), 'limit' constrains results (max 500, default 10),
    and 'fuzzy=true' enables fuzzy matching (slower, typo-tolerant)."""
    params: dict[str, Any] = {"sok": query, "limit": limit}
    if fuzzy:
        params["fuzzy"] = "true"
    result = _get(f"{STEDSNAVN_BASE}/navn", params)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def kartverket_place_types() -> str:
    """Get a list of all available place types (navneobjekttyper) in the
    Stedsnavn register. Types include By (city), Tettstad (town), Elv (river),
    Fjell (mountain), Innsjø (lake), Kirke (church), etc. Useful for filtering
    searches or understanding the categorization."""
    result = _get(f"{STEDSNAVN_BASE}/navneobjekttyper")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def kartverket_languages() -> str:
    """Get a list of all languages available in the Stedsnavn register
    (e.g. Norsk, Sámi, etc.). Place names may have versions in multiple
    languages; this shows which are supported."""
    result = _get(f"{STEDSNAVN_BASE}/sprak")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def kartverket_search_by_name(name: str, page: int = 1, results_per_page: int = 10) -> str:
    """Search for places with pagination support. Returns results grouped by
    place type/category (counties before municipalities, etc.), then sorted
    by relevance to the search term. 'name' is the search query, 'page' is
    the page number (1-indexed), and 'results_per_page' is the limit per
    page (1-500, default 10)."""
    params: dict[str, Any] = {"sok": name, "side": page, "treffPerSide": results_per_page}
    result = _get(f"{STEDSNAVN_BASE}/sted", params)
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
