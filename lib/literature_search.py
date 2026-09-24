#!/usr/bin/env python3
"""Supplerende litteratursøk: kjører PubMed (nøkkelordsøk via NCBI
E-utilities), Elicit (semantisk søk + valgfritt ClinicalTrials.gov) og
OpenAlex (tverrfaglig søk) parallelt for samme spørsmål og returnerer
resultatene samlet, hver artikkel/studie tydelig merket med kilde.

Formål: Elicits semantiske søk fanger opp relevante artikler PubMeds
nøkkelordsøk går glipp av (annen terminologi, beslektede konsepter).
OpenAlex dekker fagfelt PubMed knapt indekserer (filosofi, STS,
informatikk, arXiv-preprints) - lagt til 2026-08-26. ClinicalTrials-søket
brukes når spørsmålet gjelder pågående/nylig avsluttede kliniske studier,
ikke publisert litteratur. Dette supplerer research-monitors eksisterende
PubMed-søk (research-monitor/scripts/pubmed_search.py) - erstatter det
ikke.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(WORKSPACE / "research-monitor" / "scripts"))

from pubmed_search import _efetch, EUTILS  # noqa: E402
from lib.elicit import search_papers, search_trials, ElicitError  # noqa: E402
from lib.openalex import search_works as openalex_search_works, OpenAlexError  # noqa: E402

import requests  # noqa: E402


def search_pubmed_adhoc(query: str, max_results: int = 10) -> list[dict]:
    """Ad-hoc PubMed-søk uten tidsvindu (i motsetning til den ukentlige
    jobbens `search_pubmed()`, som alltid begrenser til siste N dager)."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
    }
    resp = requests.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=30)
    resp.raise_for_status()
    pmids = resp.json().get("esearchresult", {}).get("idlist", [])
    return _efetch(pmids)


def compare(query: str, include_trials: bool = False, max_results: int = 10) -> dict:
    """Kjører PubMed-, Elicit- og OpenAlex-søk parallelt, returnerer
    {"pubmed": [...], "elicit": [...], "openalex": [...], "trials": [...],
    "errors": [...]}."""
    with ThreadPoolExecutor(max_workers=4) as ex:
        pubmed_future = ex.submit(search_pubmed_adhoc, query, max_results)
        elicit_future = ex.submit(search_papers, query, "elicit", "semantic", None, max_results)
        openalex_future = ex.submit(openalex_search_works, query, None, max_results)
        trials_future = ex.submit(search_trials, query, "semantic", None, max_results) if include_trials else None

        result: dict = {"pubmed": [], "elicit": [], "openalex": [], "trials": [], "errors": []}
        try:
            result["pubmed"] = pubmed_future.result()
        except Exception as e:
            result["errors"].append(f"PubMed: {e}")
        try:
            result["elicit"] = elicit_future.result()
        except ElicitError as e:
            result["errors"].append(f"Elicit: {e}")
        try:
            result["openalex"] = openalex_future.result()
        except OpenAlexError as e:
            result["errors"].append(f"OpenAlex: {e}")
        if trials_future is not None:
            try:
                result["trials"] = trials_future.result()
            except ElicitError as e:
                result["errors"].append(f"Elicit ClinicalTrials: {e}")
    return result


if __name__ == "__main__":
    query = " ".join(a for a in sys.argv[1:] if a != "--trials") or "artificial intelligence in general practice"
    include_trials = "--trials" in sys.argv

    r = compare(query, include_trials=include_trials)

    print(f"=== PubMed, nøkkelordsøk ({len(r['pubmed'])} treff) ===")
    for h in r["pubmed"]:
        print(f"- [{h.get('source')}] {h['title']} ({h.get('pmid')}, {h.get('date')})")

    print(f"\n=== Elicit, semantisk søk ({len(r['elicit'])} treff) ===")
    for h in r["elicit"]:
        print(f"- [{h.get('source')}] {h['title']} ({h.get('year')}) pmid={h.get('pmid')} doi={h.get('doi')}")

    print(f"\n=== OpenAlex, tverrfaglig søk ({len(r['openalex'])} treff) ===")
    for h in r["openalex"]:
        print(f"- [{h.get('source')}] {h['title']} ({h.get('year')}) doi={h.get('doi')}")

    if include_trials:
        print(f"\n=== ClinicalTrials.gov via Elicit ({len(r['trials'])} treff) ===")
        for t in r["trials"]:
            print(f"- [{t.get('source')}] {t['title']} ({t.get('nct_id')}, {t.get('status')})")

    if r["errors"]:
        print("\nFeil underveis:")
        for err in r["errors"]:
            print(f"- {err}")
