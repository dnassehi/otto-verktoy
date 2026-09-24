#!/usr/bin/env python3
"""
Søker PubMed/MEDLINE via NCBI E-utilities (offentlig API, ingen nøkkel
strengt nødvendig for dette volumet - én kjøring i uken).

To søk kombineres og deduplisereres på PMID:
  A) Bredt emnesøk i hele PubMed, siste N dager: KI/teknologi-nøkkelord AND
     allmennmedisin/dehumanisering/arbeidsflyt-nøkkelord.
  B) Tidsskrift-skopet søk (config/journals.json), siste N dager, med et
     videre nøkkelordnett (fanger opp saker som ikke nødvendigvis nevner
     "AI" eksplisitt, men handler om teknologi/automatisering/arbeidsflyt).

Returnerer liste av {pmid, title, abstract, journal, date, authors, url}.
"""
from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET

import requests

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")

TOPIC_QUERY = (
    '("artificial intelligence"[tiab] OR "generative AI"[tiab] OR '
    '"large language model*"[tiab] OR "machine learning"[tiab] OR '
    'chatbot*[tiab] OR "clinical decision support"[tiab]) AND '
    '("general practice"[tiab] OR "primary care"[tiab] OR "family medicine"[tiab] OR '
    '"family practice"[tiab] OR "patient-physician relation*"[tiab] OR '
    '"physician-patient relation*"[tiab] OR "doctor-patient relation*"[tiab] OR '
    'dehumaniz*[tiab] OR dehumanis*[tiab] OR "clinical workflow"[tiab] OR '
    '"clinical work"[tiab])'
)

JOURNAL_KEYWORDS = (
    '(artificial intelligence[tiab] OR "generative AI"[tiab] OR '
    '"large language model*"[tiab] OR "machine learning"[tiab] OR '
    'chatbot*[tiab] OR digital health[tiab] OR automation[tiab] OR '
    '"clinical workflow"[tiab] OR technology[tiab])'
)


def _esearch(query: str, days: int, retmax: int = 100) -> list[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "reldate": days,
        "datetype": "pdat",
        "retmax": retmax,
        "retmode": "json",
    }
    resp = requests.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("esearchresult", {}).get("idlist", [])


def _efetch(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    results = []
    # NCBI ber om batcher <=200 og <=3 req/sek uten API-nøkkel
    for i in range(0, len(pmids), 150):
        batch = pmids[i : i + 150]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
        resp = requests.get(f"{EUTILS}/efetch.fcgi", params=params, timeout=60)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else None
            title_el = article.find(".//ArticleTitle")
            title = "".join(title_el.itertext()).strip() if title_el is not None else "(uten tittel)"
            abstract_parts = [
                "".join(el.itertext()).strip()
                for el in article.findall(".//Abstract/AbstractText")
            ]
            abstract = " ".join(abstract_parts).strip()
            journal_el = article.find(".//Journal/Title")
            journal = journal_el.text if journal_el is not None else "(ukjent tidsskrift)"
            year_el = article.find(".//PubDate/Year")
            medline_date_el = article.find(".//PubDate/MedlineDate")
            date = year_el.text if year_el is not None else (
                medline_date_el.text if medline_date_el is not None else "ukjent dato"
            )
            authors = []
            for author in article.findall(".//AuthorList/Author")[:3]:
                last = author.find("LastName")
                if last is not None:
                    authors.append(last.text)

            # Interessekonflikt-erklæring - PubMed har denne strukturert for
            # de fleste tidsskrifter som krever den (ikke behov for
            # internett-oppslag utover selve E-utilities-kallet).
            coi_el = article.find(".//CoiStatement")
            coi_statement = "".join(coi_el.itertext()).strip() if coi_el is not None else None

            # Finansieringskilder (bevilgninger/sponsor)
            grants = []
            for grant in article.findall(".//GrantList/Grant"):
                agency = grant.find("Agency")
                if agency is not None and agency.text:
                    grants.append(agency.text)

            # Publikasjonstype (RCT, review, letter, preprint osv.) - viktig
            # for å skille uavhengig forskning fra opinion/markedsføring
            pub_types = [
                pt.text for pt in article.findall(".//PublicationTypeList/PublicationType")
                if pt.text
            ]

            results.append({
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "date": date,
                "authors": authors,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source": "PubMed",
                "coi_statement": coi_statement,
                "funding": grants,
                "publication_types": pub_types,
            })
        time.sleep(0.4)
    return results


def load_journals() -> list[str]:
    path = os.path.join(CONFIG_DIR, "journals.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [j["name"] for j in data["journals"]]


def search_pubmed(days: int = 7) -> list[dict]:
    pmids = set()

    topic_ids = _esearch(TOPIC_QUERY, days)
    pmids.update(topic_ids)

    journals = load_journals()
    journal_filter = " OR ".join(f'"{j}"[ta]' for j in journals)
    journal_query = f"({journal_filter}) AND {JOURNAL_KEYWORDS}"
    journal_ids = _esearch(journal_query, days)
    pmids.update(journal_ids)

    return _efetch(sorted(pmids))


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    hits = search_pubmed(days)
    print(f"Fant {len(hits)} unike PubMed-treff siste {days} dager.")
    for h in hits:
        print(f"- [{h['journal']}] {h['title']} ({h['pmid']})")
