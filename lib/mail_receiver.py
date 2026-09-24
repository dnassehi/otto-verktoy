#!/usr/bin/env python3
"""Felles, trygg funksjon for å hente e-post/vedlegg fra agentens egen e-postkonto
over IMAP.

Bakgrunn: samme mønster som lib/mailer.py (se lib/README.md) - de gamle
IMAP-scriptene i workspace-roten (download_attachment.py,
download_attachments.py, check_email.py, check_email_simple.py) var hver
sitt engangsscript, og minst to av dem
(download_attachment.py, download_attachments.py) lagrer vedleggets
filnavn fra e-posten direkte på disk uten å fjerne sti-elementer:

    filepath = f".../workspace/{filename}"   # filename fra e-posten selv

En avsender som setter et vedleggsnavn som f.eks. "../../.ssh/authorized_keys"
eller en absolutt sti, kan dermed få skrevet en fil UTENFOR den tiltenkte
mappen - et katalogtraversering-/vilkårlig fil-skriving-hull. Dette er ikke
teoretisk: e-postens "From"-header er heller ikke autentisert (kan
forfalskes av hvem som helst), så filtrering på avsenderadresse alene gir
ingen reell beskyttelse mot dette.

Denne modulen sanerer alltid filnavn til kun selve basisnavnet
(os.path.basename, med videre sjekk mot tomt/skjult resultat) før noe
skrives til disk.

Bruk:
    from lib.mail_receiver import fetch_recent, download_attachments

    emails = fetch_recent(n=5, unseen_only=True)
    for m in emails:
        print(m["subject"], m["from"])
        for path in download_attachments(m["id"], dest_dir="innboks_vedlegg"):
            print("lagret:", path)

Merk: denne modulen sletter/expunger ALDRI e-post. Det er bevisst utelatt
- se advarselen i README om delete_email_by_subject.py.
"""
from __future__ import annotations

import email
import imaplib
import json
import os
from email.header import decode_header
from pathlib import Path
from typing import Iterable

from lib.onepassword import OnePasswordError, op_read

WORKSPACE = Path(__file__).resolve().parent.parent

_OP_ITEM = os.environ.get("AGENT_MAIL_OP_ITEM", "op://Agent/Agent email")


class MailReceiverError(Exception):
    pass


def _load_config(config_path: Path | None) -> dict:
    if config_path is not None:
        if not config_path.exists():
            raise MailReceiverError(f"Fant ikke IMAP-konfigurasjon: {config_path}")
        with open(config_path) as f:
            return json.load(f)
    try:
        user = op_read(f"{_OP_ITEM}/username")
        password = op_read(f"{_OP_ITEM}/password")
        imap_host = op_read(f"{_OP_ITEM}/imap_host")
        imap_port = op_read(f"{_OP_ITEM}/imap_port")
    except OnePasswordError as e:
        raise MailReceiverError(f"Kunne ikke hente IMAP-oppgaver fra 1Password: {e}") from e
    return {
        "imap": {
            "host": imap_host,
            "port": int(imap_port),
            "auth": {"user": user, "pass": password},
            "mailbox": "INBOX",
        }
    }


def _decode_mime_header(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = ""
    for value, charset in parts:
        if isinstance(value, bytes):
            decoded += value.decode(charset or "utf-8", errors="replace")
        else:
            decoded += value
    return decoded


def safe_filename(raw_filename: str, fallback: str = "vedlegg") -> str:
    """Reduserer et e-post-oppgitt filnavn til et trygt basisnavn.

    Fjerner all sti-informasjon (../, absolutte stier, mappenavn) slik at
    et vedlegg aldri kan skrive utenfor mål-mappen. Se moduldocstring.
    """
    name = os.path.basename(raw_filename.strip().replace("\\", "/"))
    name = name.lstrip(".")  # hindre skjulte filer / tomt navn etter '..'
    if not name:
        return fallback
    return name


def _connect(config: dict) -> imaplib.IMAP4_SSL:
    imap_cfg = config["imap"]
    mail = imaplib.IMAP4_SSL(imap_cfg["host"], imap_cfg["port"])
    mail.login(imap_cfg["auth"]["user"], imap_cfg["auth"]["pass"])
    mail.select(imap_cfg.get("mailbox", "INBOX"))
    return mail


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload is not None:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _parse_message(email_id: bytes, msg: email.message.Message) -> dict:
    return {
        "id": email_id.decode() if isinstance(email_id, bytes) else email_id,
        "subject": _decode_mime_header(msg.get("Subject")),
        "from": _decode_mime_header(msg.get("From")),
        "to": _decode_mime_header(msg.get("To")),
        "cc": _decode_mime_header(msg.get("Cc")),
        "body": _extract_body(msg),
        # Message-ID/References er ikke encoded-word-innhold (RFC 2047),
        # så de leses rått - til bruk som in_reply_to/references i
        # lib.mailer.send_email() når man svarer på denne e-posten i tråd.
        "message_id": (msg.get("Message-ID") or "").strip(),
        "references": (msg.get("References") or "").strip(),
    }


def fetch_recent(
    n: int = 5,
    unseen_only: bool = False,
    config_path: str | Path | None = None,
) -> list[dict]:
    """Henter de n siste e-postene (metadata + tekstinnhold, ingen
    vedlegg lastes ned). Bruk download_attachments() separat for vedlegg.
    """
    config = _load_config(Path(config_path) if config_path else None)
    mail = _connect(config)
    try:
        criterion = "UNSEEN" if unseen_only else "ALL"
        status, messages = mail.search(None, criterion)
        if status != "OK":
            raise MailReceiverError(f"IMAP SEARCH feilet: {status}")

        email_ids = messages[0].split()[-n:]
        results = []
        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            results.append(_parse_message(email_id, msg))
        return results
    finally:
        mail.close()
        mail.logout()


def _find_matching_ids(
    mail: imaplib.IMAP4_SSL,
    subject: str | None,
    subject_contains: str | None,
    sender_contains: str | None,
    unseen_only: bool,
) -> list[bytes]:
    """Henter ALL/UNSEEN-IDer fra serveren med et enkelt IMAP-søk (ingen
    brukerstyrt streng i selve IMAP-kommandoen), og filtrerer deretter
    KLIENT-SIDE på subject/subject_contains/sender_contains - kun
    SUBJECT/FROM-headerne lastes ned i dette steget, ikke hele meldingen.

    Denne klient-side-filtreringen (i stedet for et IMAP SUBJECT/FROM-søk
    bygget med f-string) er bevisst: unngår IMAP-søke-injeksjon helt, og
    gir eksakt-match-semantikk uten IMAP-serverens substreng-tolkning. Se
    delete_by_subject() og TOOLS.md for bakgrunnen (tidligere sårbarhet i
    delete_email_by_subject.py).
    """
    criterion = "UNSEEN" if unseen_only else "ALL"
    status, messages = mail.search(None, criterion)
    if status != "OK":
        raise MailReceiverError(f"IMAP SEARCH feilet: {status}")

    matches = []
    for email_id in messages[0].split():
        status, msg_data = mail.fetch(email_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM)])")
        if status != "OK":
            continue
        raw_header = msg_data[0][1].decode(errors="replace")
        headers = email.message_from_string(raw_header)
        found_subject = _decode_mime_header(headers.get("Subject"))
        found_sender = _decode_mime_header(headers.get("From"))

        if subject is not None and found_subject != subject:
            continue
        if subject_contains is not None and subject_contains.lower() not in found_subject.lower():
            continue
        if sender_contains is not None and sender_contains.lower() not in found_sender.lower():
            continue
        matches.append(email_id)
    return matches


def search(
    subject: str | None = None,
    subject_contains: str | None = None,
    sender_contains: str | None = None,
    unseen_only: bool = False,
    limit: int | None = None,
    config_path: str | Path | None = None,
) -> list[dict]:
    """Søker i innboksen på emne og/eller avsender, returnerer metadata i
    samme form som fetch_recent (id/subject/from/body - ingen vedlegg).

    subject: eksakt emne (case-sensitiv, hele emnet)
    subject_contains / sender_contains: case-insensitiv delstreng-match
    Minst ett av de tre må oppgis. Filtrering skjer klient-side, se
    _find_matching_ids().
    """
    if not any([subject, subject_contains, sender_contains]):
        raise MailReceiverError(
            "search() krever minst ett av: subject, subject_contains, sender_contains"
        )
    config = _load_config(Path(config_path) if config_path else None)
    mail = _connect(config)
    try:
        matches = _find_matching_ids(mail, subject, subject_contains, sender_contains, unseen_only)
        if limit is not None:
            matches = matches[:limit]

        results = []
        for email_id in matches:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            results.append(_parse_message(email_id, msg))
        return results
    finally:
        mail.close()
        mail.logout()


def delete_by_subject(
    subject: str,
    confirm: bool = False,
    config_path: str | Path | None = None,
) -> dict:
    """Sletter e-post med EKSAKT emne (case-sensitiv, hele emnet - ikke
    delstreng-søk). Tørrkjøring med mindre confirm=True: teller da bare
    hvor mange e-poster som matcher, uten å slette noe.

    Returnerer {"matched": <antall>, "deleted": <bool>}.

    All tidligere sletting via delete_email_by_subject.py gikk gjennom et
    engangsscript som expunget automatisk uten bekreftelse og brukte et
    IMAP-substreng-søk bygget med f-string (kommando-injeksjonspunkt).
    Denne funksjonen filtrerer klient-side på eksakt emne (se
    _find_matching_ids()) og krever et eksplisitt confirm=True for å
    faktisk slette noe.
    """
    config = _load_config(Path(config_path) if config_path else None)
    mail = _connect(config)
    try:
        matches = _find_matching_ids(mail, subject, None, None, unseen_only=False)
        if not matches:
            return {"matched": 0, "deleted": False}
        if not confirm:
            return {"matched": len(matches), "deleted": False}
        for email_id in matches:
            mail.store(email_id, "+FLAGS", "\\Deleted")
        mail.expunge()
        return {"matched": len(matches), "deleted": True}
    finally:
        mail.close()
        mail.logout()


def archive_by_subject(
    subject: str,
    confirm: bool = False,
    archive_mailbox: str = "Archive",
    config_path: str | Path | None = None,
) -> dict:
    """Flytter e-post med EKSAKT emne (case-sensitiv, hele emnet) til
    Archive-mappen. Tørrkjøring med mindre confirm=True: teller da bare
    hvor mange e-poster som matcher, uten å flytte noe.

    Returnerer {"matched": <antall>, "archived": <bool>}.

    Samme klient-side eksakt-match-filtrering som delete_by_subject() (se
    _find_matching_ids()) - ingen brukerstyrt streng i selve IMAP-kommandoen.
    """
    config = _load_config(Path(config_path) if config_path else None)
    mail = _connect(config)
    try:
        matches = _find_matching_ids(mail, subject, None, None, unseen_only=False)
        if not matches:
            return {"matched": 0, "archived": False}
        if not confirm:
            return {"matched": len(matches), "archived": False}
        for email_id in matches:
            status, _ = mail.copy(email_id, archive_mailbox)
            if status != "OK":
                raise MailReceiverError(f"Kunne ikke kopiere e-post {email_id!r} til {archive_mailbox}")
            mail.store(email_id, "+FLAGS", "\\Deleted")
        mail.expunge()
        return {"matched": len(matches), "archived": True}
    finally:
        mail.close()
        mail.logout()


def download_attachments(
    email_id: str,
    dest_dir: str | Path,
    config_path: str | Path | None = None,
) -> list[Path]:
    """Laster ned alle vedlegg fra én e-post (gitt IMAP-ID fra fetch_recent)
    til dest_dir, med sanert filnavn (se safe_filename)."""
    config = _load_config(Path(config_path) if config_path else None)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    mail = _connect(config)
    try:
        status, msg_data = mail.fetch(
            email_id.encode() if isinstance(email_id, str) else email_id, "(RFC822)"
        )
        if status != "OK":
            raise MailReceiverError(f"Kunne ikke hente e-post {email_id}")
        msg = email.message_from_bytes(msg_data[0][1])

        saved: list[Path] = []
        if not msg.is_multipart():
            return saved

        used_names: set[str] = set()
        for part in msg.walk():
            raw_name = part.get_filename()
            if not raw_name:
                continue
            name = safe_filename(_decode_mime_header(raw_name))
            # unngå at to sanerte filnavn kolliderer og overskriver hverandre
            candidate = name
            i = 1
            while candidate in used_names or (dest / candidate).exists():
                stem, dot, ext = name.rpartition(".")
                candidate = f"{stem or name}_{i}{dot}{ext}"
                i += 1
            used_names.add(candidate)

            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            filepath = dest / candidate
            filepath.write_bytes(payload)
            saved.append(filepath)
        return saved
    finally:
        mail.close()
        mail.logout()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2 or sys.argv[1] != "--selftest":
        print("Bruk: python3 -m lib.mail_receiver --selftest")
        sys.exit(1)
    tests = [
        ("rapport.docx", "rapport.docx"),
        ("../../.ssh/authorized_keys", "authorized_keys"),
        ("/etc/cron.d/evil", "evil"),
        ("..\\..\\windows\\evil.bat", "evil.bat"),
        ("...", "vedlegg"),
        ("", "vedlegg"),
        (".hidden", "hidden"),
    ]
    ok = True
    for raw, expected in tests:
        got = safe_filename(raw)
        status = "OK" if got == expected else "FEIL"
        if got != expected:
            ok = False
        print(f"{status}: safe_filename({raw!r}) = {got!r} (forventet {expected!r})")
    sys.exit(0 if ok else 1)
