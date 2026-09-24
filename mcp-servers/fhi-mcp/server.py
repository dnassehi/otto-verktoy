#!/usr/bin/env python3
"""FHI Statistikk Open API MCP server.

Thin, read-only wrapper around the Folkehelseinstituttet (FHI) Statistikk
Open API (https://github.com/folkehelseinstituttet/Fhi.Statistikk.OpenAPI),
base URL https://statistikk-data.fhi.no/. No authentication required - all
data published through this API is open.

Mirrors the workflow used by ssb-statistikk (search/discover -> metadata ->
data), adapted to FHI's actual endpoint shape:

    source -> table -> query (dimension/category template) -> data (POST)
                     \\-> dimension (readable labels) -> metadata (free text)

Only GET/POST requests against documented read endpoints are made - there
is no write capability in the upstream API to begin with.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://statistikk-data.fhi.no/api/open/v1"
TIMEOUT = 30

mcp = FastMCP("fhi-mcp")


def _get(path: str, params: dict | None = None) -> Any:
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: dict) -> Any:
    resp = requests.post(f"{BASE_URL}{path}", json=body, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def fhi_list_sources() -> str:
    """List all data sources published through FHI Statistikk (e.g. Folkehelsestatistikk,
    Dodsarsaksregisteret, Legemiddelregisteret). Each source has an 'id' used as
    SourceId in all other tools. Call this first."""
    return json.dumps(_get("/Common/source"), ensure_ascii=False, indent=2)


@mcp.tool()
def fhi_list_tables(source_id: str, modified_after: str | None = None) -> str:
    """List published tables for a given source_id (from fhi_list_sources).
    Each table has a 'tableId' used in all table-level tools. Optional
    modified_after (ISO date, e.g. '2025-01-01') filters to tables changed
    since that date."""
    params = {"modifiedAfter": modified_after} if modified_after else None
    return json.dumps(_get(f"/{source_id}/table", params=params), ensure_ascii=False, indent=2)


@mcp.tool()
def fhi_get_query_template(source_id: str, table_id: int) -> str:
    """Get the dimension/category template for a table: every filterable
    dimension (e.g. GEO, AAR, KJONN, MEASURE_TYPE) and every category value
    available for it. Call this BEFORE fhi_get_data to know what values are
    valid to filter on. Note: values are internal codes, not human-readable -
    use fhi_get_dimensions for readable labels of the same codes."""
    return json.dumps(_get(f"/{source_id}/Table/{table_id}/query"), ensure_ascii=False, indent=2)


@mcp.tool()
def fhi_get_dimensions(source_id: str, table_id: int) -> str:
    """Get human-readable labels for every dimension and category code in a
    table (e.g. GEO code '0301' -> 'Oslo'). Use alongside fhi_get_query_template
    to translate codes before building a fhi_get_data filter, and to translate
    codes back to labels when presenting results."""
    return json.dumps(_get(f"/{source_id}/Table/{table_id}/dimension"), ensure_ascii=False, indent=2)


@mcp.tool()
def fhi_get_metadata(source_id: str, table_id: int) -> str:
    """Get descriptive metadata for a table (free-text sections written by
    the publishing source: what the table contains, definitions, caveats)."""
    return json.dumps(_get(f"/{source_id}/Table/{table_id}/metadata"), ensure_ascii=False, indent=2)


@mcp.tool()
def fhi_get_data(source_id: str, table_id: int, dimensions_json: str, max_row_count: int = 50000) -> str:
    """Fetch actual data from a table. dimensions_json must be a JSON array
    string of {"code": "<DIM>", "filter": "item"|"top"|"all", "values": [...]}
    - one entry per dimension listed in fhi_get_query_template (all dimensions
    must be specified, including MEASURE_TYPE). filter 'item' = exact values
    listed, 'top' = last N categories (values=["N"]), 'all' = every category
    (values=["*"]) or wildcard match (e.g. values=["A*"]). Returns json-stat2
    format (same structure as SSB's json-stat2: dimension labels + a flat
    'value' array in dimension order). Always filter AAR (year) to avoid
    huge result sets, and always include GEO='0' first if only national-level
    figures are needed (avoids pulling ~400 municipality rows)."""
    dims = json.loads(dimensions_json)
    body = {"dimensions": dims, "response": {"format": "json-stat2", "maxRowCount": max_row_count}}
    return json.dumps(_post(f"/{source_id}/Table/{table_id}/data", body), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
