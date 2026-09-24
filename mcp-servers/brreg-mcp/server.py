#!/usr/bin/env python3
"""Brønnøysundregistrene (BRREG) Entity Register API MCP server.

Thin, read-only wrapper around the Norwegian Brønnøysundregistrene Entity
Register API (Enhetsregisteret), base URL https://data.brreg.no/enhetsregisteret/api.
No authentication required for public lookups.

The API provides:
- enheter: search/lookup organizations/entities and their details (name, address,
  status, industry code, number of employees)
- underenheter: search for sub-units (branches) of organizations
- roller: lookup roles (board members, CEO, auditor, accountant, etc.) for an entity

Documentation: https://data.brreg.no/enhetsregisteret/api/dokumentasjon/no/swagger-ui.html
License: NLOD (Norwegian Licence for Open Government Data)

Workflow:
    search entity -> get details + roles
    or: get entity directly by org number -> get roles and sub-units
"""
from __future__ import annotations

import json
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://data.brreg.no/enhetsregisteret/api"
TIMEOUT = 30

mcp = FastMCP("brreg-mcp")


def _get(path: str, params: dict | None = None) -> Any:
    resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def brreg_search_entity(query: str, size: int = 20) -> str:
    """Search for entities (organizations, companies) by name or free text.
    Returns paginated results with entity details: organization number (orgnr),
    name, industry code, addresses, status, and more. Use the orgnr from
    results in brreg_get_entity to fetch full details and roles. 'query' is
    free-text (e.g. "University of Bergen", "DNB"), and 'size' limits
    results (max 100, default 20). Response includes pagination links."""
    params = {"navn": query, "size": size}
    result = _get("enheter", params)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def brreg_get_entity(org_number: str) -> str:
    """Get full details for a specific entity by its Norwegian organization
    number (orgnr), a 9-digit identifier. Includes name, addresses (postal and
    business), phone, email, website, industry code (NACE), number of employees,
    establishment date, VAT status, sector classification, and various
    registration dates. org_number example: 874789542 (UiB)."""
    result = _get(f"enheter/{org_number}")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def brreg_search_subunit(query: str, size: int = 20) -> str:
    """Search for sub-units (branches, regional offices) by name or free text.
    Each sub-unit belongs to a main entity (identified by its orgnr in the
    'overordnetEnhet' field). Use this to find branch offices or organizational
    divisions. 'size' limits results (max 100, default 20). Response includes
    pagination links."""
    params = {"navn": query, "size": size}
    result = _get("underenheter", params)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def brreg_get_roles(org_number: str) -> str:
    """Get all roles/positions for an entity: CEO (DAGL), board members (STYR),
    auditor (REVI), accountant (REGN), organizational hierarchy (ORGL), etc.
    Each role entry includes person/entity name, role type, and registration
    details. Roles are grouped by type (e.g. all board members together).
    org_number is the 9-digit Norwegian organization number."""
    result = _get(f"enheter/{org_number}/roller")
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
