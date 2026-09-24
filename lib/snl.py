#!/usr/bin/env python3
"""Klient for Store norske leksikons åpne API (SNL, SML, NBL).

Dekker tre verk, publisert av Store norske leksikon, på hvert sitt
underdomene:
- "snl"  Store norske leksikon (generelt oppslagsverk)      snl.no
- "sml"  Store medisinske leksikon (medisin)                 sml.snl.no
- "nbl"  Norsk biografisk leksikon (biografier)               nbl.snl.no

Ingen autentisering/API-nøkkel nødvendig - åpent API. Dokumentasjon:
https://meta.snl.no/API-dokumentasjon (verifisert 2026-09-02).

To endepunkt:
- Søk: GET https://{subdomene}.snl.no/api/v1/search?query=...&limit=&offset=
  Returnerer en liste med treff (headword, snippet, article_url_json,
  license, first_image_url, first_two_sentences, m.fl.).
- Enkeltartikkel: GET https://{subdomene}.snl.no/{permalink}.json
  Returnerer full artikkeltekst + metadata + lisens.

Lisens oppgis per artikkel/bilde i svaret ("fri" eller "begrenset") - siter
alltid kilde-URL og sjekk lisensfeltet før gjenbruk av tekst/bilder utenfor
sitat.
"""
from __future__ import annotations

from typing import Any

import requests

SUBDOMAINS = {
    "snl": "snl.no",
    "sml": "sml.snl.no",
    "nbl": "nbl.snl.no",
}


class SNLError(Exception):
    """Feil ved kall mot Store norske leksikons API."""


def _subdomain(verk: str) -> str:
    try:
        return SUBDOMAINS[verk]
    except KeyError:
        raise SNLError(
            f"Ukjent verk '{verk}' - gyldige verdier: {', '.join(SUBDOMAINS)}"
        ) from None


def search(query: str, verk: str = "sml", limit: int = 3, offset: int = 0) -> list[dict[str, Any]]:
    """Søk i ett av verkene. limit: 1-10 (API-standard 3), offset for paginering."""
    domain = _subdomain(verk)
    resp = requests.get(
        f"https://{domain}/api/v1/search",
        params={"query": query, "limit": limit, "offset": offset},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_article(permalink: str, verk: str = "sml") -> dict[str, Any]:
    """Hent full artikkel (tekst + metadata + lisens) ved permalink (fra
    søketreff sitt "permalink"-felt, eller artikkelens URL-slug)."""
    domain = _subdomain(verk)
    resp = requests.get(f"https://{domain}/{permalink}.json", timeout=15)
    if resp.status_code == 404:
        raise SNLError(f"Fant ingen artikkel '{permalink}' i {verk}")
    resp.raise_for_status()
    return resp.json()
