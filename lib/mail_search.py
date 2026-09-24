#!/usr/bin/env python3
"""Søk på tvers av flere IMAP-mapper (INBOX/Sent/Archive) for agentens egen e-postkonto.

Bakgrunn: lib.mail_receiver.search() søker kun i én mappe (default INBOX),
kun på emne/avsender (ikke brødtekst), og lister ikke vedlegg uten å laste
dem ned. Etter hvert som flere e-poster sendes/arkiveres (Sent-arkivering
satt opp 2026-09-02, se lib/mailer.py) blir det upraktisk å måtte vite på
forhånd hvilken mappe og hvilket eksakt emne man leter etter. Denne modulen
dekker det bredere søkebehovet: fritekstsøk i emne+avsender+brødtekst på
tvers av flere mapper samtidig, datofiltrering, og en liste over
vedleggsnavn (uten å laste dem ned) slik at man kan finne "det gamle
vedlegget fra i vår" uten å hente hver eneste e-post.

Bruk:
    from lib.mail_search import search_mail, get_attachment

    treff = search_mail("Nesheim")  # søker emne+avsender+brødtekst, alle mapper
    for m in treff:
        print(m["folder"], m["date"], m["subject"], m["attachments"])

    # last ned ett spesifikt vedlegg funnet over
    path = get_attachment(m["folder"], m["id"], "rapport.docx", "nedlastet/")

CLI:
    python3 -m lib.mail_search "søkeord"
    python3 -m lib.mail_search --subject "Nesheim" --folder Sent
    python3 -m lib.mail_search --attachments-only --since 2026-01-01
    python3 -m lib.mail_search --get-attachment --folder Sent --id 123 \\
        --filename rapport.docx --dest nedlastet/

Gjenbruker konfigurasjon/hjelpefunksjoner fra lib.mail_receiver (samme
1Password-oppslag, samme filnavn-sanering for vedlegg) - se lib/README.md.
"""
from __future__ import annotations

import email
import imaplib
from datetime import datetime
from pathlib import Path

from lib.mail_receiver import (
    MailReceiverError,
    _decode_mime_header,
    _extract_body,
    _load_config,
    safe_filename,
)

DEFAULT_FOLDERS = ("INBOX", "Sent", "Archive")


def _connect_folder(config: dict, folder: str) -> imaplib.IMAP4_SSL | None:
    """Kobler til og velger én mappe. Returnerer None (i stedet for å
    kaste feil) hvis mappen ikke finnes på kontoen, slik at søk på tvers
    av flere mapper kan hoppe over manglende mapper i stedet for å stoppe
    helt."""
    imap_cfg = config["imap"]
    mail = imaplib.IMAP4_SSL(imap_cfg["host"], imap_cfg["port"])
    mail.login(imap_cfg["auth"]["user"], imap_cfg["auth"]["pass"])
    status, _ = mail.select(folder)
    if status != "OK":
        mail.logout()
        return None
    return mail


def _fmt_imap_date(raw: str, label: str) -> str:
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as e:
        raise MailReceiverError(f"Ugyldig {label}-dato (bruk YYYY-MM-DD): {raw}") from e
    return dt.strftime("%d-%b-%Y")


def _attachment_names(msg: email.message.Message) -> list[str]:
    if not msg.is_multipart():
        return []
    names = []
    for part in msg.walk():
        raw_name = part.get_filename()
        if raw_name:
            names.append(_decode_mime_header(raw_name))
    return names


def search_mail(
    query: str | None = None,
    subject_contains: str | None = None,
    sender_contains: str | None = None,
    body_contains: str | None = None,
    folders: tuple[str, ...] = DEFAULT_FOLDERS,
    since: str | None = None,
    before: str | None = None,
    attachments_only: bool = False,
    limit: int = 50,
    config_path: str | Path | None = None,
) -> list[dict]:
    """Søker etter e-post på tvers av flere IMAP-mapper (standard: INBOX,
    Sent, Archive).

    query: fritekst-snarvei - treff hvis strengen finnes i emne ELLER
    avsender ELLER brødtekst (delstreng, case-insensitiv).
    subject_contains/sender_contains/body_contains: mer presist søk, kan
    kombineres (alle oppgitte må matche). Minst ett av query/de tre/
    since/before/attachments_only må oppgis (rent datofilter eller "kun
    med vedlegg" uten tekstsøk er altså gyldig - lister da alt i perioden).
    since/before: "YYYY-MM-DD", server-side IMAP SINCE/BEFORE (dato
    valideres og formateres selv - ingen brukerstreng i IMAP-kommandoen).
    attachments_only: kun e-poster som faktisk har vedlegg.
    limit: stopper når så mange treff er funnet (på tvers av alle mapper).

    Returnerer liste av dict: folder, id, date, subject, from, to,
    attachments (kun filnavn, IKKE lastet ned - bruk get_attachment() eller
    lib.mail_receiver.download_attachments() for selve nedlastingen).
    """
    if not any(
        [query, subject_contains, sender_contains, body_contains, since, before, attachments_only]
    ):
        raise MailReceiverError(
            "search_mail() krever minst ett av: query, subject_contains, "
            "sender_contains, body_contains, since, before, attachments_only"
        )

    config = _load_config(Path(config_path) if config_path else None)
    results: list[dict] = []

    search_args = []
    if since:
        search_args += ["SINCE", _fmt_imap_date(since, "since")]
    if before:
        search_args += ["BEFORE", _fmt_imap_date(before, "before")]
    if not search_args:
        search_args = ["ALL"]

    for folder in folders:
        mail = _connect_folder(config, folder)
        if mail is None:
            continue
        try:
            status, messages = mail.search(None, *search_args)
            if status != "OK":
                continue
            for email_id in messages[0].split():
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                if status != "OK":
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                subject = _decode_mime_header(msg.get("Subject"))
                sender = _decode_mime_header(msg.get("From"))
                body = _extract_body(msg)

                if query is not None:
                    haystacks = (subject, sender, body or "")
                    if not any(query.lower() in h.lower() for h in haystacks):
                        continue
                else:
                    if subject_contains and subject_contains.lower() not in subject.lower():
                        continue
                    if sender_contains and sender_contains.lower() not in sender.lower():
                        continue
                    if body_contains and body_contains.lower() not in (body or "").lower():
                        continue

                attachments = _attachment_names(msg)
                if attachments_only and not attachments:
                    continue

                results.append(
                    {
                        "folder": folder,
                        "id": email_id.decode() if isinstance(email_id, bytes) else email_id,
                        "date": _decode_mime_header(msg.get("Date")),
                        "subject": subject,
                        "from": sender,
                        "to": _decode_mime_header(msg.get("To")),
                        "attachments": attachments,
                    }
                )
                if len(results) >= limit:
                    return results
        finally:
            mail.close()
            mail.logout()
    return results


def get_attachment(
    folder: str,
    email_id: str,
    filename: str,
    dest_dir: str | Path,
    config_path: str | Path | None = None,
) -> Path:
    """Laster ned ett navngitt vedlegg fra en spesifikk e-post (funnet via
    search_mail()) til dest_dir.

    filename matches case-insensitivt som delstreng mot det MIME-dekodede
    vedleggsnavnet. Lagres med sanert filnavn (lib.mail_receiver.safe_filename)
    - samme beskyttelse mot katalogtraversering som resten av mail_receiver.
    """
    config = _load_config(Path(config_path) if config_path else None)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    mail = _connect_folder(config, folder)
    if mail is None:
        raise MailReceiverError(f"Fant ikke mappen {folder!r}")
    try:
        status, msg_data = mail.fetch(
            email_id.encode() if isinstance(email_id, str) else email_id, "(RFC822)"
        )
        if status != "OK":
            raise MailReceiverError(f"Kunne ikke hente e-post {email_id} fra {folder}")
        msg = email.message_from_bytes(msg_data[0][1])
        if not msg.is_multipart():
            raise MailReceiverError("E-posten har ingen vedlegg")

        for part in msg.walk():
            raw_name = part.get_filename()
            if not raw_name:
                continue
            decoded_name = _decode_mime_header(raw_name)
            if filename.lower() not in decoded_name.lower():
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            filepath = dest / safe_filename(decoded_name)
            filepath.write_bytes(payload)
            return filepath
        raise MailReceiverError(f"Fant ikke vedlegg som matcher {filename!r} i e-post {email_id}")
    finally:
        mail.close()
        mail.logout()


def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?", help="Fritekstsøk i emne+avsender+brødtekst")
    parser.add_argument("--subject", dest="subject_contains", help="Delstreng i emnefeltet")
    parser.add_argument("--from", dest="sender_contains", help="Delstreng i avsenderfeltet")
    parser.add_argument("--body", dest="body_contains", help="Delstreng i brødteksten")
    parser.add_argument("--folder", help="Kommaseparert mappeliste (default: INBOX,Sent,Archive)")
    parser.add_argument("--since", help="YYYY-MM-DD")
    parser.add_argument("--before", help="YYYY-MM-DD")
    parser.add_argument("--attachments-only", action="store_true")
    parser.add_argument("--limit", type=int, default=50)

    parser.add_argument("--get-attachment", action="store_true", help="Last ned ett vedlegg i stedet for å søke")
    parser.add_argument("--id", help="E-post-ID (fra et tidligere søk) - kreves med --get-attachment")
    parser.add_argument("--filename", help="Vedleggsnavn (delstreng) - kreves med --get-attachment")
    parser.add_argument("--dest", default=".", help="Mål-mappe for --get-attachment (default: nåværende mappe)")

    args = parser.parse_args()

    if args.get_attachment:
        if not (args.folder and args.id and args.filename):
            parser.error("--get-attachment krever --folder, --id og --filename")
        path = get_attachment(args.folder, args.id, args.filename, args.dest)
        print(f"Lagret: {path}")
        return 0

    folders = tuple(f.strip() for f in args.folder.split(",")) if args.folder else DEFAULT_FOLDERS
    try:
        results = search_mail(
            query=args.query,
            subject_contains=args.subject_contains,
            sender_contains=args.sender_contains,
            body_contains=args.body_contains,
            folders=folders,
            since=args.since,
            before=args.before,
            attachments_only=args.attachments_only,
            limit=args.limit,
        )
    except MailReceiverError as e:
        parser.error(str(e))
        return 2

    if not results:
        print("Ingen treff.")
        return 0

    for m in results:
        att = f" [vedlegg: {', '.join(m['attachments'])}]" if m["attachments"] else ""
        print(f"[{m['folder']}#{m['id']}] {m['date']} — {m['subject']} (fra: {m['from']}){att}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_cli())
