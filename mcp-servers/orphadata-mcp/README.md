# orphadata-mcp

Egenbygget MCP-wrapper rundt Orphadata, Orphanets strukturerte kunnskapsbase
om sjeldne sykdommer, satt opp 2026-08-26. Samme
mønster som eurostat-mcp/who-mcp (Python, `mcp==1.29.0`, egen venv).

## API-et

- Base: `https://api.orphadata.com`
- Full OpenAPI-spec: `https://api.orphadata.com/openapi.json`
- Ingen autentiseringsnøkkel nødvendig, CC-BY-4.0-lisensiert data.
- Dekker klassifisering, kryssreferanser (ICD-10/ICD-11/OMIM/UMLS/MeSH),
  assosierte gener, HPO-fenotype-assosiasjoner og epidemiologi
  (prevalens/insidens) for alle sjeldne sykdommer i Orphanet.

## Verktøy (MCP-server `orphadata`)

1. **`orphadata_search_disease`** — søk på sykdomsnavn (f.eks. "marfan"),
   returnerer ORPHAcode(r) + ICD-10/11-kryssreferanser.
2. **`orphadata_get_disease`** — full forstyrrelsespost for et ORPHAcode:
   synonymer, type/gruppe, kryssreferanser (ICD-10/11, OMIM, UMLS, MeSH,
   MedDRA).
3. **`orphadata_get_genes`** — assosierte gener (HGNC/OMIM/Ensembl/
   ClinVar/UniProt-referanser, assosiasjonstype).
4. **`orphadata_get_phenotypes`** — HPO-fenotyper med frekvensklasse
   (f.eks. "Very frequent (99-80%)") og om det er diagnostisk kriterium.
5. **`orphadata_get_epidemiology`** — prevalens/insidens-klasse, geografisk
   område, kilde.

## Oppsett

- `server.py` — MCP-server (fem verktøy over).
- Egen venv: `.venv-orphadata-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `orphadata` via
  `openclaw mcp add orphadata --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor orphadata --probe`.

## Testet 2026-08-26

Hele kjeden verifisert direkte mot `server.py` sine Python-funksjoner (live
API, ingen mocks):

1. `orphadata_search_disease("marfan")` → ORPHAcode 558, med ICD-10 Q87.4
   og ICD-11 LD28.01 kryssreferanser.
2. `orphadata_get_disease(558)` → full forstyrrelsespost for Marfan
   syndrom.
3. `orphadata_get_genes(586)` (cystisk fibrose) → gen-assosiasjon inkl.
   ClinVar/HGNC/OMIM/Ensembl-referanser.
4. `orphadata_get_phenotypes(558)` → HPO-termer inkl. "Pectus carinatum"
   (HP:0000768, "Very frequent").
5. `orphadata_get_epidemiology(558)` → prevalensklasse "1-5 / 10 000"
   (Europa).

Merk: `orphadata_get_genes` returnerer feil/tom respons for ORPHAcoder uten
dokumentert gen-assosiasjon i Orphanets database (ikke en feil i
verktøyet).
