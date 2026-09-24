#!/usr/bin/env python3
"""Konverterer markdown til docx/pdf via pandoc, til bruk når notater/filer
skal leveres til brukeren i et lesbart format i stedet for rå markdown.

PDF-motor er weasyprint (lett HTML/CSS->PDF, installert 2026-08-08 sammen
med pandoc) - ikke pdflatex/texlive, som er unødvendig tungt (~1GB+) for
enkle tekstnotater uten matteformler/avansert typografi.

For docx->pdf (f.eks. ferdig utfylte skjemaer mottatt fra andre) brukes
LibreOffice headless (installert 2026-08-18), IKKE pandoc: pandocs
docx-leser flytter flytende/forankrede tabeller (w:tblpPr) ut av naturlig
leserekkefølge og dropper cellefarging (w:shd) i markdown-mellomsteget -
oppdaget da FAMFIB2027-spørreskjema V8 fikk feil spørsmålsrekkefølge og
mistet fargene i PDF-en. LibreOffice rendrer docx-en slik Word ville gjort.

Bruk:
    from lib.docconvert import convert_markdown, convert_docx_to_pdf
    docx_path = convert_markdown(Path("notat.md"), fmt="docx")
    pdf_path = convert_markdown(Path("notat.md"), fmt="pdf")
    pdf_path = convert_docx_to_pdf(Path("skjema.docx"))
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_PDF_ENGINE = "weasyprint"
_SUPPORTED = {"docx", "pdf"}
_CONVERTIBLE_SUFFIXES = {".md", ".markdown", ".txt"}


class DocConvertError(Exception):
    """Feil ved konvertering av markdown til et annet format."""


def convert_markdown(md_path: Path, fmt: str, out_dir: Path | None = None) -> Path:
    """Konverterer en markdown-fil til `fmt` ("docx" eller "pdf") med pandoc.
    Returnerer stien til den nye filen. Kaster DocConvertError ved feil."""
    if fmt not in _SUPPORTED:
        raise DocConvertError(f"Ustøttet format {fmt!r}, må være ett av {_SUPPORTED}")
    if shutil.which("pandoc") is None:
        raise DocConvertError("pandoc er ikke installert")

    md_path = Path(md_path)
    if not md_path.exists():
        raise DocConvertError(f"Fant ikke kildefil: {md_path}")

    target_dir = Path(out_dir) if out_dir else md_path.parent
    out_path = target_dir / f"{md_path.stem}.{fmt}"

    # +hard_line_breaks: uten dette slår pandoc sammen linjer uten tom linje
    # mellom til én flytende avsnittstekst - ødeleggende for f.eks.
    # segment-for-segment transkripsjonslister der hver linje skal bestå.
    cmd = [
        "pandoc", str(md_path), "-f", "markdown+hard_line_breaks",
        "--standalone", "-o", str(out_path),
    ]
    if fmt == "pdf":
        cmd += ["--pdf-engine", _PDF_ENGINE]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out_path.exists():
        raise DocConvertError(f"pandoc feilet ({fmt}): {result.stderr.strip()}")
    return out_path


def convert_docx_to_pdf(docx_path: Path, out_dir: Path | None = None) -> Path:
    """Konverterer en docx-fil til PDF med LibreOffice headless, som
    beholder original layout (flytende tabeller, cellefarging) korrekt -
    i motsetning til pandoc-veien i convert_markdown(). Returnerer stien
    til den nye filen. Kaster DocConvertError ved feil."""
    if shutil.which("soffice") is None:
        raise DocConvertError("libreoffice (soffice) er ikke installert")

    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise DocConvertError(f"Fant ikke kildefil: {docx_path}")

    target_dir = Path(out_dir) if out_dir else docx_path.parent
    out_path = target_dir / f"{docx_path.stem}.pdf"

    cmd = [
        "soffice", "--headless", "--convert-to", "pdf",
        "--outdir", str(target_dir), str(docx_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not out_path.exists():
        raise DocConvertError(f"libreoffice feilet: {result.stderr.strip()}")
    return out_path


def convert_for_delivery(path: Path, fmt: str = "docx", out_dir: Path | None = None) -> Path:
    """Konverterer `path` til `fmt` hvis det er en tekst/markdown-fil
    (.md/.markdown/.txt) og fmt != "md". Filer med andre endelser (pdf,
    docx, bilder, allerede krypterte .pgp osv.) eller fmt="md" returneres
    uendret. Faller trygt tilbake til originalfilen hvis konvertering
    feiler, i stedet for å blokkere en sending."""
    path = Path(path)
    if fmt == "md" or path.suffix.lower() not in _CONVERTIBLE_SUFFIXES:
        return path
    try:
        return convert_markdown(path, fmt=fmt, out_dir=out_dir)
    except DocConvertError:
        return path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Bruk: python3 -m lib.docconvert <fil.md> <docx|pdf>")
        sys.exit(1)
    result_path = convert_markdown(Path(sys.argv[1]), sys.argv[2])
    print(f"Skrev {result_path}")
