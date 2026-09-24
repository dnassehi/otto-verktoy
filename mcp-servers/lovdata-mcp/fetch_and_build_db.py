#!/usr/bin/env python3
"""Last ned Lovdatas gratis offentlige datasett (NLOD 2.0, ingen konto krevd)
og bygg en lokal SQLite FTS5-database for fulltekstsøk og paragrafoppslag.

Kilde: https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2
       https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2
"""
import os
import bz2
import io
import re
import sqlite3
import sys
import tarfile
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
DB_PATH = HERE / "lovdata.db"

SOURCES = {
    "https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2": "lov",
    "https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2": "forskrift",
}

# Undermapper i forskrift-arkivet og hva de faktisk er
SUBTYPE_LABELS = {
    "nl": "lov",
    "sf": "sentral forskrift",
    "del": "delegeringsvedtak",
    "ins": "instruks",
    "stv": "stortingsvedtak",
}


def fetch_archive(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"my-agent/1.0 (contact: {os.environ.get('CONTACT_EMAIL', 'you@example.org')})"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def meta_field(soup, cls):
    dd = soup.find("dd", class_=cls)
    return dd.get_text(strip=True) if dd else None


def clean_text(el) -> str:
    text = el.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_document(xml_bytes: bytes, subtype: str):
    soup = BeautifulSoup(xml_bytes, "lxml")
    tittel = meta_field(soup, "title")
    korttittel = meta_field(soup, "titleShort")
    legacy_id = meta_field(soup, "legacyID")
    ref_id = meta_field(soup, "refid")
    dato_ikraft = meta_field(soup, "dateInForce")
    sist_endret = meta_field(soup, "lastChangeInForce")
    if not tittel or not ref_id:
        return None, []

    main = soup.find("main", class_="documentBody")
    if main is None:
        return {
            "tittel": tittel, "korttittel": korttittel, "legacy_id": legacy_id,
            "ref_id": ref_id, "dato_ikraft": dato_ikraft, "sist_endret": sist_endret,
            "subtype": subtype,
        }, []

    paragrafer = []
    for section in main.find_all("section", class_="section", recursive=True):
        h2 = section.find("h2", recursive=False)
        kapittel_tittel = clean_text(h2) if h2 else None
        for art in section.find_all("article", class_="legalArticle", recursive=True):
            if art.find_parent("article", class_="legalArticle") is not None:
                continue  # unngå nøstede duplikater
            data_name = art.get("data-name") or ""
            url_path = art.get("data-lovdata-url") or art.get("data-lovdata-URL") or ""
            header = art.find("h3", class_="legalArticleHeader")
            paragraf_tittel = None
            if header:
                title_span = header.find("span", class_="legalArticleTitle")
                paragraf_tittel = clean_text(title_span) if title_span else None
            text = clean_text(art)
            if not text:
                continue
            paragrafer.append({
                "paragraf": data_name,
                "paragraf_tittel": paragraf_tittel,
                "kapittel_tittel": kapittel_tittel,
                "text": text,
                "url_path": url_path,
            })

    # Noen forskrifter/vedtak har ingen <section>, bare <article> direkte i <main>
    if not paragrafer:
        for art in main.find_all("article", class_="legalArticle", recursive=True):
            if art.find_parent("article", class_="legalArticle") is not None:
                continue
            data_name = art.get("data-name") or ""
            url_path = art.get("data-lovdata-url") or art.get("data-lovdata-URL") or ""
            header = art.find("h3", class_="legalArticleHeader")
            paragraf_tittel = None
            if header:
                title_span = header.find("span", class_="legalArticleTitle")
                paragraf_tittel = clean_text(title_span) if title_span else None
            text = clean_text(art)
            if not text:
                continue
            paragrafer.append({
                "paragraf": data_name, "paragraf_tittel": paragraf_tittel,
                "kapittel_tittel": None, "text": text, "url_path": url_path,
            })

    doc = {
        "tittel": tittel, "korttittel": korttittel, "legacy_id": legacy_id,
        "ref_id": ref_id, "dato_ikraft": dato_ikraft, "sist_endret": sist_endret,
        "subtype": subtype,
    }
    return doc, paragrafer


def build_db(tmp_files):
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE dokumenter (
            id INTEGER PRIMARY KEY,
            doc_type TEXT NOT NULL,
            subtype TEXT NOT NULL,
            tittel TEXT NOT NULL,
            korttittel TEXT,
            legacy_id TEXT,
            ref_id TEXT NOT NULL,
            dato_ikraft TEXT,
            sist_endret TEXT
        );
        CREATE TABLE paragrafer (
            id INTEGER PRIMARY KEY,
            dokument_id INTEGER NOT NULL REFERENCES dokumenter(id),
            paragraf TEXT,
            paragraf_tittel TEXT,
            kapittel_tittel TEXT,
            text TEXT NOT NULL,
            url TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE paragrafer_fts USING fts5(
            tittel, korttittel, paragraf, paragraf_tittel, text,
            content='', tokenize='unicode61 remove_diacritics 2'
        );
        CREATE INDEX idx_dokumenter_reftype ON dokumenter(doc_type, korttittel);
        CREATE INDEX idx_paragrafer_dok ON paragrafer(dokument_id);
        """
    )

    n_docs = 0
    n_paragrafer = 0
    for path, doc_type, subtype in tmp_files:
        try:
            xml_bytes = path.read_bytes()
        except Exception as e:
            print(f"WARN: klarte ikke lese {path}: {e}", file=sys.stderr)
            continue
        doc, paragrafer = parse_document(xml_bytes, subtype)
        if doc is None:
            continue
        cur = conn.execute(
            "INSERT INTO dokumenter (doc_type, subtype, tittel, korttittel, legacy_id, ref_id, dato_ikraft, sist_endret) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (doc_type, doc["subtype"], doc["tittel"], doc["korttittel"], doc["legacy_id"],
             doc["ref_id"], doc["dato_ikraft"], doc["sist_endret"]),
        )
        dokument_id = cur.lastrowid
        n_docs += 1
        for p in paragrafer:
            url = f"https://lovdata.no/dokument/{p['url_path']}" if p["url_path"] else f"https://lovdata.no/dokument/{doc['ref_id'].upper()}"
            cur2 = conn.execute(
                "INSERT INTO paragrafer (dokument_id, paragraf, paragraf_tittel, kapittel_tittel, text, url) "
                "VALUES (?,?,?,?,?,?)",
                (dokument_id, p["paragraf"], p["paragraf_tittel"], p["kapittel_tittel"], p["text"], url),
            )
            paragraf_id = cur2.lastrowid
            conn.execute(
                "INSERT INTO paragrafer_fts (rowid, tittel, korttittel, paragraf, paragraf_tittel, text) "
                "VALUES (?,?,?,?,?,?)",
                (paragraf_id, doc["tittel"], doc["korttittel"] or "", p["paragraf"] or "",
                 p["paragraf_tittel"] or "", p["text"]),
            )
            n_paragrafer += 1
    conn.commit()
    conn.close()
    print(f"Bygget {DB_PATH} med {n_docs} dokumenter og {n_paragrafer} paragrafer.")


def main():
    import tempfile
    all_files = []  # (path, doc_type, subtype)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        for url, doc_type in SOURCES.items():
            print(f"Laster ned {url} ...")
            data = fetch_archive(url)
            print(f"  {len(data)/1e6:.1f} MB, pakker ut ...")
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as tar:
                extract_dir = tmpdir / doc_type
                tar.extractall(extract_dir, filter="data")
            for xml_file in extract_dir.rglob("*.xml"):
                subdir = xml_file.parent.name  # nl / sf / del / ins
                subtype = SUBTYPE_LABELS.get(subdir, subdir)
                effective_type = "lov" if subdir == "nl" else "forskrift"
                all_files.append((xml_file, effective_type, subtype))
            print(f"  {sum(1 for _ in extract_dir.rglob('*.xml'))} dokumenter funnet")
        build_db(all_files)


if __name__ == "__main__":
    main()
