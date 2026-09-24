#!/usr/bin/env python3
"""Delt hjelper for å lese hemmeligheter fra 1Password (eget hvelv for agenten) via
service account-token.

Tokenet leses fra .secrets/1password-service-account.token og sendes til
`op`-CLI-en kun som miljøvariabel for det enkelte underprosess-kallet -
ligger aldri i selve prosessens globale miljø eller i kode/logger.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
TOKEN_PATH = WORKSPACE / ".secrets" / "1password-service-account.token"


class OnePasswordError(Exception):
    """Feil ved lesing av hemmelighet fra 1Password."""


def _token() -> str:
    if not TOKEN_PATH.exists():
        raise OnePasswordError(f"Fant ikke 1Password service account-token: {TOKEN_PATH}")
    token = TOKEN_PATH.read_text().strip()
    if not token:
        raise OnePasswordError(f"1Password service account-token er tomt: {TOKEN_PATH}")
    return token


def op_read(reference: str) -> str:
    """Leser én hemmelighet via `op read op://...`. Kaster OnePasswordError
    ved feil (ugyldig referanse, manglende tilgang, manglende token)."""
    result = subprocess.run(
        ["op", "read", reference],
        env={"OP_SERVICE_ACCOUNT_TOKEN": _token(), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OnePasswordError(f"op read feilet for {reference!r}: {result.stderr.strip()}")
    return result.stdout.rstrip("\n")
