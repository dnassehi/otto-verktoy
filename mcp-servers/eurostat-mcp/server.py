#!/usr/bin/env python3
"""Eurostat dissemination API MCP server.

Thin wrapper around Eurostat's public statistics APIs:

- Table of contents (catalogue): browse/search all ~7000 dataset codes and
  titles.
- Statistics API (JSON-stat 2.0): fetch actual data for a dataset, filtered
  by dimension codes (geo, time, sex, age, ...).

Base URLs:
- https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt
- https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{code}

No authentication key required.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

TOC_URL = "https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt"
DATA_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
TIMEOUT = 30

mcp = FastMCP("eurostat-mcp")


def _get(url: str, params: dict | None = None) -> requests.Response:
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


@mcp.tool()
def eurostat_search_datasets(query: str, lang: str = "en", limit: int = 30) -> str:
    """Search the Eurostat table of contents for dataset titles matching a
    keyword (e.g. "life expectancy", "unemployment", "renewable energy").
    Case-insensitive substring match on the title. Returns rows with
    title/code/type/last update/data start-end/number of values. Only rows
    of type "dataset" or "table" (not "folder") are directly queryable with
    eurostat_dataset_info/eurostat_get_data - use the 'code' field as
    dataset_code. lang: "en" (default), "fr" or "de"."""
    resp = _get(TOC_URL, {"lang": lang})
    reader = csv.reader(io.StringIO(resp.text), delimiter="\t", quotechar='"')
    rows = list(reader)
    header = rows[0]
    q = query.lower()
    matches = []
    for row in rows[1:]:
        if len(row) < 3:
            continue
        title = row[0].strip()
        row_type = row[2].strip()
        if q in title.lower() and row_type in ("dataset", "table"):
            matches.append(dict(zip(header, row)))
        if len(matches) >= limit:
            break
    return json.dumps(matches, ensure_ascii=False, indent=2)


@mcp.tool()
def eurostat_dataset_info(dataset_code: str, lang: str = "en") -> str:
    """Get the dimension structure of an Eurostat dataset: every dimension
    (freq, unit, geo, sex, age, ...) and how many/which category codes exist
    for it, using the most recent time period as a representative sample
    (via lastTimePeriod=1) so the call stays small. Call this BEFORE
    eurostat_get_data to know which dimension codes are valid, e.g. which
    'geo' codes (country codes like "NO", "DK", "EU27_2020") or 'sex'/'age'
    codes the dataset actually uses. dataset_code is the code from
    eurostat_search_datasets (e.g. "DEMO_PJAN"), case-insensitive."""
    data = _get(
        f"{DATA_URL}/{dataset_code}",
        {"format": "JSON", "lang": lang, "lastTimePeriod": 1},
    ).json()
    dims = data.get("dimension", {})
    summary = {}
    for dim_id, dim in dims.items():
        categories = dim.get("category", {}).get("label", {})
        summary[dim_id] = {
            "label": dim.get("label"),
            "n_categories": len(categories),
            "categories": categories,
        }
    return json.dumps(
        {"label": data.get("label"), "updated": data.get("updated"), "dimensions": summary},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def eurostat_get_data(dataset_code: str, filters_json: str = "{}", lang: str = "en") -> str:
    """Fetch actual data from an Eurostat dataset in JSON-stat 2.0 format.
    filters_json is a JSON object string mapping dimension id to one or more
    codes, e.g. '{"geo": ["NO", "DK", "SE"], "sex": ["T"], "age": ["TOTAL"],
    "time": ["2022", "2023"]}' (use eurostat_dataset_info first to find
    valid dimension ids and codes). Omitting a dimension includes all its
    values, which can make the response very large - always filter 'geo'
    and 'time' at minimum for large datasets. dataset_code is case
    insensitive. lang: "en" (default), "fr" or "de"."""
    filters = json.loads(filters_json)
    params: dict[str, Any] = {"format": "JSON", "lang": lang}
    for dim_id, values in filters.items():
        if isinstance(values, list):
            params[dim_id] = values
        else:
            params[dim_id] = [values]
    data = _get(f"{DATA_URL}/{dataset_code}", params).json()
    return json.dumps(data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
