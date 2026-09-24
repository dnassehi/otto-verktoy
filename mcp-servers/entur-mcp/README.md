# entur-mcp

Egenbygget MCP-wrapper rundt Enturs offentlige API-er for norsk offentlig
transport, satt opp 2026-08-16. Samme mønster som brreg-mcp,
dk-statbank-mcp, osv. (Python, `mcp==1.29.0`, egen venv).

## API-et

- Base: Entur tilbyr flere API-er:
  - **Geocoder**: https://api.entur.io/geocoder/v1 - finne stoppesteder,
    adresser, og deres koordinater
  - **GTFS-RT Realtime**: https://api.entur.io/realtime/v1/gtfs-rt - sanntids
    kjøretøyposisjoner, forsinkelser, varsler
  - **Journey Planner GraphQL**: https://api.entur.io/journey-planner/v3/graphql -
    reiseplanlegging (krever kompleks GraphQL-schema)
- Alle endepunkter krever `ET-Client-Name`-header (bruker-identifikasjon,
  ingen autentiseringsnøkkel).
- Lisens: Åpne data fra norske transportoperatører.

## Verktøy (MCP-server `entur`)

Tre verktøy, fokusert på geocoding som er mest praktisk uten fullt GraphQL-setup:

1. **`entur_geocode`** - søk etter stoppesteder/adresser etter navn eller
   fritekst. Returnerer koordinater, stop-ID-er (for reiseplanlegging), og
   adresseopplysninger.
2. **`entur_reverse_geocode`** - finne stoppesteder/adresser ved koordinater
   (lat/lon). Nyttig for å finne hva som er i nærheten av en gitt lokasjon.
3. **`entur_realtime_alerts`** - hent aktive varsler/forsinkelser for et område
   (f.eks. "NO" = hele Norge, "NO:Bergen" = Bergen).

## Oppsett

- `server.py` - MCP-server (Python, tre verktøy over).
- Egen venv: `.venv-entur-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `entur` via
  `openclaw mcp add entur --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor entur --probe`.
- Ingen API-nøkkel nødvendig, kun header-identifikasjon.

## Bruk fremover

Letebok for stoppesteder, adresser, og sanntids transportforhold - nyttig for
reiseplanlegging, lokalitetskontekst, eller når brukeren spør om "hva er
bussholdeplassen nærmest X?". Geocoder brukes som oppslag før journey planner
GraphQL-spørringer (som ikke implementert fullstendig her).
