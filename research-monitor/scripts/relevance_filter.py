#!/usr/bin/env python3
"""
Vurderer relevans av hvert funn (PubMed + nyheter) lokalt via Ollama, med
STRENG terskel. Bygger few-shot-eksempler inn i prompten fra
feedback/log.jsonl (brukerens tidligere "relevant"/"ikke relevant"-vurderinger)
slik at kriteriene gradvis kalibreres mot hans faktiske smak.

Bruk:
    python3 relevance_filter.py <input.json> <output.json> [--model qwen3:8b|gemma3:12b]
"""
from __future__ import annotations

import json
import os
import sys

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
FEEDBACK_LOG = os.path.join(os.path.dirname(__file__), "..", "feedback", "log.jsonl")

RELEVANCE_CRITERIA = """Du vurderer om et funn (vitenskapelig artikkel eller nyhetssak) er RELEVANT \
for en lege og forsker (TILPASS TIL DITT FELT) som forsker på teknologidrevet \
(hovedsakelig generativ og agentisk KI-drevet) dehumanisering av allmennmedisin, \
primærhelsetjenesten og medisin som helhet.

RELEVANT betyr at funnet handler substansielt om MINST ÉN av disse temaene:
1. KI/teknologi i klinisk praksis - konkret bruk, evaluering eller effekt, ikke bare nevnt i forbifarten
2. Dehumanisering av helsevesenet - hvordan teknologi endrer det menneskelige i pasientmøtet
3. Arbeidsflytendringer for helsepersonell drevet av KI/automatisering
4. Pasient-lege-relasjonen påvirket av teknologi
5. Politikk/regulering av KI i helsevesenet

IKKE relevant (avvis) hvis funnet:
- Kun er en teknisk/algoritmisk studie (f.eks. et nytt bildediagnostikk-verktøy) UTEN \
diskusjon av klinisk arbeidsflyt, pasientrelasjon eller dehumanisering
- Er en produktlansering eller overflatisk nyhetssak uten reell substans
- Gjentar kjent/allment stoff uten noe nytt perspektiv eller funn
- Handler om helseteknologi generelt, men UTEN kobling til KI/automatisering eller \
til allmennmedisin/primærhelsetjeneste/pasient-lege-relasjon spesifikt
- Er en ren metodestudie (validering av spørreskjema, statistisk metode) uten \
tydelig relevans for temaene over

TERSKELEN SKAL VÆRE STRENG. Ved tvil: avvis. Vi ønsker kun de virkelig substansielle \
funnene, ikke trivielle eller banale treff."""


def _load_few_shot_examples(max_examples: int = 8) -> str:
    if not os.path.exists(FEEDBACK_LOG):
        return ""
    entries = []
    with open(FEEDBACK_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    if not entries:
        return ""

    recent = entries[-max_examples:]
    lines = ["\nTIDLIGERE TILBAKEMELDINGER FRA BRUKEREN (bruk disse som eksempler på hva som faktisk er relevant/ikke relevant for akkurat denne personen):"]
    for e in recent:
        verdict = "RELEVANT" if e["relevant"] else "IKKE relevant"
        lines.append(f"- \"{e['title']}\" ({e.get('journal', 'ukjent kilde')}) -> {verdict}")
    return "\n".join(lines)


def _chat(model: str, system_prompt: str, user_prompt: str) -> str:
    payload = {
        "model": model,
        "think": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 400},
        "keep_alive": 0,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def judge_relevance(item: dict, model: str = "qwen3:8b") -> dict:
    system_prompt = RELEVANCE_CRITERIA + _load_few_shot_examples()
    system_prompt += ("\n\nSvar KUN med gyldig JSON: "
                       '{"relevant": true/false, "begrunnelse": "1 kort setning"}')

    user_prompt = (
        f"Tittel: {item['title']}\n"
        f"Kilde: {item.get('journal', 'ukjent')}\n"
        f"Sammendrag: {item.get('abstract', '(ingen sammendrag tilgjengelig)')}"
    )

    try:
        raw = _chat(model, system_prompt, user_prompt)
        parsed = json.loads(raw)
        return {
            "relevant": bool(parsed.get("relevant", False)),
            "begrunnelse": parsed.get("begrunnelse", ""),
        }
    except Exception as e:
        return {"relevant": False, "begrunnelse": f"[Vurderingsfeil: {e}]"}


def filter_items(items: list[dict], model: str = "qwen3:8b") -> list[dict]:
    results = []
    for item in items:
        verdict = judge_relevance(item, model=model)
        item = dict(item)
        item["relevant"] = verdict["relevant"]
        item["begrunnelse"] = verdict["begrunnelse"]
        item["vurdert_av_modell"] = model
        results.append(item)
    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Bruk: python3 relevance_filter.py <input.json> <output.json> [modell]")
        sys.exit(1)

    in_path, out_path = sys.argv[1], sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else "qwen3:8b"

    with open(in_path, encoding="utf-8") as f:
        items = json.load(f)

    results = filter_items(items, model=model)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    relevant = [r for r in results if r["relevant"]]
    print(f"Vurdert {len(results)} funn med {model}: {len(relevant)} vurdert relevante.")
    for r in relevant:
        print(f"  [RELEVANT] {r['title']} - {r['begrunnelse']}")
