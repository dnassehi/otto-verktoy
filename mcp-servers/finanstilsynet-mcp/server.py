#!/usr/bin/env python3
"""Finanstilsynet (Norwegian Financial Supervisory Authority) MCP server.

Provides access to public financial supervision data, specifically the Short
Sale Register (SSR) which tracks public short selling positions in financial
instruments under Finanstilsynet's supervision.

Base URL: https://ssr.finanstilsynet.no/api/v2
No authentication required for public data.

The SSR provides information about:
- Publicly shorted instruments (stocks, bonds, etc.)
- Short positions reported to Finanstilsynet
- Historical shorting data (last 2 years)
- Position holders and their shareholding percentages

License: Public data from Finanstilsynet.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://ssr.finanstilsynet.no/api/v2"
TIMEOUT = 30

mcp = FastMCP("finanstilsynet-mcp")


def _get(path: str, params: dict | None = None) -> Any:
    resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def ft_get_short_sales() -> str:
    """Get all publicly shorted instruments with their shorting history.
    Returns a list of instruments (ISIN, issuer name, and events) showing
    short selling positions that have been active in the past 2 years.
    Each event includes the date, aggregated short percentage, shares shorted,
    and list of individual position holders with their shareholding details."""
    result = _get("instruments")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def ft_search_short_position(isin: str | None = None, issuer_name: str | None = None) -> str:
    """Search for short selling positions by ISIN or issuer name. 'isin' is
    the security identifier (e.g. 'NO0010400295' for Oslo Børs stocks),
    and 'issuer_name' is the company name. Returns matching instruments with
    their complete shorting history and position holder details. Note: this
    is a client-side filter of the full instruments list (no server-side
    query parameter)."""
    instruments = _get("instruments")

    filtered = instruments
    if isin:
        filtered = [i for i in filtered if i.get("isin", "").upper() == isin.upper()]
    if issuer_name:
        name_lower = issuer_name.lower()
        filtered = [i for i in filtered if name_lower in i.get("issuerName", "").lower()]

    return json.dumps(filtered, ensure_ascii=False, indent=2)


@mcp.tool()
def ft_get_short_sales_csv(separator: str = ";", locale: str = "nb-NO") -> str:
    """Export all short selling data as CSV (comma-separated values).
    Each row represents an instrument on a specific date when its short
    position changed. Contains: ISIN, issuer name, date, aggregated short %,
    and number of shares shorted. 'separator' defaults to ';' and 'locale'
    to 'nb-NO' (Norwegian format). Other locales must be valid .NET culture
    names (e.g. 'en-US', 'sv-SE')."""
    params = {"separator": separator, "locale": locale}
    resp = requests.get(f"{BASE_URL}/instruments/export-csv", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    # Return as JSON with CSV content included
    return json.dumps({"csv_content": resp.text}, ensure_ascii=False, indent=2)


@mcp.tool()
def ft_get_current_positions() -> str:
    """Get current (most recent) short selling positions and position
    holders. Filters the full history to show only the latest entries,
    useful for seeing which entities currently hold significant short
    positions in which instruments."""
    instruments = _get("instruments")

    current = []
    for instrument in instruments:
        if instrument.get("events"):
            # Get the most recent event (latest date)
            latest_event = instrument["events"][0]
            current.append({
                "isin": instrument.get("isin"),
                "issuer_name": instrument.get("issuerName"),
                "date": latest_event.get("date"),
                "short_percent": latest_event.get("shortPercent"),
                "shares": latest_event.get("shares"),
                "position_holders": latest_event.get("activePositions", [])
            })

    return json.dumps(current, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
