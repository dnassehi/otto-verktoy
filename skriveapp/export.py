"""Eksport av dokumentinnhold (HTML fra Quill-editoren) til docx/pdf, sendt
på e-post. lib/docconvert.py sin convert_markdown() antar markdown-input
(+hard_line_breaks) og passer ikke for allerede strukturert HTML herfra.

docx bruker LibreOffice headless, IKKE pandoc: verifisert 2026-09-11 (etter
at skriftstørrelse-velgeren ble lagt til i editoren) at pandocs HTML-leser
dropper inline font-size helt - ingen w:sz i det hele tatt i resultat-docx-en,
uansett størrelse. LibreOffice bevarer størrelsen korrekt (og resten av
formateringen - fet/kursiv/lister/lenker - identisk til pandoc, bekreftet
ved sammenligning). pdf beholder pandoc+weasyprint, som viste seg å bevare
font-size korrekt (bekreftet med bbox-måling av faktisk tekststørrelse i
PDF-en) - trolig fordi weasyprint-veien går via pandocs HTML-writer, som
tar vare på style-attributter, mens docx-writeren ikke har noe sted å
legge en vilkårlig CSS-størrelse."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))
from lib.mailer import send_email, MailerError  # noqa: E402
from agentname import AGENT_NAME  # noqa: E402

EXPORT_DIR = Path(__file__).resolve().parent / "exports"


class ExportError(Exception):
    pass


def _safe_filename(title: str) -> str:
    """Fjerner tegn som er ugyldige/farlige i filnavn (f.eks. "/" i datoer som
    3/9/26, som ellers tolkes som mappeskille av både Path og pandoc)."""
    safe = re.sub(r'[\\/:*?"<>|]', "-", title).strip()
    return safe or "utkast"


def _write_temp_html(html: str, title: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(f"<html><head><meta charset='utf-8'><title>{title}</title></head><body>{html}</body></html>")
        return Path(f.name)


def _pandoc_convert(html_path: Path, out_path: Path, extra_args: list[str] | None = None) -> None:
    cmd = ["pandoc", str(html_path), "-f", "html", "--standalone", *(extra_args or []), "-o", str(out_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ExportError(f"pandoc feilet: {result.stderr}")


def _libreoffice_convert_docx(html_path: Path, out_path: Path) -> None:
    if shutil.which("soffice") is None:
        raise ExportError("libreoffice (soffice) er ikke installert")
    cmd = [
        "soffice", "--headless", "--convert-to", "docx:MS Word 2007 XML",
        "--outdir", str(out_path.parent), str(html_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    produced = out_path.parent / f"{html_path.stem}.docx"
    if result.returncode != 0 or not produced.exists():
        raise ExportError(f"libreoffice feilet: {result.stderr.strip()}")
    produced.replace(out_path)


def html_to_docx(html: str, title: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = _write_temp_html(html, title)
    docx_path = out_dir / f"{_safe_filename(title)}.docx"
    try:
        _libreoffice_convert_docx(html_path, docx_path)
    finally:
        html_path.unlink(missing_ok=True)
    return docx_path


def html_to_pdf(html: str, title: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = _write_temp_html(html, title)
    pdf_path = out_dir / f"{_safe_filename(title)}.pdf"
    try:
        _pandoc_convert(html_path, pdf_path, ["--pdf-engine", "weasyprint"])
    finally:
        html_path.unlink(missing_ok=True)
    return pdf_path


def export_and_send(slug: str, title: str, html: str, to_email: str) -> str:
    docx_path = html_to_docx(html, title, EXPORT_DIR)
    try:
        send_email(
            to=to_email,
            subject=f"Utkast: {title}",
            body=f"Vedlagt: \"{title}\", generert fra skriveappen.\n\n{AGENT_NAME}",
            attachments=[docx_path],
            display_name=f"{AGENT_NAME} (skriveapp)",
        )
    except MailerError as e:
        raise ExportError(f"Kunne ikke sende e-post: {e}") from e
    return str(docx_path)
