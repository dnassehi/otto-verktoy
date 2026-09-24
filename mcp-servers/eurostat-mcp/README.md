# eurostat-mcp

Egenbygget MCP-wrapper rundt Eurostats offentlige dissemination-API, satt
opp 2026-08-16 (etter WHO/World Bank/MET-oppsettet
samme kveld). Samme mønster som who-mcp/worldbank-mcp (Python,
`mcp==1.29.0`, egen venv).

## API-et

- Table of contents (katalog/søk): `https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt`
  — TSV-liste over alle ~7000 datasett-koder/titler/hierarki.
- Data (JSON-stat 2.0): `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{code}`
- Ingen autentiseringsnøkkel nødvendig.
- Dekker EU/EØS-land + kandidatland: demografi, økonomi, arbeidsmarked,
  helse, miljø, energi, utdanning m.m. — samme rolle for EU-sammenligning
  som worldbank-mcp spiller globalt.

## Verktøy (MCP-server `eurostat`)

1. **`eurostat_search_datasets`** — fritekstsøk i datasett-titler (f.eks.
   "life expectancy", "unemployment", "renewable energy"). Returnerer
   dataset-koder til bruk i de to andre verktøyene.
2. **`eurostat_dataset_info`** — henter dimensjonsstrukturen for et datasett
   (geo, sex, age, unit, osv.) og hvilke koder som faktisk finnes, ved å
   bruke `lastTimePeriod=1` (siste tidsperiode) som representativt utvalg
   slik at kallet holdes lite. Kjøres FØR `eurostat_get_data`.
3. **`eurostat_get_data`** — henter faktiske data (JSON-stat 2.0), filtrert
   på dimensjonskoder (f.eks. `geo: ["NO","DK","SE"]`, `time: ["2023"]`).

## Oppsett

- `server.py` — MCP-server (tre verktøy over).
- Egen venv: `.venv-eurostat-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `eurostat` via
  `openclaw mcp add eurostat --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor eurostat --probe`.

## Testet 2026-08-16

Hele kjeden verifisert direkte mot server.py sine Python-funksjoner (live
API, ingen mocks):

1. `eurostat_search_datasets("life expectancy")` → traff bl.a.
   `demo_r_mlifexp` (levealder etter NUTS 2-region) og `tgs00101`.
2. `eurostat_dataset_info("DEMO_PJAN")` (befolkning 1. januar) →
   6 dimensjoner (freq, unit, age, sex, geo, time), 59 geo-koder, 103
   alderskategorier for siste tidsperiode.
3. `eurostat_get_data("DEMO_PJAN", {"geo":["NO","DK","SE"],"sex":["T"],
   "age":["TOTAL"],"time":["2023"]})` → Norge 5 488 984, Danmark 5 932 654,
   Sverige 10 521 556 — måltall direkte fra Eurostats kilde, verifisert
   riktig størrelsesorden.

Også bekreftet at rå `curl` mot TOC- og data-endepunktene fungerer uten
nøkkel/header, samme som de andre nylige oppsettene.

## Bruk fremover

EU-sammenligningsdata som supplement til worldbank-mcp (globalt) og
who-mcp (helse) — Eurostat har finere granularitet for EU/EØS-land
(NUTS-regioner, ofte lengre tidsserier og flere variabler enn Verdensbanken
for europeiske land spesifikt). Bruk når brukeren eksplisitt ber om EU-/
europeisk sammenligningsdata, eller foreslå det når det tydelig ville
styrket et europeisk sammenligningspunkt i skrivearbeidet — spør først,
hent aldri uoppfordret, samme regel som de andre statistikkildene.
