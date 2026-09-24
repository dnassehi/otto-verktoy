"""Enkel passordbasert innlogging - kun for én bruker, ingen registrering,
ingen flerbrukerstøtte. Passord hentes fra 1Password (SKRIVEAPP_OP_ITEM),
sesjon er en signert cookie (itsdangerous), ingen server-side sesjonslagring
nødvendig for én bruker.

Rate-limiting (lagt til 2026-09-01): hvis appen eksponeres på åpent internett
(f.eks. via Tailscale Funnel og ikke bare tailnettet), er innlogging brute force-utsatt uten dette. In-memory (ikke persistent på tvers av restart) - greit nok
for et enkeltbruker-verktøy, tilbakestilles ved tjeneste-restart."""
from __future__ import annotations

import hmac
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))
from lib.onepassword import op_read, OnePasswordError  # noqa: E402

SESSION_COOKIE = "skriveapp_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 dager

_SECRET_PATH = Path(__file__).resolve().parent / ".session_secret"


def _get_secret() -> str:
    if _SECRET_PATH.exists():
        return _SECRET_PATH.read_text().strip()
    import secrets

    secret = secrets.token_hex(32)
    _SECRET_PATH.write_text(secret)
    _SECRET_PATH.chmod(0o600)
    return secret


_serializer = URLSafeTimedSerializer(_get_secret())


_OP_ITEM = os.environ.get("SKRIVEAPP_OP_ITEM", "op://Agent/Skriveapp login")


MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
LOCKOUT_SECONDS = 15 * 60

_failed_attempts: dict[str, list[float]] = defaultdict(list)
_locked_until: dict[str, float] = {}


def is_locked_out(ip: str) -> int:
    """Returnerer sekunder igjen av lockout, eller 0 hvis ikke låst."""
    until = _locked_until.get(ip)
    if until is None:
        return 0
    remaining = until - time.time()
    if remaining <= 0:
        _locked_until.pop(ip, None)
        _failed_attempts.pop(ip, None)
        return 0
    return int(remaining)


def record_failed_attempt(ip: str) -> None:
    now = time.time()
    attempts = [t for t in _failed_attempts[ip] if now - t < WINDOW_SECONDS]
    attempts.append(now)
    _failed_attempts[ip] = attempts
    if len(attempts) >= MAX_ATTEMPTS:
        _locked_until[ip] = now + LOCKOUT_SECONDS


def record_success(ip: str) -> None:
    _failed_attempts.pop(ip, None)
    _locked_until.pop(ip, None)


def check_password(password: str) -> bool:
    try:
        expected = op_read(f"{_OP_ITEM}/password")
    except OnePasswordError:
        return False
    return hmac.compare_digest(password, expected)


def make_session_token(username: str = "user") -> str:
    return _serializer.dumps({"u": username, "t": time.time()})


def verify_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return True
