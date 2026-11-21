"""Dane przykładowe radaru zamiast systemu kadrowego i EZD RP - wyłącznie w trybie demonstracyjnym.

Wszystkie liczby są zmyślone i powtarzalne: dla tego samego stanowiska powstaje zawsze ten sam zestaw. Profile
osób z danych pokazowych są spójne z ich przykładowymi sprawami w `ezd_przyklad`.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

from asystent_ocen.radar import DaneRadaru

# Liczby jednej osoby; `miesiace_od_wypoczynku` to czas od ostatniego urlopu trwającego co najmniej 14 dni.
PROFILE: dict[str, dict] = {
    "stanowisko-anna": dict(
        urlop_zalegly_dni=6, miesiace_od_wypoczynku=14, nadgodziny_w_roku_h=38, dni_zastepstw_12_mies=16,
        sprawy_w_toku=9, sprawy_w_toku_mediana_komorki=8, czynnosci_poza_godzinami_3_mies=4,
        sprawy_zakonczone_12_mies=21, sprawy_w_terminie_12_mies=21, sprawy_przejete_po_nieobecnych_12_mies=7,
        pisma_12_mies=12, pisma_bez_poprawek_12_mies=11,
    ),
    "stanowisko-marek": dict(
        urlop_zalegly_dni=11, miesiace_od_wypoczynku=17, nadgodziny_w_roku_h=96, dni_zastepstw_12_mies=3,
        sprawy_w_toku=14, sprawy_w_toku_mediana_komorki=8, czynnosci_poza_godzinami_3_mies=31,
        sprawy_zakonczone_12_mies=17, sprawy_w_terminie_12_mies=11, sprawy_przejete_po_nieobecnych_12_mies=1,
        pisma_12_mies=9, pisma_bez_poprawek_12_mies=6,
    ),
    "stanowisko-robert": dict(
        urlop_zalegly_dni=0, miesiace_od_wypoczynku=4, nadgodziny_w_roku_h=84, dni_zastepstw_12_mies=12,
        sprawy_w_toku=13, sprawy_w_toku_mediana_komorki=8, czynnosci_poza_godzinami_3_mies=22,
        sprawy_zakonczone_12_mies=26, sprawy_w_terminie_12_mies=21, sprawy_przejete_po_nieobecnych_12_mies=6,
        pisma_12_mies=8, pisma_bez_poprawek_12_mies=6,
    ),
}


def _losowy(identyfikator: str) -> random.Random:
    # Generator pseudolosowy służy tylko do rozłożenia zmyślonych liczb - nie ma związku z bezpieczeństwem.
    ziarno = int.from_bytes(hashlib.sha256(("radar:" + identyfikator).encode("utf-8")).digest()[:8], "big")
    return random.Random(ziarno)


def _profil(identyfikator: str) -> dict:
    if identyfikator in PROFILE:
        return PROFILE[identyfikator]
    los = _losowy(identyfikator)
    zakonczone = los.randint(12, 30)
    pisma = los.randint(6, 16)
    return dict(
        urlop_zalegly_dni=los.choice((0, 0, 3, 5, 8)), miesiace_od_wypoczynku=los.randint(2, 15),
        nadgodziny_w_roku_h=los.choice((0, 12, 30, 55, 88)), dni_zastepstw_12_mies=los.randint(0, 14),
        sprawy_w_toku=los.randint(4, 13), sprawy_w_toku_mediana_komorki=8,
        czynnosci_poza_godzinami_3_mies=los.choice((0, 2, 6, 14, 24)),
        sprawy_zakonczone_12_mies=zakonczone, sprawy_w_terminie_12_mies=zakonczone - los.randint(0, 4),
        sprawy_przejete_po_nieobecnych_12_mies=los.randint(0, 7),
        pisma_12_mies=pisma, pisma_bez_poprawek_12_mies=pisma - los.randint(0, 3),
    )


def dane_przykladowe(identyfikator: str, dzien: date) -> DaneRadaru:
    """Zmyślone liczby jednego stanowiska na wskazany dzień."""
    profil = dict(_profil(identyfikator))
    miesiace = profil.pop("miesiace_od_wypoczynku")
    return DaneRadaru(
        stan_na=dzien, koniec_ostatniego_wypoczynku_14_dni=dzien - timedelta(days=miesiace * 30 + 12), **profil
    )
