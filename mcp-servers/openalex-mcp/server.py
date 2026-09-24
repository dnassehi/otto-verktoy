#!/usr/bin/env python3
"""OpenAlex API MCP server.

Thin wrapper around OpenAlex, a free open catalog of ~250M scholarly works
across all fields (aggregated from Crossref, PubMed, arXiv, institutional
repositories and publishers) - broader coverage than PubMed for philosophy,
STS, computer science and other non-biomedical fields.

Base URL: https://api.openalex.org
No authentication key required. A mailto param is sent on every request to
use OpenAlex's "polite pool" (faster, more reliable rate limits) - this is
OpenAlex's own recommended practice, not a data submission to a third party.
"""
from __future__ import annotations

import os
import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://api.openalex.org"
TIMEOUT = 30
MAILTO = os.environ.get("CONTACT_EMAIL", "you@example.org")  # set CONTACT_EMAIL to your own address (OpenAlex polite pool)

mcp = FastMCP("openalex-mcp")


def _get(url: str, params: dict | None = None) -> Any:
    params = dict(params or {})
    params["mailto"] = MAILTO
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _abstract_from_inverted_index(inv_index: dict | None) -> str | None:
    if not inv_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inv_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def _simplify_work(w: dict) -> dict:
    primary_loc = w.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    return {
        "id": w.get("id"),
        "doi": w.get("doi"),
        "title": w.get("title"),
        "publication_year": w.get("publication_year"),
        "type": w.get("type"),
        "authors": [
            (a.get("author") or {}).get("display_name")
            for a in (w.get("authorships") or [])
        ],
        "source": source.get("display_name"),
        "is_oa": (w.get("open_access") or {}).get("is_oa"),
        "oa_url": (w.get("open_access") or {}).get("oa_url"),
        "cited_by_count": w.get("cited_by_count"),
        "topics": [t.get("display_name") for t in (w.get("topics") or [])[:5]],
        "abstract": _abstract_from_inverted_index(w.get("abstract_inverted_index")),
    }


@mcp.tool()
def openalex_search_works(
    query: str,
    from_year: int | None = None,
    to_year: int | None = None,
    open_access_only: bool = False,
    limit: int = 20,
) -> str:
    """Search OpenAlex for scholarly works (articles, preprints, books, ...)
    matching a keyword/title/abstract search (e.g. "TESCREAL", "AI ethics
    clinical decision support", "science and technology studies AI"). Covers
    all fields - not just biomedicine - including philosophy, STS, computer
    science and arXiv preprints, which are poorly indexed in PubMed.
    Optional from_year/to_year filter by publication year (inclusive).
    open_access_only restricts to works with a freely available full text.
    Returns simplified records (title, authors, year, source, OA link,
    citation count, topics, abstract) - use the 'id' field (OpenAlex work
    ID, e.g. "https://openalex.org/W2755950973") or 'doi' with
    openalex_get_work for full metadata."""
    filters = []
    if from_year is not None:
        filters.append(f"from_publication_date:{from_year}-01-01")
    if to_year is not None:
        filters.append(f"to_publication_date:{to_year}-12-31")
    if open_access_only:
        filters.append("is_oa:true")
    params: dict[str, Any] = {"search": query, "per_page": limit}
    if filters:
        params["filter"] = ",".join(filters)
    data = _get(f"{BASE}/works", params)
    results = [_simplify_work(w) for w in data.get("results", [])]
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def openalex_get_work(work_id: str) -> str:
    """Get full metadata for a single OpenAlex work by its OpenAlex ID
    (e.g. "W2755950973" or full URL), or by DOI (e.g.
    "10.1038/s41586-021-03819-2" or "doi.org/10.1038/..."). Returns
    simplified metadata including reconstructed abstract, authors,
    open-access link if available, and top topics."""
    ident = work_id.strip()
    if ident.lower().startswith("10."):
        url = f"{BASE}/works/doi:{ident}"
    elif "doi.org/" in ident.lower():
        doi = ident.split("doi.org/", 1)[-1]
        url = f"{BASE}/works/doi:{doi}"
    else:
        ident = ident.rsplit("/", 1)[-1]
        url = f"{BASE}/works/{ident}"
    data = _get(url)
    return json.dumps(_simplify_work(data), ensure_ascii=False, indent=2)


@mcp.tool()
def openalex_search_authors(query: str, limit: int = 20) -> str:
    """Search OpenAlex for authors by name (e.g. "Kirsti Malterud"). Returns
    author id, name, current institution/affiliation, works count and
    citation count - use the 'id' with openalex_search_works via a filter
    if you need all works by a specific author (pass
    filter=author.id:<id> manually, or ask to extend this tool)."""
    data = _get(f"{BASE}/authors", {"search": query, "per_page": limit})
    results = [
        {
            "id": a.get("id"),
            "display_name": a.get("display_name"),
            "affiliation": ((a.get("last_known_institutions") or [{}])[0] or {}).get("display_name"),
            "works_count": a.get("works_count"),
            "cited_by_count": a.get("cited_by_count"),
            "orcid": a.get("orcid"),
        }
        for a in data.get("results", [])
    ]
    return json.dumps(results, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
