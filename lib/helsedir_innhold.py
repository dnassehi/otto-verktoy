#!/usr/bin/env python3
"""Klient for Helsedirektoratets innholdstjenester (produktet
"Helsedirektoratets innholdstjenester" på utvikler.helsedirektoratet.no,
del av HAPI - Helsedirektoratets API-tjeneste).

Dekker: nasjonale faglige retningslinjer, nasjonale faglige råd,
pakkeforløp, rundskriv, tilskudd, rapporter, artikler, nyheter, veiledere,
lov-/forskriftstekst med merknad, takst med merknad, LIS-læringsmål m.m. -
alt innhold fra helsedirektoratet.no.

Samme Ocp-Apim-Subscription-Key som for "Legemidler"-produktet (se
helsedir_legemidler.py) fungerer også her.

Kilde til endepunktdokumentasjon (offentlig, ikke fra portalens JS-rendrede
"Try it"-konsoll): https://www.helsedirektoratet.no/om-oss/apne-data-api/
hvordan-finne-frem-i-innholdet

Bekreftet endepunkt: GET /innhold/innhold
- Spørring på innholdstype: ?infoTyper=<teknisk navn> (se INFOTYPER under).
  Returnerer HELE resultatsettet i ett kall, IKKE paginert (testet:
  infoTyper=anbefaling ga 3145 poster i ett svar). skip/take (som i
  legemiddel-API-et) gir 500-feil her - IKKE bruk. $skip/$top ignoreres
  stille (som i legemiddel-API-et).
- Spørring på kodeverk/kode: ?kodeverk=<kodeverk>&kode=<kode>. VIKTIG:
  kodeverk-navnet skal IKKE ha bindestrek her, selv om den offisielle
  dokumentasjonen skriver "ICPC-2"/"ICD-10" - testet empirisk:
  kodeverk=ICPC2 (ikke ICPC-2) og kodeverk=ICD10 (ikke ICD-10) er det som
  faktisk gir treff. Feil skrivemåte gir 200 med tom liste, ikke feilmelding.
- Kan kombineres: ?infoTyper=anbefaling&kodeverk=ICPC2&kode=U70 (ikke
  separat testet, men konsistent med dokumentasjonen).
- Enkeltoppslag: GET /innhold/innhold/{id} - id-format
  [kildekode]-[innholdstypekode]-[unik id], f.eks.
  "0006-0069-40018d15-7a86-44bb-bf75-39dd53b37e75". Kildekoder: 0006
  Helsedirektoratet, 0004 FEST, 0003 NKI, 0007 Covid-data.
- Hvert element har et "koder"-felt (dict, f.eks. {"ICD10": ["N10","N12"],
  "ICPC2": ["U70"]}) når innholdet er kodet - IKKE alt innhold er kodet
  (mange har koder: null).
- "links"-felt gir hierarki: "root" (toppnode for strukturen) og
  "publikasjon" (hele publikasjonsstrukturen) med href til
  /innhold/retningslinjer/{id} og /innhold/publikasjoner/{strukturId} -
  disse alternative stiene er IKKE selv testet, kun sett i responsen.
- Feltstruktur (utover koder/links): id, tittel, kortTittel, tekst (HTML),
  intro, kortIntro, gruppeId, tema, eier, opprettet, forstPublisert,
  sistOppdatert, sistFagligOppdatert, status, maalgruppe, spraak,
  redaksjonelleier, fagansvarlig, fagansvarligMedAvdeling, arkivreferanse,
  bidragsyter, bidragsytersRolle, data (nøkkelinfo/praktisk/rasjonale for
  anbefalinger m.m.), tekniskeData, attachments, url (lenke til
  helsedirektoratet.no), dokumentType, sistImportertTilHapi.
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

# Delt nøkkel, samme som legemiddel-atc-fest (lib/helsedir_legemidler.py) -
# bekreftet 11.08.2026 å dekke også dette produktet.
OP_REFERENCE = os.environ.get("HELSEDIR_OP_REF", "op://Agent/Helsedirektoratet API/primary API-key")

# Tekniske navn for infoTyper-parameteren (se modul-docstring for kilde).
# Ikke uttømmende testet enkeltvis - kun "rundskriv", "nyhet", "retningslinje"
# og "anbefaling" er faktisk bekreftet å gi treff (11.08.2026).
INFOTYPER = {
    "anbefaling": "anbefaling",
    "artikkel": "artikkel",
    "atc_kode": "atc-kode",
    "faglig_rad": "faglig-rad",
    "fil": "fil",
    "generisk_normerende_enhet": "generisk-normerende-enhet",
    "generisk_produkt": "generisk-produkt",
    "horing": "horing",
    "kapittel": "kapittel",
    "konferanse": "konferanse",
    "legemiddel": "legemiddel",
    "legemiddelpakning": "legemiddelpakning",
    "legemiddel_virkestoff": "legemiddelvirkestoff",
    "lis_laeringsaktivitet": "lis-laeringsaktivitet",
    "lis_laeringsmal": "lis-laeringsmal",
    "lis_laeringsmalkategori": "lis-laeringsmalkategori",
    "lis_spesialitet": "lis-spesialitet",
    "lovtekst_med_kommentar": "lov-eller-forskriftstekst-med-kommentar",
    "medisinsk_utstyr": "medisinskutstyr",
    "nasjonal_veileder": "nasjonal-veileder",
    "nasjonalt_forlop": "nasjonalt-forlop",
    "nyhet": "nyhet",
    "pakkeforlop_anbefaling": "pakkeforlop-anbefaling",
    "paragraf_med_kommentar": "paragraf-med-kommentar",
    "pico": "pico",
    "prioriteringsveileder": "prioriteringsveileder",
    "rad": "rad",
    "rapport": "rapport",
    "referanse": "referanse",
    "regelverk": "regelverk-lov-eller-forskrift",
    "retningslinje": "retningslinje",
    "rundskriv": "rundskriv",
    "statistikk": "statistikk",
    "statistikkelement": "statistikkelement",
    "takst_med_merknad": "takst-med-merknad",
    "tilskudd": "tilskudd",
    "veileder": "veileder",
    "veileder_lov_forskrift": "veileder-lov-forskrift",
    "veiledning": "veiledning",
    "nki": "NKI",
}

# Kodeverk-navn slik de FAKTISK skal skrives i ?kodeverk= (uten bindestrek,
# avviker fra den offisielle dokumentasjonens skrivemåte "ICPC-2"/"ICD-10").
KODEVERK = {
    "icpc2": "ICPC2",
    "icd10": "ICD10",
    "snomed_ct": "SNOMED-CT",  # ikke selv testet - dokumentert skrivemåte
    "takstkode": "takstkode",
    "lis_spesialitet": "lis-spesialitet",
    "lis_laeringsmal": "lis-laeringsmaal",
    "lis_felles_kompetansemal": "lis-felleskompetansemaal",
}


class InnholdAPIError(Exception):
    """Feil ved kall mot Helsedirektoratets innholdstjenester."""


def _subscription_key() -> str:
    try:
        return op_read(OP_REFERENCE)
    except OnePasswordError as e:
        raise InnholdAPIError(
            "Fant ikke Ocp-Apim-Subscription-Key i 1Password "
            f"({OP_REFERENCE})."
        ) from e


class InnholdClient:
    def __init__(self, prod: bool = True, subscription_key: str | None = None):
        self.base_url = PROD_BASE_URL if prod else QA_BASE_URL
        self.subscription_key = subscription_key or _subscription_key()

    def _headers(self) -> dict:
        return {"Ocp-Apim-Subscription-Key": self.subscription_key}

    def get(self, path: str, params: dict | None = None):
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=20)
        if resp.status_code == 401:
            raise InnholdAPIError(
                "401 Unauthorized - subscription key ugyldig, ikke aktivert "
                "ennå, eller mangler tilgang til innholdstjenester."
            )
        resp.raise_for_status()
        return resp.json()

    def query(
        self,
        info_typer: str | list[str] | None = None,
        kodeverk: str | None = None,
        kode: str | None = None,
    ) -> list[dict]:
        """Generisk spørring mot /innhold/innhold. `info_typer` kan være ett
        teknisk navn eller en liste (kommaseparert i spørringen). `kodeverk`
        skal være den faktiske API-skrivemåten (se KODEVERK, f.eks. "ICPC2"
        ikke "ICPC-2")."""
        params: dict = {}
        if info_typer:
            if isinstance(info_typer, list):
                params["infoTyper"] = ",".join(info_typer)
            else:
                params["infoTyper"] = info_typer
        if kodeverk:
            params["kodeverk"] = kodeverk
        if kode:
            params["kode"] = kode
        return self.get("/innhold/innhold", params=params)

    def search_by_icpc2(self, kode: str, info_typer: str | list[str] | None = None) -> list[dict]:
        return self.query(info_typer=info_typer, kodeverk="ICPC2", kode=kode)

    def search_by_icd10(self, kode: str, info_typer: str | list[str] | None = None) -> list[dict]:
        return self.query(info_typer=info_typer, kodeverk="ICD10", kode=kode)

    def get_retningslinjer(self) -> list[dict]:
        return self.query(info_typer="retningslinje")

    def get_by_id(self, innhold_id: str) -> dict:
        return self.get(f"/innhold/innhold/{innhold_id}")
