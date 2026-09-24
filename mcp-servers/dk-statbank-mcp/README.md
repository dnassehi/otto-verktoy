# dk-statbank-mcp

Egenbygget MCP-wrapper rundt Danmarks Statistiks (DST) API for
Statistikbanken (api.statbank.dk), satt opp 2026-08-11. Samme mønster som
fhi-mcp (Python, `mcp==1.29.0`, egen venv, ingen ferdig MCP-server
fantes for dette API-et).

## API-et

- Base URL: `https://api.statbank.dk/v1`
- Registrert i den offentlige datakatalogen på data.norge.no under
  datasett-ID `3f7926bc-4db0-3ea6-9d74-3373f027137a` (kun katalogoppføring
  - selve API-dokumentasjonen ligger hos DST, ikke der).
- Klassifisert som "allmenn tilgang", men i praksis krever ingen av de
  fire funksjonene som brukes her (`subjects`, `tables`, `tableinfo`,
  `data`) autentisering - kun den femte funksjonen `CATALOGUE` krever
  API-nøkkel, og er ikke implementert her siden den ikke trengs for vanlig
  tabelloppslag.
- Lisens: CC BY 4.0.
- Kallmønster (viktig forskjell fra SSB-MCP-en): POST av JSON-objekt til
  funksjonsspesifikk URL (`/v1/subjects`, `/v1/tables`, `/v1/tableinfo`,
  `/v1/data`), ikke ren GET/REST-URL-navigasjon.
- Arbeidsflyt: `subjects` (bla i emnehierarkiet) -> `tables` (tabeller per
  emne/oppdateringsdato) -> `tableinfo` (variabler + gyldige koder for en
  tabell, nødvendig FØR `data`) -> `data` (POST, faktiske verdier,
  JSON-stat2 eller CSV).
- Begrensning: maks 1 000 000 celler (rader × kolonner) per uttrekk - ikke
  relevant for de fleste enkeltoppslag, men et uttrekk med `"*"` på flere
  variabler samtidig kan feile med `EXTRACT-TOOBIG`.
- Standard språk satt til engelsk (`lang: "en"`) i alle verktøy, med mindre
  dansk eksplisitt bes om - variabel-/kode-ID-er er identiske uansett
  språk, kun tekstetiketter endres.

## Oppsett

- `server.py` - MCP-server (Python, fire verktøy: `dkstat_subjects`,
  `dkstat_tables`, `dkstat_table_info`, `dkstat_data`).
- Egen venv: `.venv-dk-statbank-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `dkstat` via
  `openclaw mcp add dkstat --command .../python --arg .../server.py`
  (probet automatisk ved lagring). Sjekk status:
  `openclaw mcp doctor dkstat --probe`.
- Ingen API-nøkkel, ingen 1Password-oppslag.

## Testet 2026-08-11

Hele kjeden verifisert både direkte mot server.py sine Python-funksjoner
og med rå `curl` mot API-et:

1. `subjects` -> 10 hovedemner (People, Labour and income, Economy, Social
   conditions, Education and research, Business, Transport, Culture and
   leisure, Environment and energy, About Statistics Denmark). Rekursivt
   søk fant emne `3412` (People > Health) og `20933` (Economy > General
   government economy > Health care expenditure).
2. `tables` for emne `3412` -> 46 tabeller, bl.a. `SBR01`-`SBR04`
   "Hospital utilisation in the population".
3. `tableinfo` for `SBR01` -> 5 variabler: `KOMMUNEDK` (kommune, 99
   verdier inkl. "All Denmark"), `OPHOLD_PÅ_SYGEHUS` (oppholdstype),
   `ALDER` (aldersgruppe), `KØN` (kjønn), `Tid` (år 2017-2025).
4. `data` for `SBR01`, hele landet, "All durations", alder totalt, begge
   kjønn, alle år -> antall personer med sykehusopphold i Danmark:
   2017: 2 727 718 -> 2025: 2 918 015 (jevn økning, med et lite fall under
   2020-2021). MÅLT nasjonal data fra DSTs egen kilde, ikke modellert.

Ingen autentiseringsfeil, ingen `EXTRACT-TOOBIG` på dette enkeltoppslaget.

## Bruk fremover

Supplerende dansk statistikkilde til forskningsarbeidet - samme rolle som
ssb-statistikk/fhi-statistikk spiller for norske data, men for
Danmark. Bruk når brukeren eksplisitt spør om dansk sammenligningsdata,
eller foreslå det (spør først, hent aldri uoppfordret - samme regel som
de norske kildene) når et dansk datapunkt åpenbart ville styrket en
sammenligning i skrivearbeidet. dataviz-healy er standard
visualiseringsmetode, som for de norske kildene.
