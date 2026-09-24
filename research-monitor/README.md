# research-monitor: ukentlig litteraturovervåking

Ukentlig søk etter nye publikasjoner og nyheter om et tema du følger, med kritisk kvalitetsvurdering
av agenten og varsling på Telegram/e-post. Eksemplet er satt opp for KI i allmennmedisin. Bytt
søkestrenger og journalliste til ditt eget felt.

## Arbeidsdeling

1. **Cron (uten agent):** `scripts/weekly_report.py` søker og skriver rå kandidater til
   `output/pending_shortlist.json`. Kilder: PubMed (E-utilities, åpent), nyheter (Perplexity API,
   valgfritt), Elicit (valgfritt) og OpenAlex (åpent, tverrfaglig). Feiler en valgfri kilde, stopper
   ikke resten.
2. **Agenten (ved neste heartbeat):** leser filen, gjør en bred relevanstriage med streng terskel,
   vurderer kvaliteten på de som består (formål, opphav og interesser inkl. finansiering/COI, metode,
   retorikk, ideologiske premisser, resultater, hva som mangler), velger 4-8 og sender dem med
   tittel, lenke og kort begrunnelse. Filen arkiveres etterpå.
3. **Du:** svarer med numrene som var relevante. Agenten logger det med en tilbakemeldingsfil
   (`feedback/log.jsonl`), som `relevance_filter.py` kan bruke som few-shot-eksempler.

`relevance_filter.py` og `quality_appraisal.py` er lokale (Ollama) varianter av steg 2 som ligger
igjen som referanse, for dem som vil holde hele vurderingen på egen maskin.

## Oppsett

```bash
pip install requests
export CONTACT_EMAIL=deg@example.org      # NCBI og OpenAlex ber om kontaktadresse
# valgfritt: PERPLEXITY_OP_REF, ELICIT_OP_REF (1Password-referanser, se ../lib/README.md)
python3 scripts/weekly_report.py          # test manuelt først
```

Legg deretter en crontab-linje som kjører den ukentlig, og be agenten om å legge en blokk i
`HEARTBEAT.md` som behandler `output/pending_shortlist.json`. Rediger `TOPIC_QUERY` i
`scripts/pubmed_search.py`, `config/journals.json` og kriteriene i `scripts/relevance_filter.py`.

## Kvalitetsvurdering: to tips

- Hent finansiering og interessekonflikter strukturert fra PubMed (ikke gjett), og merk hva som ikke
  kan vurderes fra sammendraget alene.
- Vurder p-verdier som terskel (signifikant eller ikke) og rangér funn etter effektstørrelse og
  konfidensintervall.

## Ansvar

Verktøyet finner og sorterer, det erstatter ikke din egen faglige vurdering. Les kildene selv før du
siterer dem.
