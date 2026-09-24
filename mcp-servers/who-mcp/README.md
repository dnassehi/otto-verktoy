# who-mcp

Egenbygget MCP-wrapper rundt WHOs offentlige Global Health Observatory (GHO)
OData API, satt opp 2026-08-16. Samme mønster som brreg-mcp,
entur-mcp, osv. (Python, `mcp==1.29.0`, egen venv).

## API-et

- Base: `https://ghoapi.azureedge.net/api`
- OData-protokoll, ingen autentiseringsnøkkel nødvendig.
- ~2000 helseindikatorer per land/år: levealder, sykdomsforekomst, ernæring,
  helsesystemkapasitet, miljø/helse, m.m. for WHOs 194 medlemsland.

## Verktøy (MCP-server `who`)

1. **`who_search_indicators`** - fritekstsøk i indikatornavn (f.eks. "life
   expectancy", "diabetes", "maternal mortality"). Returnerer IndicatorCode
   til bruk i `who_get_data`.
2. **`who_get_data`** - hent data for en indikator, valgfritt filtrert på
   ISO3-landkode og/eller år.
3. **`who_list_dimension_values`** - liste gyldige verdier for en dimensjon,
   vanligst "COUNTRY" (ISO3-koder + navn) eller "REGION".

## Oppsett

- `server.py` - MCP-server (tre verktøy over).
- Egen venv: `.venv-who-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `who` via
  `openclaw mcp add who --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor who --probe`.

## Testet 2026-08-16

`who_search_indicators("life expectancy")` -> flere treff inkl.
WHOSIS_000015 (levealder ved 60 år), WHOSIS_000002 (HALE ved fødsel).
Verifisert mot live API.

## Bruk fremover

Internasjonal helsestatistikk som supplement til `ssb-statistikk`/
`fhi-statistikk` - for sammenligning av Norge mot andre land, eller globale
helsetrender. Merk: dette er landsnivå-aggregater, ikke egnet for kliniske
enkeltspørsmål (bruk `gp-fagstotte`/`helsedir-innholdstjenester` til det).
