#!/usr/bin/env python3
"""Generisk lesing av Outlook-kalender-abonnement (webcal/ICS-lenker delt
via native "Del kalender"). Generisk hjelper for read-only kalender via ICS-abonnement-URL (URL-en hentes fra 1Password)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import requests

from lib.onepassword import op_read


class IcsCalendarError(Exception):
    pass


@dataclass
class IcsEvent:
    start: datetime
    summary: str


def fetch_ics(op_ref: str) -> str:
    url = op_read(op_ref)
    resp = requests.get(url, timeout=15)
    if resp.status_code != 200:
        raise IcsCalendarError(f"ICS-feed svarte {resp.status_code}")
    return resp.text


def parse_events(ics_text: str) -> list[IcsEvent]:
    # RFC5545 line unfolding: fortsettelseslinjer starter med mellomrom/tab
    unfolded = re.sub(r"\r?\n[ \t]", "", ics_text)
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfolded, re.S):
        summary_m = re.search(r"^SUMMARY:(.*)$", block, re.M)
        dtstart_m = re.search(r"^DTSTART[^:]*:(\d{8}(T\d{6}Z?)?)", block, re.M)
        if not dtstart_m:
            continue
        raw = dtstart_m.group(1)
        try:
            dt = (
                datetime.strptime(raw.rstrip("Z"), "%Y%m%dT%H%M%S")
                if "T" in raw
                else datetime.strptime(raw, "%Y%m%d")
            )
        except ValueError:
            continue
        summary = summary_m.group(1).strip() if summary_m else "(uten tittel)"
        events.append(IcsEvent(start=dt, summary=summary))
    return events


def get_upcoming_events(op_ref: str, days: int = 14) -> list[IcsEvent]:
    """Henter kommende hendelser fra en ICS-feed, sortert kronologisk.
    `days` filtrerer hvor langt frem man ser (basert på dagens dato)."""
    events = parse_events(fetch_ics(op_ref))
    today = date.today()
    upcoming = [e for e in events if e.start.date() >= today]
    upcoming.sort(key=lambda e: e.start)
    if days:
        cutoff = today + timedelta(days=days)
        upcoming = [e for e in upcoming if e.start.date() <= cutoff]
    return upcoming
