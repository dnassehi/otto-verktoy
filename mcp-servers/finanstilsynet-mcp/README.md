# finanstilsynet-mcp

Egenbygget MCP-wrapper rundt Finanstilsynets offentlige API-er, satt opp
2026-08-16. Fokusert på Short Sales Register (SSR) som er fullt funksjonell.
Samme mønster som brreg-mcp, entur-mcp, osv. (Python, `mcp==1.29.0`,
egen venv).

## API-et

- **Short Sales Register (SSR)**: https://ssr.finanstilsynet.no/api/v2
  - Registrerer offentlige shortposisjoner i finansielle instrumenter under
    Finanstilsynets tilsyn.
  - Inneholder historikkdata siste 2 år.
  - OpenAPI/Swagger spec: https://ssr.finanstilsynet.no/api/v2/openapi.json
  - Lisens: Offentlige data fra Finanstilsynet.
  - Ingen autentisering nødvendig.

- **Virksomhetsregisteret** (Business Registry): https://api.finanstilsynet.no/registry/
  - Dokumentert i oppgaven, men API-struktur uklar (ble ikke tilgjengelig
    under oppsett). Kan utbygges senere.

## Verktøy (MCP-server `finanstilsynet`)

Fire verktøy, alle basert på SSR:

1. **`ft_get_short_sales`** - hent alle offentlig shortede instrumenter med
   deres komplett historikk (2 år tilbake). Inkluderer dato, shortprosent,
   antall aksjer, og liste over individuelle posisjonsholdere.
2. **`ft_search_short_position`** - søk etter shortposisjoner ved ISIN
   (verdipapirkode, f.eks. NO0010400295 for Oslo Børs) eller
   utstedernavn (f.eks. "DNB"). Client-side filtrer av full liste.
3. **`ft_get_short_sales_csv`** - eksporter all shortdata som CSV-format.
   Kan spesifisere skilletegn (default ";") og lokale/språkformat
   (default "nb-NO").
4. **`ft_get_current_positions`** - hent BARE de aktuelt aktive shortposisjonene
   (nyeste dato per instrument). Lett oversikt over hvem som shorter hva
   akkurat nå.

## Oppsett

- `server.py` - MCP-server (Python, fire verktøy over).
- Egen venv: `.venv-finanstilsynet-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `finanstilsynet` via
  `openclaw mcp add finanstilsynet --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor finanstilsynet --probe`.
- Ingen API-nøkkel nødvendig.

## Testet 2026-08-16

SSR API verifisert mot live data:

1. `ft_get_short_sales()` -> 99 instrumenter med aktive shortposisjoner.
   Eksempel: BMG9156K1018 "2020 BULKERS" med kortsalg rapportert 2026-08-13,
   shortprosent 1,92%, 443 147 aksjer. Posisjonsholdere: GSA CAPITAL PARTNERS
   LLP (1,24%), CITADEL SECURITIES (EUROPE) LIMITED (0,68%).
2. CSV-eksport testet (strukturen OK).
3. Client-side filtrer fungerer korrekt.

Virksomhetsregisteret API ikke fullt undersøkt (forhåndsvis ikke tilgjengelig
under testen; kan utbygges senere basert på dokumentasjon).

## Bruk fremover

Oppslag av offentlige shortposisjoner - nyttig for finansmarkedsanalytikk,
risikokontroll, eller når brukeren spør om "hvem shorter denne aksjen?" eller
"hva er de største shortposisjonene nå?". SSR er primærkilden, og er testet
arbeider fullt ut. Virksomhetsregisteret kan legges til når API-strukturen
avklares.
