# tresor: kryptert mappe for personlige data

Verktøy for å lage en kryptert mappe (gocryptfs) på assistentens PC, slik at egne personlige
dokumenter (helse, forsikring, økonomi) ikke ligger i klartekst på disken eller i sikkerhetskopien.

Full veiledning: **[nassehi.no/alt/otto-veileder/tresor.html](https://nassehi.no/alt/otto-veileder/tresor.html)**.
Les avsnittet om hva kryptering ikke beskytter mot før du legger inn noe. Pasientopplysninger hører
ikke hjemme her.

| Fil | Hva |
|---|---|
| `setup.sh` | Oppretter og monterer mappen (`~/.tresor-cipher` krypterte filer, `~/tresor` klartekst). `--service` installerer en systemd-brukertjeneste som monterer ved oppstart |
| `extpass.sh` | Henter passordet fra 1Password (`TRESOR_OP_REF`) og skriver det til stdout, aldri til disk |
| `retention.py` | Sletter filer eldre enn N dager (for eksempel mottatte PDF-er), med valgfri sperre |
| [`../lib/tresor.py`](../lib/tresor.py) | Sti-hjelper som feiler i stedet for å skrive klartekst hvis mappen ikke er montert |

## Kort

```bash
sudo apt install gocryptfs
export TRESOR_OP_REF="op://Assistent/Tresor gocryptfs/password"
./setup.sh              # én gang: opprett og monter (lagre masternøkkelen som skrives ut!)
./setup.sh --service    # monter automatisk ved oppstart
```

Test status: `setup.sh` (opprett og monter) og `retention.py` er kjørt på en testmappe med et
prøvepassord. `extpass.sh` mot 1Password og `--service` er ikke kjørt fra denne kopien.

## Begrensninger

- Passordet hentes automatisk via en token på samme disk. Beskytter mot backup-lekkasje og
  utrangert disk, ikke mot at hele PC-en blir stjålet (sperr tokenet hos passordbehandleren).
- Alt assistenten leser fra mappen går til skymodellen og samtaleloggen (ukryptert).
- Eldre sikkerhetskopier kan inneholde klartekstversjoner av filer du flytter inn.
- Ingen garanti. Du er selv ansvarlig for personvern og lovkrav.
