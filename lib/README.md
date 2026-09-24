# lib: felles hjelpemoduler for agenten

Små, gjenbrukbare Python-moduler som en OpenClaw-agent (eller et hvilket som helst annet
agent-oppsett) kan bruke i stedet for å skrive engangsscript hver gang. Tanken er at agenten
alltid importerer disse, slik at feil du en gang har rettet (for eksempel norske tegn i
vedleggsnavn) ikke kommer tilbake.

Alle hemmeligheter hentes fra 1Password via `onepassword.py`. Ingenting leses fra klartekstfiler,
og ingen nøkler ligger i koden. Se sikkerhetsseksjonen i
[Otto-veilederen](https://nassehi.no/alt/otto-veileder/).

| Modul | Hva den gjør |
|---|---|
| `onepassword.py` | `op_read("op://Hvelv/Item/felt")`. Leser service account-token fra `.secrets/1password-service-account.token` (chmod 600, ikke i git) og sender det kun til `op`-prosessen. |
| `mailer.py` | `send_email(to, subject, body, cc=, attachments=, in_reply_to=)`. Bruker `email.message.EmailMessage`, som koder filnavn med æøå riktig. Logger Message-ID for tråding. Nekter linjeskift i headere (header-injeksjon). |
| `mail_receiver.py` | Henter e-post og vedlegg via IMAP. Vedleggsfilnavn saneres før de skrives til disk (unngår katalogtraversering). |
| `mail_search.py` | Fritekstsøk på tvers av mapper (INBOX/Sent/Archive), med liste over vedleggsnavn. |
| `docconvert.py` | Markdown til docx (standard) eller pdf via `pandoc` og `weasyprint`. |
| `refdb.py` | Lokal referansedatabase (SQLite + FTS5). Se `../reference-manager/README.md`. |
| `openalex.py`, `elicit.py`, `literature_search.py` | Litteratursøk. OpenAlex er åpent. Elicit krever egen nøkkel. |
| `helsedir_innhold.py`, `helsedir_legemidler.py` | Helsedirektoratets åpne API-er (retningslinjer, ATC/FEST). Krever egen abonnementsnøkkel fra utvikler.helsedirektoratet.no. |
| `helserefusjon.py` | Takstbruk/refusjonsstatistikk (åpent API, ingen nøkkel). |
| `snl.py`, `wikipedia_lookup.py` | Oppslag i Store norske leksikon og Wikipedia. |
| `ics_calendar.py` | Read-only lesing av en kalender via ICS-abonnementslenke (lenken ligger i 1Password). |

## Konfigurasjon (miljøvariabler)

| Variabel | Bruk | Standard |
|---|---|---|
| `AGENT_MAIL_OP_ITEM` | 1Password-item for agentens e-postkonto | `op://Agent/Agent email` |
| `CONTACT_EMAIL` | Kontaktadresse i User-Agent/`mailto` mot åpne API-er (OpenAlex, Unpaywall, Wikipedia) | `you@example.org` |
| `ELICIT_OP_REF` | Elicit API-nøkkel i 1Password | `op://Agent/Elicit API Key/credential` |
| `HELSEDIR_OP_REF` | Helsedirektoratet-nøkkel i 1Password | `op://Agent/Helsedirektoratet API/primary API-key` |

1Password-itemet for e-post må ha feltene `username`, `password`, `smtp_host`, `smtp_port`,
`imap_host` og `imap_port` (se `_load_config()` i `mailer.py`). Bruk en egen e-postadresse til agenten, ikke din egen.

## Testing

Ingen av modulene er testet mot din konto. Kjør dem først mot en testadresse, og les koden før du
gir agenten tilgang. Modulene er skrevet for én bruker på én maskin.
