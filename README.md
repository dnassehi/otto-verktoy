# otto-verktoy

Verktøy jeg har bygget rundt en personlig OpenClaw-agent (min heter "Otto", din kan hete hva du vil) som lege og forsker, delt som
utgangspunkt for deg som vil lage din egen. Alt er hentet fra et fungerende oppsett, men er renset
for personlige data og gjort konfigurerbart. Det er **ikke** testet på din maskin eller mot dine
kontoer, og det er **ikke** medisinsk utstyr eller en ferdig tjeneste.

Start med veilederen: **[nassehi.no/alt/otto-veileder](https://nassehi.no/alt/otto-veileder/)**
(for mennesker), og la agenten din lese
[agent-veilederen](https://nassehi.no/alt/otto-veileder/agent.html).

## Innhold

| Mappe | Hva |
|---|---|
| [`lib/`](lib/) | Felles Python-moduler: e-post (sende, motta, søke), 1Password, dokumentkonvertering, litteratursøk, referansedatabase, Helsedirektoratets API-er |
| [`reference-manager/`](reference-manager/) og [`refman-mcp/`](refman-mcp/) | Lokal referansedatabase (SQLite/FTS5) og en skrivebeskyttet MCP-server rundt den |
| [`research-monitor/`](research-monitor/) | Ukentlig litteraturovervåking med kritisk vurdering |
| [`skriveapp/`](skriveapp/) | Selvhostet skriveapp med kommentarer, agent-chat og eksport |
| [`mcp-servers/`](mcp-servers/) | MCP-servere mot åpne norske og internasjonale datakilder (SSB, FHI, Brønnøysund, Lovdata, MET, Kartverket, WHO, m.fl.) |
| [`private-analytiker/`](private-analytiker/) | Veileder og skript for en helt lokal KI-analytiker med Ollama og Qwen3 |

## Bevisste utelatelser

Følgende er med vilje ikke publisert: kode som bruker lisensierte tilganger (Felleskatalogen via
institusjonsavtale), mirroring av opphavsrettsbeskyttet innhold (Legemiddelhåndboka, RELIS),
uoffisielle innlogginger mot private bibliotek, kode som omgår bot-sperrer for å hente PDF-er, og
alt som er knyttet til mine egne kontoer, kalendere og infrastruktur. SSB-serveren er ikke kopiert,
den er en annens prosjekt: [langtind/ssb-mcp-server](https://github.com/langtind/ssb-mcp-server).

## Sikkerhet og ansvar

- Ingen nøkler eller passord i repoet. Bruk en passordbehandler (1Password service account) og
  miljøvariabler. Se `lib/README.md`.
- Gi agenten sin egen e-postkonto. Ikke gi den tilgang til din egen e-post, kalender eller
  pasientdata.
- Les koden før du kjører den. Du er selv ansvarlig for bruken, også for personvern,
  helsepersonelloven og institusjonens regler.
- Alt er utgangspunkt, ikke fasit. Feil kan forekomme.

## Lisens

MIT, se [LICENSE](LICENSE).
