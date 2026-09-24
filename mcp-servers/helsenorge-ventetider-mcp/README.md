# helsenorge-ventetider-mcp

Egenbygget MCP-wrapper rundt det interne (udokumenterte) frontend-APIet bak
[tjenester.helsenorge.no/velg-behandlingssted](https://tjenester.helsenorge.no/velg-behandlingssted/behandlinger),
satt opp 2026-09-14. Samme mønster som
kartverket-mcp, brreg-mcp, osv. (Python, `mcp==1.29.0`, egen venv).

## Bakgrunn / hvordan API-et ble funnet

Siden er en SPA (ingen data i rå HTML). Endepunktene ble funnet ved å åpne
siden i nettleser-verktøyet og lese `performance.getEntriesByType('resource')`
for faktiske XHR-kall.

**Viktig lærdom fra oppsettet:** et første gjettet endepunkt,
`Behandlingssteder?behandlingsId=<id>`, så plausibelt ut (returnerte 200 OK
og ekte data), men viste seg å **ignorere `behandlingsId` helt** - samme
595 steder uansett hvilken (eller hvor ugyldig) ID som ble sendt inn. Dette
ble oppdaget ved å teste flere behandlings-ID-er og se at resultatet var
byte-for-byte identisk. Det faktiske filtrerte endepunktet ble funnet ved å
faktisk bruke søkefeltet i nettleseren og klikke på et treff, og lese av
kallet siden selv gjorde: `VentetiderForBehandling?behandlingId=<id>` (merk:
entall `behandlingId`, ikke `behandlingsId`). Verifisert riktig ved å
sammenligne to ulike behandlings-ID-er og bekrefte at de ga ulike,
korrekt store lister.

## API-et

- Base URL: `https://tjenester.helsenorge.no/proxy/velgbehandlingssted/api/v1`
- Ingen autentisering nødvendig - samme åpne kall siden selv bruker før
  innlogging.
- **Ikke** en dokumentert/stabil offentlig API (ingen Swagger, ingen nøkkel)
  - det er nettsidens eget interne frontend-API og kan endre seg uten
  varsel.
- To relevante kall:
  1. `GET /Behandlinger` - full skattefri-tekst-taksonomi av alle
     behandlinger/undersøkelser (gruppe -> undergruppe -> behandling), med
     `behandlingsId` per behandling. ~30 KB, endres sjelden - cachet 24t i
     minnet i serveren.
  2. `GET /VentetiderForBehandling?behandlingId=<id>` - ventetider (i uker)
     per behandlingssted for én spesifikk behandling. Hvert sted kan ha
     flere ventetid-typer (f.eks. "poliklinisk utredning/behandling" vs
     "innleggelse").

## Verktøy (MCP-server `helsenorge-ventetider`)

To verktøy:

1. **`helsenorge_sok_behandling`** - fritekstsøk i behandlingstaksonomien
   (matcher navn, synonym og undergruppe), returnerer `behandlingsId` for
   bruk i verktøy 2. Taksonomien er prosedyre-/undersøkelsesbasert, ikke
   diagnosebasert (f.eks. finnes ikke "overaktiv blære" som egen oppføring,
   kun de relevante undersøkelsene som cystoskopi/uroflowmetri) - vurder
   klinisk hvilket treff som faktisk er relevant.
2. **`helsenorge_ventetider`** - henter ventetider for en gitt
   `behandlingsId`. **Standardoppførsel (satt
   2026-09-14):** returnerer kun steder i Helse Vest (Helse Stavanger,
   Helse Bergen, Helse Fonna, Helse Førde) + Sørlandet sykehus Flekkefjord
   (matchet på navn, siden Flekkefjord administrativt hører til Helse
   Sør-Øst). Hvis korteste ventetid i regionen er over 10 uker (eller
   ingen regionalt sted tilbyr behandlingen), inkluderes automatisk de 5
   stedene i Norge med kortest ventetid som alternativ - ingen ekstra kall
   nødvendig. `kun_region=false` gir alle behandlingssteder i Norge.

## Oppsett

- `server.py` - MCP-server (Python, to verktøy over).
- Egen venv: `.venv-helsenorge-ventetider-mcp/` (`mcp==1.29.0`,
  `requests==2.34.2`).
- Registrert i OpenClaw som MCP-server `helsenorge-ventetider` via
  `openclaw mcp add helsenorge-ventetider --command .../python --arg
  .../server.py`. Sjekk status: `openclaw mcp doctor helsenorge-ventetider
  --probe`.
- Ingen API-nøkkel nødvendig.

## Testet 2026-09-14

Verifisert mot live data:

1. `helsenorge_sok_behandling("koloskopi")` -> topptreff "Koloskopi og
   sigmoidoskopi" (id 235), korrekt over "Rektoskopi"/"Gastroskopi".
2. `helsenorge_ventetider("235")` -> 12 regionale steder, Stavanger
   universitetssjukehus 8 uker, Flekkefjord 12 uker, Bergen/Voss/Førde
   varierende - realistiske og internt konsistente tall.
3. Nasjonal fallback testet med "Allergiutredning hos øre-nese-
   halsspesialist, voksne": korteste region 26 uker (over terskel) ->
   `nasjonaleAlternativer` fylt med 5 steder med kortest ventetid nasjonalt
   (bl.a. Ahus/Kristiansand/Gjøvik/Drammen 0 uker), `merknad` forklarer
   hvorfor.
4. Null-ventetid-håndtering testet med "Barne- og ungdomsavdeling" (en
   kategori-lignende oppføring uten reelle ventetidsdata) - alle steder
   fikk `kortesteVentetidUker: null` korrekt, trigget nasjonalt søk uten
   å krasje.
5. Bekreftet at det tidligere (feilaktige) `Behandlingssteder`-endepunktet
   returnerte identisk data for ulike/ugyldige ID-er - IKKE brukt i den
   endelige implementasjonen.

## Bruk fremover

Ventetidsoppslag direkte i en henvisningssamtale, f.eks. via
gp-fagstøtte-skillen: "hva er ventetiden for X i mitt område, og er det
raskere andre steder i Norge?"
