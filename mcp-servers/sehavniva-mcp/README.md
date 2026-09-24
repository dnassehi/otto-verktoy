# sehavniva-mcp

Egenbygget MCP-wrapper rundt Kartverkets "Se havnivå" API for vannstand og
tidevann, satt opp 2026-08-16 etter forespørsel om å grave i
`sehavniva.no`. Samme mønster som de andre nylige oppsettene (Python,
`mcp==1.29.0`, egen venv).

## API-et

- **Viktig funn:** `sehavniva.no` (og den gamle `api.sehavniva.no`) er
  UTGÅTT — `http://sehavniva.no/` 301-redirecter til
  `kartverket.no/til-sjos/se-havniva`, og selve dataAPI-et flyttet til en
  ny URL i juni 2025 ("Major revision: restructured and updated. New
  URL"), ifølge protokolldokumentet.
- Ny base: `https://vannstand.kartverket.no/tideapi.php`
- Fullstendig protokollspesifikasjon (PDF, hentet og lest 2026-08-16):
  `https://vannstand.kartverket.no/API%20for%20water%20level%20and%20tides%20-%20communication%20protocol_revJune2025.pdf`
  — også lesbar interaktivt på `vannstand.kartverket.no/tideapi_en.html`.
- XML-only respons, ingen autentiseringsnøkkel, fri bruk (kun krav: navngi
  Kartverket som kilde). Lisens CC BY 4.0.
- Dekker observert/estimert vannstand, tidevannsprediksjon, varsel,
  tidevannstabeller (flo/fjære), og referansenivåer inkl. statistiske
  stormflo-returnivåer (10/20/50/100/200/1000-års høyvann).

## Verktøy (MCP-server `sehavniva`)

1. **`sehavniva_stationlist`** — liste over alle permanente
   målestasjoner (navn, kode, koordinater).
2. **`sehavniva_locationdata`** — vannstands-/tidevannsdata for en
   posisjon (lat/lon): observert, predikert, varsel, eller tidevannstabell
   (`datatype=tab`).
3. **`sehavniva_locationlevels`** — referansenivåer for en posisjon,
   inkl. astronomiske tidevannsnivåer (HAT/LAT) og statistiske
   stormflo-returnivåer (`flag=return`) — relevant for
   flom-/stormflorisiko på en konkret adresse.

## Oppsett

- `server.py` — MCP-server (tre verktøy over), egen XML→JSON-konvertering
  (ingen tredjeparts XML-til-JSON-avhengighet).
- Egen venv: `.venv-sehavniva-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `sehavniva` via
  `openclaw mcp add sehavniva --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor sehavniva --probe`.

## Kjent begrensning

API-et har et dokumentert dekningshull: for kyststrekningen mellom Lista og
Hellvik svarer det *"There are no sea level data ... The area between Lista
and Hellvik does not have sufficient data."* Dette er et hull i Kartverkets
egen tidevannssonemodell, ikke en feil i koden. Andre kyststrekninger gir
vannstands- og stormflonivåer (returnivåer 100/1000 år) fra nærmeste
stasjon. Sjekk alltid `error`-feltet i svaret før du tolker tallene.
