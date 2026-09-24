#!/usr/bin/env python3
"""Økonomi.no utvikler-API MCP server.

Provides access to Økonomi.no's free public REST API: Norwegian market
data (stock indices, currencies, crypto) and grocery price data (via
Kassal.app - product search, EAN/barcode lookup, nearby stores, price
history).

Base URL: https://www.okonomi.no/wp-json/okonomi/v1
API documentation: https://www.okonomi.no/utvikler-api/

No authentication required for the public endpoints. Please attribute
("Data fra Økonomi.no") and cache responses / avoid unnecessarily frequent
calls per the API's own usage guidance.

Data sources per the API: Norges Bank, SSB, CoinGecko, Morningstar and
Kassal.app - see each response for source attribution.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://www.okonomi.no/wp-json/okonomi/v1"
TIMEOUT = 30

mcp = FastMCP("okonomi-mcp")


def _get(path: str, params: dict | None = None) -> Any:
    resp = requests.get(f"{BASE}{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: dict) -> Any:
    resp = requests.post(f"{BASE}{path}", json=body, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def okonomi_markeder_topbar() -> str:
    """Get the ticker feed for stock indices, currencies, and crypto (same
    data as the topbar on okonomi.no's front page). Returns a flat list of
    instruments with name, current value, change (absolute and %), and
    direction (up/down)."""
    result = _get("/markeder/topbar")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def okonomi_markeder(category: str | None = None) -> str:
    """Get market data. With no category, returns all active categories
    (e.g. Indekser, Valuta, Krypto, Renter) each with their list of
    instruments. With category set (e.g. "krypto", "valuta", "indekser"),
    returns only that category's instruments in more detail."""
    if category:
        result = _get(f"/markeder/{category}")
    else:
        result = _get("/markeder")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def okonomi_dagligvarer_sok(query: str) -> str:
    """Search Norwegian grocery products by name across chains (via
    Kassal.app). Returns products with brand, vendor, EAN barcode, category,
    ingredients (when available), current price, unit price, weight, which
    store chain the price is from, and recent price history."""
    result = _get("/dagligvarer/sok", {"q": query})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def okonomi_dagligvarer_ean(ean: str) -> str:
    """Look up a grocery product by EAN/barcode. Returns all known product
    listings (across chains/vendors) matching that barcode, with prices per
    store."""
    result = _get(f"/dagligvarer/ean/{ean}")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def okonomi_dagligvarer_butikker(lat: float, lng: float, km: float = 5) -> str:
    """Find grocery stores near a geographic point. 'lat'/'lng' are
    latitude/longitude (e.g. from kartverket_search_place), 'km' is the
    search radius in kilometers (default 5). Returns store name, chain
    group, address, phone, opening hours, and coordinates."""
    result = _get("/dagligvarer/butikker", {"lat": lat, "lng": lng, "km": km})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def okonomi_dagligvarer_prishistorikk(eans: list[str], days: int = 30) -> str:
    """Get price history for up to 100 grocery products by EAN/barcode over
    the last N days (default 30). NOTE: in testing (2026-08-16) this
    endpoint returned an empty result with an underlying HTTP 422 from the
    Kassal.app backend even for a barcode with confirmed price history via
    okonomi_dagligvarer_sok - it may require upstream authentication the agent
    does not have. Try okonomi_dagligvarer_sok or okonomi_dagligvarer_ean
    instead, which both already include recent price_history inline."""
    result = _post("/dagligvarer/prishistorikk", {"eans": eans, "days": days})
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
