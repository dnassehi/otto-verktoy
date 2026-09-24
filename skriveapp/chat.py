"""Chat med agenten fra skriveappen: hvert dokument har sin egen isolerte
sesjon under den avgrensede agenten "skriveapp" (agent:skriveapp:<slug>),
adressert via `openclaw agent` CLI-en (ett-gangs agent-tur gjennom Gateway,
se docs/cli/agent.md). Dette gir persistent samtalehistorikk per dokument
uten å blande det inn i hovedsesjonen (Telegram).

Sikkerhet (hva kan noen gjøre hvis skriveapp-passordet lekker): "skriveapp"-agenten er konfigurert i
openclaw.json med tools.profile "minimal" + alsoAllow web_search/web_fetch
- ingen exec, ingen filsystemtilgang, ingen meldingsutsendelse (e-post/
Telegram), ingen sesjons-/1Password-tilgang. Den kan altså kun generere
tekst og gjøre nettsøk. Dokumentoppretting/-redigering skjer IKKE via
agent-verktøy, men ved at denne modulen selv tolker to avtalte kodeblokk-
merker i svarteksten (se _extract_update/_extract_create under) og utfører
den faktiske skrivingen via storage.py - dvs. i klarert apputkode, ikke i
noe LLM-et har direkte tilgang til å utføre selv."""
from __future__ import annotations

import json
import re
import subprocess

import storage
from agentname import AGENT_NAME

CHAT_TIMEOUT_SECONDS = 120

AGENT_ID = "skriveapp"

CAPABILITY_NOTE = """
Du kjører her som en avgrenset skriveapp-assistent, IKKE med din vanlige fulle
verktøytilgang - ingen tilgang til e-post, andre tjenester, 1Password, filsystem
eller å kjøre kommandoer. Du kan kun: (1) skrive tekst, (2) søke/lese på nett
(web_search/web_fetch) til research, og (3) opprette/redigere dokumenter i
DENNE skriveappen via kodeblokk-merkene under - ikke via noe annet.

For enkle tekstendringer (finn-og-erstatt, ett eller flere steder, f.eks.
"bytt ord X til Y gjennom hele dokumentet" eller "rett denne setningen"), bruk
ALLTID "skriveapp:replace" i stedet for "skriveapp:update". Da trenger du
IKKE å ha sett hele dokumentet - hver "old"-streng slås opp og erstattes i det
faktiske lagrede dokumentet, ikke i det avkuttede utdraget du fikk vist:
```skriveapp:replace
[
  {"old": "eksakt tekst som skal erstattes", "new": "ny tekst"},
  {"old": "evt. et annet sted som også skal endres", "new": "ny tekst"}
]
```
"old" må være eksakt (ordrett) tekst som faktisk finnes i dokumentet - kopier
den nøyaktig fra "Nåværende innhold" under, ikke fra hukommelsen. Blir "old"
ikke funnet, blir HELE handlingen avvist og ingenting endres.

For å ERSTATTE HELE innholdet i dokumentet (kun når du har fått/sett hele det
eksisterende innholdet, eller når du skriver noe helt nytt fra bunnen), bruk:
```skriveapp:update
<p>Nytt/oppdatert innhold ...</p>
```
ADVARSEL: "Nåværende innhold" du får vist kan være avkuttet ved lengde-grensen
(det står i så fall eksplisitt under). Bruk ALDRI skriveapp:update når
innholdet du fikk er avkuttet - da vet du ikke hva resten av dokumentet
inneholder, og en skriveapp:update-blokk erstatter ALT. Bruk skriveapp:replace
i stedet, eller spør brukeren om å få hele teksten.

For å OPPRETTE et helt nytt dokument, bruk i stedet:
```skriveapp:create
title: Tittel på det nye dokumentet
---
<p>Innhold ...</p>
```

Bruk kun HTML-tagger editoren faktisk støtter: <h1>-<h3>, <p>, <strong>, <em>,
<u>, <ul>/<ol>/<li>, <a href="...">. Ikke bruk disse blokkene med mindre
brukeren faktisk ba om at noe skal skrives/opprettes i dokumentet - vanlige
spørsmål/diskusjon skal bare besvares som ren tekst uten kodeblokk.
""".strip()

_UPDATE_RE = re.compile(r"```skriveapp:update\s*\n(.*?)```", re.S)
_CREATE_RE = re.compile(r"```skriveapp:create\s*\ntitle:\s*(.+?)\n-{3,}\s*\n(.*?)```", re.S)
_REPLACE_RE = re.compile(r"```skriveapp:replace\s*\n(.*?)```", re.S)

# Dokumentinnhold sendt til modellen kuttes ved denne lengden (se send_to_agent).
# Terskelen brukes også som sikkerhetsnett: en skriveapp:update som krymper et
# ikke-trivielt dokument til under halvparten av gjeldende lengde blir avvist,
# siden det nesten alltid betyr at modellen jobbet ut fra et avkuttet utdrag
# (et utkast kan miste over halve innholdet
# på nøyaktig denne måten).
CONTEXT_CHAR_LIMIT = 6000
_MIN_KEEP_RATIO = 0.5
_SHRINK_GUARD_FLOOR = 500

_ALLOWED_TAGS = {
    "p", "br", "h1", "h2", "h3", "strong", "b", "em", "i", "u",
    "ul", "ol", "li", "blockquote", "a", "span", "div",
}


class ChatError(Exception):
    pass


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sanitize_html(html: str) -> str:
    """Minimal allowlist-sanitizer for HTML agenten selv genererer (skriveapp:update/
    create-blokker). Nødvendig fordi web_fetch/web_search-innhold agenten har lest
    under research i prinsippet kunne prøve å presse ham til å inkludere en
    <script>/on*-payload i dokument-HTML-en, som ellers ville kjørt usanert i
    brukerens innloggede nettleser (lagret XSS) - i motsetning til Quill-editorens
    egen innhold, som kommer fra brukerens egen skriving og ikke sanitiseres her."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        attrs = dict(tag.attrs)
        for attr, value in attrs.items():
            if tag.name == "a" and attr == "href":
                val = str(value).strip()
                if not (val.startswith("http://") or val.startswith("https://") or val.startswith("mailto:")):
                    del tag.attrs[attr]
                continue
            del tag.attrs[attr]
    for bad in soup.find_all(["script", "style", "iframe", "object", "embed"]):
        bad.decompose()

    # Quill 2.x har kun ett listeblot: <ol><li data-list="bullet|ordered">...</li></ol>.
    # Ren <ul>/<ol><li>-HTML uten data-list blir stille fjernet av Quill når den
    # setter quill.root.innerHTML (Parchment gjenkjenner ikke <ul> i det hele
    # tatt, og <li> uten data-list dropper attributtet ved normalisering) -
    # oppdaget 2026-09-01 etter gjentatte rapporter om manglende punktlister.
    for tag in soup.find_all(["ul", "ol"]):
        list_type = "bullet" if tag.name == "ul" else "ordered"
        for li in tag.find_all("li", recursive=False):
            li["data-list"] = list_type
        tag.name = "ol"

    return str(soup)


def _apply_document_actions(slug: str, reply: str) -> str:
    display = reply

    m = _CREATE_RE.search(reply)
    if m:
        title = m.group(1).strip()
        html = _sanitize_html(m.group(2).strip())
        meta = storage.create_doc(title)
        storage.save_content(meta["slug"], html)
        display = display[: m.start()] + display[m.end():]
        display += f'\n\n_(Opprettet nytt dokument: "{title}")_'

    m = _REPLACE_RE.search(display)
    if m:
        try:
            pairs = json.loads(m.group(1).strip())
        except json.JSONDecodeError as e:
            raise ChatError(f"Ugyldig skriveapp:replace-blokk (ikke gyldig JSON): {e}") from e
        current = storage.get_doc(slug)
        if current is None:
            raise ChatError(f"Fant ikke dokumentet {slug}")
        html = current["content"]
        applied = []
        for pair in pairs:
            old, new = pair.get("old", ""), pair.get("new", "")
            if not old:
                raise ChatError("Tomt \"old\"-felt i skriveapp:replace - ingen endringer utført")
            count = html.count(old)
            if count == 0:
                raise ChatError(
                    f'Fant ikke teksten "{old[:80]}" i dokumentet - '
                    "ingen endringer utført (hele handlingen avvist for å unngå delvis skriving)"
                )
            html = html.replace(old, new)
            applied.append(f'"{old[:40]}" -> "{new[:40]}" ({count}x)')
        storage.save_content(slug, _sanitize_html(html))
        display = display[: m.start()] + display[m.end():]
        display += "\n\n_(Erstattet: " + "; ".join(applied) + ")_"

    m = _UPDATE_RE.search(display)
    if m:
        html = _sanitize_html(m.group(1).strip())
        current = storage.get_doc(slug)
        if current is not None:
            old_len = len(_strip_html(current["content"]))
            new_len = len(_strip_html(html))
            if old_len > _SHRINK_GUARD_FLOOR and new_len < old_len * _MIN_KEEP_RATIO:
                raise ChatError(
                    f"skriveapp:update avvist: ny tekst ({new_len} tegn) er under halvparten av "
                    f"gjeldende dokumentlengde ({old_len} tegn). Dette blokkeres automatisk fordi det "
                    "nesten alltid betyr at du har jobbet ut fra et avkuttet utdrag av dokumentet, "
                    "ikke hele det faktiske innholdet. Bruk skriveapp:replace for målrettede endringer "
                    "i stedet, eller be brukeren lime inn hele teksten hvis du faktisk trenger å se alt."
                )
        storage.save_content(slug, html)
        display = display[: m.start()] + display[m.end():]
        display += "\n\n_(Dokumentet er oppdatert.)_"

    return display.strip()


def send_to_agent(slug: str, title: str, doc_html: str, open_comments: list[dict], message: str) -> str:
    context_parts = [CAPABILITY_NOTE, f'[Skriveapp-dokument: "{title}"]']
    plain = _strip_html(doc_html)
    if plain:
        if len(plain) > CONTEXT_CHAR_LIMIT:
            shown = plain[:CONTEXT_CHAR_LIMIT]
            context_parts.append(
                f"Nåværende innhold (AVKUTTET - dette er kun de første {CONTEXT_CHAR_LIMIT} av "
                f"{len(plain)} tegn i dokumentet. Bruk IKKE skriveapp:update basert på denne "
                "visningen alene - bruk skriveapp:replace for målrettede endringer):\n"
                f"{shown}"
            )
        else:
            context_parts.append(f"Nåværende innhold:\n{plain}")
    if open_comments:
        quotes = "\n".join(f"- \"{c['quote']}\": {c['thread'][-1]['text']}" for c in open_comments)
        context_parts.append(f"Uløste kommentarer:\n{quotes}")
    context_parts.append(f"Melding fra brukeren (i chatten for dette dokumentet):\n{message}")
    full_message = "\n\n".join(context_parts)

    session_key = f"agent:{AGENT_ID}:{slug}"
    result = subprocess.run(
        [
            "openclaw", "agent",
            "--session-key", session_key,
            "--message", full_message,
            "--json",
            "--timeout", str(CHAT_TIMEOUT_SECONDS),
        ],
        capture_output=True, text=True, timeout=CHAT_TIMEOUT_SECONDS + 15,
    )
    if result.returncode != 0:
        raise ChatError(f"openclaw agent feilet: {result.stderr[-2000:]}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ChatError(f"Kunne ikke tolke svar fra {AGENT_NAME}: {e}") from e
    if data.get("status") != "ok":
        raise ChatError(f"{AGENT_NAME}-sesjon feilet: {data.get('summary')}")
    payloads = data.get("result", {}).get("payloads", [])
    texts = [p.get("text", "") for p in payloads if p.get("text")]
    reply = "\n\n".join(texts) if texts else f"({AGENT_NAME} svarte uten tekst.)"

    try:
        reply = _apply_document_actions(slug, reply)
    except Exception as e:  # noqa: BLE001 - never let a malformed action block break the chat reply
        reply += f"\n\n_(Klarte ikke å utføre dokumenthandling: {e})_"

    return reply
