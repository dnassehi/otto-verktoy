# reference-manager: agentens egen referansedatabase

En lokal referansedatabase agenten kan bruke til å huske artikler den har funnet, fått tilsendt
eller vurdert: metadata, PDF (når den finnes) og kommentarer med kritisk vurdering. Koden ligger i
[`../lib/refdb.py`](../lib/refdb.py). Denne mappen inneholder bare data (`db/`, `pdfs/`), og begge er
tomme i repoet og ignorert av git.

## Arkitektur

- **Database:** `db/library.db` (SQLite). Tabeller: `articles` (metadata, `pdf_path`, `pdf_text`,
  `read_status`), `comments` (fritekst, mange per artikkel) og `articles_fts` (FTS5 på tittel,
  forfattere, sammendrag og PDF-tekst).
- **PDF:** `pdfs/<id>.pdf`. Ved vedlegging kjøres `pdftotext` (poppler-utils), slik at innholdet blir
  fulltekstsøkbart. Skannede PDF-er uten tekstlag lagres, men er ikke søkbare.
- **Åpen tilgang:** `_try_fetch_oa_pdf` slår opp lovlig åpen PDF via Unpaywall og Semantic Scholar.
  Finnes ingen, må et menneske skaffe PDF-en (via biblioteket eller forlaget). Verktøyet forsøker
  ikke å omgå betalingsmurer eller bot-sperrer.
- **Kildefelt:** `VALID_SOURCES` i `refdb.py` (research-monitor, telegram, epost, manual, importer).

## Bruk

```python
from lib import refdb
article_id = refdb.add_article(title="...", doi="10.xxxx/...", source="manual")  # returnerer id
refdb.add_comment(article_id, "Tillitsgrad middels: sponset av leverandør, se COI.")
refdb.attach_pdf(article_id, "/sti/til/fil.pdf")
refdb.search("omsorgsetikk")
refdb.export_bibtex()
```

CLI (importer og eksport uten agent):

```bash
python3 -m lib.refdb import biblioteket.bib          # BibTeX, RIS eller PubMed .nbib (autodetekterer)
python3 -m lib.refdb export bibtex ut.bib
python3 -m lib.refdb reindex-pdf
```

Sett `CONTACT_EMAIL` til din egen adresse (Unpaywall krever en kontaktadresse).

## Anbefaling til agenten

Legg inn en kort kommentar med tillitsgrad og begrunnelse hver gang en artikkel er vurdert
(finansiering/COI, metode, hva som mangler). Da kan du senere søke på egne vurderinger.
