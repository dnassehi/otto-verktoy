#!/usr/bin/env python3
"""Rent lokal analyse av en fil med Ollama (Qwen3 som standard).

HARD REGEL: scriptet kaller bare http://127.0.0.1:11434 (Ollama på samme
maskin). Ingen sky-API. Kildeteksten og modellens svar skrives kun til fil,
aldri til stdout eller logg. Til terminalen (og dermed til en agent som
kjører scriptet via Bash) skrives bare metadata: filsti, antall tegn, antall
deler, modell, tidsbruk. Dette er det som gjør at en skybasert agent kan
starte en analyse uten å se innholdet.

Bruk:
    python3 analyze_local.py inn/notat.pdf --oppgave "Oppsummer hovedpunktene"
    python3 analyze_local.py inn/intervju.docx --oppgave-fil prompts/tematisk.txt \\
        --modell qwen3:8b --ut ut/

Støttede filer: .pdf (pdftotext), .docx/.odt/.html (pandoc), .txt/.md.
Store filer deles i deler (kart), hver del analyseres, og delresultatene slås
sammen til ett svar (reduser).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3:8b"
NUM_CTX = 16384          # 16k passer i 12 GB VRAM med en 8B-modell. Øk hvis du har mer.
MAX_CHUNK_CHARS = 20000  # ca. 5000 tokens norsk tekst, gir plass til svar og instruks
NUM_PREDICT = 2000
TIMEOUT_S = 900

SYSTEM = (
    "Du er en nøyaktig analytiker. Svar på norsk. Bruk bare det som står i teksten. "
    "Hvis teksten ikke sier noe om et punkt, skriv 'ikke omtalt'. Ikke gjett og ikke finn på "
    "sitater, tall eller navn. Siter korte, ordrette utdrag når du støtter en påstand."
)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError("pdftotext feilet (mangler poppler-utils, eller PDF uten tekstlag)")
        return out.stdout
    if suffix in {".docx", ".odt", ".html", ".htm", ".rtf"}:
        out = subprocess.run(["pandoc", str(path), "-t", "plain", "--wrap=none"], capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError("pandoc feilet")
        return out.stdout
    if suffix in {".txt", ".md", ""}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise RuntimeError(f"Ukjent filtype: {suffix}")


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for para in re.split(r"\n\s*\n", text):
        if len(para) > max_chars:  # veldig lang "avsnitt": kutt hardt
            if current:
                chunks.append("\n\n".join(current))
                current, size = [], 0
            chunks += [para[i:i + max_chars] for i in range(0, len(para), max_chars)]
            continue
        if size + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(para)
        size += len(para)
    if current:
        chunks.append("\n\n".join(current))
    return [c.strip() for c in chunks if c.strip()]


def chat(prompt: str, model: str, num_predict: int = NUM_PREDICT) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "stream": False,
        "think": False,  # Qwen3: slå av tenkemodus. Raskere og gir ren tekst.
        "options": {"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": num_predict},
        "keep_alive": "10m",  # behold modellen i VRAM mellom delene, frigjør etter 10 min
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_S)
    r.raise_for_status()
    text = r.json()["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def analyze(text: str, task: str, model: str) -> tuple[str, int]:
    chunks = chunk_text(text)
    n = len(chunks)
    if n == 1:
        return chat(f"OPPGAVE:\n{task}\n\nTEKST:\n{chunks[0]}", model), 1
    partials = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"del {i}/{n} ...", file=sys.stderr)  # kun fremdrift, aldri innhold
        partials.append(chat(
            f"OPPGAVE:\n{task}\n\nDette er del {i} av {n} av en lengre tekst. Løs oppgaven for "
            f"akkurat denne delen.\n\nTEKST:\n{chunk}", model))
    joined = "\n\n---\n\n".join(f"Delresultat {i}:\n{p}" for i, p in enumerate(partials, 1))
    merged = chat(
        f"OPPGAVE:\n{task}\n\nUnder er delresultater fra {n} deler av samme tekst. Slå dem sammen "
        f"til ett helhetlig svar. Fjern gjentakelser, behold ordrette sitater, og ikke legg til noe "
        f"som ikke står i delresultatene.\n\n{joined}", model, num_predict=3000)
    return merged, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fil")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--oppgave", help="hva modellen skal gjøre med teksten")
    g.add_argument("--oppgave-fil", help="fil med oppgavebeskrivelsen")
    ap.add_argument("--modell", default=DEFAULT_MODEL)
    ap.add_argument("--ut", default="ut", help="mappe for resultatfilen (opprettes med rettighet 700)")
    args = ap.parse_args()

    src = Path(args.fil)
    task = args.oppgave or Path(args.oppgave_fil).read_text(encoding="utf-8")
    out_dir = Path(args.ut)
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    started = time.time()
    try:
        text = extract_text(src)
        if not text.strip():
            print("FEIL: ingen tekst i filen (skannet PDF uten tekstlag trenger OCR)")
            return 1
        result, n_chunks = analyze(text, task, args.modell)
    except (RuntimeError, requests.RequestException) as e:
        print(f"FEIL: {type(e).__name__}")  # ikke skriv feilteksten, den kan inneholde utdrag
        return 1

    out_path = out_dir / f"{src.stem}_{datetime.now():%Y%m%d_%H%M%S}.md"
    header = (f"---\nkilde: {src.name}\nmodell: {args.modell}\ndeler: {n_chunks}\n"
              f"laget: {datetime.now():%Y-%m-%d %H:%M}\n---\n\n")
    out_path.write_text(header + result + "\n", encoding="utf-8")
    out_path.chmod(0o600)

    # Kun metadata til stdout.
    print(json.dumps({"status": "OK", "resultat": str(out_path), "tegn_inn": len(text),
                      "tegn_ut": len(result), "deler": n_chunks, "modell": args.modell,
                      "sekunder": round(time.time() - started)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
