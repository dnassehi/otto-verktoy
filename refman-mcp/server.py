#!/usr/bin/env python3
"""MCP wrapper around lib/refdb.py (the agent's own reference-manager SQLite
database), built 2026-09-01 so the sandboxed `skriveapp` agent can search
articles the agent has already vetted/commented on, without shell/filesystem
access. Deliberately exposes only the read functions (search/find/stats/
list) - never add_article/attach_pdf/export/import here, those stay
Bash-only on the main agent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from mcp.server.fastmcp import FastMCP

from lib import refdb

mcp = FastMCP("refman-mcp")


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@mcp.tool()
def refman_search(query: str, limit: int = 20) -> str:
    """Sok i agentens egen referansedatabase (artikler han har funnet/mottatt/
    vurdert, med kommentarer/tillitsgrad og PDF-fulltekst der tilgjengelig)
    pa tittel/forfattere/sammendrag/PDF-innhold/kommentarer."""
    return _json(refdb.search(query, limit=limit))


@mcp.tool()
def refman_find_by_doi(doi: str) -> str:
    """Slaa opp en artikkel i reference-manager ved DOI. Returnerer null
    hvis ikke funnet."""
    return _json(refdb.find_by_doi(doi))


@mcp.tool()
def refman_find_by_pmid(pmid: str) -> str:
    """Slaa opp en artikkel i reference-manager ved PubMed-ID. Returnerer
    null hvis ikke funnet."""
    return _json(refdb.find_by_pmid(pmid))


@mcp.tool()
def refman_stats() -> str:
    """Statistikk over reference-manager-biblioteket: antall artikler,
    fordelt pa kilde, PDF-dekning."""
    return _json(refdb.stats())


if __name__ == "__main__":
    mcp.run()
