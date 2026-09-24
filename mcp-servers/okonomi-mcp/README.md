# okonomi-mcp

Egenbygget MCP-wrapper rundt Økonomi.no sitt offentlige utvikler-API, satt
opp 2026-08-16. Samme mønster som kartverket-mcp, brreg-mcp,
entur-mcp osv. (Python, `mcp==1.29.0`, egen venv).

## API-et

- Base URL: `https://www.okonomi.no/wp-json/okonomi/v1`
- Dokumentasjon: <https://www.okonomi.no/utvikler-api/>
- To datakategorier:
  - **Markeder**: børsindekser, valuta, krypto (kilder: Norges Bank, SSB,
    CoinGecko, Morningstar).
  - **Dagligvarer**: produktsøk, EAN/strekkode-oppslag, prishistorikk og
    butikksøk på tvers av norske dagligvarekjeder (kilde: Kassal.app).
- Ingen autentisering nødvendig for de offentlige endepunktene.
- API-ets egne bruksvilkår: oppgi kilde ("Data fra Økonomi.no"), cache svar,
  unngå unødig hyppige kall.

## Verktøy (MCP-server `okonomi`)

1. **`okonomi_markeder_topbar`** - ticker-feed for indekser/valuta/krypto
   (samme som topbaren på forsiden).
2. **`okonomi_markeder`** - markedsdata, enten alle kategorier samlet eller
   én kategori i detalj (`category="krypto"`/`"valuta"`/`"indekser"` osv.).
3. **`okonomi_dagligvarer_sok`** - fritekstsøk på dagligvarer på tvers av
   kjeder, med pris, enhetspris, kategori og nylig prishistorikk.
4. **`okonomi_dagligvarer_ean`** - produktoppslag på EAN/strekkode.
5. **`okonomi_dagligvarer_butikker`** - dagligvarebutikker nær et
   geografisk punkt (lat/lng + radius i km).
6. **`okonomi_dagligvarer_prishistorikk`** - prishistorikk for inntil 100
   EAN-koder samtidig (POST). **Se begrensning under.**

## Begrensning

`okonomi_dagligvarer_prishistorikk` (POST-endepunktet) ga `HTTP 422` fra
Kassal.app-bakenden i testing 2026-08-16, selv med en EAN som har bekreftet
prishistorikk tilgjengelig via `okonomi_dagligvarer_sok`. Trolig krever
dette spesifikke endepunktet en autentisering Otto ikke har mot
Kassal.app direkte (Økonomi.no sitt eget wrapper-lag ser ut til å fungere,
men viderefører feilen). Bruk i stedet `okonomi_dagligvarer_sok` eller
`okonomi_dagligvarer_ean`, som begge allerede returnerer nylig
prishistorikk inline i produktdataene.

## Oppsett

- `server.py` - MCP-server (Python, seks verktøy over).
- Egen venv: `.venv-okonomi-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `okonomi` via
  `openclaw mcp add okonomi --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor okonomi --probe`.
- Ingen API-nøkkel, ingen 1Password-oppslag.

## Testet 2026-08-16

Alle GET-endepunkter verifisert mot live API:

1. `okonomi_markeder_topbar` -> S&P 500, Nasdaq, Dow Jones, DAX m.fl. med
   korrekte verdier/endring.
2. `okonomi_markeder(category="krypto")` -> Bitcoin, Ethereum, XRP i NOK.
3. `okonomi_dagligvarer_sok("kaffe")` -> treff med pris, kjede, kategori,
   prishistorikk inline.
4. `okonomi_dagligvarer_ean("7041013200110")` -> Freia Melkesjokolade
   Sjokoladeis, riktig produkt/pris.
5. `okonomi_dagligvarer_butikker(lat=59.9, lng=10.7, km=5)` -> nærbutikker i
   Oslo-området med adresse og åpningstider.
6. `okonomi_dagligvarer_prishistorikk` -> feiler (se Begrensning).
