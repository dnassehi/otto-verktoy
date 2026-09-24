# met-mcp

Egenbygget MCP-wrapper rundt Meteorologisk institutts offentlige API
(`api.met.no`, samme datakilde som Yr), satt opp 2026-08-16. Samme mønster
som brreg-mcp, entur-mcp, osv. (Python, `mcp==1.29.0`, egen venv).

## API-et

- Base: `https://api.met.no/weatherapi`
- Ingen autentiseringsnøkkel, men krever en unik, identifiserende
  `User-Agent`-header (generiske/manglende gir 403). Bruker
  `my-agent/1.0 (contact: $CONTACT_EMAIL)` (sett `CONTACT_EMAIL` til din egen adresse).
- MET har flere produkter; denne wrapperen dekker fire:
  - **Locationforecast 2.0** - værvarsel 9 dager frem, hvor som helst
  - **Oceanforecast 2.0** - bølge-/sjøvarsel for punkter til havs i
    Nordvest-Europa (dekker norskekysten)
  - **MetAlerts 2.0** - offisielle farevarsler (storm, vind, regn, snø, is),
    filtrerbart på koordinat, fylke, og land/sjø-domene
  - **Nowcast 2.0** - nedbørsvarsel oppdatert hvert 5. minutt (kun Norden)

## Verktøy (MCP-server `met`)

1. **`met_locationforecast`** - temperatur/vind/nedbør for et punkt
2. **`met_oceanforecast`** - bølgehøyde/-retning, sjøtemperatur, strøm
3. **`met_alerts`** - aktive (eller siste 30 dager) farevarsler, filtrert på
   lat/lon (mest presist for en konkret adresse), fylkesnummer, og/eller
   land/sjø
4. **`met_nowcast`** - kortids nedbørsvarsel

## Oppsett

- `server.py` - MCP-server (fire verktøy over).
- Egen venv: `.venv-met-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `met` via
  `openclaw mcp add met --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor met --probe`.

## Bruk

Værvarsel og sjøvarsel generelt. `met_alerts` filtrert på koordinat egner
seg som grunnlag for en periodisk sjekk (cron) av farevarsler for adresser
du bryr deg om; kombiner med varsling til Telegram.
