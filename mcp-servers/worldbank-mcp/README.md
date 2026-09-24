# worldbank-mcp

Egenbygget MCP-wrapper rundt Verdensbankens offentlige Indicators API, satt
opp 2026-08-16. Samme mønster som brreg-mcp, entur-mcp, osv. (Python,
`mcp==1.29.0`, egen venv).

## API-et

- Base: `https://api.worldbank.org/v2`
- Ingen autentiseringsnøkkel nødvendig, ingen kjent rate-limit.
- ~16 000 utviklingsindikatorer (befolkning, GDP, fattigdom, utdanning,
  helse, klima m.m.) for alle land og regioner.

## Verktøy (MCP-server `worldbank`)

1. **`worldbank_search_indicators`** - fritekstsøk i indikatornavn (f.eks.
   "population", "life expectancy", "unemployment", "CO2"). Henter hele
   ~16 000-katalogen i ett kall og filtrerer lokalt - kan ta noen sekunder.
2. **`worldbank_get_data`** - tidsserie for en indikator + land (ISO2/ISO3,
   eller "all"), valgfritt årsintervall (f.eks. "2015:2025").
3. **`worldbank_list_countries`** - liste land-/regionkoder, valgfritt
   filtrert på navn.

## Oppsett

- `server.py` - MCP-server (tre verktøy over).
- Egen venv: `.venv-worldbank-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `worldbank` via
  `openclaw mcp add worldbank --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor worldbank --probe`.

## Testet 2026-08-16

`worldbank_get_data("NOR", "SP.POP.TOTL", "2024")` -> 5 572 279 (Norges
befolkning 2024). Verifisert mot live API.

## Bruk fremover

Internasjonale demografi-/utviklingsdata som supplement til
`ssb-statistikk`/`dk-statistikk`/`se-statistikk` - dekker det meste av
"demografisk sammenligning mellom land"-behov uten å måtte gå til FN/OECD
separat.
