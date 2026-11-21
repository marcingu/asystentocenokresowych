"""Anonimizacja tekstu przed wysłaniem poza infrastrukturę urzędu (np. do zewnętrznego modelu AI).

Wymaganie: treść wyzwania KPRM, pkt 5 - „bezpieczne pod względem danych (...) anonimizacją
w razie przetwarzania danych poza infrastrukturą użytkownika”.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_ODSTEP = r"[ \u00a0-]?"  # odstęp, twarda spacja albo łącznik między grupami cyfr numeru telefonu
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PESEL = re.compile(r"(?<!\d)\d{11}(?!\d)")
_TELEFON = re.compile(
    r"(?<![\w+])"
    rf"(?:(?:\+|00)48{_ODSTEP})?"  # opcjonalny prefiks kraju
    r"(?:"
    rf"\d{{3}}{_ODSTEP}\d{{3}}{_ODSTEP}\d{{3}}"  # 501 234 567, 501-234-567, 501234567
    rf"|\(?\d{{2}}\)?{_ODSTEP}\d{{3}}{_ODSTEP}\d{{2}}{_ODSTEP}\d{{2}}"  # 22 597 09 27, (22) 597-09-27
    r")"
    r"(?!\w)"
)


@dataclass(frozen=True)
class WynikAnonimizacji:
    tekst: str
    mapa: dict[str, str]  # znacznik zastępczy -> oryginalna wartość


def anonimizuj(tekst: str, osoby: Sequence[str] = ()) -> WynikAnonimizacji:
    """Zastępuje PESEL, adresy e-mail, numery telefonów i wskazane imiona i nazwiska znacznikami.

    Ta sama wartość dostaje zawsze ten sam znacznik (np. „[OSOBA_1]”), a mapa pozwala odwrócić zamianę.
    Imiona i nazwiska są wyszukiwane w podanym brzmieniu (bez odmiany przez przypadki).
    """
    mapa: dict[str, str] = {}
    znaczniki: dict[tuple[str, str], str] = {}  # (rodzaj, oryginał) -> znacznik
    liczniki: dict[str, int] = {}

    def znacznik_dla(rodzaj: str, oryginal: str) -> str:
        klucz = (rodzaj, oryginal)
        if klucz not in znaczniki:
            while True:
                liczniki[rodzaj] = liczniki.get(rodzaj, 0) + 1
                znacznik = f"[{rodzaj}_{liczniki[rodzaj]}]"
                if znacznik not in tekst:  # tekst wejściowy mógł już zawierać podobny znacznik
                    break
            znaczniki[klucz] = znacznik
            mapa[znacznik] = oryginal
        return znaczniki[klucz]

    def zamien(wzorzec: re.Pattern[str], rodzaj: str, zrodlo: str) -> str:
        return wzorzec.sub(lambda trafienie: znacznik_dla(rodzaj, trafienie.group(0)), zrodlo)

    wynik = zamien(_EMAIL, "EMAIL", tekst)
    # Telefony przed numerami PESEL: numer z prefiksem kraju pisany łącznie („+48501234567”) to też 11 cyfr.
    wynik = zamien(_TELEFON, "TELEFON", wynik)
    wynik = zamien(_PESEL, "PESEL", wynik)
    # Dłuższe nazwy najpierw, żeby „Anna Nowak-Kowalska” nie została rozbita przez „Anna Nowak”.
    for osoba in sorted({o.strip() for o in osoby if o and o.strip()}, key=len, reverse=True):
        czlony = r"\s+".join(re.escape(czlon) for czlon in osoba.split())
        wynik = zamien(re.compile(rf"(?<!\w){czlony}(?!\w)"), "OSOBA", wynik)
    return WynikAnonimizacji(tekst=wynik, mapa=mapa)


def przywroc(tekst: str, mapa: Mapping[str, str]) -> str:
    """Odwraca anonimizację w odpowiedzi otrzymanej z zewnątrz."""
    if not mapa:
        return tekst
    # Jedno przejście po tekście: przywrócona wartość nie jest ponownie przeszukiwana.
    wzorzec = re.compile("|".join(re.escape(znacznik) for znacznik in sorted(mapa, key=len, reverse=True)))
    return wzorzec.sub(lambda trafienie: mapa[trafienie.group(0)], tekst)
