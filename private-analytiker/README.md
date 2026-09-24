# Lag en privat KI-analytiker med Qwen3 (data forlater aldri PC-en)

Denne veilederen viser hvordan du setter opp en analytiker som leser dokumenter (intervjuer,
notater, manuskripter, spørreskjema-fritekst) og analyserer dem med en språkmodell som kjører på
din egen PC. Teksten sendes ikke til noen sky. Den er en fortsettelse av
[Otto-veilederen](https://nassehi.no/alt/otto-veileder/) og forutsetter at du har en PC med Ubuntu,
en GPU og en fungerende OpenClaw-agent.

## 1. Les dette først

**Lokal analyse gjør ikke sensitive data trygge.** Den fjerner bare ett risikoledd, nemlig at
innholdet sendes til en leverandør. Resten er fortsatt ditt ansvar:

- Pasientopplysninger og forskningsdata krever behandlingsgrunnlag, riktig oppbevaringssted og
  ofte godkjenning fra institusjonen din (personvernombud, REK, databehandleravtale,
  risikovurdering). En privat PC hjemme er sjelden et godkjent sted for identifiserbare
  pasientdata. Avklar dette **før** du flytter noe dit.
- Pseudonymisering er ikke anonymisering. Data med kode-nøkkel er fortsatt personopplysninger.
- Start med **syntetiske eller fullstendig anonymiserte tekster** mens du lærer verktøyet å kjenne.
- Egnet uten spesielle godkjenninger: dine egne notater, upubliserte manuskripter du har fått
  til vurdering (sjekk tidsskriftets regler), egne utkast, eksamensoppgaver og intervjudata som
  allerede er anonymisert.

**En liten modell er ikke Claude.** Qwen3 med 8 milliarder parametre er god på å strukturere,
oppsummere og trekke ut temaer. Den er dårligere på nyanser, lange resonnementer og norsk fagspråk,
og den kan finne på ting. Bruk den som en første leser og kontroller alt mot kilden. Bruk den aldri
som beslutningsstøtte for enkeltpasienter.

## 2. Hva du trenger

| Del | Anbefaling |
|---|---|
| GPU | 12 GB VRAM er nok for 8B-modeller (Nvidia RTX 3060 12 GB er et godt, rimelig valg). Mer VRAM gir større modeller og lengre kontekst. |
| RAM | 32 GB |
| Disk | SSD, og **full diskkryptering** (se steg 3) |
| Programvare | Ubuntu, [Ollama](https://ollama.com), `poppler-utils` (pdftotext), `pandoc`, Python 3 |

Modeller jeg har brukt på en 12 GB-GPU (størrelse på disk):

| Modell | Størrelse | Brukes til |
|---|---|---|
| `qwen3:8b` | 5,2 GB | Standardvalget: strukturering, temaanalyse, sammendrag |
| `gemma3:12b` | 8,1 GB | Alternativ når du vil sammenligne, litt tyngre |
| `medgemma:4b` | 3,3 GB | Medisinsk domenetrening, liten og rask |

Ingen av dem er validert for klinisk bruk. Test på eget materiale og sammenlign to modeller når
noe er viktig.

## 3. Sikre PC-en

Gjør dette før du legger inn data:

1. **Diskkryptering (LUKS).** Velg "Encrypt the new Ubuntu installation" under installasjonen.
   Det kan ikke slås på i etterkant uten ominstallering. Uten dette er alt lesbart for den som
   får fysisk tilgang til PC-en.
2. **Skjermlås og sterkt passord.** Sett automatisk lås.
3. **Brannmur:** `sudo ufw enable`. La ingen tjenester lytte mot internett.
4. **Ollama skal bare lytte lokalt.** Standard er `127.0.0.1:11434`. Kontroller:
   ```bash
   ss -ltn | grep 11434     # skal vise 127.0.0.1:11434, ikke 0.0.0.0
   ```
5. **Egen mappe med begrensede rettigheter:**
   ```bash
   mkdir -p ~/privat-analyse/{inn,ut}
   chmod 700 ~/privat-analyse ~/privat-analyse/inn ~/privat-analyse/ut
   ```
6. **Ingen skysynkronisering** av mappen (ikke Dropbox, OneDrive, iCloud eller Google Drive), og ikke
   la agenten ta sikkerhetskopi av den til en skytjeneste. Krypterte lokale sikkerhetskopier er
   greit.

## 4. Installer Ollama og modellen

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b
ollama run qwen3:8b "Svar kort: hva er en kohortstudie?"
sudo apt install -y poppler-utils pandoc python3-requests
```

`ollama run` skal svare i løpet av noen sekunder. Første kall er tregere fordi modellen lastes inn
i GPU-minnet. Sjekk at GPU-en brukes med `nvidia-smi` mens den svarer.

## 5. Få data over på PC-en privat

Dette er den viktigste delen. **Telegram er ikke et privat overføringsmiddel.** Vanlige
Telegram-chatter (og bot-samtaler spesielt) er ikke ende-til-ende-kryptert, filer går via
Telegrams servere, og en agent som mottar filen der kan ha lest innholdet før du rekker å si
"ikke les". Det samme gjelder WhatsApp-, Messenger- og SMS-vedlegg, vanlig e-post og skytjenester
som OneDrive og Google Drive.

Velg en av disse veiene:

### A. Taildrop (Tailscale), enklest fra telefon og andre PC-er

[Tailscale](https://tailscale.com) lager et privat, kryptert nettverk mellom dine enheter
(WireGuard). Taildrop sender filer direkte mellom dem, uten å gå innom en skytjeneste.

1. Installer Tailscale på PC-en og på telefonen/laptopen, og logg inn med **samme konto**.
2. I [Tailscale-adminkonsollen](https://login.tailscale.com/admin) skal Taildrop være tillatt.
3. Engangsoppsett på PC-en (slik at mottak går uten sudo):
   ```bash
   sudo tailscale set --operator=$USER
   ```
4. **Send** fra telefonen: Del-knappen, velg Tailscale, velg PC-en. Fra en annen Linux-maskin:
   ```bash
   tailscale file cp intervju.pdf pc-navn:
   ```
5. **Motta** på PC-en, manuelt eller automatisk:
   ```bash
   tailscale file get ~/privat-analyse/inn/            # henter det som ligger i innboksen
   ```
   For automatisk mottak (starter selv etter omstart), bruk
   [`taildrop-loop.service`](taildrop-loop.service):
   ```bash
   mkdir -p ~/.config/systemd/user
   cp taildrop-loop.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now taildrop-loop.service
   ```

Taildrop fungerer mellom enheter på samme Tailscale-konto. Andre kan bare sende deg filer hvis du
selv har delt enheten med dem.

### B. `scp` eller `rsync` over Tailscale eller lokalnett

Fra en annen Linux/Mac-maskin på samme Tailscale-nett:

```bash
scp intervju.pdf bruker@pc-navn:privat-analyse/inn/
```

Krever at SSH er slått på (`sudo apt install openssh-server`) og helst nøkkelinnlogging i stedet for
passord.

### C. Kryptert USB-disk

Lavterskel og robust når du ikke har nettverk. Bruk en USB-disk med diskkryptering (Ubuntu "Disks"
kan lage en LUKS-kryptert partisjon), kopier filene over, og slett dem fra disken etterpå.

### D. PGP-kryptert e-post (når du ikke kan installere noe på avsendermaskinen)

Nyttig hvis du sender fra en jobb-PC hvor du ikke får lov til å installere Tailscale. Det krever at
avsenderen kan kryptere e-post med PGP (Proton Mail har det innebygd).

1. Lag et nøkkelpar på PC-en: `gpg --full-generate-key`. Privatnøkkelen forlater aldri maskinen.
2. Eksporter den offentlige nøkkelen (`gpg --armor --export din@adresse`) og last den opp som
   kontaktnøkkel i avsenderens e-postprogram.
3. Sender krypterer meldingen og vedlegget. Mottaks-skriptet henter e-posten via IMAP og
   dekrypterer lokalt med `gpg --decrypt`.
4. **Emnefeltet krypteres ikke.** Skriv et nøytralt emne uten navn eller opplysninger.

Dette er mer omstendelig. Bruk A eller C hvis du kan.

### Ikke bruk

Telegram, WhatsApp, Messenger, SMS, vanlig e-post, OneDrive/Google Drive/Dropbox, og å lime inn
tekst i chatten med agenten.

## 6. Analyseskriptet

[`analyze_local.py`](analyze_local.py) leser en PDF, docx, txt eller md, deler lange tekster i
biter, ber modellen løse oppgaven for hver bit, og slår delresultatene sammen. Det kaller bare
`127.0.0.1:11434`. Resultatet skrives til en fil (`chmod 600`), og til terminalen kommer bare
metadata.

```bash
python3 analyze_local.py ~/privat-analyse/inn/intervju1.pdf \
    --oppgave "Finn de tre viktigste temaene. Gi ett ordrett sitat per tema." \
    --ut ~/privat-analyse/ut/
```

Eksempel på utskrift (og alt agenten ser):

```json
{"status": "OK", "resultat": "/home/deg/privat-analyse/ut/intervju1_20260924_104420.md",
 "tegn_inn": 54132, "tegn_ut": 287, "deler": 3, "modell": "qwen3:8b", "sekunder": 19}
```

Testet mot en syntetisk tekst på 54 000 tegn (delt i tre) på en RTX 3060 12 GB: ca. 20 sekunder
etter at modellen var lastet, og ca. 45 sekunder for første kall.

Noen valg i skriptet du bør kjenne til:

- `think: false` slår av Qwen3s tenkemodus. Det gir raskere og renere svar. Slå på igjen ved
  vanskelige resonnementsoppgaver, men da må du stripe `<think>`-blokkene.
- `temperature: 0.2` gir mer stabile og mindre kreative svar.
- Kontekstvinduet er 16 384 tokens, og bitene er 20 000 tegn. Med mer VRAM kan du øke begge.
- Systemprompten forbyr å finne på sitater, tall og navn og krever "ikke omtalt" når teksten
  er stum. Det reduserer, men fjerner ikke, hallusinasjon.
- Skannede PDF-er uten tekstlag gir ingen tekst. De trenger OCR (`ocrmypdf`) først.

### Oppgaver som fungerer bra

- "Lag en tematisk kode-oversikt med definisjon og ett ordrett sitat per tema."
- "Trekk ut alle steder der intervjupersonen omtaler ventetid, og siter dem ordrett."
- "Oppsummer i 10 setninger, og list opp hva teksten ikke sier noe om."
- "Lag en liste med metodiske svakheter." (for manuskripter du skal fagfellevurdere; du skriver selv
  vurderingen)

Be alltid om ordrette sitater. Da kan du kontrollere med søk i kildeteksten (Ctrl+F). Et sitat som
ikke finnes i kilden er et hallusinasjons-signal.

## 7. Bruk sammen med agenten uten at agenten ser innholdet

Agenten din bruker en skymodell (Claude eller OpenAI). **Alt agenten leser, sendes til leverandøren.**
Poenget med oppsettet er derfor at agenten kjører skriptet, men aldri åpner filen eller resultatet.

Legg dette i agentens instruksjoner (`AGENTS.md` eller en egen skill) og bekreft at den følger det:

```markdown
## Konfidensielt materiale (privat analyse)

- Materiale i ~/privat-analyse/ skal ALDRI leses av deg. Ikke bruk Read, cat, head, tail, grep
  eller lignende på filer der. Ikke åpne resultatfiler.
- Du kjører kun: python3 ~/privat-analyse/analyze_local.py <fil> --oppgave "<oppgave>" og
  rapporterer metadataene (filsti, tegn, tid). Ikke skriv innholdet i chatten.
- Bruk aldri sub-agenter eller andre skymodeller på dette materialet.
- Hvis jeg limer konfidensiell tekst rett inn i chatten, si fra at det allerede er sendt til
  skyen, og be meg sende det som fil neste gang.
- Før du starter, bekreft: "Dette behandles nå kun med den lokale modellen, korrekt?"
```

Dette er en instruks, ikke en teknisk sperre. Agenten kan i prinsippet lese filene hvis den bryter
regelen. Vil du ha en hard sperre, kjør analysen som en egen Linux-bruker uten agentens tilgang, eller
kjør skriptet selv i terminalen. Det er da bare du som ser resultatet.

**Tekst limt inn i chatten er allerede sendt.** Send alltid som fil (Taildrop), aldri som melding.

## 8. Hvis du vil bygge videre

- **Mappe-overvåking:** la et lite skript (systemd-tjeneste) kjøre `analyze_local.py` på nye filer i
  `inn/` med en fast oppgave, og flytte ferdige filer til `arkiv/`.
- **Andre modeller:** `ollama pull gemma3:12b` og `--modell gemma3:12b`. For bokmål finnes
  norskspesifikke modeller (for eksempel Nasjonalbibliotekets NB-serie). Test mot eget materiale
  før du velger.
- **Lydopptak:** `whisper` (lokalt) kan transkribere intervjuer før analyse. Da kjører også
  transkripsjonen lokalt. Se agent-veilederen for oppskrift.
- **Slette:** når analysen er ferdig, slett kildefilen og eventuelle mellomfiler. Sikker sletting
  (`shred`) virker dårlig på moderne SSD-er, så det er diskkrypteringen som er den reelle beskyttelsen.

## 9. Feilsøking

| Symptom | Årsak og løsning |
|---|---|
| `FEIL: ConnectionError` | Ollama kjører ikke. `systemctl status ollama`, eller `ollama serve`. |
| Veldig treg | Modellen kjører på CPU. Sjekk `ollama ps` (skal vise GPU) og `nvidia-smi`. En annen jobb kan ha fylt VRAM. |
| `FEIL: RuntimeError` med PDF | Skannet PDF uten tekstlag, eller `poppler-utils` mangler. |
| Svaret er tomt eller avbrutt | Øk `NUM_PREDICT`, eller bruk kortere oppgave. |
| Modellen "glemmer" innhold i lange filer | Delene er for store for konteksten. Reduser `MAX_CHUNK_CHARS`. |
| Sitater som ikke finnes i kilden | Hallusinasjon. Kontroller mot kilden, og prøv en annen modell. |
