"""Dane przykładowe zamiast EZD RP - wyłącznie w trybie demonstracyjnym. Wszystkie sprawy są zmyślone.

Dane są powtarzalne: dla tego samego stanowiska i okresu powstaje zawsze ten sam zestaw. Mają taki sam kształt
jak dane z Integrator API (`SprawaEzd`, `AkceptacjaEzd`, `Odwolanie`), więc karta kontekstu liczy na nich te
same wskaźniki co na danych rzeczywistych.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date, timedelta

from asystent_ocen.wskazniki_pracy import (
    ODRZUCONY,
    UCHYLONA,
    UTRZYMANA,
    W_TOKU,
    ZAAKCEPTOWANY,
    ZAKONCZONA,
    AkceptacjaEzd,
    Odwolanie,
    SprawaEzd,
)

PELNY_OKRES_DNI = 730  # liczby w profilu odnoszą się do dwuletniego okresu oceny
_TERMIN_DNI = 30
_KLASY_SPRAW = ("1410", "1411", "1510", "0124")


@dataclass(frozen=True)
class Profil:
    """Rozmiar przykładowych danych jednego stanowiska za pełny okres oceny."""

    sprawy: int
    po_terminie: int = 0
    w_toku_po_terminie: int = 0
    projekty: int = 20
    odrzucenia: int = 0
    uwaga_akceptujacego: str = "Do poprawy: styl i układ pisma."
    odwolania_utrzymane: int = 0
    odwolania_uchylone: int = 0


# Profile osób z danych pokazowych - spójne z notatkami i uzasadnieniami w `dane_demo`.
PROFILE = {
    "stanowisko-anna": Profil(sprawy=41, projekty=24, odrzucenia=2),
    "stanowisko-marek": Profil(
        sprawy=34, po_terminie=11, w_toku_po_terminie=2, projekty=18, odrzucenia=6,
        uwaga_akceptujacego="Do poprawy: błędnie wskazana podstawa prawna.",
        odwolania_utrzymane=2, odwolania_uchylone=3,
    ),
    "stanowisko-robert": Profil(sprawy=52, po_terminie=9, w_toku_po_terminie=1, projekty=15, odrzucenia=3),
    "stanowisko-ewa": Profil(sprawy=27, po_terminie=2, projekty=30, odrzucenia=1),
    "stanowisko-naczelnik": Profil(sprawy=63, po_terminie=4, projekty=12, odrzucenia=0),
}


def _losowy(identyfikator: str) -> random.Random:
    # Generator pseudolosowy służy tylko do rozłożenia zmyślonych dat - nie ma związku z bezpieczeństwem.
    ziarno = int.from_bytes(hashlib.sha256(identyfikator.encode("utf-8")).digest()[:8], "big")
    return random.Random(ziarno)


def profil_stanowiska(identyfikator: str) -> Profil:
    if identyfikator in PROFILE:
        return PROFILE[identyfikator]
    los = _losowy("profil:" + identyfikator)
    return Profil(
        sprawy=los.randint(20, 48), po_terminie=los.randint(0, 3), projekty=los.randint(10, 24),
        odrzucenia=los.randint(0, 3),
    )


def _w_skali(liczba: int, dni_okresu: int) -> int:
    """Liczba zdarzeń przeliczona na długość okresu; okres zbliżony do pełnego dostaje liczbę z profilu."""
    if dni_okresu >= 600:
        return liczba
    return round(liczba * max(dni_okresu, 0) / PELNY_OKRES_DNI)


def _rozlozone(ile: int, sposrod: int) -> set[int]:
    """`ile` numerów rozłożonych równomiernie wśród `sposrod` pozycji."""
    if ile <= 0 or sposrod <= 0:
        return set()
    return {(numer * sposrod) // ile for numer in range(min(ile, sposrod))}


def dane_przykladowe(
    identyfikator: str, od: date, do: date
) -> tuple[list[SprawaEzd], list[AkceptacjaEzd], list[Odwolanie]]:
    """Zmyślone sprawy, akceptacje projektów pism i odwołania stanowiska za okres [od, do]."""
    profil = profil_stanowiska(identyfikator)
    los = _losowy(f"{identyfikator}:{od.isoformat()}")
    dni_okresu = (do - od).days
    zasieg = max(dni_okresu - 60, 1)  # sprawy wszczęte na tyle wcześnie, żeby zakończyły się w okresie

    liczba_spraw = _w_skali(profil.sprawy, dni_okresu)
    spoznione = _rozlozone(_w_skali(profil.po_terminie, dni_okresu), liczba_spraw)
    sprawy: list[SprawaEzd] = []
    for numer in range(liczba_spraw):
        wszczecie = od + timedelta(days=(numer * zasieg) // max(liczba_spraw, 1))
        trwanie = los.randint(33, 52) if numer in spoznione else los.randint(4, 28)
        sprawy.append(SprawaEzd(
            id=f"przyklad-{numer + 1}",
            znak=f"WO.{_KLASY_SPRAW[numer % len(_KLASY_SPRAW)]}.{numer + 1}.{wszczecie.year}",
            tytul="Sprawa przykładowa",
            status=ZAKONCZONA,
            data_wszczecia=wszczecie,
            termin_zalatwienia=wszczecie + timedelta(days=_TERMIN_DNI),
            data_zakonczenia=wszczecie + timedelta(days=trwanie),
        ))
    for numer in range(_w_skali(profil.w_toku_po_terminie, dni_okresu)):
        wszczecie = do - timedelta(days=45 + 9 * numer)
        sprawy.append(SprawaEzd(
            id=f"przyklad-w-toku-{numer + 1}",
            znak=f"WO.{_KLASY_SPRAW[numer % len(_KLASY_SPRAW)]}.{liczba_spraw + numer + 1}.{wszczecie.year}",
            tytul="Sprawa przykładowa",
            status=W_TOKU,
            data_wszczecia=wszczecie,
            termin_zalatwienia=wszczecie + timedelta(days=_TERMIN_DNI),
        ))

    liczba_projektow = _w_skali(profil.projekty, dni_okresu)
    odrzucone = _rozlozone(_w_skali(profil.odrzucenia, dni_okresu), liczba_projektow)
    akceptacje: list[AkceptacjaEzd] = []
    for numer in range(liczba_projektow):
        dokument = f"przyklad-pismo-{numer + 1}"
        dzien = od + timedelta(days=(numer * max(dni_okresu - 5, 1)) // max(liczba_projektow, 1))
        if numer in odrzucone:
            akceptacje.append(AkceptacjaEzd(
                dokument, ODRZUCONY, dzien, akceptujacy="bezpośredni przełożony", opis=profil.uwaga_akceptujacego
            ))
            dzien += timedelta(days=2)
        akceptacje.append(AkceptacjaEzd(dokument, ZAAKCEPTOWANY, dzien, akceptujacy="bezpośredni przełożony"))

    wyniki = [UTRZYMANA] * profil.odwolania_utrzymane + [UCHYLONA] * profil.odwolania_uchylone
    zakonczone = [sprawa for sprawa in sprawy if sprawa.data_zakonczenia and sprawa.data_zakonczenia <= do]
    odwolania: list[Odwolanie] = []
    if dni_okresu >= 600:
        for numer, wynik in enumerate(wyniki[: len(zakonczone)]):
            sprawa = zakonczone[(numer * len(zakonczone)) // len(wyniki)]
            rozstrzygniecie = min(sprawa.data_zakonczenia + timedelta(days=60), do)
            odwolania.append(Odwolanie(sprawa.znak, wynik, rozstrzygniecie))
    return sprawy, akceptacje, odwolania
