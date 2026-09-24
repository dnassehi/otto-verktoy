# brreg-mcp

Egenbygget MCP-wrapper rundt Brønnøysundregistrenes (BRREG) offentlige API
for Enhetsregisteret, satt opp 2026-08-16. Samme mønster som dk-statbank-mcp,
scb-pxweb-mcp, og fhi-mcp (Python, `mcp==1.29.0`, egen venv, ingen
ferdig MCP-server fantes for dette API-et).

## API-et

- Base URL: `https://data.brreg.no/enhetsregisteret/api`
- Enkelt, GET-basert REST API for søk og oppslag av norske organisasjoner,
  virksomheter, og deres roller.
- Ingen autentisering nødvendig for åpne data (hele APIet).
- Lisens: NLOD (Norwegian Licence for Open Government Data).
- Dokumentasjon: https://data.brreg.no/enhetsregisteret/api/dokumentasjon/no/swagger-ui.html

## Verktøy (MCP-server `brreg`)

Fire verktøy:

1. **`brreg_search_entity`** - søk etter organisasjoner/virksomheter ved navn
   eller fritekst. Returner sidert liste med organisasjonsnummer (orgnr),
   navn, næringskode, adresser, status.
2. **`brreg_get_entity`** - hent full detaljinformasjon for en spesifikk
   virksomhet via orgnr (9-sifret). Inkluderer postadrasse, besøksadresse,
   telefon, e-post, nettsted, næringskode, ansatte, stiftelsesdato,
   MVA-status, sektor, og diverse registreringsdatoer.
3. **`brreg_search_subunit`** - søk etter underenheter (avdelinger, filialer).
   Hver underenhet har en overordnet virksomhet (`overordnetEnhet`).
4. **`brreg_get_roles`** - hent roller/stillingsposter for en virksomhet: CEO
   (DAGL), styremedlemmer (STYR), revisor (REVI), regnskapsfører (REGN), og
   organisatoriske bindinger (ORGL). Grupperes etter rolletype.

## Oppsett

- `server.py` - MCP-server (Python, fire verktøy over).
- Egen venv: `.venv-brreg-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `brreg` via
  `openclaw mcp add brreg --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor brreg --probe`.
- Ingen API-nøkkel, ingen 1Password-oppslag.

## Testet 2026-08-16

Hele kjeden verifisert direkte mot live API-et:

1. `brreg_search_entity("Bergen")` -> 20 treff, inkl. UNIVERSITETET I BERGEN
   (orgnr 874789542).
2. `brreg_get_entity("874789542")` (UiB):
   - Navn: UNIVERSITETET I BERGEN
   - Næringskode: 85.401 (Undervisning ved universiteter)
   - Ansatte: 5133
   - Adresse: Muséplassen 1, Bergen
   - Status: Aktiv
3. `brreg_get_roles("874789542")` -> 13 roller totalt, inkl. daglig leder
   (Tore Tungodden), styreleder (Margareth Hagen), 10 styremedlemmer, revisor
   (Riksrevisjonen), regnskapsfører, og organisatorisk binding til
   Kunnskapsdepartementet.

Ingen autentiseringsfeil, sidepaginering fungerer korrekt.

## Bruk fremover

Oppslag av norske virksomheter, styrer, revisorer, og andre roller - nyttig
for klinisk/faglig arbeid som krever organisatorisk kontekst eller
interessekonfliktkontroll. Bruk når brukeren eksplisitt spør om organisasjons-
eller personer-detaljer, eller foreslå det når fagstøtte-arbeid krever å vite
hvem som leder eller styrer et foretak/institusjon.
