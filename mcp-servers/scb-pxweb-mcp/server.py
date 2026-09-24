#!/usr/bin/env python3
"""Statistics Sweden (SCB) PxWebApi 2.0 MCP server.

Thin, read-only wrapper around https://api.scb.se/OV0104/v2beta/api/v2
(the API described publicly as "PxWebApi 2", replacing the older
PxWebApi 1 during 2026). No authentication required.

Unlike Danmarks Statistiks Statistikbank (dk-statbank-mcp), which is
POST-of-JSON to function-specific URLs, PxWebApi 2 is GET-based REST
navigation (confirmed against SCB's live OpenAPI spec at
api.scb.se/ov0104/v2beta/api/v2/swagger/v2/swagger.json on 2026-08-11 -
the "POST-based browsing" assumed at build time turned out not to match
what SCB actually exposes; only the data endpoint optionally accepts POST,
for large/complex selections):

    tables (search/browse) -> table metadata (variables + codes) -> data

- tables: GET /tables, list/search tables. Supports a free-text `query`
  filter and returns each table's hierarchical `paths` (subject/folder
  breadcrumbs) - there is no separate subjects/navigation endpoint on this
  API, browsing happens through the query filter and the paths field.
- table metadata: GET /tables/{id}/metadata, JSON-stat2 dataset shape
  with every variable's category codes/labels - call this BEFORE
  scb_get_data to know which codes are valid.
- data: GET /tables/{id}/data with a `valuecodes[<VariableCode>]=<comma
  separated codes>` query parameter per variable (e.g.
  valuecodes[Region]=00). Output format defaults to json-stat2 (same
  shape as the ssb-statistikk/dk-statistikk tools) but also supports csv,
  px, html, json-px; xlsx/parquet are binary and returned as raw bytes
  text is not meaningful for those, avoid them from this wrapper.

Default language is English ("en") unless Swedish is explicitly requested.

Limits (enforced by SCB, not just documentation): max 150,000 data cells
per single extract, and max 30 requests per 10 seconds per IP. This
wrapper enforces the second limit client-side with a simple sliding-window
throttle so a burst of calls in one turn cannot trip SCB's rate limiter.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://api.scb.se/OV0104/v2beta/api/v2"
TIMEOUT = 30

RATE_LIMIT_CALLS = 30
RATE_LIMIT_WINDOW_SEC = 10.0

mcp = FastMCP("scb-pxweb-mcp")

_call_times: deque[float] = deque()
_rate_lock = threading.Lock()


def _throttle() -> None:
    """Block just long enough to stay under 30 calls / 10 sec per IP."""
    with _rate_lock:
        now = time.monotonic()
        while _call_times and now - _call_times[0] > RATE_LIMIT_WINDOW_SEC:
            _call_times.popleft()
        if len(_call_times) >= RATE_LIMIT_CALLS:
            sleep_for = RATE_LIMIT_WINDOW_SEC - (now - _call_times[0]) + 0.05
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()
            while _call_times and now - _call_times[0] > RATE_LIMIT_WINDOW_SEC:
                _call_times.popleft()
        _call_times.append(time.monotonic())


def _get(path: str, params: dict) -> requests.Response:
    _throttle()
    resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def _valuecodes_params(valuecodes: dict[str, list[str]]) -> dict[str, str]:
    return {f"valuecodes[{var}]": ",".join(codes) for var, codes in valuecodes.items()}


@mcp.tool()
def scb_tables(
    query: str | None = None,
    lang: str = "en",
    past_days: int | None = None,
    include_discontinued: bool = False,
    page_number: int = 1,
    page_size: int = 20,
) -> str:
    """Search/browse SCB's PxWebApi 2 tables. There is no separate subject
    tree endpoint - browsing is done via free-text `query` (matches table
    titles/labels, e.g. "life expectancy", "population by region") and each
    result's `paths` field shows the subject/folder breadcrumb(s) the table
    lives under (e.g. Population > Population projections). Omit query to
    list tables page by page (large database, ~15000+ tables - always use
    query unless you specifically want to browse). past_days filters to
    tables updated within the last N days. Each result's 'id' (e.g.
    "TAB6473") is the table id used in scb_table_metadata and scb_get_data.
    lang: "en" (default) or "sv"."""
    params: dict[str, Any] = {"lang": lang, "pageNumber": page_number, "pageSize": page_size}
    if query:
        params["query"] = query
    if past_days is not None:
        params["pastDays"] = past_days
    if include_discontinued:
        params["includeDiscontinued"] = "true"
    return _get("tables", params).text


@mcp.tool()
def scb_table_metadata(table_id: str, lang: str = "en") -> str:
    """Get full metadata for a table: title, source, notes, and - most
    importantly - every variable and its valid category codes/labels
    (JSON-stat2 'dimension' object). Call this BEFORE scb_get_data to know
    which variable codes (e.g. "Region", "Kon", "ContentsCode", "Tid") and
    which value codes within each (e.g. Region "00" = whole of Sweden, Kon
    "TotSa" = both sexes) are valid for this specific table. lang: "en"
    (default) or "sv" (variable/value codes are identical either way, only
    labels change)."""
    return _get(f"tables/{table_id}/metadata", {"lang": lang}).text


@mcp.tool()
def scb_get_data(
    table_id: str,
    valuecodes_json: str,
    lang: str = "en",
    output_format: str = "json-stat2",
) -> str:
    """Fetch actual data from a table. valuecodes_json must be a JSON
    object string mapping variable code -> list of value codes, e.g.
    '{"Region": ["00"], "Forandringar": ["100"], "Kon": ["TotSa"],
    "ContentsCode": ["000007SR"], "Tid": ["2025M12","2026M05"]}' - one
    entry per variable listed in scb_table_metadata (variables you omit
    fall back to their eliminated/total category if the variable allows
    elimination - check the metadata's "extension.elimination" per
    variable; safest to specify every variable explicitly). Use "*" as a
    single value code to select every category of a variable, but avoid
    doing this on more than one or two variables at once: a single extract
    may not exceed 150,000 cells (rows x columns product across all
    variables) and will otherwise fail. output_format: "json-stat2"
    (default, same structure as the ssb-statistikk/dk-statistikk tools),
    "csv", "px", "html", or "json-px" - avoid "xlsx"/"parquet" here, they
    are binary and this wrapper returns text. lang: "en" (default) or "sv"
    for Swedish labels/CSV headers."""
    valuecodes = json.loads(valuecodes_json)
    params: dict[str, Any] = {"lang": lang, "outputFormat": output_format}
    params.update(_valuecodes_params(valuecodes))
    return _get(f"tables/{table_id}/data", params).text


@mcp.tool()
def scb_get_url(
    table_id: str,
    valuecodes_json: str,
    lang: str = "en",
    output_format: str = "json-stat2",
) -> str:
    """Build a shareable GET URL for the same query scb_get_data would run
    (useful if the user wants to open the data themselves in a browser, or
    check it against the SCB documentation/Swagger UI). Same arguments as
    scb_get_data. Does not make the request itself."""
    valuecodes = json.loads(valuecodes_json)
    params: dict[str, Any] = {"lang": lang, "outputFormat": output_format}
    params.update(_valuecodes_params(valuecodes))
    req = requests.PreparedRequest()
    req.prepare_url(f"{BASE_URL}/tables/{table_id}/data", params)
    return req.url


if __name__ == "__main__":
    mcp.run()
