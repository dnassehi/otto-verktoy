#!/usr/bin/env python3
"""OpenAlex API-klient (works search) - se docs.openalex.org.

Brukes til å supplere PubMeds nøkkelordsøk og Elicits semantiske søk med
et tredje, tverrfaglig søk: OpenAlex dekker filosofi, STS (science and
technology studies), informatikk og arXiv-preprints langt bedre enn
PubMed, som er relevant for KI-etikk-/TESCREAL-materiale som ikke er
medisinsk. Samme rolle i research-monitor som lib/elicit.py.

Gratis, ingen API-nøkkel nødvendig - kun et mailto-param for "polite
pool" (raskere/mer stabil rate-limiting, OpenAlex' egen anbefalte
praksis, ikke datadeling til tredjepart). Samme underliggende API som
openalex-mcp/server.py (MCP-verktøy for interaktiv bruk i en aktiv
agent-sesjon) - denne modulen finnes fordi weekly_report.py kjøres
frittstående via cron, uten MCP-tilgang.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

BASE = "https://api.openalex.org"
MAILTO = os.environ.get("CONTACT_EMAIL", "you@example.org")
TIMEOUT = 30


class OpenAlexError(Exception):
    """Feil ved kall mot OpenAlex API."""


def _abstract_from_inverted_index(inv_index: dict | None) -> str | None:
    if not inv_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inv_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def search_works(
    query: str,
    from_date: str | None = None,
    max_results: int = 15,
) -> list[dict]:
    """Fritekstsøk (tittel/abstract) over OpenAlex' ~250M arbeider.
    from_date filtrerer på publiseringsdato (YYYY-MM-DD, inklusiv) - brukes
    til å begrense til siste N dager, samme som Elicits minEpochS. Returnerer
    samme felt-form som lib/elicit.py.search_papers og pubmed_search.py, for
    enkel sammenslåing i weekly_report.py."""
    filters = []
    if from_date:
        filters.append(f"from_publication_date:{from_date}")
    params: dict = {"search": query, "per_page": max_results, "mailto": MAILTO}
    if filters:
        params["filter"] = ",".join(filters)
    try:
        resp = requests.get(f"{BASE}/works", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise OpenAlexError(f"OpenAlex: feil ved søk: {e}") from e
    data = resp.json()
    works = []
    for w in data.get("results", []):
        primary_loc = w.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        oa = w.get("open_access") or {}
        doi = w.get("doi")
        works.append({
            "title": w.get("title") or "(uten tittel)",
            "authors": [
                (a.get("author") or {}).get("display_name")
                for a in (w.get("authorships") or [])
            ],
            "year": w.get("publication_year"),
            "abstract": _abstract_from_inverted_index(w.get("abstract_inverted_index")),
            "journal": source.get("display_name"),
            "doi": doi.replace("https://doi.org/", "") if doi else None,
            "pmid": None,
            "url": oa.get("oa_url") or w.get("id"),
            "cited_by_count": w.get("cited_by_count"),
            "source": "OpenAlex",
        })
    return works


if __name__ == "__main__":
    import json as _json

    q = " ".join(sys.argv[1:]) or "artificial intelligence in general practice"
    try:
        result = search_works(q, max_results=5)
        print(_json.dumps(result, indent=2, ensure_ascii=False))
    except OpenAlexError as e:
        print(f"Feil: {e}")
