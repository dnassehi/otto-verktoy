# pubchem-mcp

Egenbygget MCP-wrapper rundt PubChem PUG REST, NIH/NLMs frie database over
kjemiske stoffer/legemidler, satt opp 2026-08-26.
Samme mønster som eurostat-mcp/who-mcp (Python, `mcp==1.29.0`, egen
venv).

## API-et

- Base: `https://pubchem.ncbi.nlm.nih.gov/rest/pug`
- Docs: `https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest`
- Ingen autentiseringsnøkkel nødvendig.
- Dekker molekylstruktur/egenskaper, synonymer/handelsnavn og korte
  beskrivelser (aggregert bl.a. fra ChEBI) for ~120M kjemiske forbindelser.
- **Viktig begrensning**: PubChem har IKKE DrugBanks kliniske
  CYP450-substrat/hemmer/induser-klassifisering — kun rene kjemiske
  egenskaper (XLogP, TPSA osv.) som korrelerer med, men ikke beviser,
  CYP-metabolisme. For eksplisitt CYP450-klassifisering trengs fortsatt
  DrugBank eller tilsvarende (se `TOOLS.md`-notat om akademisk lisens,
  ikke avklart).

## Verktøy (MCP-server `pubchem`)

1. **`pubchem_search_compound`** — søk på navn (generisk eller handelsnavn),
   returnerer PubChem CID-er.
2. **`pubchem_get_compound`** — kjemiske egenskaper (molekylformel/-vekt,
   IUPAC-navn, SMILES, InChI/InChIKey, XLogP, TPSA, H-bond-teller).
3. **`pubchem_get_synonyms`** — synonymer/handelsnavn/CAS-nummer, nyttig
   for å koble norske handelsnavn (f.eks. "Ibux") til generisk navn.
4. **`pubchem_get_description`** — kort tekstbeskrivelse/farmakologisk
   rolle.

Alle fire aksepterer enten et PubChem CID (heltall) eller et navn — navnet
løses automatisk til CID internt.

## Oppsett

- `server.py` — MCP-server (fire verktøy over).
- Egen venv: `.venv-pubchem-mcp/` (`mcp==1.29.0`, `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `pubchem` via
  `openclaw mcp add pubchem --command .../python --arg .../server.py`.
  Sjekk status: `openclaw mcp doctor pubchem --probe`.

## Testet 2026-08-26

Hele kjeden verifisert direkte mot `server.py` sine Python-funksjoner (live
API, ingen mocks):

1. `pubchem_search_compound("ibux")` → CID 3672 (ibuprofen) — PubChems
   navnesøk matchet det norske handelsnavnet direkte via synonymtabellen.
2. `pubchem_get_compound("aspirin")` → CID 2244, formel C9H8O4, XLogP 1.2.
3. `pubchem_get_synonyms("warfarin")` → CID 54678486, inkl. "Coumafene",
   CAS 81-81-2.
4. `pubchem_get_description("ibuprofen")` → ChEBI-basert beskrivelse
   ("non-steroidal anti-inflammatory drug, ... cyclooxygenase 2
   inhibitor...").
