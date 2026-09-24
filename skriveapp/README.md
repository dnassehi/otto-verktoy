# skriveapp

Liten, selvhostet skriveapp: rik tekst (Quill), kommentarfelt, en chat-sidebar mot agenten per
dokument og eksport til docx/pdf (nedlasting eller på e-post). FastAPI, én bruker, ingen
registrering. Tenkt som "en veldig lav versjon av Word" agenten kan skrive i og du kan rette i.

## Slik fungerer det

- Dokumenter lagres som filer i `docs/<slug>/` (HTML, kommentarer, chat, metadata) og versjoneres
  automatisk med git i den mappen. `docs/` og `exports/` er ignorert i dette repoet.
- Chatten kjører via `openclaw agent` mot en avgrenset agent (`skriveapp`, egen konfigurasjon med
  `tools.profile: minimal` pluss web_search/web_fetch, uten exec, filsystem eller
  meldingsverktøy). Agenten kan bare foreslå endringer i tre kodeblokk-formater
  (`skriveapp:replace`, `skriveapp:update`, `skriveapp:create`). Selve skrivingen gjøres av
  appkoden, ikke av modellen. Lagret dokument beskyttes mot krymping (en oppdatering som kutter
  over halvparten avvises).
- Innlogging: ett passord (1Password), signert cookie, rate-limiting per IP.
- Eksport på e-post går bare til adresser du selv setter i `SKRIVEAPP_EXPORT_EMAILS`.

## Kjøring

```bash
cd skriveapp
python3 -m venv venv && venv/bin/pip install fastapi uvicorn itsdangerous python-multipart beautifulsoup4
sudo apt install pandoc libreoffice-writer      # for docx/pdf-eksport
export SKRIVEAPP_OP_ITEM="op://Agent/Skriveapp login"     # 1Password-item med feltet "password"
export SKRIVEAPP_EXPORT_EMAILS="deg@example.org"
export SKRIVEAPP_AGENT_NAME="Assistenten"                 # navnet på din egen agent, vises i chatten
export SKRIVEAPP_BASE_PATH=""                             # f.eks. "/skriv" bak en proxy-sti
venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

`auth.py` og `export.py` importerer `lib/` (1Password og e-post) fra repo-roten, så mappen må
ligge ved siden av `lib/`.

## Sikkerhet

- Kjør på `127.0.0.1` og gi tilgang via Tailscale (tailnet) i stedet for åpent internett. Bruker du
  Tailscale Funnel eller en annen offentlig løsning, er passordet den eneste sperren. Bruk da et
  langt, unikt passord.
- Ikke skriv pasientopplysninger i appen. Chatten sender dokumentutdrag til skymodellen.
- `.session_secret` genereres ved første start og skal aldri i git (står i `.gitignore`).
