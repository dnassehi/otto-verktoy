# lovdata-mcp

Lokalt oppslags-/søkeverktøy for gjeldende norske lover og sentrale
forskrifter, satt opp 2026-08-21. Samme mønster som legemiddel-interaksjoner
(FEST) og met-mcp m.fl.

## Bakgrunn

Lovdata åpnet i november 2025 et gratis, kontofritt API for gjeldende lover
og sentrale forskrifter (NLOD 2.0-lisens):
https://api.lovdata.no/ — dokumentert på https://api.lovdata.no/swagger.

Kun de to "Public data"-endepunktene er kontofrie:
- `GET /v1/publicData/get/gjeldende-lover.tar.bz2` (~5,8 MB, 759 lover)
- `GET /v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2`
  (~21 MB, 5123 dokumenter: sentrale forskrifter, delegeringsvedtak,
  instrukser, stortingsvedtak)

Alle øvrige endepunkter (strukturert søk, enkeltparagraf-oppslag,
AI-funksjonalitet) krever en Lovdata API-konto (`X-API-Key`), som Otto ikke
har. Løsningen er derfor samme mønster som FEST-legemiddeldatabasen: last
ned hele det gratis datasettet periodisk og bygg en lokal søkbar database.

## Filer

- `fetch_and_build_db.py` — laster ned begge arkivene, pakker ut XML/HTML5,
  parser hvert dokument (tittel, korttittel, ikrafttredelse, kapitler,
  paragrafer med full tekst) og bygger `lovdata.db` (SQLite + FTS5 for
  fulltekstsøk). Kjøres av cron 1. i hver måned kl. 04:00 (`crontab -l`),
  logger til `cron.log`. Bygging tar under ett minutt.
- `server.py` — MCP-server (tre verktøy, se under).
- `lovdata.db` — generert database (~220 MB, ikke i git).

## Verktøy (MCP-server `lovdata`)

1. **`lovdata_search(query, doc_type=None, limit=10)`** — fulltekstsøk på
   tvers av alle lover/forskrifter, returnerer lovtittel, paragraf,
   paragraftittel, utdrag og lenke, sortert etter relevans.
2. **`lovdata_find_document(query, doc_type=None, limit=10)`** — finn riktig
   offisiell tittel/korttittel for en lov/forskrift ut fra uformelt navn.
3. **`lovdata_get_paragraph(lov, paragraf)`** — hent hele, ordrette teksten
   til én bestemt paragraf. `lov` matches mot tittel/korttittel (med
   automatisk innsnevring til eksakt navnedel før evt. "– kortform", for å
   unngå falske treff i endringslover som nevner samme lovnavn i sin egen
   tittel). `paragraf` normaliserer bort §/mellomrom/bindestrek-varianter.
   Ved flertydighet returneres en kandidatliste i stedet for å gjette.

## Oppsett

- Egen venv: `.venv-lovdata-mcp/` (`mcp==1.29.0`, `bs4`, `lxml` — disse er
  også tilgjengelige system-Python, så selve cron-jobben bruker
  `/usr/bin/python3` som resten av workspacet).
- Registrert i OpenClaw som MCP-server `lovdata` via
  `openclaw mcp add lovdata --command .../python3 --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor lovdata --probe`.

## Testet 2026-08-21

- `lovdata_get_paragraph("arbeidsmiljøloven", "14-9")` → eksakt treff, tekst
  verifisert ord-for-ord mot lovdata.no.
- `lovdata_get_paragraph("helsepersonelloven", "§ 21")` → eksakt treff.
- `lovdata_search("prøvetid midlertidig ansettelse")` → relevante treff i
  skipsarbeidsloven, statsansatteloven og arbeidsmiljøloven § 15-6.

## Begrensninger

- Kun **gjeldende** versjon av lover/sentrale forskrifter — ingen historikk,
  rettsavgjørelser, forarbeider eller juridisk litteratur (det krever
  Lovdata Pro-abonnement eller en betalt API-konto).
- Lokale forskrifter (kommunale/fylkeskommunale) er ikke inkludert i det
  gratis datasettet.
- Databasen kan være inntil en måned gammel (cron-syklus). For
  ikrafttredelsesdatoer nær cron-kjøringen: dobbeltsjekk på lovdata.no.
- Dette er beslutningsstøtte for å finne/sitere riktig paragraftekst — ikke
  juridisk rådgivning.
