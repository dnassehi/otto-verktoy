#!/usr/bin/env python3
"""Sletter filer som matcher et mønster og er eldre enn N dager i en mappe.

Eksempel (daglig i cron):
    retention.py ~/tresor/dokumenter/mottak --pattern "*.pdf" --days 30 --require oversikt.md

--require NAVN: hopper over undermapper der NAVN ikke finnes (f.eks. når PDF-en
er eneste kopi fordi analysen ikke er kjørt). Alder tas fra filens endringstid.
Hopper over hvis mappen ikke finnes (tresoret ikke montert). Skriver bare filnavn til loggen.
"""
import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--pattern", default="*.pdf")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--require")
    a = ap.parse_args()
    root = a.root.expanduser()
    if not root.is_dir():
        print(f"hoppet over: {root} finnes ikke (tresoret montert?)")
        return 0
    cutoff = time.time() - a.days * 86400
    for f in sorted(root.rglob(a.pattern)):
        if not f.is_file() or f.stat().st_mtime > cutoff:
            continue
        if a.require and not (f.parent / a.require).exists():
            print(f"beholdt {f.name}: mangler {a.require} i mappen")
            continue
        f.unlink()
        print(f"slettet {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
