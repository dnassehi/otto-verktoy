# kartverket-mcp

Egenbygget MCP-wrapper rundt Kartverkets offentlige Stedsnavn-API, satt opp
2026-08-16. Samme mønster som brreg-mcp, entur-mcp, osv. (Python,
`mcp==1.29.0`, egen venv).

## API-et

- Base URL: `https://ws.geonorge.no/stedsnavn/v1`
- Kartverkets Stedsnavn-API (Place Names Register) - søk og oppslag av norske
  stedsnavn (byer, tettsteder, elver, fjell, kirker, osv.).
- Returnerer koordinater (nord/øst = lat/lon), administrative tilknytninger
  (fylke/kommune), plasstype, og status (aktiv/relikt/planlagt).
- Støtter wildcard-søk (*) og fuzzy-søk (typo-tolerant).
- Ingen autentisering nødvendig for åpne data.
- Lisens: CC0 / Kartverket offentlige data.

## Verktøy (MCP-server `kartverket`)

Fire verktøy:

1. **`kartverket_search_place`** - søk etter stedsnavn etter navn eller fritekst.
   Støtter wildcard-søk (f.eks. "Bergen*") og fuzzy-søk. Returnerer stedsnavn,
   koordinater, kommune/fylke, plasstype.
2. **`kartverket_place_types`** - hent liste over alle stedsnavntyper
   (By, Tettstad, Elv, Fjell, Innsjø, Kirke, osv.). Nyttig for å forstå
   kategoriseringen.
3. **`kartverket_languages`** - hent liste over språk tilgjengelig i registeret
   (Norsk, Sámi, osv.). Stedsnavn kan ha versjoner på flere språk.
4. **`kartverket_search_by_name`** - søk med sidepaginering. Samme søk som tool 1,
   men med eksplisitt side/resultat-per-side-kontroll.

## Oppsett

- `server.py` - MCP-server (Python, fire verktøy over).
- Egen venv: `.venv-kartverket-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `kartverket` via
  `openclaw mcp add kartverket --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor kartverket --probe`.
- Ingen API-nøkkel nødvendig.

## Bruk fremover

Letebok for norske geografiske navn, steder, og administrative grenser -
nyttig for lokalitetskontekst, administrasjonsoppslag, eller når brukeren
spør "hva fylke/kommune er X i?", eller "finn alle steder som starter på
Y i Norge".
