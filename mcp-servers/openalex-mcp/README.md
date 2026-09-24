# openalex-mcp

Egenbygget MCP-wrapper rundt OpenAlex, satt opp 2026-08-26 på brukerens
forespørsel (svar på "ja, sett opp" til forslaget om et tredje
forskningssøk ved siden av PubMed/Elicit). Samme mønster som
worldbank-mcp/eurostat-mcp (Python, `mcp==1.29.0`, egen venv).

## API-et

- `https://api.openalex.org` — gratis, åpen katalog over ~250M
  vitenskapelige arbeider (aggregert fra Crossref, PubMed, arXiv,
  institusjonsrepositorier, forlag).
- Ingen autentiseringsnøkkel nødvendig. Alle kall sender
  `mailto=$CONTACT_EMAIL` (OpenAlex' egen anbefalte praksis for
  "polite pool" — raskere/mer stabil rate-limiting, ikke datadeling til
  tredjepart).
- Dekker *alle* fagfelt, ikke bare biomedisin — styrken er filosofi, STS
  (science and technology studies), informatikk og arXiv-preprints, som er
  dårlig indeksert i PubMed. Relevant for KI-etikk-/TESCREAL-materiale i
  forskningsvarselet.

## Verktøy (MCP-server `openalex`)

1. **`openalex_search_works`** — fritekstsøk (tittel/abstract) på arbeider,
   med valgfritt år-filter og open-access-filter. Returnerer forenklet
   metadata (tittel, forfattere, år, kilde, OA-lenke, siteringstall,
   emner/topics, rekonstruert abstract).
2. **`openalex_get_work`** — full metadata for ett arbeid via OpenAlex-ID
   eller DOI.
3. **`openalex_search_authors`** — søk på forfatternavn, returnerer
   ID/tilknytning/antall arbeider/siteringer/ORCID.

## Oppsett

- `server.py` — MCP-server (tre verktøy over).
- Egen venv: `.venv-openalex-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `openalex` via
  `openclaw mcp add openalex --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor openalex --probe`.

## Testet 2026-08-26

Alle tre verktøy verifisert direkte mot server.py sine Python-funksjoner
(live API, ingen mocks):

1. `openalex_search_works("TESCREAL")` → traff bl.a. Gebru & Torres (2024)
   "The TESCREAL bundle" (First Monday, open access, 153 siteringer).
2. `openalex_get_work("10.1038/s41586-021-03819-2")` → AlphaFold-artikkelen
   (Jumper et al. 2021, Nature) med full forfatterliste.
3. `openalex_search_authors("Kirsti Malterud")` → korrekt treff (341
   arbeider, 29 499 siteringer, riktig ORCID).

## Bruk fremover

Tredje søkekilde ved siden av PubMed og Elicit i research-monitor og
`nva-fulltekst-henting` — fanger opp filosofisk/STS-orientert KI-etikk-
materiale som PubMed-triagen i dag går glipp av. Ikke koblet inn i selve
research-monitor-scriptet ennå (kun MCP-serveren er satt opp) — bruk det
manuelt ved forskningsspørsmål inntil videre, eller si fra om du vil at det
kobles inn i den ukentlige automatikken.
