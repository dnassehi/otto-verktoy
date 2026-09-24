#!/usr/bin/env python3
"""Lovdata MCP server.

Lokalt oppslags-/søkeverktøy for norske lover og sentrale forskrifter,
bygget fra Lovdatas gratis offentlige datasett (api.lovdata.no, NLOD 2.0,
ingen konto/API-nøkkel krevd). Databasen (lovdata.db) bygges av
fetch_and_build_db.py og oppdateres periodisk via cron.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(__file__).parent / "lovdata.db"

mcp = FastMCP("lovdata-mcp")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _fts_query(q: str) -> str | None:
    tokens = re.findall(r"\w+", q, re.UNICODE)
    if not tokens:
        return None
    return " AND ".join(f'"{t}"' for t in tokens)


def _norm(s: str) -> str:
    return re.sub(r"[\s§]+", "", s or "").lower()


@mcp.tool()
def lovdata_search(query: str, doc_type: str | None = None, limit: int = 10) -> str:
    """Fulltekstsøk i norske lover og sentrale forskrifter (gjeldende versjon).
    query er søkeord (norsk), f.eks. "midlertidig ansettelse" eller
    "taushetsplikt helsepersonell". doc_type kan begrenses til "lov" eller
    "forskrift" (utelat for begge). Returnerer lovtittel, paragraf,
    paragraftittel, et tekstutdrag og direkte lenke til lovdata.no for hver
    treff, sortert etter relevans. Bruk lovdata_get_paragraph etterpå for å
    hente hele paragrafteksten."""
    match = _fts_query(query)
    if not match:
        return json.dumps({"error": "Tomt søk"}, ensure_ascii=False)
    conn = _conn()
    sql = """
        SELECT d.tittel, d.korttittel, d.doc_type, p.paragraf, p.paragraf_tittel,
               p.kapittel_tittel, p.text, p.url
        FROM paragrafer_fts f
        JOIN paragrafer p ON p.id = f.rowid
        JOIN dokumenter d ON d.id = p.dokument_id
        WHERE paragrafer_fts MATCH ?
    """
    params: list[Any] = [match]
    if doc_type in ("lov", "forskrift"):
        sql += " AND d.doc_type = ?"
        params.append(doc_type)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    results = []
    for r in rows:
        snippet = r["text"]
        if len(snippet) > 400:
            snippet = snippet[:400].rsplit(" ", 1)[0] + " …"
        results.append({
            "tittel": r["tittel"],
            "korttittel": r["korttittel"],
            "type": r["doc_type"],
            "paragraf": r["paragraf"],
            "paragraf_tittel": r["paragraf_tittel"],
            "kapittel": r["kapittel_tittel"],
            "utdrag": snippet,
            "url": r["url"],
        })
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def lovdata_find_document(query: str, doc_type: str | None = None, limit: int = 10) -> str:
    """Søk etter en lov eller forskrift ved navn (f.eks. "arbeidsmiljøloven",
    "helsepersonelloven", "journalforskriften", "pasient- og
    brukerrettighetsloven"). Bruk denne først for å finne riktig offisiell
    tittel/korttittel før du kaller lovdata_get_paragraph, siden folk ofte
    bruker uformelle navn. doc_type kan begrenses til "lov" eller
    "forskrift". Returnerer tittel, korttittel, dato for ikrafttredelse og
    sist endret."""
    conn = _conn()
    like = f"%{query}%"
    sql = """
        SELECT DISTINCT tittel, korttittel, doc_type, subtype, legacy_id,
               ref_id, dato_ikraft, sist_endret
        FROM dokumenter
        WHERE (tittel LIKE ? OR korttittel LIKE ?)
    """
    params: list[Any] = [like, like]
    if doc_type in ("lov", "forskrift"):
        sql += " AND doc_type = ?"
        params.append(doc_type)
    sql += " LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    results = [dict(r) for r in rows]
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def lovdata_get_paragraph(lov: str, paragraf: str) -> str:
    """Hent den fullstendige, ordrette teksten til én bestemt paragraf i en
    navngitt lov eller forskrift. lov matches mot offisiell tittel eller
    korttittel (delvis, case-insensitive) — bruk gjerne lovdata_find_document
    først hvis du er usikker på riktig navn. paragraf er paragrafnummeret,
    f.eks. "14-9", "§ 14-9", "21" eller "4-1" — bindestrek/mellomrom/§ spiller
    ingen rolle. Returnerer full paragraftekst inkludert alle ledd/bokstaver,
    kapitteltilhørighet og lenke til lovdata.no. Hvis flere lover/forskrifter
    matcher lov-navnet, returneres en liste over kandidater i stedet."""
    conn = _conn()
    like = f"%{lov}%"
    docs = conn.execute(
        "SELECT id, tittel, korttittel, doc_type FROM dokumenter WHERE tittel LIKE ? OR korttittel LIKE ? LIMIT 20",
        (like, like),
    ).fetchall()
    if not docs:
        conn.close()
        return json.dumps({"error": f"Fant ingen lov/forskrift som matcher '{lov}'"}, ensure_ascii=False)
    if len(docs) > 1:
        # Prøv å innsnevre: eksakt treff på korttittelens navnedel (før evt. "– kortform")
        target_norm = _norm(lov)
        exact = [d for d in docs if _norm((d["korttittel"] or "").split("–")[0]) == target_norm]
        if len(exact) == 1:
            docs = exact
        elif len(exact) > 1:
            docs = exact
    if len(docs) > 1:
        conn.close()
        kandidater = [{"tittel": d["tittel"], "korttittel": d["korttittel"], "type": d["doc_type"]} for d in docs]
        return json.dumps({"flere_treff": kandidater}, ensure_ascii=False, indent=2)

    dokument_id = docs[0]["id"]
    target = _norm(paragraf)
    rows = conn.execute(
        "SELECT paragraf, paragraf_tittel, kapittel_tittel, text, url FROM paragrafer WHERE dokument_id = ?",
        (dokument_id,),
    ).fetchall()
    conn.close()
    for r in rows:
        if _norm(r["paragraf"] or "") == target:
            return json.dumps({
                "tittel": docs[0]["tittel"],
                "korttittel": docs[0]["korttittel"],
                "paragraf": r["paragraf"],
                "paragraf_tittel": r["paragraf_tittel"],
                "kapittel": r["kapittel_tittel"],
                "text": r["text"],
                "url": r["url"],
            }, ensure_ascii=False, indent=2)
    return json.dumps({
        "error": f"Fant '{docs[0]['korttittel'] or docs[0]['tittel']}', men ingen paragraf som matcher '{paragraf}'",
        "tilgjengelige_paragrafer": [r["paragraf"] for r in rows if r["paragraf"]][:40],
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
