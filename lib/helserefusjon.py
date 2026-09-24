#!/usr/bin/env python3
"""Klient for Helserefusjon Open Data API (opne-data-api.helserefusjon.no).

Dette er IKKE en del av Helsedirektoratets HAPI-portal (utvikler.
helsedirektoratet.no) selv om "Helserefusjon" var oppført som ett av de
fem produktene der - dette er en helt separat, FULLT ÅPEN API uten noen
API-nøkkel/subscription i det hele tatt. Portalproduktet "Helserefusjon"
under HAPI er trolig kun en katalogoppføring som peker hit, eller dekker
noe annet (ikke undersøkt videre siden denne åpne API-en allerede dekker
behovet).

Dekker: takstbruk (statistikk over bruk av honorartakster i helsevesenet,
nasjonalt/fylke/kommune, måned/år), takstkoder, fagområder/praksistyper,
NLK-koder (laboratoriekoder), refusjonskategorier, APAT-kombinasjoner
(patologitakst-kombinasjoner).

STATUS (2026-08-11, bekreftet fungerende): Testet direkte uten
autentisering mot prod. Full dokumentasjon funnet via context7.com
(indeksert fra opne-data-api.helserefusjon.no sin egen API-dokumentasjon,
44 dokumenterte endepunkter) - IKKE fra Helsedirektoratets JS-rendrede
portal.

Bekreftet endepunkter (alle GET, ingen auth):
- /v1/fagomraader - kodeliste: fagområder (LE=Legetjenester m.fl.), hvert
  fagområde har nøstede praksistyper (f.eks. FALE=Fastlege,
  LEVA=Legevakt, LEKO=Legevakt kommunal).
- /v1/takstkoder - kodeliste: alle takstkoder med honorar/refusjon,
  fagområde, gyldighetsperiode (fradato/tildato), beskrivelse.
- /v1/nlkkoder - kodeliste: NLK-koder (laboratorietakster), med
  refusjonskategori og historiske refusjonssatser.
- /v1/apatkombinasjoner - kodeliste: T-kode/P-kode-kombinasjoner for
  patologitakster, med beløp og gyldighetsperiode.
- /v1/takstbruk/agtakst/landet/{maned|ar} - aggregert takstbruk for hele
  landet, per måned eller år.
- /v1/takstbruk/agtakst/fylke/{maned|ar} - aggregert takstbruk per fylke.
- /v1/takstbruk/agtakst/kommune/{maned|ar} - aggregert takstbruk per
  kommune.
- Samme takstbruk-stier finnes også under /v1/takstbruk/eksport/... for
  CSV, og /v1/takstbruk/eksport/msexcel/... for Excel-format (ikke testet
  her, kun JSON-variantene).

Felles query-parametre for takstbruk-endepunktene:
- fagomraade (påkrevd, kommaseparert, f.eks. "LE") - se /v1/fagomraader.
- fommaned/tommaned (måned-endepunkter, format YYYYMM) ELLER fomar/tomar
  (år-endepunkter) - periode kan maks være 13 måneder for måned-variantene.
- takstkoder (valgfri, kommaseparert) - se /v1/takstkoder.
- praksistyper (valgfri, kommaseparert, f.eks. "FALE,LEVA").
- fylker/kommuner (valgfri, kun for hhv. fylke-/kommune-variantene).

Eksempel testet 11.08.2026: GET /v1/takstbruk/agtakst/landet/ar
?fagomraade=LE&fomar=2023&tomar=2024&takstkoder=2ad ga 11 rader med
reelle nasjonale tall for takst "2ad" (bl.a. fastlege 2023: 10 831 466
takstbruk, kr 880 613 727 i refusjon).

Responsfelter i takstbruk-svar: ar/maned, sum_antall_takst, takstkode,
fagomraade, praksis_type_kode, samhandler_praksis_type,
antall_regninger, sum_refusjon, sum_egenandel_betalt_av_pasient,
sum_egenandel_dekket_av_folketrygden (+ fylke/kommune-felt for de
aggregerte variantene).
"""
from __future__ import annotations

import requests

BASE_URL = "https://opne-data-api.helserefusjon.no/v1"


class HelserefusjonAPIError(Exception):
    """Feil ved kall mot Helserefusjon Open Data API."""


class HelserefusjonClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url

    def get(self, path: str, params: dict | None = None):
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            raise HelserefusjonAPIError(f"{resp.status_code} fra {url}: {resp.text[:300]}")
        return resp.json()

    # --- Kodelister ---

    def get_fagomraader(self) -> list[dict]:
        return self.get("/fagomraader")["fagomraader"]

    def get_takstkoder(self) -> list[dict]:
        return self.get("/takstkoder")["takstkoder"]

    def get_nlkkoder(self) -> list[dict]:
        return self.get("/nlkkoder")["nlkkoder"]

    def get_apatkombinasjoner(self) -> list[dict]:
        return self.get("/apatkombinasjoner")["apatKombinasjoner"]

    # --- Takstbruk (statistikk) ---

    def _takstbruk(
        self,
        niva: str,  # "landet" | "fylke" | "kommune"
        periode: str,  # "maned" | "ar"
        fagomraade: str,
        takstkoder: str | None = None,
        praksistyper: str | None = None,
        fylker: str | None = None,
        kommuner: str | None = None,
        **periode_params,
    ) -> dict:
        params: dict = {"fagomraade": fagomraade, **periode_params}
        if takstkoder:
            params["takstkoder"] = takstkoder
        if praksistyper:
            params["praksistyper"] = praksistyper
        if fylker:
            params["fylker"] = fylker
        if kommuner:
            params["kommuner"] = kommuner
        return self.get(f"/takstbruk/agtakst/{niva}/{periode}", params=params)

    def takstbruk_landet_ar(
        self, fagomraade: str, fomar: int, tomar: int, takstkoder: str | None = None, praksistyper: str | None = None
    ) -> dict:
        return self._takstbruk("landet", "ar", fagomraade, takstkoder, praksistyper, fomar=fomar, tomar=tomar)

    def takstbruk_landet_maned(
        self, fagomraade: str, fommaned: str, tommaned: str, takstkoder: str | None = None, praksistyper: str | None = None
    ) -> dict:
        return self._takstbruk(
            "landet", "maned", fagomraade, takstkoder, praksistyper, fommaned=fommaned, tommaned=tommaned
        )

    def takstbruk_fylke_ar(
        self,
        fagomraade: str,
        fomar: int,
        tomar: int,
        fylker: str | None = None,
        takstkoder: str | None = None,
        praksistyper: str | None = None,
    ) -> dict:
        return self._takstbruk("fylke", "ar", fagomraade, takstkoder, praksistyper, fylker=fylker, fomar=fomar, tomar=tomar)

    def takstbruk_fylke_maned(
        self,
        fagomraade: str,
        fommaned: str,
        tommaned: str,
        fylker: str | None = None,
        takstkoder: str | None = None,
        praksistyper: str | None = None,
    ) -> dict:
        return self._takstbruk(
            "fylke", "maned", fagomraade, takstkoder, praksistyper, fylker=fylker, fommaned=fommaned, tommaned=tommaned
        )

    def takstbruk_kommune_ar(
        self,
        fagomraade: str,
        fomar: int,
        tomar: int,
        kommuner: str | None = None,
        takstkoder: str | None = None,
        praksistyper: str | None = None,
    ) -> dict:
        return self._takstbruk(
            "kommune", "ar", fagomraade, takstkoder, praksistyper, kommuner=kommuner, fomar=fomar, tomar=tomar
        )

    def takstbruk_kommune_maned(
        self,
        fagomraade: str,
        fommaned: str,
        tommaned: str,
        kommuner: str | None = None,
        takstkoder: str | None = None,
        praksistyper: str | None = None,
    ) -> dict:
        return self._takstbruk(
            "kommune",
            "maned",
            fagomraade,
            takstkoder,
            praksistyper,
            kommuner=kommuner,
            fommaned=fommaned,
            tommaned=tommaned,
        )
