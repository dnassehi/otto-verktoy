#!/usr/bin/env python3
"""Klient mot Wikipedias åpne API - dansk/engelsk motstykke til lib/snl.py
for termkorrigering (se whisper-pipeline/encyclopedia_term_correction.py).

Store norske leksikon (SML) finnes kun på norsk - det finnes ikke noe
tilsvarende åpent, dokumentert API for et dansk medisinsk oppslagsverk
(Den Store Danske/lex.dk har ingen offentlig API, sjekket 2026-09-02).
Wikipedia dekker begge språk med samme åpne, nøkkelfrie API og har god
dekning av medisinsk terminologi - brukes derfor som autoritativ kilde for
"finnes dette som et ekte oppslagsord" på samme måte som SML brukes for
norsk.

Ingen autentisering/API-nøkkel nødvendig. Dokumentasjon:
https://www.mediawiki.org/wiki/API:Main_page

To funksjoner, samme rolle som lib/snl.py sine to endepunkt:
- search(): fuzzy søk (action=opensearch) - til å bygge kandidatlister.
- verify_title(): eksakt tittel-oppslag inkl. redirect-oppløsning
  (action=query&titles=...&redirects=1) - til å VERIFISERE at et
  spesifikt kandidatord er et ekte oppslagsord, analogt med SMLs
  "headword"-sjekk i sml_term_correction.py.
"""
from __future__ import annotations

from typing import Any

import requests

DOMAINS = {
    "da": "da.wikipedia.org",
    "en": "en.wikipedia.org",
}

# Wikimedia avviser (403) forespørsler med standard python-requests
# User-Agent - krever en identifiserende UA per deres retningslinjer
# (https://meta.wikimedia.org/wiki/User-Agent_policy). Verifisert 2026-09-02.
_HEADERS = {
    "User-Agent": "MyAgent/1.0 (" + __import__("os").environ.get("CONTACT_EMAIL", "you@example.org") + ")"
}


class WikipediaError(Exception):
    """Feil ved kall mot Wikipedias API."""


def _domain(lang: str) -> str:
    try:
        return DOMAINS[lang]
    except KeyError:
        raise WikipediaError(
            f"Ukjent språk '{lang}' - gyldige verdier: {', '.join(DOMAINS)}"
        ) from None


def search(query: str, lang: str, limit: int = 5) -> list[str]:
    """Fuzzy søk (action=opensearch). Returnerer liste med artikkeltitler."""
    domain = _domain(lang)
    resp = requests.get(
        f"https://{domain}/w/api.php",
        headers=_HEADERS,
        params={
            "action": "opensearch", "search": query, "limit": limit,
            "namespace": 0, "format": "json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data[1] if len(data) > 1 else []


def normalize_case(title: str) -> str:
    """MediaWiki tvinger stor forbokstav i HELE artikkeltittelen uansett
    ordklasse (i motsetning til SML, der f.eks. "diabetes" er et vanlig
    substantiv og forblir små bokstaver i søketreff) - dette er et
    artefakt av wiki-programvaren/redirect-opprettelse, ikke en
    indikasjon på at ordet er et egennavn. Small-caser hvert ord, unntatt
    ord som er HELT store bokstaver (sannsynlig forkortelse, f.eks.
    "TSH", "COVID-19")."""
    return " ".join(
        w if w.isupper() else w[0].lower() + w[1:] if w else w
        for w in title.split(" ")
    )


def verify_title(candidate: str, lang: str) -> str | None:
    """Sjekker om `candidate` er en ekte Wikipedia-artikkeltittel (løser
    redirects, f.eks. entall/synonym -> kanonisk tittel). Returnerer den
    kanoniske tittelen hvis siden finnes, ellers None. Analogt med SMLs
    headword-sjekk i sml_term_correction.py._validated_correction()."""
    domain = _domain(lang)
    resp = requests.get(
        f"https://{domain}/w/api.php",
        headers=_HEADERS,
        params={
            "action": "query", "titles": candidate, "format": "json",
            "redirects": 1,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        if "missing" in page:
            return None
        title = page.get("title")
        if title:
            return title
    return None
