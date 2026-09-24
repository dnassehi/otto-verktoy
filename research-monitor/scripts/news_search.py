#!/usr/bin/env python3
"""
Nyhetssøk via Perplexity API (web-søk-grounded), norsk og internasjonalt,
om KI i helsevesenet/allmennmedisin siste N dager.

Returnerer liste av {title, url, snippet, source="Nyheter"} - Perplexity
returnerer selv kilder/lenker i "citations"-feltet på svaret.

Kjent bug funnet 2026-08-02: Perplexity (sonar) leverte gjentatte ganger
artikler stemplet med feil/manglende dato som i realiteten var 1-5 måneder
gamle, trass i eksplisitt instruks om "siste N dager" i prompten (verifisert
manuelt mot 3 artikler). Fikset her med to lag: (1) "search_recency_filter"
ber Perplexitys søkelag selv begrense til tidsvinduet, ikke bare modellens
egen (upålitelige) selvrapporterte dato; (2) _within_window() dobbeltsjekker
alle datoer modellen faktisk oppgir og forkaster treff som er utenfor
vinduet. Items med "ukjent" dato kan ikke verifiseres og beholdes fortsatt -
agenten bør lese dem med et kritisk blikk til dato ved gjennomgang.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.onepassword import op_read  # noqa: E402

PPLX_URL = "https://api.perplexity.ai/chat/completions"

QUERY_TEMPLATE = """Søk etter norske og internasjonale nyhetssaker fra de siste {days} \
dagene om kunstig intelligens (KI) i helsevesenet, med særlig vekt på:
- automatisering av klinisk arbeid / endringer i legers og annet helsepersonells arbeidsflyt
- pasient-lege-relasjonen, dehumanisering av allmennmedisin/primærhelsetjenesten
- politikk, regulering eller store beslutninger om KI i helsevesenet (nasjonalt eller internasjonalt)
- generativ/agentisk KI brukt klinisk eller administrativt i helsetjenesten

Ekskluder rene produktlanseringer uten substans, generelle "KI er fremtiden"-saker \
uten konkret nyhetsverdi, og saker som bare gjentar kjent stoff fra tidligere uker.

Svar med en JSON-liste, ett objekt per sak: \
{{"tittel": "...", "url": "...", "kort_sammendrag": "1-2 setninger", "dato": "YYYY-MM-DD eller ukjent"}}. \
Maks 15 saker. Kun gyldig JSON, ingen annen tekst."""


def load_key() -> str:
    return op_read(os.environ.get("PERPLEXITY_OP_REF", "op://Agent/Perplexity API Key/credential"))


def _recency_filter(days: int) -> str:
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


def _within_window(date_str: str, days: int) -> bool:
    """True hvis datoen ikke kan tolkes (ukjent - behold), eller faller
    innenfor tidsvinduet (+1 dags slark for tidssone-avrunding)."""
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=days + 1)
    return parsed >= cutoff


def search_news(days: int = 7) -> list[dict]:
    key = load_key()
    payload = {
        "model": "sonar",
        "messages": [
            {"role": "user", "content": QUERY_TEMPLATE.format(days=days)},
        ],
        "temperature": 0.1,
        "search_recency_filter": _recency_filter(days),
    }
    resp = requests.post(
        PPLX_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]

    # Modellen kan pakke JSON i markdown-kodeblokk - trekk ut om nødvendig
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        items = json.loads(content)
    except json.JSONDecodeError:
        return []

    results = []
    for item in items:
        date = item.get("dato", "ukjent")
        if not _within_window(date, days):
            continue
        results.append({
            "title": item.get("tittel", "(uten tittel)"),
            "url": item.get("url", ""),
            "abstract": item.get("kort_sammendrag", ""),
            "journal": "Nyhet",
            "date": date,
            "authors": [],
            "source": "Nyhetssøk",
            "pmid": None,
        })
    return results


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    hits = search_news(days)
    print(f"Fant {len(hits)} nyhetssaker siste {days} dager.")
    for h in hits:
        print(f"- {h['title']} ({h['url']})")
