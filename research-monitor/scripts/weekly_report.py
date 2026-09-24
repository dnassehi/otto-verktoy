#!/usr/bin/env python3
"""
Ukentlig forskningssøk - kjøres frakoblet fra cron (natt til torsdag, kl.
03:00), ingen aktiv agent-sesjon nødvendig: søker PubMed + nyheter + Elicit
(semantisk søk, tredje kilde lagt til 2026-08-08) + OpenAlex (tverrfaglig
søk, fjerde kilde lagt til 2026-08-26) og lagrer RÅ (ufiltrerte) kandidater
til output/pending_shortlist.json.

Elicit og OpenAlex supplerer PubMed - erstatter det ikke. Elicit fanger opp
relevante artikler PubMeds nøkkelordsøk kan gå glipp av (annen
terminologi/beslektede konsepter). OpenAlex dekker fagfelt PubMed knapt
indekserer i det hele tatt - filosofi, STS, informatikk, arXiv-preprints -
relevant for KI-etikk-/TESCREAL-materiale som ikke er medisinsk. Feiler
Elicit- eller OpenAlex-kallet (manglende API-nøkkel/kvote/nede) stopper det
ALDRI resten av jobben - PubMed og nyheter er hovedkildene og skal alltid
komme gjennom.

Frem til 2026-08-02 gjorde denne skriptet selv en bred relevansfiltrering
lokalt med qwen3:8b (steg 1 av en hybrid-arkitektur) før agenten gjorde en
kritisk kvalitetsvurdering (steg 2). brukeren ba om at agenten gjør ALT selv
fremover - lokal filtrering var dessuten upraktisk sakte for interaktive
kjøringer (sekvensielle Ollama-kall per kandidat, 10-20+ min stillhet). agenten
gjør nå både den brede relevanstriagen og kvalitetsvurderingen når den
plukker opp filen (se README.md). relevance_filter.py og
quality_appraisal.py ligger fortsatt igjen som referanse/fallback.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "whisper-pipeline"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pubmed_search import search_pubmed
from news_search import search_news
from notify_telegram import send_telegram
from lib.refdb import add_article, RefDBError
from lib.elicit import search_papers as elicit_search_papers, ElicitError
from lib.openalex import search_works as openalex_search_works, OpenAlexError

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
PENDING_PATH = os.path.join(OUTPUT_DIR, "pending_shortlist.json")
DAYS = 7

# Naturlig-språk-versjon av pubmed_search.TOPIC_QUERY - Elicits semantiske
# søk vil ikke ha Lucene-boolsk syntakk som PubMed-spørringen bruker.
ELICIT_TOPIC_QUERY = (
    "Artificial intelligence, generative AI, large language models, or "
    "clinical decision support in general practice, primary care, or family "
    "medicine, especially effects on the physician-patient relationship, "
    "dehumanization of care, or clinical workflow"
)


def _search_news(days: int) -> list[dict]:
    """search_news (Perplexity) skal aldri felle hele jobben - samme mønster
    som _search_elicit. Feilet uten dette 2026-08-13 (ReadTimeout), som
    knuste hele kjøringen uten varsling og uten pending_shortlist.json."""
    try:
        return search_news(days)
    except Exception as e:
        with open(os.path.join(OUTPUT_DIR, "cron.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} Nyhetssøk (Perplexity) feilet, hoppet over: {e}\n")
        return []


def _search_elicit(days: int) -> list[dict]:
    import time

    min_epoch = int(time.time()) - days * 86400
    try:
        return elicit_search_papers(
            ELICIT_TOPIC_QUERY,
            filters={"minEpochS": min_epoch},
            max_results=15,
        )
    except ElicitError as e:
        with open(os.path.join(OUTPUT_DIR, "cron.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} Elicit-søk feilet, hoppet over: {e}\n")
        return []


def _search_openalex(days: int) -> list[dict]:
    from datetime import timedelta

    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        return openalex_search_works(ELICIT_TOPIC_QUERY, from_date=from_date, max_results=15)
    except OpenAlexError as e:
        with open(os.path.join(OUTPUT_DIR, "cron.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} OpenAlex-søk feilet, hoppet over: {e}\n")
        return []


def _save_raw_candidates(pubmed: list[dict], news: list[dict], elicit: list[dict], openalex: list[dict]) -> None:
    """Lagrer ALLE rå kandidater (også de agenten senere forkaster i triagen)
    i agentens egen referansedatabase (lib/refdb.py) - dedup på PMID/tittel,
    ingen duplikater ved gjentatt kjøring. Feil her skal aldri stoppe selve
    forskningsvarselet."""
    for item in pubmed:
        try:
            add_article(
                title=item.get("title") or "(uten tittel)",
                pmid=item.get("pmid"),
                authors=", ".join(item.get("authors") or []) or None,
                journal=item.get("journal"),
                year=item.get("date"),
                url=item.get("url"),
                abstract=item.get("abstract"),
                source="research-monitor",
            )
        except RefDBError:
            pass
    for item in elicit:
        try:
            add_article(
                title=item.get("title") or "(uten tittel)",
                doi=item.get("doi"),
                pmid=item.get("pmid"),
                authors=", ".join(item.get("authors") or []) or None,
                journal=item.get("journal"),
                year=item.get("year"),
                url=item.get("url"),
                abstract=item.get("abstract"),
                source="research-monitor-elicit",
            )
        except RefDBError:
            pass
    for item in news:
        try:
            add_article(
                title=item.get("title") or "(uten tittel)",
                url=item.get("url"),
                abstract=item.get("abstract"),
                journal=item.get("journal"),
                year=item.get("date"),
                source="research-monitor",
            )
        except RefDBError:
            pass
    for item in openalex:
        try:
            add_article(
                title=item.get("title") or "(uten tittel)",
                doi=item.get("doi"),
                pmid=item.get("pmid"),
                authors=", ".join(a for a in (item.get("authors") or []) if a) or None,
                journal=item.get("journal"),
                year=item.get("year"),
                url=item.get("url"),
                abstract=item.get("abstract"),
                source="research-monitor-openalex",
            )
        except RefDBError:
            pass


def run() -> None:
    if os.path.exists(PENDING_PATH):
        # Forrige ukes kandidater er ikke plukket opp av agenten ennå - ikke
        # overskriv dem stille. Varsle i stedet for å bytte dem ut.
        send_telegram("Ukentlig forskningssøk: forrige ukes kandidater er ikke gjennomgått ennå - hopper over denne kjøringen for å unngå å overskrive dem.")
        return

    pubmed = search_pubmed(DAYS)
    news = _search_news(DAYS)
    elicit = _search_elicit(DAYS)
    openalex = _search_openalex(DAYS)
    _save_raw_candidates(pubmed, news, elicit, openalex)

    timestamp = datetime.now(timezone.utc).isoformat()
    shortlist = {
        "generert": timestamp,
        "pubmed": pubmed,
        "nyheter": news,
        "elicit": elicit,
        "openalex": openalex,
    }

    total = len(pubmed) + len(news) + len(elicit) + len(openalex)
    if total == 0:
        send_telegram("Ukentlig forskningsvarsel: ingen treff i det hele tatt denne uken (PubMed + nyhetssøk + Elicit + OpenAlex).")
        return

    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(shortlist, f, ensure_ascii=False, indent=2)
    os.chmod(PENDING_PATH, 0o600)
    # Ingen "klar for gjennomgang"-melding sendes her - agenten gjør selv triage
    # + kvalitetsvurdering og sender ÉN samlet oppsummering når han plukker
    # opp filen.


if __name__ == "__main__":
    run()
