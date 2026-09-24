#!/usr/bin/env python3
"""Agentens egen lokale referansedatabase - metadata, PDF-filer og kommentarer
for artikler agenten finner (research-monitor, forskning-workflow) eller får
tilsendt. Se reference-manager/README.md for
arkitektur/triggerpunkter og lib/README.md for kort oppsummering.

Ren SQLite, ingen eksterne avhengigheter (sqlite3 er i standardbiblioteket).
Dette er agentens EGEN database over artikler den har behandlet - ikke
et komplett bibliotek.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent / "reference-manager"
DB_PATH = BASE_DIR / "db" / "library.db"
PDF_DIR = BASE_DIR / "pdfs"

VALID_SOURCES = {
    "research-monitor",
    "research-monitor-elicit",
    "forskning-workflow",
    "telegram",
    "epost",
    "manual",
    "bibtex-import",
    "ris-import",
    "nbib-import",
}


class RefDBError(Exception):
    """Feil ved bruk av referansedatabasen."""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT,
            pmid TEXT,
            title TEXT NOT NULL,
            authors TEXT,
            journal TEXT,
            year TEXT,
            url TEXT,
            abstract TEXT,
            source TEXT NOT NULL,
            date_added TEXT NOT NULL,
            pdf_path TEXT,
            read_status TEXT NOT NULL DEFAULT 'ulest'
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_doi
            ON articles(doi) WHERE doi IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_articles_pmid ON articles(pmid);

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            comment TEXT NOT NULL,
            date_added TEXT NOT NULL
        );
        """
    )
    conn.commit()

    # Migrering: pdf_text-kolonne (fulltekst hentet ut av pdftotext) fantes
    # ikke i v1-skjemaet - lagt til for at PDF-innhold skal bli søkbart.
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
    if "pdf_text" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN pdf_text TEXT")
        conn.commit()

    # FTS5-tabellen må ha pdf_text som egen indeksert kolonne for at
    # fulltekstsøk skal dekke PDF-innhold i tillegg til tittel/forfattere/
    # sammendrag. Eksisterende v1-installasjoner må bygges om (FTS5 støtter
    # ikke ALTER TABLE ADD COLUMN), derfor sjekkes den lagrede DDL-en her.
    fts_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'articles_fts'"
    ).fetchone()
    if fts_sql_row is None or "pdf_text" not in fts_sql_row["sql"]:
        conn.executescript(
            """
            DROP TRIGGER IF EXISTS articles_ai;
            DROP TRIGGER IF EXISTS articles_ad;
            DROP TRIGGER IF EXISTS articles_au;
            DROP TABLE IF EXISTS articles_fts;

            CREATE VIRTUAL TABLE articles_fts USING fts5(
                title, authors, abstract, pdf_text,
                content='articles', content_rowid='id'
            );

            CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
                INSERT INTO articles_fts(rowid, title, authors, abstract, pdf_text)
                VALUES (new.id, new.title, new.authors, new.abstract, new.pdf_text);
            END;
            CREATE TRIGGER articles_ad AFTER DELETE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, authors, abstract, pdf_text)
                VALUES ('delete', old.id, old.title, old.authors, old.abstract, old.pdf_text);
            END;
            CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, authors, abstract, pdf_text)
                VALUES ('delete', old.id, old.title, old.authors, old.abstract, old.pdf_text);
                INSERT INTO articles_fts(rowid, title, authors, abstract, pdf_text)
                VALUES (new.id, new.title, new.authors, new.abstract, new.pdf_text);
            END;
            """
        )
        conn.execute(
            """INSERT INTO articles_fts(rowid, title, authors, abstract, pdf_text)
               SELECT id, title, authors, abstract, pdf_text FROM articles"""
        )
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add_article(
    title: str,
    doi: str | None = None,
    pmid: str | None = None,
    authors: str | None = None,
    journal: str | None = None,
    year: str | None = None,
    url: str | None = None,
    abstract: str | None = None,
    source: str = "manual",
    comment: str | None = None,
    pdf_source_path: str | None = None,
) -> int:
    """Legger til en artikkel, eller returnerer id-en til en eksisterende
    hvis DOI/PMID/tittel allerede finnes (ingen duplikater). Ved treff på
    en eksisterende artikkel oppdateres kun tomme felt - eksisterende data
    overskrives aldri stille."""
    if source not in VALID_SOURCES:
        raise RefDBError(f"Ukjent kilde '{source}' - gyldige: {sorted(VALID_SOURCES)}")
    if not title or not title.strip():
        raise RefDBError("Artikkel må ha en tittel")

    conn = _connect()
    try:
        existing = _find_existing(conn, doi=doi, pmid=pmid, title=title)
        if existing is not None:
            article_id = existing["id"]
            _fill_missing_fields(
                conn, article_id, doi=doi, pmid=pmid, authors=authors,
                journal=journal, year=year, url=url, abstract=abstract,
            )
        else:
            cur = conn.execute(
                """INSERT INTO articles
                   (doi, pmid, title, authors, journal, year, url, abstract,
                    source, date_added)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doi.strip() if doi else None,
                    str(pmid).strip() if pmid else None,
                    title.strip(),
                    authors,
                    journal,
                    year,
                    url,
                    abstract,
                    source,
                    _now(),
                ),
            )
            article_id = cur.lastrowid
            conn.commit()

        if comment:
            _add_comment(conn, article_id, comment)
        if pdf_source_path:
            _attach_pdf(conn, article_id, pdf_source_path)
        return article_id
    finally:
        conn.close()


def _find_existing(conn: sqlite3.Connection, doi: str | None, pmid: str | None, title: str) -> sqlite3.Row | None:
    if doi:
        row = conn.execute(
            "SELECT * FROM articles WHERE doi = ?", (doi.strip(),)
        ).fetchone()
        if row:
            return row
    if pmid:
        row = conn.execute(
            "SELECT * FROM articles WHERE pmid = ?", (str(pmid).strip(),)
        ).fetchone()
        if row:
            return row
    row = conn.execute(
        "SELECT * FROM articles WHERE lower(title) = lower(?)", (title.strip(),)
    ).fetchone()
    return row


def _fill_missing_fields(conn: sqlite3.Connection, article_id: int, **fields) -> None:
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    updates = {}
    for key, value in fields.items():
        if value and not row[key]:
            updates[key] = value.strip() if isinstance(value, str) else str(value)
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE articles SET {set_clause} WHERE id = ?",
        (*updates.values(), article_id),
    )
    conn.commit()


def add_comment(article_id: int, comment: str) -> None:
    conn = _connect()
    try:
        _add_comment(conn, article_id, comment)
    finally:
        conn.close()


def _add_comment(conn: sqlite3.Connection, article_id: int, comment: str) -> None:
    row = conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone()
    if row is None:
        raise RefDBError(f"Fant ingen artikkel med id {article_id}")
    conn.execute(
        "INSERT INTO comments (article_id, comment, date_added) VALUES (?, ?, ?)",
        (article_id, comment, _now()),
    )
    conn.commit()


def attach_pdf(article_id: int, pdf_source_path: str) -> str:
    conn = _connect()
    try:
        return _attach_pdf(conn, article_id, pdf_source_path)
    finally:
        conn.close()


def _attach_pdf(conn: sqlite3.Connection, article_id: int, pdf_source_path: str) -> str:
    src = Path(pdf_source_path)
    if not src.is_file():
        raise RefDBError(f"PDF-fil finnes ikke: {pdf_source_path}")
    dest = PDF_DIR / f"{article_id}.pdf"
    shutil.copyfile(src, dest)
    pdf_text = _extract_pdf_text(dest)
    conn.execute(
        "UPDATE articles SET pdf_path = ?, pdf_text = ? WHERE id = ?",
        (str(dest.relative_to(BASE_DIR)), pdf_text, article_id),
    )
    conn.commit()
    return str(dest)


def _extract_pdf_text(pdf_path: Path) -> str | None:
    """Kjører pdftotext (poppler-utils, allerede installert i miljøet) for
    å hente ut ren tekst fra PDF-en slik at innholdet blir fulltekstsøkbart
    via FTS5. Returnerer None stille ved feil (skannede PDF-er uten
    tekstlag, korrupte filer, manglende pdftotext-binær) - PDF-en er
    uansett lagret, bare ikke fulltekstsøkbar i det tilfellet."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def reindex_pdfs() -> int:
    """Kjører PDF-tekstuttrekk på nytt for artikler som har en lagret PDF
    men mangler pdf_text ennå - relevant for artikler lagt til før
    fulltekstsøk-funksjonen fantes (f.eks. de tre første seed-artiklene fra
    2026-08-07). Returnerer antall artikler som fikk oppdatert tekst."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, pdf_path FROM articles WHERE pdf_path IS NOT NULL AND pdf_text IS NULL"
        ).fetchall()
        updated = 0
        for row in rows:
            full_path = BASE_DIR / row["pdf_path"]
            if not full_path.is_file():
                continue
            text = _extract_pdf_text(full_path)
            if text:
                conn.execute(
                    "UPDATE articles SET pdf_text = ? WHERE id = ?", (text, row["id"])
                )
                updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def mark_read(article_id: int, read: bool = True) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE articles SET read_status = ? WHERE id = ?",
            ("lest" if read else "ulest", article_id),
        )
        conn.commit()
    finally:
        conn.close()


def find_by_doi(doi: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM articles WHERE doi = ?", (doi.strip(),)).fetchone()
        return _row_with_comments(conn, row) if row else None
    finally:
        conn.close()


def find_by_pmid(pmid: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM articles WHERE pmid = ?", (str(pmid).strip(),)
        ).fetchone()
        return _row_with_comments(conn, row) if row else None
    finally:
        conn.close()


def find_by_title(title: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM articles WHERE lower(title) = lower(?)", (title.strip(),)
        ).fetchone()
        return _row_with_comments(conn, row) if row else None
    finally:
        conn.close()


def search(query: str, limit: int = 20) -> list[dict]:
    """Søk i tittel/forfattere/sammendrag/PDF-fulltekst (FTS5, håndterer
    engelske ord/fraser) OG i kommentarfeltet (enkelt substreng-søk -
    kommentarene er ofte norske vurderingstekster som FTS5 sin
    standardtokenizer ikke stemmer/matcher pent mot). Returnerer union av
    begge, nyeste først."""
    conn = _connect()
    try:
        ids: dict[int, None] = {}
        try:
            fts_rows = conn.execute(
                """SELECT a.id FROM articles_fts f
                   JOIN articles a ON a.id = f.rowid
                   WHERE articles_fts MATCH ?
                   ORDER BY rank""",
                (query,),
            ).fetchall()
            for r in fts_rows:
                ids[r["id"]] = None
        except sqlite3.OperationalError:
            pass  # ugyldig FTS5-spørresyntaks (f.eks. bare tegnsetting) - hopp over
        comment_rows = conn.execute(
            """SELECT DISTINCT article_id FROM comments
               WHERE comment LIKE ? ORDER BY article_id""",
            (f"%{query}%",),
        ).fetchall()
        for r in comment_rows:
            ids[r["article_id"]] = None

        results = []
        for article_id in ids:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            if row:
                results.append(_row_with_comments(conn, row))
        results.sort(key=lambda a: a["date_added"], reverse=True)
        return results[:limit]
    finally:
        conn.close()


def list_all(limit: int = 100) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM articles ORDER BY date_added DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _row_with_comments(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    d = dict(row)
    comments = conn.execute(
        "SELECT comment, date_added FROM comments WHERE article_id = ? ORDER BY date_added",
        (row["id"],),
    ).fetchall()
    d["comments"] = [dict(c) for c in comments]
    return d


def stats() -> dict:
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        with_pdf = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE pdf_path IS NOT NULL"
        ).fetchone()[0]
        with_pdf_text = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE pdf_text IS NOT NULL"
        ).fetchone()[0]
        by_source = conn.execute(
            "SELECT source, COUNT(*) AS n FROM articles GROUP BY source"
        ).fetchall()
        return {
            "total": total,
            "with_pdf": with_pdf,
            "with_pdf_text": with_pdf_text,
            "by_source": {r["source"]: r["n"] for r in by_source},
        }
    finally:
        conn.close()


# --- BibTeX/RIS-eksport --------------------------------------------------
# Forfattere lagres internt som "Fornavn Etternavn, Fornavn Etternavn" (se
# add_article-eksemplene i README). BibTeX/RIS forventer "Etternavn,
# Fornavn"-rekkefølge - konverteringen under er beste-innsats (siste
# mellomromsseparerte ord tolkes som etternavn), ikke en garantert korrekt
# navnesplitting for alle navneformer.

def _ascii_slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]", "", ascii_text)


def _split_name(name: str) -> tuple[str, str]:
    """Beste-innsats: 'Fornavn Etternavn' -> (etternavn, fornavn)."""
    tokens = name.split()
    if len(tokens) >= 2:
        return tokens[-1], " ".join(tokens[:-1])
    return name, ""


def _authors_to_bibtex(authors: str | None) -> str | None:
    if not authors:
        return None
    names = [a.strip() for a in authors.split(",") if a.strip()]
    converted = []
    for name in names:
        last, first = _split_name(name)
        converted.append(f"{last}, {first}" if first else last)
    return " and ".join(converted)


def _authors_to_ris(authors: str | None) -> list[str]:
    if not authors:
        return []
    names = [a.strip() for a in authors.split(",") if a.strip()]
    result = []
    for name in names:
        last, first = _split_name(name)
        result.append(f"{last}, {first}" if first else last)
    return result


def _bibtex_escape(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _bibtex_citekey(row: dict, used_keys: set[str]) -> str:
    first_author = (row.get("authors") or "").split(",")[0].strip()
    last_name = _ascii_slug(first_author.split()[-1]) if first_author else ""
    year = re.sub(r"\D", "", row.get("year") or "")
    title_word = ""
    for word in re.split(r"\s+", row.get("title") or ""):
        slug = _ascii_slug(word)
        if len(slug) >= 4:
            title_word = slug.lower()
            break
    base_key = f"{last_name.lower()}{year}{title_word}" or f"ref{row['id']}"
    key = base_key
    n = 2
    while key in used_keys:
        key = f"{base_key}{n}"
        n += 1
    used_keys.add(key)
    return key


def export_bibtex(article_ids: list[int] | None = None) -> str:
    """Eksporterer artikler (alle, eller en gitt liste med id-er) til en
    BibTeX-streng. Én @article-blokk per artikkel, siteringsnøkkel bygget
    fra førsteforfatter+år+første lange tittelord (unik ved kollisjon)."""
    conn = _connect()
    try:
        rows = _select_articles(conn, article_ids)
        used_keys: set[str] = set()
        entries = []
        for row in rows:
            d = dict(row)
            key = _bibtex_citekey(d, used_keys)
            fields: list[tuple[str, str]] = []
            author_bibtex = _authors_to_bibtex(d.get("authors"))
            if author_bibtex:
                fields.append(("author", author_bibtex))
            if d.get("title"):
                fields.append(("title", d["title"]))
            if d.get("journal"):
                fields.append(("journal", d["journal"]))
            if d.get("year"):
                fields.append(("year", d["year"]))
            if d.get("doi"):
                fields.append(("doi", d["doi"]))
            if d.get("url"):
                fields.append(("url", d["url"]))
            if d.get("abstract"):
                fields.append(("abstract", d["abstract"]))
            if d.get("pmid"):
                fields.append(("note", f"PMID: {d['pmid']}"))
            field_lines = ",\n".join(
                f"  {name} = {{{_bibtex_escape(str(value))}}}" for name, value in fields
            )
            entries.append(f"@article{{{key},\n{field_lines}\n}}")
        return "\n\n".join(entries) + ("\n" if entries else "")
    finally:
        conn.close()


def export_ris(article_ids: list[int] | None = None) -> str:
    """Eksporterer artikler (alle, eller en gitt liste med id-er) til en
    RIS-streng. PMID lagres i AN-taggen (Accession Number), samme
    konvensjon PubMed selv bruker ved RIS-eksport."""
    conn = _connect()
    try:
        rows = _select_articles(conn, article_ids)
        blocks = []
        for row in rows:
            d = dict(row)
            lines = ["TY  - JOUR"]
            for author in _authors_to_ris(d.get("authors")):
                lines.append(f"AU  - {author}")
            if d.get("title"):
                lines.append(f"TI  - {d['title']}")
            if d.get("journal"):
                lines.append(f"JO  - {d['journal']}")
            if d.get("year"):
                lines.append(f"PY  - {d['year']}")
            if d.get("doi"):
                lines.append(f"DO  - {d['doi']}")
            if d.get("url"):
                lines.append(f"UR  - {d['url']}")
            if d.get("abstract"):
                lines.append(f"AB  - {d['abstract']}")
            if d.get("pmid"):
                lines.append(f"AN  - {d['pmid']}")
            lines.append("ER  - ")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + ("\n" if blocks else "")
    finally:
        conn.close()


def _select_articles(conn: sqlite3.Connection, article_ids: list[int] | None):
    if article_ids:
        placeholders = ",".join("?" * len(article_ids))
        return conn.execute(
            f"SELECT * FROM articles WHERE id IN ({placeholders}) ORDER BY id",
            article_ids,
        ).fetchall()
    return conn.execute("SELECT * FROM articles ORDER BY id").fetchall()


# --- BibTeX-import ---------------------------------------------------------
# Hånd-skrevet parser (ingen bibtexparser-avhengighet, i tråd med resten av
# modulen) - dekker standard .bib-filer eksportert fra EndNote/Zotero/
# Mendeley/PubMed: {}- eller ""-avgrensede feltverdier med balanserte
# krøllparenteser innenfor verdien (f.eks. title = {{AI} i klinikken}).

def _split_bibtex_entries(text: str) -> list[str]:
    entries = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "@":
            start = i
            depth = 0
            opened = False
            j = i
            while j < n:
                if text[j] == "{":
                    depth += 1
                    opened = True
                elif text[j] == "}":
                    depth -= 1
                    if opened and depth == 0:
                        j += 1
                        break
                j += 1
            entries.append(text[start:j])
            i = j
        else:
            i += 1
    return entries


def _parse_bibtex_entry(raw: str) -> dict | None:
    m = re.match(r"@(\w+)\s*\{\s*([^,\s]*)\s*,", raw, re.DOTALL)
    if not m:
        return None
    entry_type = m.group(1).strip().lower()
    if entry_type in {"comment", "string", "preamble"}:
        return None

    body = raw[m.end():]
    if body.rstrip().endswith("}"):
        body = body.rstrip()[:-1]

    fields: dict[str, str] = {}
    pos, body_len = 0, len(body)
    while pos < body_len:
        fm = re.match(r"\s*,?\s*([a-zA-Z][\w:-]*)\s*=\s*", body[pos:], re.DOTALL)
        if not fm:
            break
        field_name = fm.group(1).strip().lower()
        pos += fm.end()
        if pos >= body_len:
            break
        if body[pos] == "{":
            depth, start, k = 1, pos + 1, pos + 1
            while k < body_len and depth > 0:
                if body[k] == "{":
                    depth += 1
                elif body[k] == "}":
                    depth -= 1
                k += 1
            value = body[start:k - 1]
            pos = k
        elif body[pos] == '"':
            start, k = pos + 1, pos + 1
            while k < body_len and body[k] != '"':
                k += 1
            value = body[start:k]
            pos = k + 1
        else:
            m2 = re.match(r"([^,]*)", body[pos:])
            value = m2.group(1) if m2 else ""
            pos += len(value)
        fields[field_name] = re.sub(r"\s+", " ", value).strip()

    return {"type": entry_type, "fields": fields}


def _name_lastfirst_to_storage(name: str) -> str:
    """'Etternavn, Fornavn' -> 'Fornavn Etternavn' (brukt av RIS/nbib-import
    der hvert navn allerede kommer som én egen 'Last, First'-streng)."""
    name = re.sub(r"\s+", " ", name).strip()
    if "," in name:
        last, _, first = name.partition(",")
        return f"{first.strip()} {last.strip()}".strip()
    return name


def _lastfirst_list_to_storage(names: list[str]) -> str | None:
    converted = [_name_lastfirst_to_storage(n) for n in names if n and n.strip()]
    return ", ".join(converted) if converted else None


def _bibtex_authors_to_storage(raw: str) -> str | None:
    if not raw:
        return None
    parts = [p.strip() for p in re.split(r"\s+and\s+", raw) if p.strip()]
    return _lastfirst_list_to_storage(parts)


def _try_fetch_oa_pdf(
    doi: str | None, title: str | None, contact_email: str
) -> bytes | None:
    """Beste-innsats: finn og last ned en åpen-tilgang-PDF via Unpaywall
    (DOI) og deretter Semantic Scholar (DOI, så tittel) som fallback.
    Begge er gratis, nøkkelfrie API-er som kun peker til lovlig
    open-access-innhold (forlags- eller repository-versjon) - ingen
    betalingsmur omgås og ingen blokkering forsøkes omgått. Returnerer
    None stille hvis ingen åpen PDF finnes (vanligste utfall for
    lukket-tilgang-tidsskrifter; da må et menneske skaffe PDF-en)."""
    pdf_url = None
    landing_url = None
    if doi:
        try:
            r = requests.get(
                f"https://api.unpaywall.org/v2/{doi}",
                params={"email": contact_email}, timeout=15,
            )
            if r.ok:
                loc = r.json().get("best_oa_location") or {}
                pdf_url = loc.get("url_for_pdf")
                landing_url = loc.get("url")
        except requests.RequestException:
            pass
    if not pdf_url and doi:
        try:
            r = requests.get(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
                params={"fields": "openAccessPdf"}, timeout=15,
            )
            if r.ok:
                oa = r.json().get("openAccessPdf") or {}
                pdf_url = oa.get("url")
        except requests.RequestException:
            pass
    if not pdf_url and title:
        try:
            r = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": title, "fields": "title,openAccessPdf", "limit": 1},
                timeout=15,
            )
            if r.ok:
                papers = r.json().get("data") or []
                if papers:
                    oa = papers[0].get("openAccessPdf") or {}
                    pdf_url = oa.get("url")
        except requests.RequestException:
            pass

    if pdf_url:
        try:
            resp = requests.get(
                pdf_url, timeout=30, allow_redirects=True,
                headers={"User-Agent": "reference-manager/1.0"},
            )
            content_type = resp.headers.get("Content-Type", "").lower()
            if resp.ok and (content_type.startswith("application/pdf") or resp.content[:4] == b"%PDF"):
                return resp.content
        except requests.RequestException:
            pass

    return None


def _bibtex_entries_from_text(text: str) -> list[dict]:
    entries = []
    for raw in _split_bibtex_entries(text):
        parsed = _parse_bibtex_entry(raw)
        if parsed is None:
            continue
        f = parsed["fields"]
        doi = (f.get("doi") or "").replace("https://doi.org/", "").replace("http://doi.org/", "").strip() or None
        entries.append({
            "title": f.get("title") or None,
            "doi": doi,
            "pmid": f.get("pmid") or None,
            "authors": _bibtex_authors_to_storage(f.get("author", "")),
            "journal": f.get("journal") or f.get("booktitle") or f.get("publisher") or None,
            "year": f.get("year") or None,
            "url": f.get("url") or (f"https://doi.org/{doi}" if doi else None),
            "abstract": f.get("abstract") or None,
        })
    return entries


# --- RIS-import --------------------------------------------------------
# Tag-verdi-format: "XX  - verdi" per linje, én referanse avsluttes med
# "ER  - ". Fortsettelseslinjer uten egen tag (sjelden, men forekommer i
# eksport fra enkelte verktøy) slås sammen med forrige felt.

def _ris_entries_from_text(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    records: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    last_tag: str | None = None
    for line in text.split("\n"):
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z0-9]{2})\s+-\s?(.*)$", line)
        if m:
            tag = m.group(1).upper()
            value = m.group(2).strip()
            if tag == "ER":
                if current:
                    records.append(current)
                current, last_tag = {}, None
                continue
            if tag == "TY":
                last_tag = None
                continue
            current.setdefault(tag, []).append(value)
            last_tag = tag
        elif last_tag is not None and current:
            current[last_tag][-1] = (current[last_tag][-1] + " " + line.strip()).strip()
    if current:
        records.append(current)

    entries = []
    for tagged in records:
        doi = (tagged.get("DO") or tagged.get("DOI") or [None])[0]
        an = (tagged.get("AN") or [None])[0]
        pmid = an if an and an.strip().isdigit() else None
        year_raw = (tagged.get("PY") or tagged.get("Y1") or [None])[0]
        year = None
        if year_raw:
            ym = re.match(r"(\d{4})", year_raw)
            year = ym.group(1) if ym else None
        entries.append({
            "title": (tagged.get("TI") or tagged.get("T1") or [None])[0],
            "doi": doi,
            "pmid": pmid,
            "authors": _lastfirst_list_to_storage(tagged.get("AU") or tagged.get("A1") or []),
            "journal": (tagged.get("JO") or tagged.get("JF") or tagged.get("JA") or tagged.get("T2") or [None])[0],
            "year": year,
            "url": (tagged.get("UR") or tagged.get("L1") or [None])[0],
            "abstract": (tagged.get("AB") or tagged.get("N2") or [None])[0],
        })
    return entries


# --- PubMed MEDLINE/.nbib-import ----------------------------------------
# Samme tag-verdi-idé som RIS, men med fast bredde ("PMID- ", "TI  - ") og
# fortsettelseslinjer som er innrykket med mellomrom i stedet for en egen
# tag - det er det som skiller et .nbib-format fra RIS.

def _nbib_entries_from_text(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n+", text.strip())
    entries = []
    for block in blocks:
        if not block.strip():
            continue
        tagged: dict[str, list[str]] = {}
        last_tag: str | None = None
        for line in block.split("\n"):
            if not line.strip():
                continue
            m = re.match(r"^([A-Za-z]{2,4})\s*-\s?(.*)$", line)
            if m and not line[:1].isspace():
                tag = m.group(1).upper()
                tagged.setdefault(tag, []).append(m.group(2).strip())
                last_tag = tag
            elif last_tag is not None:
                tagged[last_tag][-1] = (tagged[last_tag][-1] + " " + line.strip()).strip()
        if not tagged:
            continue

        pmid = (tagged.get("PMID") or [None])[0]
        year = None
        dp = (tagged.get("DP") or [None])[0]
        if dp:
            ym = re.match(r"(\d{4})", dp)
            year = ym.group(1) if ym else None

        doi = None
        for tag in ("LID", "AID"):
            for value in tagged.get(tag, []):
                if "[doi]" in value.lower():
                    doi = re.sub(r"\s*\[doi\]\s*$", "", value, flags=re.IGNORECASE).strip()
                    break
            if doi:
                break

        if doi:
            url = f"https://doi.org/{doi}"
        elif pmid:
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        else:
            url = None

        entries.append({
            "title": (tagged.get("TI") or [None])[0],
            "doi": doi,
            "pmid": pmid,
            "authors": _lastfirst_list_to_storage(tagged.get("FAU") or tagged.get("AU") or []),
            "journal": (tagged.get("JT") or tagged.get("TA") or [None])[0],
            "year": year,
            "url": url,
            "abstract": " ".join(tagged.get("AB", [])).strip() or None,
        })
    return entries


def _import_normalized_entries(
    entries: list[dict],
    source: str,
    fetch_pdf: bool,
    contact_email: str,
) -> list[dict]:
    """Delt kjerne for import_bibtex/import_ris/import_nbib: tar en liste
    med normaliserte felt-dicts (title/doi/pmid/authors/journal/year/url/
    abstract) og lagrer hver i databasen med vanlig dedup + valgfri
    åpen-tilgang-PDF-henting. Returnerer én dict per referanse:
    {"title", "id", "status", "pdf"} der status er "ny"/"fantes allerede"/
    "feil: ..." og pdf er "lastet ned"/"ikke funnet (åpen tilgang)"/
    "hadde allerede PDF"/"ikke forsøkt"/"feil ved lagring"."""
    results = []
    for entry in entries:
        title = entry.get("title")
        if not title:
            results.append({"title": "(uten tittel)", "id": None, "status": "feil: mangler tittel", "pdf": "ikke forsøkt"})
            continue

        doi = entry.get("doi")
        pmid = entry.get("pmid")

        if doi:
            was_existing = find_by_doi(doi) is not None
        elif pmid:
            was_existing = find_by_pmid(pmid) is not None
        else:
            was_existing = find_by_title(title) is not None

        try:
            article_id = add_article(
                title=title, doi=doi, pmid=pmid, authors=entry.get("authors"),
                journal=entry.get("journal"), year=entry.get("year"),
                url=entry.get("url"), abstract=entry.get("abstract"),
                source=source,
            )
        except RefDBError as exc:
            results.append({"title": title, "id": None, "status": f"feil: {exc}", "pdf": "ikke forsøkt"})
            continue

        current = find_by_doi(doi) if doi else (find_by_pmid(pmid) if pmid else find_by_title(title))
        already_has_pdf = bool(current and current.get("pdf_path"))

        pdf_status = "ikke forsøkt"
        if already_has_pdf:
            pdf_status = "hadde allerede PDF"
        elif fetch_pdf:
            pdf_bytes = _try_fetch_oa_pdf(doi=doi, title=title, contact_email=contact_email)
            if pdf_bytes:
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                try:
                    tmp.write(pdf_bytes)
                    tmp.close()
                    attach_pdf(article_id, tmp.name)
                    pdf_status = "lastet ned"
                except RefDBError:
                    pdf_status = "feil ved lagring"
                finally:
                    os.unlink(tmp.name)
            else:
                pdf_status = "ikke funnet (åpen tilgang)"
            time.sleep(0.5)  # høflighetspause mot gratis, nøkkelfrie API-er

        results.append({
            "title": title,
            "id": article_id,
            "status": "fantes allerede" if was_existing else "ny",
            "pdf": pdf_status,
        })

    return results


def import_bibtex(
    file_path: str,
    source: str = "bibtex-import",
    fetch_pdf: bool = True,
    contact_email: str = os.environ.get("CONTACT_EMAIL", "you@example.org"),
) -> list[dict]:
    """Leser en .bib-fil (hånd-skrevet parser, dekker EndNote/Zotero/
    Mendeley/PubMed-eksport) og lagrer hver referanse - se
    _import_normalized_entries for felles dedup/PDF-oppførsel."""
    path = Path(file_path)
    if not path.is_file():
        raise RefDBError(f"Fant ikke bib-fil: {file_path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    entries = _bibtex_entries_from_text(text)
    return _import_normalized_entries(entries, source=source, fetch_pdf=fetch_pdf, contact_email=contact_email)


def import_ris(
    file_path: str,
    source: str = "ris-import",
    fetch_pdf: bool = True,
    contact_email: str = os.environ.get("CONTACT_EMAIL", "you@example.org"),
) -> list[dict]:
    """Leser en .ris-fil (EndNote/Zotero/Mendeley/PubMed RIS-eksport) og
    lagrer hver referanse - se _import_normalized_entries for felles
    dedup/PDF-oppførsel."""
    path = Path(file_path)
    if not path.is_file():
        raise RefDBError(f"Fant ikke ris-fil: {file_path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    entries = _ris_entries_from_text(text)
    return _import_normalized_entries(entries, source=source, fetch_pdf=fetch_pdf, contact_email=contact_email)


def import_nbib(
    file_path: str,
    source: str = "nbib-import",
    fetch_pdf: bool = True,
    contact_email: str = os.environ.get("CONTACT_EMAIL", "you@example.org"),
) -> list[dict]:
    """Leser en .nbib-fil (PubMed sitt eget MEDLINE-eksportformat - "Send
    to > Citation manager" på PubMed) og lagrer hver referanse - se
    _import_normalized_entries for felles dedup/PDF-oppførsel."""
    path = Path(file_path)
    if not path.is_file():
        raise RefDBError(f"Fant ikke nbib-fil: {file_path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    entries = _nbib_entries_from_text(text)
    return _import_normalized_entries(entries, source=source, fetch_pdf=fetch_pdf, contact_email=contact_email)


def _detect_format(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    if suffix in (".bib", ".bibtex"):
        return "bibtex"
    if suffix == ".ris":
        return "ris"
    if suffix in (".nbib", ".medline"):
        return "nbib"
    stripped = text.lstrip()
    if stripped.startswith("@"):
        return "bibtex"
    if re.search(r"^PMID-\s", text, re.MULTILINE):
        return "nbib"
    if re.search(r"^TY\s*-\s", text, re.MULTILINE):
        return "ris"
    raise RefDBError(
        f"Klarte ikke å gjenkjenne filformat for {path.name} "
        "(fant verken .bib/@-syntaks, .ris/TY -, eller .nbib/PMID- i innholdet)"
    )


def import_file(
    file_path: str,
    source: str | None = None,
    fetch_pdf: bool = True,
    contact_email: str = os.environ.get("CONTACT_EMAIL", "you@example.org"),
    fmt: str | None = None,
) -> list[dict]:
    """Autodetekterer format (BibTeX/.bib, RIS/.ris, PubMed MEDLINE/.nbib)
    ut fra filendelse og deretter innhold, og importerer via riktig
    parser. Bruk `fmt` for å tvinge et format i stedet for autodeteksjon.
    Dette er inngangspunktet ment for "send meg en fil, uansett format" -
    de format-spesifikke import_bibtex/import_ris/import_nbib fungerer
    fortsatt som før for direkte bruk."""
    path = Path(file_path)
    if not path.is_file():
        raise RefDBError(f"Fant ikke fil: {file_path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    detected = fmt or _detect_format(path, text)
    if detected == "bibtex":
        return import_bibtex(file_path, source=source or "bibtex-import", fetch_pdf=fetch_pdf, contact_email=contact_email)
    if detected == "ris":
        return import_ris(file_path, source=source or "ris-import", fetch_pdf=fetch_pdf, contact_email=contact_email)
    if detected == "nbib":
        return import_nbib(file_path, source=source or "nbib-import", fetch_pdf=fetch_pdf, contact_email=contact_email)
    raise RefDBError(f"Ukjent format: {detected}")


def _print_import_summary(results: list[dict], file_path: str) -> None:
    n_new = sum(1 for r in results if r["status"] == "ny")
    n_existing = sum(1 for r in results if r["status"] == "fantes allerede")
    n_pdf = sum(1 for r in results if r["pdf"] == "lastet ned")
    print(f"{len(results)} referanser lest fra {file_path}")
    print(f"  - {n_new} nye, {n_existing} fantes allerede")
    print(f"  - {n_pdf} PDF-er lastet ned automatisk (åpen tilgang)")
    for r in results:
        if r["status"].startswith("feil"):
            print(f"  FEIL: {r['title']} - {r['status']}")


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="agentens referansedatabase")
    sub = parser.add_subparsers(dest="command")

    p_import_any = sub.add_parser(
        "import",
        help="importer referanser fra en fil - autodetekterer format (BibTeX .bib, RIS .ris, PubMed MEDLINE .nbib)",
    )
    p_import_any.add_argument("file")
    p_import_any.add_argument("--format", choices=["bibtex", "ris", "nbib"], help="tving format i stedet for autodeteksjon")
    p_import_any.add_argument("--no-pdf", action="store_true", help="ikke forsøk å hente åpen-tilgang-PDF automatisk")
    p_import_any.add_argument("--source", help="standard: bibtex-import/ris-import/nbib-import ut fra gjenkjent format")

    p_import = sub.add_parser("import-bibtex", help="importer referanser fra en .bib-fil")
    p_import.add_argument("file")
    p_import.add_argument("--no-pdf", action="store_true", help="ikke forsøk å hente åpen-tilgang-PDF automatisk")
    p_import.add_argument("--source", default="bibtex-import")

    p_import_ris = sub.add_parser("import-ris", help="importer referanser fra en .ris-fil")
    p_import_ris.add_argument("file")
    p_import_ris.add_argument("--no-pdf", action="store_true", help="ikke forsøk å hente åpen-tilgang-PDF automatisk")
    p_import_ris.add_argument("--source", default="ris-import")

    p_import_nbib = sub.add_parser("import-nbib", help="importer referanser fra en PubMed .nbib-fil")
    p_import_nbib.add_argument("file")
    p_import_nbib.add_argument("--no-pdf", action="store_true", help="ikke forsøk å hente åpen-tilgang-PDF automatisk")
    p_import_nbib.add_argument("--source", default="nbib-import")

    p_export = sub.add_parser("export", help="eksporter biblioteket til BibTeX eller RIS")
    p_export.add_argument("format", choices=["bibtex", "ris"])
    p_export.add_argument("output")
    p_export.add_argument("--ids", help="komma-separert liste med artikkel-id-er (standard: alle)")

    sub.add_parser("reindex-pdf", help="hent PDF-fulltekst på nytt for artikler som mangler det")

    args = parser.parse_args()

    if args.command == "import":
        results = import_file(args.file, source=args.source, fetch_pdf=not args.no_pdf, fmt=args.format)
        _print_import_summary(results, args.file)
    elif args.command == "import-bibtex":
        results = import_bibtex(args.file, source=args.source, fetch_pdf=not args.no_pdf)
        _print_import_summary(results, args.file)
    elif args.command == "import-ris":
        results = import_ris(args.file, source=args.source, fetch_pdf=not args.no_pdf)
        _print_import_summary(results, args.file)
    elif args.command == "import-nbib":
        results = import_nbib(args.file, source=args.source, fetch_pdf=not args.no_pdf)
        _print_import_summary(results, args.file)
    elif args.command == "export":
        ids = [int(x) for x in args.ids.split(",")] if args.ids else None
        content = export_bibtex(ids) if args.format == "bibtex" else export_ris(ids)
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"Skrev {args.output}")
    elif args.command == "reindex-pdf":
        n = reindex_pdfs()
        print(f"{n} artikler fikk oppdatert PDF-fulltekst")
    else:
        s = stats()
        print(f"{s['total']} artikler i databasen ({s['with_pdf']} med PDF, {s['with_pdf_text']} fulltekstsøkbare)")
        for src, n in s["by_source"].items():
            print(f"  - {src}: {n}")


if __name__ == "__main__":
    _cli()
