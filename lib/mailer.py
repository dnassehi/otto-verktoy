#!/usr/bin/env python3
"""Felles, testet funksjon for utsending av e-post fra agentens EGEN e-postkonto.

Bakgrunn: uten en felles funksjon skriver agenten gjerne et nytt engangsscript
for hver e-post. Slike script bygger ofte
Content-Disposition-headeren for vedlegg manuelt
(f'attachment; filename= {file}'), noe som ikke RFC2231-koder filnavn med
norske tegn (æøå) - mottakeren får da et vedlegg som "ATT00001.bin" i stedet
for ".docx". Denne modulen bruker email.message.EmailMessage, som håndterer
filnavn-koding, MIME-type-gjetting og multipart-oppbygging korrekt, slik at
den feilklassen ikke kan oppstå igjen uansett hvem som kaller den.

Bruk:
    from lib.mailer import send_email
    send_email(
        to="mottaker@example.com",
        subject="Emne",
        body="Brødtekst",
        cc="kopi@example.com",           # valgfritt, str eller liste
        attachments=["fil1.docx", "fil2.pdf"],  # valgfritt
        display_name="Ola Nordmann (via assistent)",  # valgfritt
    )

Tråding: hver sending genererer en Message-ID og logger den (sammen med
mottaker/emne) til sent_threads.json, slik at en senere e-post om samme
tema kan sendes som et ekte svar i samme tråd:

    thread = find_thread(to="mottaker@example.com", subject_contains="Emne")
    send_email(..., in_reply_to=thread["message_id"])

send_email() setter da In-Reply-To/References og prefikser emnet med
"Re: " automatisk (med mindre emnet allerede starter med Re:/Sv:).
"""
from __future__ import annotations

import imaplib
import json
import mimetypes
import os
import smtplib
import time
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Iterable

from lib.onepassword import OnePasswordError, op_read

WORKSPACE = Path(__file__).resolve().parent.parent
_THREAD_LOG = WORKSPACE / "lib" / "sent_threads.json"

# 1Password-item med SMTP/IMAP-oppgavene (felt: username, password, smtp_host, ...).
# Sett AGENT_MAIL_OP_ITEM, f.eks. "op://Agent/Agent email". Se README.
_OP_ITEM = os.environ.get("AGENT_MAIL_OP_ITEM", "op://Agent/Agent email")
_HEADER_FORBIDDEN = ("\r", "\n")
_SENT_FOLDER = "Sent"


class MailerError(Exception):
    """Feil ved bygging eller sending av e-post."""


def _as_list(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _check_header_safe(name: str, value: str) -> None:
    # Hindrer header-injeksjon hvis emne/adresse noen gang bygges fra
    # innhold som stammer fra en ekstern kilde (f.eks. limt inn e-posttekst).
    if any(ch in value for ch in _HEADER_FORBIDDEN):
        raise MailerError(
            f"Ugyldig verdi i header {name!r}: inneholder linjeskift ({value!r})"
        )


def _read_thread_log() -> list[dict]:
    if not _THREAD_LOG.exists():
        return []
    try:
        return json.loads(_THREAD_LOG.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _log_thread(message_id: str, to_list: list[str], cc_list: list[str], subject: str) -> None:
    # Beste-innsats: en logg-feil skal aldri få en ellers vellykket sending
    # til å se ut som mislykket, så feil her svelges bevisst.
    try:
        entries = _read_thread_log()
        entries.append(
            {
                "message_id": message_id,
                "to": to_list,
                "cc": cc_list,
                "subject": subject,
                "sent_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            }
        )
        _THREAD_LOG.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
    except OSError:
        pass


def find_thread(to: str | None = None, subject_contains: str | None = None) -> dict | None:
    """Slår opp siste loggede utgående e-post som matcher mottaker og/eller
    en delstreng i emnet (case-insensitiv), til bruk som in_reply_to i en
    påfølgende send_email()-samtale. Returnerer None hvis ingen treff.
    """
    entries = _read_thread_log()
    matches = []
    for entry in entries:
        if to is not None and to.lower() not in [a.lower() for a in entry.get("to", [])]:
            continue
        if subject_contains is not None and subject_contains.lower() not in entry.get("subject", "").lower():
            continue
        matches.append(entry)
    return matches[-1] if matches else None


def _load_config(config_path: Path | None) -> dict:
    if config_path is not None:
        if not config_path.exists():
            raise MailerError(f"Fant ikke e-postkonfigurasjon: {config_path}")
        with open(config_path) as f:
            return json.load(f)
    try:
        user = op_read(f"{_OP_ITEM}/username")
        password = op_read(f"{_OP_ITEM}/password")
        smtp_host = op_read(f"{_OP_ITEM}/smtp_host")
        smtp_port = op_read(f"{_OP_ITEM}/smtp_port")
        imap_host = op_read(f"{_OP_ITEM}/imap_host")
        imap_port = op_read(f"{_OP_ITEM}/imap_port")
    except OnePasswordError as e:
        raise MailerError(f"Kunne ikke hente e-postoppgaver fra 1Password: {e}") from e
    return {
        "smtp": {
            "host": smtp_host,
            "port": int(smtp_port),
            "auth": {"user": user, "pass": password},
            "from": user,
        },
        "imap": {
            "host": imap_host,
            "port": int(imap_port),
            "auth": {"user": user, "pass": password},
        },
    }


def _append_to_sent(config: dict, raw_message: bytes) -> None:
    # Beste-innsats: IMAP-arkivering skal aldri få en ellers vellykket
    # sending til å se ut som mislykket, så feil her svelges bevisst (men
    # logges til stderr slik at det ikke forsvinner helt stille).
    imap_cfg = config.get("imap")
    if not imap_cfg:
        return
    try:
        with imaplib.IMAP4_SSL(imap_cfg["host"], imap_cfg["port"]) as m:
            m.login(imap_cfg["auth"]["user"], imap_cfg["auth"]["pass"])
            m.append(
                _SENT_FOLDER,
                r"\Seen",
                imaplib.Time2Internaldate(time.time()),
                raw_message,
            )
    except (OSError, imaplib.IMAP4.error) as e:
        import sys

        print(f"lib.mailer: kunne ikke arkivere sendt e-post i {_SENT_FOLDER}: {e}", file=sys.stderr)


def send_email(
    to: str | Iterable[str],
    subject: str,
    body: str,
    cc: str | Iterable[str] | None = None,
    bcc: str | Iterable[str] | None = None,
    attachments: Iterable[str | Path] | None = None,
    display_name: str | None = None,
    config_path: str | Path | None = None,
    in_reply_to: str | None = None,
    references: str | Iterable[str] | None = None,
) -> str:
    """Sender en e-post med korrekt vedleggshåndtering (RFC2231-filnavn,
    riktig MIME-type). Kaster MailerError ved feil - stille feiling er
    bevisst unngått fordi tidligere scripts bare printet en feilmelding og
    fortsatte, slik at en mislykket sending kunne se ut som suksess for den
    som leste output.

    Returnerer den genererte Message-ID-en (også logget til
    sent_threads.json). Sett in_reply_to (fra en tidligere retur-verdi,
    eller find_thread()) for å sende som et ekte svar i samme tråd - emnet
    prefikses da automatisk med "Re: " hvis det ikke allerede har et
    Re:/Sv:-prefiks.
    """
    config = _load_config(Path(config_path) if config_path else None)
    smtp_cfg = config["smtp"]

    to_list = _as_list(to)
    cc_list = _as_list(cc)
    bcc_list = _as_list(bcc)
    if not to_list:
        raise MailerError("Minst én mottaker (to) er påkrevd")

    if in_reply_to and not subject.lower().startswith(("re:", "sv:")):
        subject = f"Re: {subject}"

    for label, addr in [("To", a) for a in to_list] + [("Cc", a) for a in cc_list] + [
        ("Bcc", a) for a in bcc_list
    ]:
        _check_header_safe(label, addr)
    _check_header_safe("Subject", subject)

    from_addr = smtp_cfg["from"]
    message_id = make_msgid(domain=from_addr.split("@", 1)[-1])

    msg = EmailMessage()
    msg["From"] = f"{display_name} <{from_addr}>" if display_name else from_addr
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        ref_list = _as_list(references)
        if in_reply_to not in ref_list:
            ref_list.append(in_reply_to)
        msg["References"] = " ".join(ref_list)
    msg.set_content(body)

    for att in attachments or []:
        att_path = Path(att)
        if not att_path.exists():
            raise MailerError(f"Vedlegg finnes ikke: {att_path}")
        mime_type, _ = mimetypes.guess_type(att_path.name)
        if mime_type:
            maintype, subtype = mime_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            att_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=att_path.name,
        )

    all_recipients = to_list + cc_list + bcc_list

    with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"]) as server:
        server.starttls()
        server.login(smtp_cfg["auth"]["user"], smtp_cfg["auth"]["pass"])
        refused = server.send_message(msg, from_addr=from_addr, to_addrs=all_recipients)

    if refused:
        raise MailerError(f"SMTP-server avviste mottakere: {refused}")

    _append_to_sent(config, msg.as_bytes())
    _log_thread(message_id, to_list, cc_list, subject)
    return message_id


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2 or sys.argv[1] != "--selftest":
        print("Bruk: python3 -m lib.mailer --selftest <mottaker-epost>")
        sys.exit(1)
    if len(sys.argv) < 3:
        print("Mangler mottaker-epost for selvtest")
        sys.exit(1)
    test_recipient = sys.argv[2]
    test_attachment = WORKSPACE / "_mailer_selftest_æøå.txt"
    test_attachment.write_text("Selvtest av lib/mailer.py – vedlegg med norske tegn i filnavnet.")
    try:
        send_email(
            to=test_recipient,
            subject="Selvtest av lib/mailer.py",
            body="Dette er en automatisk selvtest av den nye e-postmodulen. "
            "Hvis vedlegget kommer frem som en lesbar .txt-fil (ikke ATT00001.bin), fungerer fiksen.",
            attachments=[test_attachment],
        )
        print("Selvtest sendt til", test_recipient)
    finally:
        test_attachment.unlink(missing_ok=True)
