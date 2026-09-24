# scb-pxweb-mcp

Egenbygget MCP-wrapper rundt Statistiska centralbyråns (SCB) offentlige
API for Statistikdatabasen, satt opp 2026-08-11. Samme mønster som
dk-statbank-mcp/fhi-mcp (Python, `mcp==1.29.0`, egen venv, ingen
ferdig MCP-server fantes for dette API-et).

## API-et

- Base URL: `https://api.scb.se/OV0104/v2beta/api/v2`
- Offisielt navn: **PxWebApi 2** (lansert høst 2025, erstatter PxWebApi 1
  som fases ut ved årsskiftet 2026/2027). Samme API-standard brukes også
  av bl.a. SSB Norge (`data.ssb.no/api/pxwebapi/v2`) - egen implementasjon
  per statistikkbyrå, men delt spesifikasjon
  ([PxTools/PxApiSpecs](https://github.com/PxTools/PxApiSpecs)).
- Ingen autentisering nødvendig for oppslag (kun tabellsøk/metadata/data -
  ingen skriveoperasjoner finnes). Lisens: CC0 (ingen krav om
  kildeangivelse, men SCB oppgis som kilde likevel av notasjonsmessig
  konsistens med ssb-statistikk/dk-statistikk).
- **Viktig avvik fra opprinnelig antakelse:** oppdraget antok
  POST-basert browsing/query, men den faktiske, live OpenAPI-spesifikasjonen
  (hentet fra `api.scb.se/ov0104/v2beta/api/v2/swagger/v2/swagger.json`
  2026-08-11) viser at **hele API-et er GET-basert REST-navigasjon** - kun
  selve dataspørringen (`/data`) støtter valgfritt POST for store/komplekse
  uttrekk, ikke brukt her siden GET dekker alt som trengs. Det finnes heller
  ingen eget emnehierarki-endepunkt (`subjects`/`navigation`) slik DST og
  SSB har - bla skjer via fritekstsøk (`query`) på `/tables`, og hver
  tabell returnerer sin egen `paths`-sti (emne/mappe-brødsmulesti) i
  søkeresultatet.
- Kallmønster: `tables` (søk/bla, GET) -> `table metadata` (GET, variabler
  + koder, JSON-stat2) -> `data` (GET, faktiske verdier via
  `valuecodes[<Variabel>]=<kode1>,<kode2>`-spørreparametre).
- Begrensninger (håndhevet av SCB): maks **150 000 celler** per uttrekk,
  og maks **30 kall per 10 sekunder per IP**. Wrapperen håndhever selv en
  enkel sliding-window-kø (klientside throttling) slik at en serie kall i
  samme runde aldri kan overskride dette.
- Standard språk satt til engelsk (`lang: "en"`) i alle verktøy, med
  mindre svensk eksplisitt bes om.

## Verktøy (MCP-server `scb`)

Fire verktøy:

1. **`scb_tables`** - søk/bla i tabeller (`query`, `past_days`,
   `include_discontinued`, paginert med `page_number`/`page_size`). Hvert
   resultats `id` (f.eks. `"TAB4394"`) er tabell-ID-en, `paths`-feltet
   viser emnetilhørighet.
2. **`scb_table_metadata`** - full metadata (JSON-stat2 `dimension`) for
   en tabell: alle variabler og deres gyldige kategori-koder/etiketter.
   Kall FØR `scb_get_data`.
3. **`scb_get_data`** - hent faktiske data. `valuecodes_json` er et
   JSON-objekt `{"Variabel": ["kode1","kode2"]}`, én per variabel fra
   metadataen. `output_format`: `"json-stat2"` (standard, samme struktur
   som SSB/DST-verktøyene), `"csv"`, `"px"`, `"html"`, `"json-px"` (unngå
   `"xlsx"`/`"parquet"` - binærformat, denne wrapperen returnerer tekst).
4. **`scb_get_url`** - bygger en delbar GET-URL for samme spørring, uten
   å faktisk kalle den (nyttig for å dele/verifisere manuelt).

## Oppsett

- `server.py` - MCP-server (Python, fire verktøy over, egen
  klientside-throttling for 30 kall/10 sek-grensen).
- Egen venv: `.venv-scb-pxweb-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `scb` via
  `openclaw mcp add scb --command .../python --arg .../server.py`
  (probet ok). Sjekk status: `openclaw mcp doctor scb --probe`.
- Ingen API-nøkkel, ingen 1Password-oppslag.

## Testet 2026-08-11

Hele kjeden verifisert både direkte mot `server.py`s Python-funksjoner og
med rå `curl` mot API-et:

1. `scb_tables(query="life expectancy county")` -> 2 treff, bl.a.
   `TAB4394` "Life expectancy at birth by region and sex
   (1998-2002)-(2021-2025)", sti Population > Population statistics >
   Deaths.
2. `scb_table_metadata("TAB4394")` -> 4 variabler: `Region` (312 verdier,
   `"00"` = hele Sverige), `Kon` (`"1"`=menn, `"2"`=kvinner),
   `ContentsCode` (kun `"000000NH"` = Number), `Tid` (24 rullerende
   5-årsperioder 1998-2002 til 2021-2025).
3. `scb_get_data("TAB4394", ...)` for hele Sverige, begge kjønn, de 5
   siste periodene -> forventet levealder ved fødsel:

   | Periode | Menn | Kvinner |
   |---|---|---|
   | 2017-2021 | 80,93 | 84,43 |
   | 2018-2022 | 81,05 | 84,56 |
   | 2019-2023 | 81,21 | 84,69 |
   | 2020-2024 | 81,40 | 84,81 |
   | 2021-2025 | 81,79 | 85,07 |

   MÅLT nasjonal data fra SCBs egen kilde (ikke modellert) - stemmer godt
   med kjente svenske levealderstall (kvinner konsekvent ~3-3,5 år over
   menn, jevn økning over perioden, med et lite fall for menn rundt
   2020-2022-periodene som inkluderer covid-årene).
4. `scb_get_url(...)` -> gyldig, delbar GET-URL bekreftet.
5. `output_format="csv"` -> gyldig CSV med samme tall.

Ingen autentiseringsfeil, ingen treff på 150 000-cellegrensen på dette
enkeltoppslaget, ingen rate-limit-feil.

## Bruk fremover

Supplerende svensk statistikkilde til forskningsarbeidet - samme rolle
som ssb-statistikk/fhi-statistikk (Norge) og
dk-statistikk (Danmark) spiller, nå for Sverige. Bruk når brukeren
eksplisitt spør om svensk sammenligningsdata, eller foreslå det (spør
først, hent aldri uoppfordret - samme regel som de andre kildene) når et
svensk datapunkt åpenbart ville styrket en nordisk sammenligning i
skrivearbeidet. dataviz-healy er standard visualiseringsmetode, som
for de andre kildene - med Norge/Sverige/Danmark nå tilgjengelig gjennom
parallelle verktøysett er trelands-sammenligningsfigurer en naturlig bruk.
