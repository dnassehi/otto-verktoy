# fhi-mcp

Egenbygget MCP-wrapper rundt FHI Statistikk Open API
(github.com/folkehelseinstituttet/Fhi.Statistikk.OpenAPI), satt opp
2026-08-08. Ingen ferdig MCP-server fantes for dette API-et - dette er
en tynn wrapper skrevet fra bunnen, samme mønster som docker-mcp
(Python, `mcp`-SDK, egen venv).

## API-et

- Base URL: `https://statistikk-data.fhi.no/api/open/v1`
- Ingen autentisering - alle data publisert gjennom dette API-et er åpne.
- Swagger: https://statistikk-data.fhi.no/swagger/index.html
- Arbeidsflyt: `source` (liste datakilder) -> `table` (liste tabeller per
  kilde) -> `query` (dimensjons-/kategori-mal for en tabell) ->
  `dimension` (lesbare etiketter for samme koder) -> `metadata`
  (fritekstbeskrivelse) -> `data` (POST, faktiske verdier, json-stat2-format
  - samme format som SSB-MCP-en bruker).
- 13 kilder tilgjengelig 2026-08-08: Abortregisteret, Dødsårsaksregisteret,
  Folkehelsestatistikk (`nokkel` - bredest, mest relevant for allmennmedisin),
  Grossistbasert legemiddelstatistikk, Hjerte- og karregisteret, Kommunalt
  pasient- og brukerregister (`kpr` - fastlege-/legevakt-relatert, men bare
  3 publiserte tabeller p.t.), Legemiddelregisteret, Medisinsk
  fødselsregister, MSIS (smittsomme sykdommer), Mikrobiologisk
  genomovervåkning, SYSVAK (vaksinasjon), Norsk pasientregister,
  Skadedyrstatistikken.

## Oppsett

- `server.py` - MCP-server (Python, `mcp==1.29.0` - NB: nyere `mcp`-pakke
  fra pip (2.0.0) har annen API-struktur uten `mcp.server.fastmcp`, må
  pinnes til 1.29.0 for å matche mønsteret fra docker-mcp).
- Egen venv: `.venv-fhi-mcp/` (`mcp==1.29.0`, `requests`).
- Registrert i OpenClaw som MCP-server `fhi`
  (`openclaw mcp doctor fhi --probe` -> ok).
- Fem verktøy: `fhi_list_sources`, `fhi_list_tables`,
  `fhi_get_query_template`, `fhi_get_dimensions`, `fhi_get_metadata`,
  `fhi_get_data` (seks, egentlig - alle GET/POST mot dokumenterte
  leseendepunkter, ingen skrivemulighet finnes i API-et i utgangspunktet).

## Testet 2026-08-08

Hentet reelle data fra kilde `nokkel` (Folkehelsestatistikk), tabell 367
"Overvekt, kvinner, MFR" - andel gravide kvinner (hele landet) registrert
med KMI-basert overvekt inkl. fedme ved svangerskapsregistrering i
Medisinsk fødselsregister, glidende 3-årsvinduer 2008-2010 til 2023-2025
(34,1 % -> 41,0 %). Dette er MÅLT nasjonal data (ikke modellert), til
forskjell fra NCD-RisC-estimatet brukt i den tidligere brystkreft/BMI-
figuren (se dataviz-healy) - en bedre BMI-proxy for norske kvinner
når den finnes for riktig tidsperiode.

Visualisert med dataviz-healy-skillens `theme_healy()` (samme stil
som SSB-baserte figurer): `fhi-mcp/output/overvekt_gravide.png`. Rådata
i `fhi-mcp/output/overvekt_gravide.csv` og
`fhi-mcp/test_data_overvekt_gravide.json`.

**NB om selve MCP-verktøyene:** de ble ikke synlige i samme samtale-tur
de ble registrert i (`openclaw mcp reload` sier eksplisitt "Active agents
use new MCP config on their next runtime build") - testdataene over ble
derfor hentet med direkte `curl`-kall mot API-et for å verifisere hele
kjeden før verktøyene var tilgjengelige i selve samtalen. Bekreftet
fungerende fra neste tur.

## Bruk fremover

SSB og FHI er komplementære norske offentlige statistikkilder - bruk
ssb-statistikk for SSBs Statistikkbank (befolkning, generell
demografi/økonomi) og `fhi-mcp` (`fhi_*`-verktøy) for helsespesifikk
statistikk (sykdomsforekomst, legemiddelbruk, vaksinasjon, MFR-baserte
mål som overvekt hos gravide). Samme regel som ssb-statistikk: foreslå
relevante tabeller proaktivt i skrivearbeid, men hent/bruk ALDRI data
uoppfordret. dataviz-healy er standard visualiseringsmetode for data
fra begge kildene.
