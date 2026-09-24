#!/usr/bin/env python3
"""Klient for Helsedirektoratets legemiddel-API (produktet "Legemidler" på
utvikler.helsedirektoratet.no, del av HAPI - Helsedirektoratets API-tjeneste).

Datasett: https://data.norge.no/datasets/3f7926bc-4db0-3ea6-9d74-3373f027137a
Kilde: hovedsakelig FEST (Forskrivnings- og ekspedisjonsstøtte, forvaltet av
Statens Legemiddelverk), forvaltet/publisert av Helsedirektoratet.
Dekker: ATC-registeret, legemidler med markedsføringstillatelse eller solgt på
godkjenningsfritak i Norge.

Krever en Ocp-Apim-Subscription-Key fra utvikler.helsedirektoratet.no
(registrer bruker og abonner på produktet; det krever menneskelig
registrering). Legg nøkkelen i 1Password og pek på den med HELSEDIR_OP_REF.

Bekreftet endepunkt: GET /legemidler/legemiddelvirkestoff
- Uten parametre: returnerer 100 poster (standard side-størrelse).
- Paginering via `skip`/`take` (ikke OData `$skip`/`$top` - de ble prøvd og
  ignorert). `take=10000&skip=0` ga hele datasettet (2199 poster 11.08.2026),
  så reell øvre grense er ikke funnet - `take` opp til minst 10000 fungerer.
- Enkeltoppslag: GET /legemidler/legemiddelvirkestoff/{legemiddelMerkevareId}
  (id-format "ID_<GUID>", hentet fra feltet i listesvaret). Ugyldig/ukjent id
  (f.eks. "1") gir 204 No Content, ikke 404.
- `atcKode`- og `varenavn`-query-parametre ble testet og IGNORERES av API-et
  (samme antall/innhold returnert med og uten dem) - filtrering må gjøres
  klient-side på hele/pagert datasettet, ikke server-side.
- Feltstruktur i hvert element: legemiddelMerkevareId, varenavn, navnFormStyrke,
  atcKode, atcNavn, form, formKode, registreringstidspunkt,
  registreringsstatus, administrasjonsmåter (liste), virkestoffMedStyrke
  (liste: navn, navnEngelsk, styrkeVerdi, styrkeEnhet), pakninger (liste:
  legemiddelPakningId, navnFormStyrke, varenummer, typeSoknadSlv,
  typeSoknadSlvKode, markedsforingsdato).

Andre kandidat-stier i PROBABLE_PATH_PREFIXES er IKKE bekreftet og kan
fjernes/ignoreres - behold kun som referanse for evt. videre kartlegging.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "lib"))
from onepassword import op_read, OnePasswordError  # noqa: E402

PROD_BASE_URL = "https://api.helsedirektoratet.no"
QA_BASE_URL = "https://api-qa.helsedirektoratet.no"

# Uverifiserte kandidat-stier for legemiddel-API-et, basert kun på at
# produktet heter "Legemidler" på portalen. Test disse (og varianter) med
# discover() så snart en gyldig subscription key finnes - ikke stol på dem.
PROBABLE_PATH_PREFIXES = [
    "/legemidler",
    "/legemiddel",
    "/atc",
    "/hapi/legemidler",
]

# 1Password-referanse - delt nøkkel for Helsedirektoratets
# pasientjournalsystemer"-produktet, bekreftet 11.08.2026 å dekke også
# "Legemidler"-produktet (samme nøkkel). Bruker item-ID (ikke tittel) fordi
# `op read` avviser 'ø' i selve op://-referansesyntaksen; feltet heter
# "primary API-key" direkte på item-toppnivå, ingen "add more"-seksjon.
OP_REFERENCE = os.environ.get("HELSEDIR_OP_REF", "op://Agent/Helsedirektoratet API/primary API-key")


class LegemidlerAPIError(Exception):
    """Feil ved kall mot Helsedirektoratets legemiddel-API."""


def _subscription_key() -> str:
    try:
        return op_read(OP_REFERENCE)
    except OnePasswordError as e:
        raise LegemidlerAPIError(
            "Fant ikke Ocp-Apim-Subscription-Key i 1Password "
            f"({OP_REFERENCE})."
        ) from e


class LegemidlerClient:
    def __init__(self, prod: bool = True, subscription_key: str | None = None):
        self.base_url = PROD_BASE_URL if prod else QA_BASE_URL
        self.subscription_key = subscription_key or _subscription_key()

    def _headers(self) -> dict:
        return {"Ocp-Apim-Subscription-Key": self.subscription_key}

    def get(self, path: str, params: dict | None = None) -> dict:
        """Generisk GET mot API-et. Bruk til å teste/kartlegge faktiske
        endepunkter før spesifikke metoder (søk på virkestoff/ATC-kode osv.)
        bygges - disse finnes ikke ennå, se modul-docstring."""
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        if resp.status_code == 401:
            raise LegemidlerAPIError(
                "401 Unauthorized - subscription key ugyldig, ikke aktivert "
                "ennå, eller mangler tilgang til produktet 'Legemidler'."
            )
        resp.raise_for_status()
        return resp.json()

    def discover(self) -> dict:
        """Prøver kandidat-stiene i PROBABLE_PATH_PREFIXES og rapporterer
        hvilke som gir noe annet enn 404, som utgangspunkt for å kartlegge
        det faktiske API-et manuelt (f.eks. via 'Try it'-konsollet på
        portalen når en nettleser er tilgjengelig igjen)."""
        results = {}
        for path in PROBABLE_PATH_PREFIXES:
            url = f"{self.base_url}{path}"
            try:
                resp = requests.get(url, headers=self._headers(), timeout=10)
                results[path] = {"status": resp.status_code, "body": resp.text[:500]}
            except requests.RequestException as e:
                results[path] = {"error": str(e)}
        return results

    def get_legemiddelvirkestoff_page(self, skip: int = 0, take: int = 100) -> list[dict]:
        """Én side av /legemidler/legemiddelvirkestoff."""
        return self.get("/legemidler/legemiddelvirkestoff", params={"skip": skip, "take": take})

    def get_all_legemiddelvirkestoff(self, page_size: int = 2000) -> list[dict]:
        """Henter hele datasettet ved å paginere med skip/take. Datasettet
        var 2199 poster 11.08.2026 - juster page_size om det vokser mye
        (take=10000 er bekreftet å fungere i ett kall, men flere mindre
        kall er skånsommere mot gatewayen)."""
        all_rows: list[dict] = []
        skip = 0
        while True:
            page = self.get_legemiddelvirkestoff_page(skip=skip, take=page_size)
            if not page:
                break
            all_rows.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
        return all_rows

    def get_by_id(self, legemiddel_merkevare_id: str) -> dict | None:
        """Enkeltoppslag på legemiddelMerkevareId (format 'ID_<GUID>').
        Returnerer None ved ukjent id (API-et gir 204 No Content, ikke 404)."""
        url = f"{self.base_url}/legemidler/legemiddelvirkestoff/{legemiddel_merkevare_id}"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        if resp.status_code == 204:
            return None
        if resp.status_code == 401:
            raise LegemidlerAPIError(
                "401 Unauthorized - subscription key ugyldig, ikke aktivert "
                "ennå, eller mangler tilgang til produktet 'Legemidler'."
            )
        resp.raise_for_status()
        return resp.json()

    def search_by_atc(self, atc_kode: str, exact: bool = False) -> list[dict]:
        """Klient-side filtrering på atcKode (API-et ignorerer atcKode som
        query-parameter - bekreftet 11.08.2026). Henter hele datasettet
        og filtrerer lokalt."""
        rows = self.get_all_legemiddelvirkestoff()
        if exact:
            return [r for r in rows if r.get("atcKode") == atc_kode]
        return [r for r in rows if str(r.get("atcKode", "")).startswith(atc_kode)]

    def search_by_navn(self, tekst: str) -> list[dict]:
        """Klient-side filtrering på varenavn/navnFormStyrke (delstreng,
        case-insensitive). API-et ignorerer varenavn som query-parameter."""
        tekst_lower = tekst.lower()
        rows = self.get_all_legemiddelvirkestoff()
        return [
            r for r in rows
            if tekst_lower in str(r.get("varenavn", "")).lower()
            or tekst_lower in str(r.get("navnFormStyrke", "")).lower()
        ]


if __name__ == "__main__":
    client = LegemidlerClient()
    page = client.get_legemiddelvirkestoff_page(skip=0, take=5)
    for row in page:
        print(row.get("varenavn"), "-", row.get("atcKode"), "-", row.get("navnFormStyrke"))
