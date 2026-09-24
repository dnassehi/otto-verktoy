# yfinance-mcp

Egenbygget MCP-wrapper rundt Python-biblioteket `yfinance`, satt opp
2026-08-16. Samme mønster som okonomi-mcp,
kartverket-mcp osv. (Python, `mcp==1.29.0`, egen venv).

## Om yfinance

- Dokumentasjon: <https://ranaroussi.github.io/yfinance/>
- GitHub: <https://github.com/ranaroussi/yfinance>
- **IKKE et offisielt Yahoo Finance-API** — et åpent Python-bibliotek som
  bruker Yahoo Finances uoffisielle endepunkter. Kan endres/begrenses uten
  varsel. Ingen API-nøkkel, men skal brukes med måtehold (ikke
  høyfrekvent/kommersiell bruk).
- Tickerformat: Oslo Børs bruker `.OL`-suffiks (`EQNR.OL`, `DNB.OL`),
  amerikanske tickere er bare (`AAPL`), indekser har `^`-prefiks
  (`^GSPC`, `^OSEBX`).

## Verktøy (MCP-server `yfinance`)

1. **`yfinance_history`** — historisk OHLCV-prisdata (åpen/høy/lav/lukk/
   volum) for én ticker. `period`/`interval`-parametre som i biblioteket
   selv (f.eks. `period="1y"`, `interval="1d"`).
2. **`yfinance_info`** — nøkkeltall og metadata for en ticker (navn,
   sektor, valuta, gjeldende kurs, market cap, P/E, utbytteavkastning,
   52-ukers-range, forretningsbeskrivelse). Returnerer et utvalg felt, ikke
   hele det rå (100+ felt, varierer mye per tickertype) dict-et.
3. **`yfinance_download`** — flere tickere samtidig, splitt-/
   utbyttejustert, gruppert per ticker (enklere å resonnere om enn
   bibliotekets rå MultiIndex-format ved flere tickere).
4. **`yfinance_dividends_splits`** — full utbytte- og aksjesplitt-historikk
   for én ticker.

## Oppsett

- `server.py` — MCP-server (Python, fire verktøy over).
- Egen venv: `.venv-yfinance-mcp/` (`mcp==1.29.0`, `yfinance` — siste
  versjon fra PyPI, ingen versjonspinning siden yfinance oppdateres ofte
  når Yahoo endrer sine uoffisielle endepunkter).
- Registrert i OpenClaw som MCP-server `yfinance` via
  `openclaw mcp add yfinance --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor yfinance --probe`.
- Ingen API-nøkkel, ingen 1Password-oppslag.

## Testet 2026-08-16

Alle fire verktøy verifisert mot live Yahoo Finance-data:

1. `yfinance_info("EQNR.OL")` -> Equinor ASA, NOK, sektor Energy, korrekt
   kurs/market cap/P/E.
2. `yfinance_history("EQNR.OL", period="5d")` -> 5 dagers OHLCV-rader med
   korrekte datoer/priser.
3. `yfinance_download(["EQNR.OL","DNB.OL"], period="1mo")` -> begge
   tickere, 23 dagers rader hver, korrekt gruppert per ticker.
4. `yfinance_dividends_splits("DNB.OL")` -> full utbyttehistorikk
   (2024–2026), ingen splitter.
