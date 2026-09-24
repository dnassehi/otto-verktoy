#!/usr/bin/env python3
"""Orphadata API MCP server.

Thin wrapper around Orphadata, Orphanet's structured knowledge base on rare
diseases (classification, cross-referencing to ICD-10/ICD-11/OMIM, associated
genes, HPO phenotype associations, epidemiology/prevalence). Free, open,
no authentication key required (CC-BY-4.0 licensed data).

Base URL: https://api.orphadata.com
Full spec: https://api.orphadata.com/openapi.json
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://api.orphadata.com"
TIMEOUT = 30

mcp = FastMCP("orphadata-mcp")


def _get(path: str, params: dict | None = None) -> Any:
    resp = requests.get(f"{BASE}{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def orphadata_search_disease(name: str, lang: str = "en") -> str:
    """Search Orphanet's rare disease database by disease name (e.g.
    "marfan", "cystic fibrosis", "ehlers-danlos"). Case-insensitive
    partial match. Returns the ORPHAcode(s) and preferred term(s) plus
    ICD-10/ICD-11 cross-references - use the ORPHAcode with the other
    orphadata_* tools for genes/phenotypes/epidemiology. lang: "en"
    (default), "fr", "de", "es", "it", "nl", "pt", "cs", "pl", "tr", "uk"
    or "zh"."""
    data = _get(f"/rd-cross-referencing/orphacodes/names/{name}", {"lang": lang})
    return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)


@mcp.tool()
def orphadata_get_disease(orphacode: int, lang: str = "en") -> str:
    """Get the full disorder record for a rare disease by its ORPHAcode
    (from orphadata_search_disease): synonyms, disorder type/group,
    and cross-references to ICD-10, ICD-11, OMIM, UMLS, MeSH, MedDRA.
    lang: "en" (default), "fr", "de", "es", "it", "nl", "pt", "cs", "pl",
    "tr", "uk" or "zh"."""
    data = _get(f"/rd-cross-referencing/orphacodes/{orphacode}", {"lang": lang})
    return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)


@mcp.tool()
def orphadata_get_genes(orphacode: int) -> str:
    """Get genes associated with a rare disease by its ORPHAcode (from
    orphadata_search_disease). Returns gene-disorder association type
    (e.g. "Disease-causing germline mutation in") and gene cross-references
    (HGNC, OMIM, Ensembl, ClinVar, Reactome, UniProt). Returns an empty/
    error result if no gene association is documented for this disorder."""
    try:
        data = _get(f"/rd-associated-genes/orphacodes/{orphacode}")
    except requests.HTTPError as exc:
        return json.dumps({"error": str(exc), "note": "No gene association found for this ORPHAcode"}, ensure_ascii=False)
    return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)


@mcp.tool()
def orphadata_get_phenotypes(orphacode: int, lang: str = "en") -> str:
    """Get the clinical phenotype (HPO - Human Phenotype Ontology) terms
    associated with a rare disease by its ORPHAcode (from
    orphadata_search_disease), each with an HPOFrequency (e.g. "Very
    frequent (99-80%)", "Occasional (29-5%)") and whether it is a
    diagnostic criterion. lang: "en" (default), "fr", "de", "es", "it",
    "nl" or "pt"."""
    data = _get(f"/rd-phenotypes/orphacodes/{orphacode}", {"lang": lang})
    return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)


@mcp.tool()
def orphadata_get_epidemiology(orphacode: int, lang: str = "en") -> str:
    """Get epidemiology data (prevalence/incidence class, geographic area,
    source) for a rare disease by its ORPHAcode (from
    orphadata_search_disease). lang: "en" (default), "fr", "de", "es",
    "it", "nl", "pt", "cs", "pl" or "tr"."""
    data = _get(f"/rd-epidemiology/orphacodes/{orphacode}", {"lang": lang})
    return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
