#!/usr/bin/env python3
"""
Kritisk kvalitetsvurdering (brukerens rammeverk, 2026-07-29) av PubMed-funn
som allerede har bestått den brede relevansfiltreringen. Kjøres KUN lokalt
via Ollama (qwen3:8b) - aldri Claude/sky-API.

Vurderer: formål/spørsmål, opphav/interesser (finansiering/COI - hentet
strukturert fra PubMed, ikke gjettet), metode, retorikk, TESCREAL-ideologiske
premisser, resultater/klinisk relevans, og hva som ikke er sagt. Output er
KOMPAKT (kvalitetsnivå + korte flagg) - selve vurderingsteksten skal ikke
være lang, siden brukeren vil ha korte varsler og heller åpne kilden selv.

Punkter som krever fullteksttilgang (f.eks. eksakt promptutforming,
temperatur, evaluator-identitet) markeres eksplisitt som "ikke vurderbart
fra sammendrag" i stedet for gjettet - IKKE alle 8 punkter i brukerens
rammeverk er besvarbare fra et PubMed-sammendrag alene.
"""
from __future__ import annotations

import json
import os

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:8b"

APPRAISAL_SYSTEM_PROMPT = """Du er en erfaren kritisk leser av medisinsk litteratur med spesialkompetanse \
på kunstig intelligens i allmennmedisin. Vurder artikkelen systematisk etter \
dette rammeverket, basert KUN på tittel, sammendrag, tidsskrift, \
publikasjonstype, oppgitt finansiering og interessekonflikt-erklæring (hvis \
tilgjengelig) - du har IKKE tilgang til fullteksten.

VURDER:
1. FORMÅL: Er forskningsspørsmålet uavhengig formulert, eller forutsetter \
det allerede at KI-verktøyet er nyttig/nødvendig?
2. OPPHAV/INTERESSER: Finansiering og interessekonflikter (bruk oppgitt \
finansierings-/COI-data hvis tilgjengelig - ikke gjett hvis fraværende). Er \
det fagfellevurdert forskning, eller preprint/whitepaper/opinion fremstilt \
som forskning (bruk publikasjonstype)?
3. METODE (vurder kun det som fremgår av sammendraget): fare for benchmark \
contamination, hvem som evaluerte resultatene (menneske med klinisk \
kompetanse, LLM-as-judge, eller modellen selv), rettferdig \
sammenligningsgrunnlag, skille mellom KI som sekretærverktøy vs. \
diagnostisk/beslutningsstøttende verktøy.
4. RETORIKK: antroposentrerende/overselgende språk ("revolusjonerende", \
"som en erfaren kollega", "frigjør tid") uten datagrunnlag.
5. TESCREAL-PREMISSER: transhumanistiske/effektiv-altruisme/longtermisme-premisser \
- mennesket som flaskehals, teknologisk determinisme, "mer data/skala er \
alltid et gode".
6. RESULTATER/KLINISK RELEVANS: gap mellom målt utfall (benchmark-skår) og \
faktisk klinisk relevans (pasientutfall, tillit, kontinuitet, klinisk skjønn).
7. HVA SOM MANGLER: pasientens stemme, klinikerens autonomi, konsekvenser \
for lege-pasient-kontinuitet.

For punkter der sammendraget IKKE gir nok grunnlag til å vurdere (typisk \
eksakt promptutforming, temperatur, evaluator-identitet i detalj), skal du \
IKKE gjette - marker punktet som ikke vurderbart.

Svar KUN med gyldig JSON på formen:
{"kvalitet": "høy"|"middels"|"lav", \
"kort_begrunnelse": "1-3 setninger - hovedkonklusjon, er dette uavhengig \
forskning eller markedsføring med akademisk innpakning", \
"flagg": ["konkrete bekymringer funnet, f.eks. 'finansiert av leverandør', \
'ikke fagfellevurdert', 'LLM-as-judge uten menneskelig evaluator', \
'TESCREAL-retorikk', 'svakt sammenligningsgrunnlag' - tom liste hvis ingen"], \
"ikke_vurderbart": ["hvilke av punktene 1-7 over som ikke kunne vurderes \
fra sammendraget alene"]}

Ingen innledning, ingen forklaring, ingen tenke-tags - kun JSON-objektet."""


def _chat(system_prompt: str, user_prompt: str) -> str:
    payload = {
        "model": MODEL,
        "think": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 600},
        "keep_alive": 0,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def appraise(item: dict) -> dict:
    coi = item.get("coi_statement") or "Ikke oppgitt i PubMed-posten"
    funding = ", ".join(item.get("funding") or []) or "Ikke oppgitt i PubMed-posten"
    pub_types = ", ".join(item.get("publication_types") or []) or "Ukjent"

    user_prompt = (
        f"Tittel: {item['title']}\n"
        f"Tidsskrift: {item.get('journal', 'ukjent')}\n"
        f"Publikasjonstype: {pub_types}\n"
        f"Finansiering (fra PubMed): {funding}\n"
        f"Interessekonflikt-erklæring (fra PubMed): {coi}\n"
        f"Sammendrag: {item.get('abstract', '(ingen sammendrag tilgjengelig)')}"
    )

    try:
        raw = _chat(APPRAISAL_SYSTEM_PROMPT, user_prompt)
        parsed = json.loads(raw)
        verdict = {
            "kvalitet": parsed.get("kvalitet", "lav"),
            "kort_begrunnelse": parsed.get("kort_begrunnelse", ""),
            "flagg": parsed.get("flagg", []),
            "ikke_vurderbart": parsed.get("ikke_vurderbart", []),
        }
        return _apply_hard_rules(verdict, item)
    except Exception as e:
        return {"kvalitet": "lav", "kort_begrunnelse": f"[Vurderingsfeil: {e}]",
                "flagg": [], "ikke_vurderbart": []}


# Publikasjonstyper som per definisjon ikke er empirisk primærforskning -
# kan aldri vurderes "høy" uansett hva modellen selv konkluderer, siden
# "uavhengig forskning vs. opinion/markedsføring" er kjernen i rammeverket.
NON_EMPIRICAL_TYPES = {
    "Letter", "Comment", "Editorial", "News", "Retraction of Publication",
    "Published Erratum", "Congress",
}


def _apply_hard_rules(verdict: dict, item: dict) -> dict:
    """Modellen er ikke alltid selv-konsistent (har gitt 'høy' til funn den
    selv beskriver som 'uten empirisk forskning' eller 'ikke
    fagfellevurdert') - disse faste reglene overstyrer slike tilfeller i
    stedet for å stole blindt på modellens egen kvalitetslabel."""
    pub_types = set(item.get("publication_types") or [])
    flagg = verdict.get("flagg") or []

    if verdict["kvalitet"] == "høy":
        if pub_types & NON_EMPIRICAL_TYPES:
            verdict["kvalitet"] = "middels"
            verdict["kort_begrunnelse"] += " [Nedgradert: publikasjonstype er ikke empirisk primærforskning.]"
        elif flagg:
            verdict["kvalitet"] = "middels"
            verdict["kort_begrunnelse"] += " [Nedgradert: hadde ett eller flere kvalitetsflagg.]"

    return verdict


QUALITY_RANK = {"høy": 2, "middels": 1, "lav": 0}


def select_top(items: list[dict], min_n: int = 4, max_n: int = 8) -> list[dict]:
    """Rangerer etter kvalitetsnivå og velger topp min_n-max_n. Tvinger
    ALDRI frem lavkvalitets funn for å nå min_n - bedre færre enn åtte enn
    å inkludere noe som ikke holder mål."""
    appraised = []
    for item in items:
        verdict = appraise(item)
        item = dict(item)
        item.update(verdict)
        appraised.append(item)

    # Kun høy/middels kvalifiserer i det hele tatt
    qualified = [i for i in appraised if i["kvalitet"] in ("høy", "middels")]
    qualified.sort(key=lambda i: QUALITY_RANK[i["kvalitet"]], reverse=True)

    return qualified[:max_n]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Bruk: python3 quality_appraisal.py <input.json> <output.json>")
        sys.exit(1)
    in_path, out_path = sys.argv[1], sys.argv[2]
    with open(in_path, encoding="utf-8") as f:
        items = json.load(f)
    top = select_top(items)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(top, f, ensure_ascii=False, indent=2)
    print(f"Valgt ut {len(top)} av {len(items)} etter kvalitetsvurdering.")
    for t in top:
        print(f"  [{t['kvalitet'].upper()}] {t['title']}")
        print(f"    {t['kort_begrunnelse']}")
        if t["flagg"]:
            print(f"    Flagg: {', '.join(t['flagg'])}")
