#!/usr/bin/env python3
"""Elicit API-klient (search/papers, search/trials) - se docs.elicit.com.

Brukes til å supplere PubMeds nøkkelordsøk med semantisk søk (finner
relevante artikler selv når terminologien ikke matcher eksakt) og til å
koble mot ClinicalTrials.gov for pågående/nylig avsluttede kliniske
studier.

Bevisst KUN Search-endepunktene (papers/trials) - ikke Reports eller
Systematic Review. De sistnevnte er asynkrone, tunge (5-15 min) operasjoner
ment for helt andre oppgaver og bruker mer av kvoten enn nødvendig for et
ukentlig litteraturvarsel (valgfri kilde).

Valgt REST API direkte fremfor Elicits offisielle MCP-server
(https://elicit.com/api/mcp): den MCP-serveren bruker OAuth 2.0
(nettleser-innlogging), som ikke passer en ubetjent ukentlig cron-jobb -
samme begrensning som ble avdekket for Scite. Den rå API-en trenger bare en
statisk Bearer-nøkkel, som også er det Elicits egne offisielle eksempler
(github.com/elicit/api-examples) bruker som standardoppsett.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from lib.onepassword import op_read, OnePasswordError  # noqa: E402

API_BASE = "https://elicit.com/api/v2"
API_KEY_REF = os.environ.get("ELICIT_OP_REF", "op://Agent/Elicit API Key/credential")


class ElicitError(Exception):
    """Feil ved kall mot Elicit API (auth, kvote, ratelimit, ugyldig forespørsel)."""


def _api_key() -> str:
    try:
        return op_read(API_KEY_REF)
    except OnePasswordError as e:
        raise ElicitError(
            "Fant ikke Elicit API-nøkkel i 1Password "
            f"({API_KEY_REF}). Generer én på https://elicit.com/settings "
            "(krever Pro-plan eller høyere) og lagre den i et 1Password-item "
            "kalt 'Elicit API Key' med nøkkelen i feltet 'credential'."
        ) from e


def _post(path: str, payload: dict) -> dict:
    key = _api_key()
    resp = requests.post(
        f"{API_BASE}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code == 401:
        raise ElicitError("Elicit: ugyldig eller utløpt API-nøkkel.")
    if resp.status_code == 402:
        raise ElicitError("Elicit: kvote brukt opp.")
    if resp.status_code == 403:
        raise ElicitError("Elicit: API-tilgang krever Pro-plan eller høyere på kontoen.")
    if resp.status_code == 429:
        raise ElicitError("Elicit: rate limit nådd (100 forespørsler/min per IP), prøv igjen om litt.")
    if resp.status_code >= 400:
        raise ElicitError(f"Elicit: feil ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def search_papers(
    query: str,
    corpus: str = "elicit",
    search_mode: str = "semantic",
    filters: dict | None = None,
    max_results: int = 10,
) -> list[dict]:
    """Semantisk (eller nøkkelord-) søk over Elicits 138M+ artikkelindeks,
    evt. begrenset til PubMed-korpuset (corpus='pubmed'). Standard corpus
    'elicit' er det som faktisk supplerer PubMeds nøkkelordsøk - fanger opp
    beslektede artikler uavhengig av eksakt terminologi."""
    payload: dict = {
        "query": query,
        "corpus": corpus,
        "searchMode": search_mode,
        "maxResults": max_results,
    }
    if filters:
        payload["filters"] = filters
    data = _post("/search/papers", payload)
    source_label = "Elicit-PubMed" if corpus == "pubmed" else "Elicit-semantisk"
    papers = []
    for p in data.get("papers", []):
        papers.append({
            "title": p.get("title") or "(uten tittel)",
            "authors": p.get("authors") or [],
            "year": p.get("year"),
            "abstract": p.get("abstract"),
            "journal": p.get("venue"),
            "doi": p.get("doi"),
            "pmid": p.get("pmid"),
            "url": (p.get("urls") or [None])[0],
            "cited_by_count": p.get("citedByCount"),
            "source": source_label,
        })
    return papers


def search_trials(
    query: str,
    search_mode: str = "semantic",
    trial_filters: dict | None = None,
    max_results: int = 10,
) -> list[dict]:
    """Søk i ClinicalTrials.gov via Elicit - for pågående/nylig avsluttede
    kliniske studier, ikke publisert litteratur."""
    payload: dict = {"query": query, "searchMode": search_mode, "maxResults": max_results}
    if trial_filters:
        payload["trialFilters"] = trial_filters
    data = _post("/search/trials", payload)
    trials = []
    for t in data.get("trials", []):
        trials.append({
            "title": t.get("title") or "(uten tittel)",
            "nct_id": t.get("nctId"),
            "status": t.get("overallStatus"),
            "phase": t.get("phase") or [],
            "conditions": t.get("conditions") or [],
            "interventions": t.get("interventions") or [],
            "sponsor": t.get("leadSponsor"),
            "summary": t.get("summary"),
            "url": t.get("url"),
            "source": "Elicit-ClinicalTrials",
        })
    return trials


if __name__ == "__main__":
    import json as _json

    q = " ".join(sys.argv[1:]) or "artificial intelligence in general practice"
    try:
        result = search_papers(q, max_results=5)
        print(_json.dumps(result, indent=2, ensure_ascii=False))
    except ElicitError as e:
        print(f"Feil: {e}")
