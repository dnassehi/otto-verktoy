#!/usr/bin/env python3
"""Helsenorge "Velg behandlingssted" MCP server.

Wraps two calls of the internal (undocumented) frontend API behind
https://tjenester.helsenorge.no/velg-behandlingssted/behandlinger, which
lists current wait times ("ventetider") per behandlingssted for every
treatment/examination in Norway's specialist health service. Discovered
2026-09-14 by inspecting the page's own network calls while interacting
with the real UI (search -> pick a treatment -> read the resulting
request), NOT by guessing REST paths - an earlier guess
(`Behandlingssteder?behandlingsId=`) looked plausible and returned data,
but turned out to silently ignore the id and always return the same
global site list regardless of treatment. The endpoint actually used by
the page itself, `VentetiderForBehandling?behandlingId=`, is the one that
truly filters by treatment (verified: different ids return different,
correctly-sized site lists).

Base URL: https://tjenester.helsenorge.no/proxy/velgbehandlingssted/api/v1
No authentication required - this is the same open call the public website
itself makes before login. Not a documented/stable public API (no Swagger,
no key) - it may change without notice.

Region default: Helse Vest (Helse Stavanger, Helse Bergen, Helse Fonna,
Helse Førde), plus Sørlandet sykehus Flekkefjord specifically (administratively
part of Helse Sør-Øst so it is not tagged "HelseVest" by the API - matched
separately by name). Adapt the region constants below to your own region.
"""
from __future__ import annotations

import json
import time
from difflib import SequenceMatcher
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://tjenester.helsenorge.no/proxy/velgbehandlingssted/api/v1"
TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OttoMCP/1.0)"}

REGION_TAG = "HelseVest"
REGION_LABEL = "Helse Vest (Helse Stavanger, Helse Bergen, Helse Fonna, Helse Førde) + Sørlandet sykehus Flekkefjord"
EXTRA_REGION_NAME_MATCH = "flekkefjord"

mcp = FastMCP("helsenorge-ventetider-mcp")

_behandlinger_cache: dict[str, Any] = {"data": None, "fetched": 0.0}
_CACHE_TTL_SECONDS = 24 * 60 * 60


def _get(path: str, params: dict | None = None) -> Any:
    resp = requests.get(f"{BASE}/{path}", params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _behandlinger_tree() -> dict:
    now = time.time()
    if _behandlinger_cache["data"] is None or now - _behandlinger_cache["fetched"] > _CACHE_TTL_SECONDS:
        _behandlinger_cache["data"] = _get("Behandlinger")
        _behandlinger_cache["fetched"] = now
    return _behandlinger_cache["data"]


def _flatten_behandlinger(tree: dict) -> list[dict]:
    rows = []
    for gruppe in tree.get("behandlingsGrupper", []):
        gnavn = gruppe.get("navn")
        for undergruppe in gruppe.get("behandlingsUnderGrupper", []):
            ugnavn = undergruppe.get("navn")
            kode = undergruppe.get("kode")
            for b in undergruppe.get("behandlinger", []):
                rows.append(
                    {
                        "behandlingsId": b.get("behandlingsId"),
                        "navn": b.get("navn"),
                        "synonym": b.get("synonym"),
                        "gruppe": gnavn,
                        "undergruppe": ugnavn,
                        "kode": kode,
                    }
                )
    return rows


def _match_score(query: str, text: str | None) -> float:
    if not text:
        return 0.0
    q = query.lower().strip()
    t = text.lower()
    if q == t:
        return 1.0
    if q in t:
        return 0.9 + 0.05 * (len(q) / max(len(t), 1))
    return SequenceMatcher(None, q, t).ratio() * 0.7


def _is_regional(site: dict) -> bool:
    if REGION_TAG in (site.get("helseRegioner") or []):
        return True
    return EXTRA_REGION_NAME_MATCH in (site.get("navn") or "").lower()


def _simplify_site(site: dict, regional: bool) -> dict:
    adr = site.get("besoksAdresse") or {}
    adresse = ", ".join(
        p for p in [adr.get("gateadresse"), f"{adr.get('postnr') or ''} {adr.get('poststed') or ''}".strip()] if p
    )
    ventetider = [
        {"type": v.get("type"), "uker": v.get("uker"), "ukerTotalt": v.get("ukerTotalt")}
        for v in site.get("ventetider") or []
    ]
    korteste = min((v["uker"] for v in ventetider if v["uker"] is not None), default=None)
    return {
        "navn": site.get("navn"),
        "enhet": site.get("enhetInterntNavn"),
        "orgnummer": site.get("orgnummer"),
        "kommune": site.get("kommune"),
        "fylke": site.get("fylke"),
        "helseRegioner": site.get("helseRegioner"),
        "regional": regional,
        "ventetider": ventetider,
        "kortesteVentetidUker": korteste,
        "antallBehandletIFjor": site.get("antall"),
        "antallAr": site.get("antallAr"),
        "kommentar": site.get("kommentar"),
        "adresse": adresse or None,
        "telefon": site.get("telefon"),
        "avtaleMedHelfo": site.get("avtaleMedHelfo"),
        "erPrivat": site.get("erPrivat"),
        "henvisningVurdering": site.get("henvisningVurdering"),
        "harVurderingskompetanse": site.get("harVurderingskompetanse"),
    }


@mcp.tool()
def helsenorge_sok_behandling(query: str, limit: int = 10) -> str:
    """Search Helsenorge's "Velg behandlingssted" treatment/examination
    taxonomy for entries matching free text (e.g. "koloskopi", "hofteprotese",
    "angst voksne"). Returns candidates ranked by match quality, each with
    'behandlingsId' (needed for helsenorge_ventetider), 'navn', 'synonym',
    'gruppe' and 'undergruppe'. Use this first to resolve a treatment name
    to a behandlingsId - names are specific (e.g. separate entries for
    "barn og unge" vs "voksne"), and the taxonomy is procedure/examination
    based rather than diagnosis based (e.g. there is no entry for "overaktiv
    blære" itself, only for the relevant investigations like cystoskopi/
    uroflowmetri), so check the top candidates and pick the clinically
    relevant one rather than assuming the first hit is right - ask the user
    if it's genuinely ambiguous."""
    rows = _flatten_behandlinger(_behandlinger_tree())
    scored = []
    for r in rows:
        score = max(
            _match_score(query, r["navn"]),
            _match_score(query, r.get("synonym")),
            _match_score(query, r.get("undergruppe")) * 0.95,
        )
        if score > 0.3:
            scored.append((score, r))
    scored.sort(key=lambda pair: -pair[0])
    top = [r for _, r in scored[:limit]]
    return json.dumps(top, ensure_ascii=False, indent=2)


@mcp.tool()
def helsenorge_ventetider(
    behandlings_id: str,
    kun_region: bool = True,
    terskel_uker: int = 10,
    vis_nasjonalt_ved_lang_ventetid: bool = True,
    maks_nasjonale_alternativer: int = 5,
) -> str:
    """Get current wait times (ventetider, in weeks) per behandlingssted for
    a given treatment/examination, identified by 'behandlingsId' (resolve
    this first with helsenorge_sok_behandling). Each site can report more
    than one wait-time 'type' (e.g. "poliklinisk utredning/behandling" vs
    "innleggelse") - all are listed per site, with 'kortesteVentetidUker'
    as the shortest of them for sorting/threshold purposes.

    Default behavior: only
    the region Helse Vest + Sørlandet sykehus Flekkefjord is returned
    ('kun_region'=true). If the shortest regional wait
    ('kortesteVentetidUker' among regional sites) exceeds 'terskel_uker'
    (default 10 weeks), or no regional site offers the treatment at all,
    the response automatically also includes the shortest-wait alternatives
    nationwide ('nasjonaleAlternativer') so a genuinely shorter option
    elsewhere in Norway isn't missed - this happens even when 'kun_region'
    is left at its default, no extra call needed. Set 'kun_region'=false to
    get every behandlingssted in Norway instead (useful if the patient is
    open to travelling regardless of the 10-week threshold)."""
    data = _get("VentetiderForBehandling", {"behandlingId": behandlings_id})
    payload = data.get("ventetiderForBehandling") or {}
    sites = payload.get("behandlingssteder") or []

    regional_raw = [s for s in sites if _is_regional(s)]
    other_raw = [s for s in sites if not _is_regional(s)]

    def _sort_key(s: dict) -> float:
        v = s["kortesteVentetidUker"]
        return v if v is not None else float("inf")

    regional = sorted((_simplify_site(s, True) for s in regional_raw), key=_sort_key)
    korteste_region = min((s["kortesteVentetidUker"] for s in regional if s["kortesteVentetidUker"] is not None), default=None)

    result: dict[str, Any] = {
        "behandlingsId": behandlings_id,
        "behandlingsnavn": payload.get("navn"),
        "antallStederTotalt": len(sites),
        "region": REGION_LABEL,
        "regionaleSteder": regional,
        "kortesteVentetidRegionUker": korteste_region,
    }

    trenger_nasjonalt_sok = vis_nasjonalt_ved_lang_ventetid and (
        korteste_region is None or korteste_region > terskel_uker
    )

    if not kun_region:
        alle = sorted(
            [_simplify_site(s, True) for s in regional_raw] + [_simplify_site(s, False) for s in other_raw],
            key=_sort_key,
        )
        result["alleSteder"] = alle
    elif trenger_nasjonalt_sok:
        nasjonale = sorted((_simplify_site(s, False) for s in other_raw), key=_sort_key)
        result["nasjonaleAlternativer"] = nasjonale[:maks_nasjonale_alternativer]
        if korteste_region is None:
            result["merknad"] = (
                "Ingen behandlingssted i regionen tilbyr denne behandlingen - "
                f"her er de {maks_nasjonale_alternativer} stedene i Norge med kortest ventetid."
            )
        else:
            result["merknad"] = (
                f"Korteste ventetid i regionen er {korteste_region} uker, over terskelen på "
                f"{terskel_uker} uker - her er de {maks_nasjonale_alternativer} stedene i Norge "
                "med kortest ventetid som alternativ."
            )

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
