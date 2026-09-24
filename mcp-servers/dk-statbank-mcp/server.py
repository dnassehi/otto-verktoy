#!/usr/bin/env python3
"""Danmarks Statistik (Statistikbanken) API MCP server.

Thin, read-only wrapper around the Statistics Denmark API
(https://www.dst.dk/en/Statistik/brug-statistikken/muligheder-i-statistikbanken/api),
base URL https://api.statbank.dk/v1. No authentication required for the four
functions below (only the CATALOGUE function needs an API key, and is not
implemented here since it isn't needed for normal table lookups).

Mirrors the workflow used by ssb-statistikk/fhi-statistikk (discover ->
metadata -> data), adapted to Statbank's actual endpoint shape - unlike SSB's
REST-URL navigation, every Statbank function is a POST of a JSON body to its
own URL:

    subjects -> tables -> tableinfo -> data

- subjects: browse/search the subject hierarchy tables live under
- tables: list tables filtered by subject and/or update date
- tableinfo: get a table's variables and their valid codes (needed before
  querying data)
- data: fetch actual values for chosen variables/codes, in CSV or
  JSON-stat2 format

Default language is English ("en") unless Danish is explicitly requested,
since output normally feeds into English-language research/viz work.

Limit: a single data extract may not exceed 1,000,000 cells (rows x
columns). Not relevant for most single-table lookups, but a query that
requests too many variable/value combinations at once will fail with an
EXTRACT-TOOBIG error - narrow the filter (e.g. pick specific years/regions)
instead of using "*" everywhere.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://api.statbank.dk/v1"
TIMEOUT = 30

mcp = FastMCP("dk-statbank-mcp")


def _post(path: str, body: dict) -> Any:
    resp = requests.post(f"{BASE_URL}/{path}", json=body, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def dkstat_subjects(subjects_json: str = "[]", lang: str = "en", recursive: bool = False) -> str:
    """Browse the Statbank subject hierarchy that tables are organised under.
    Call with subjects_json="[]" (default) to list the 10 top-level subjects
    (People, Labour and income, Economy, Social conditions, Education and
    research, Business, Transport, Culture and leisure, Environment and
    energy, About Statistics Denmark). Pass subjects_json as a JSON array of
    subject ids (e.g. '["3412"]') to drill into a specific branch; set
    recursive=true to expand the whole subtree in one call instead of
    walking it level by level. Each node's 'id' is used as a subject filter
    in dkstat_tables. lang: "en" (default) or "da"."""
    subjects = json.loads(subjects_json)
    body: dict[str, Any] = {"lang": lang}
    if subjects:
        body["subjects"] = subjects
    if recursive:
        body["recursive"] = True
    return json.dumps(_post("subjects", body), ensure_ascii=False, indent=2)


@mcp.tool()
def dkstat_tables(subjects_json: str | None = None, past_days: int | None = None, lang: str = "en") -> str:
    """List Statbank tables, optionally filtered by subject id(s) (from
    dkstat_subjects) and/or how recently they were updated. subjects_json is
    a JSON array of subject ids (e.g. '["3412"]' for People > Health); omit
    or pass "[]" to list across all subjects (large result). past_days
    limits to tables updated within the last N days. Each result's 'id'
    field (e.g. "SBR01") is the table id used in dkstat_table_info and
    dkstat_data. lang: "en" (default) or "da"."""
    body: dict[str, Any] = {"lang": lang}
    if subjects_json:
        subjects = json.loads(subjects_json)
        if subjects:
            body["subjects"] = subjects
    if past_days is not None:
        body["pastDays"] = past_days
    return json.dumps(_post("tables", body), ensure_ascii=False, indent=2)


@mcp.tool()
def dkstat_table_info(table: str, lang: str = "en") -> str:
    """Get metadata for a table: description, unit, contacts, documentation
    link, footnotes, and - most importantly - every variable and its valid
    codes/labels. Call this BEFORE dkstat_data to know what 'code' and
    'values' to pass for each variable (e.g. table SBR01 has variables
    KOMMUNEDK/municipality, hospital stays, age, sex, Tid/time - each with
    an id like "000" for "All Denmark" or "TOT" for age total). lang: "en"
    (default) or "da" (variable ids stay the same either way, only labels
    change)."""
    return json.dumps(_post("tableinfo", {"table": table, "lang": lang}), ensure_ascii=False, indent=2)


@mcp.tool()
def dkstat_data(table: str, variables_json: str, response_format: str = "JSONSTAT", lang: str = "en") -> str:
    """Fetch actual data from a table. variables_json must be a JSON array
    string of {"code": "<VARIABLE_ID>", "values": [...]}  - one entry per
    variable listed in dkstat_table_info (variables not listed default to
    their "eliminated"/total category if the variable allows elimination,
    but it's safer to specify every variable explicitly). Each "values"
    entry is a list of variable-code ids (e.g. ["000"] for a single value,
    ["2020","2021","2022"] for specific years, ["*"] for every category -
    but avoid "*" on more than one or two variables at once, since a single
    extract may not exceed 1,000,000 cells; narrow with specific ids
    instead). response_format: "JSONSTAT" (default, json-stat2 - same
    structure as the SSB/FHI tools use) or "CSV". lang: "en" (default) or
    "da" for Danish labels/CSV headers."""
    variables = json.loads(variables_json)
    body = {"table": table, "format": response_format, "lang": lang, "variables": variables}
    result = _post("data", body)
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
