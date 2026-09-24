#!/usr/bin/env python3
"""PubChem PUG REST API MCP server.

Thin wrapper around PubChem, NIH/NLM's free open database of ~120M chemical
substances/compounds (structures, properties, synonyms/trade names, and
short descriptions aggregated from sources like ChEBI/DrugBank-derived
public records). No authentication key required.

Base URL: https://pubchem.ncbi.nlm.nih.gov/rest/pug
Docs: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
TIMEOUT = 30
PROPERTIES = (
    "MolecularFormula,MolecularWeight,IUPACName,SMILES,InChI,InChIKey,"
    "XLogP,TPSA,HBondDonorCount,HBondAcceptorCount,RotatableBondCount"
)

mcp = FastMCP("pubchem-mcp")


def _get(path: str) -> Any:
    resp = requests.get(f"{BASE}{path}", timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _resolve_cid(cid_or_name: str) -> int:
    ident = str(cid_or_name).strip()
    if ident.isdigit():
        return int(ident)
    data = _get(f"/compound/name/{ident}/cids/JSON")
    return data["IdentifierList"]["CID"][0]


@mcp.tool()
def pubchem_search_compound(query: str, limit: int = 10) -> str:
    """Search PubChem for a chemical substance/drug by name (e.g.
    "ibuprofen", "warfarin", "acetylsalicylic acid"). Returns matching
    PubChem CIDs (Compound IDs) - use a CID with pubchem_get_compound or
    pubchem_get_synonyms for full details. Note: PubChem's name search is
    largely exact/synonym-based, not fuzzy - try pubchem_get_synonyms on a
    known compound if a name variant doesn't match."""
    try:
        data = _get(f"/compound/name/{query}/cids/JSON")
    except requests.HTTPError:
        return json.dumps({"results": [], "note": f"No PubChem match for '{query}'"}, ensure_ascii=False)
    cids = data.get("IdentifierList", {}).get("CID", [])[:limit]
    return json.dumps({"cids": cids}, ensure_ascii=False, indent=2)


@mcp.tool()
def pubchem_get_compound(cid_or_name: str) -> str:
    """Get chemical properties for a compound, identified by PubChem CID
    (integer) or by name (e.g. "aspirin"). Returns molecular
    formula/weight, IUPAC name, SMILES, InChI/InChIKey, XLogP
    (lipophilicity), TPSA (topological polar surface area), and H-bond
    donor/acceptor/rotatable bond counts - useful for pharmacokinetic
    reasoning (e.g. CYP substrate likelihood correlates with lipophilicity/
    size, though PubChem itself does not classify CYP450 substrates/
    inhibitors - for that, a dedicated source like DrugBank is needed)."""
    cid = _resolve_cid(cid_or_name)
    data = _get(f"/compound/cid/{cid}/property/{PROPERTIES}/JSON")
    props = data.get("PropertyTable", {}).get("Properties", [{}])[0]
    return json.dumps(props, ensure_ascii=False, indent=2)


@mcp.tool()
def pubchem_get_synonyms(cid_or_name: str, limit: int = 20) -> str:
    """Get known synonyms for a compound, identified by PubChem CID or
    name - includes trade/brand names, CAS registry numbers, and
    alternative chemical names. Useful for mapping a Norwegian trade name
    (e.g. "Ibux") to its generic/chemical identity, or vice versa."""
    cid = _resolve_cid(cid_or_name)
    data = _get(f"/compound/cid/{cid}/synonyms/JSON")
    syns = data.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
    return json.dumps({"cid": cid, "synonyms": syns[:limit]}, ensure_ascii=False, indent=2)


@mcp.tool()
def pubchem_get_description(cid_or_name: str) -> str:
    """Get a short textual description of a compound (aggregated from
    sources such as ChEBI/LiverTox/NCI), identified by PubChem CID or
    name. Often includes pharmacological role/mechanism in plain text
    (e.g. "non-steroidal anti-inflammatory drug", "cyclooxygenase 2
    inhibitor")."""
    cid = _resolve_cid(cid_or_name)
    data = _get(f"/compound/cid/{cid}/description/JSON")
    infos = data.get("InformationList", {}).get("Information", [])
    descriptions = [i for i in infos if "Description" in i]
    return json.dumps({"cid": cid, "descriptions": descriptions}, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
