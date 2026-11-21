"""Symulacja oceny dla pracownika: na jaką ocenę cząstkową wskazują fakty z EZD RP.

Symulacja jest przypuszczeniem i służy wyłącznie ocenianemu - oceniający jej nie widzi, żeby wyliczona liczba nie
zastępowała jego oceny. Nie korzysta z modelu językowego: wskazanie powstaje z jawnych progów zapisanych
w `symulacja.toml`, które ustala urząd. Przepisy takich progów nie znają, dlatego nie ma ich w `przepisy.toml`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from .konfiguracja import Przepisy, _ustal_przepisy

DOMYSLNY_PLIK = Path(__file__).with_name("symulacja.toml")
# Wskaźniki rdzenia (`wskazniki_pracy`) wyrażone udziałem - tylko one mają skalę, którą da się porównać z progami.
WSKAZNIKI_PROCENTOWE = ("TERMINOWOSC", "PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM", "ROZSTRZYGNIECIA_UTRZYMANE")


@dataclass(frozen=True)
class Powiazanie:
    """Które fakty z EZD RP mówią coś o kryterium oceny - i dlaczego."""

    kryterium: str
    wskazniki: tuple[str, ...]
    uzasadnienie: str


@dataclass(frozen=True)
class UstawieniaSymulacji:
    progi: tuple[tuple[int, int], ...]  # (ocena cząstkowa, dolna granica udziału w %), od najwyższej oceny
    powiazania: tuple[Powiazanie, ...]


@dataclass(frozen=True)
class SkladnikWskazania:
    kod: str  # kod wskaźnika z `wskazniki_pracy`
    udzial: Fraction  # wartość wskaźnika, ułamek z przedziału 0-1
    ocena: int  # ocena cząstkowa, na którą wskazuje sam ten fakt


@dataclass(frozen=True)
class Wskazanie:
    kryterium: str
    ocena: int
    skladniki: tuple[SkladnikWskazania, ...]
    uzasadnienie: str


def wczytaj_ustawienia(sciezka: Path | str | None = None, przepisy: Przepisy | None = None) -> UstawieniaSymulacji:
    """Ustawienia symulacji z pliku TOML (domyślnie `symulacja.toml`). Niespójny plik -> ValueError."""
    plik = Path(sciezka) if sciezka is not None else DOMYSLNY_PLIK
    stan = plik.stat()
    return _zbuduj(_wczytaj_plik(str(plik), stan.st_mtime_ns, stan.st_size), str(plik), _ustal_przepisy(przepisy))


@lru_cache(maxsize=8)
def _wczytaj_plik(plik: str, czas_modyfikacji_ns: int, rozmiar: int) -> dict:
    """Treść pliku ustawień; czas modyfikacji i rozmiar są kluczem pamięci podręcznej - zmiana pliku działa od razu."""
    try:
        return tomllib.loads(Path(plik).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as wyjatek:
        raise ValueError(f"Ustawienia symulacji {plik}: plik nie jest poprawnym plikiem TOML: {wyjatek}") from wyjatek


def _zbuduj(dane: dict, plik: str, przepisy: Przepisy) -> UstawieniaSymulacji:
    def blad(opis: str) -> ValueError:
        return ValueError(f"Ustawienia symulacji {plik}: {opis}")

    surowe = dane.get("progi_procentowe")
    if not isinstance(surowe, dict) or not surowe:
        raise blad("brak sekcji [progi_procentowe]")
    oceny_z_progiem = sorted(przepisy.skala)[1:]  # najniższa ocena nie ma progu - obejmuje wszystko poniżej
    if set(surowe) != {str(ocena) for ocena in oceny_z_progiem}:
        raise blad(
            "sekcja [progi_procentowe] musi mieć po jednym progu dla ocen: "
            + ", ".join(str(ocena) for ocena in oceny_z_progiem)
        )
    progi = []
    for ocena in sorted(oceny_z_progiem, reverse=True):
        prog = surowe[str(ocena)]
        if type(prog) is not int or not 0 < prog <= 100:
            raise blad(f"próg dla oceny {ocena} musi być liczbą całkowitą od 1 do 100 (jest: {prog!r})")
        if progi and prog >= progi[-1][1]:
            raise blad("progi muszą rosnąć razem z oceną")
        progi.append((ocena, prog))

    powiazania = []
    for wpis in dane.get("powiazania", []):
        kryterium = wpis.get("kryterium") if isinstance(wpis, dict) else None
        wskazniki = wpis.get("wskazniki") if isinstance(wpis, dict) else None
        if kryterium not in przepisy.katalog_kryteriow:
            raise blad(f"kryterium {kryterium!r} nie występuje w wykazie kryteriów (załącznik nr 1 do rozp.)")
        if kryterium in {powiazanie.kryterium for powiazanie in powiazania}:
            raise blad(f"kryterium {kryterium!r} ma więcej niż jedno powiązanie")
        if not isinstance(wskazniki, list) or not wskazniki or not set(wskazniki) <= set(WSKAZNIKI_PROCENTOWE):
            raise blad(
                f"powiązanie kryterium {kryterium!r} może wskazywać tylko wskaźniki procentowe: "
                + ", ".join(WSKAZNIKI_PROCENTOWE)
            )
        powiazania.append(Powiazanie(kryterium, tuple(wskazniki), str(wpis.get("uzasadnienie", "")).strip()))
    return UstawieniaSymulacji(progi=tuple(progi), powiazania=tuple(powiazania))


def ocena_dla_udzialu(
    udzial: Fraction, ustawienia: UstawieniaSymulacji | None = None, przepisy: Przepisy | None = None
) -> int:
    """Ocena cząstkowa, na którą wskazuje fakt wyrażony udziałem (np. 68% spraw w terminie) - według progów urzędu."""
    przepisy = _ustal_przepisy(przepisy)
    ustawienia = ustawienia or wczytaj_ustawienia(przepisy=przepisy)
    for ocena, prog in ustawienia.progi:
        if udzial * 100 >= prog:
            return ocena
    return min(przepisy.skala)


def _najblizsza_ocena(srednia: Fraction, skala: Sequence[int]) -> int:
    """Ocena ze skali najbliższa średniej; przy równej odległości niższa - symulacja nie obiecuje ponad dane."""
    return min(skala, key=lambda ocena: (abs(ocena - srednia), ocena))


def wskazania_z_ezd(
    kryteria: Sequence[str],
    udzialy: Mapping[str, Fraction | None],
    ustawienia: UstawieniaSymulacji | None = None,
    przepisy: Przepisy | None = None,
) -> list[Wskazanie]:
    """Wskazania dla tych kryteriów, o których fakty z EZD RP coś mówią - w kolejności kryteriów.

    `udzialy` to wartości wskaźników procentowych według kodów (None albo brak = wskaźnika nie policzono).
    Kryterium bez powiązania albo bez policzonych faktów nie dostaje wskazania: o współpracy czy komunikacji
    dane o sprawach nic nie mówią.
    """
    przepisy = _ustal_przepisy(przepisy)
    ustawienia = ustawienia or wczytaj_ustawienia(przepisy=przepisy)
    powiazania = {powiazanie.kryterium: powiazanie for powiazanie in ustawienia.powiazania}
    wskazania = []
    for kryterium in kryteria:
        powiazanie = powiazania.get(kryterium)
        if powiazanie is None:
            continue
        skladniki = tuple(
            SkladnikWskazania(kod, udzialy[kod], ocena_dla_udzialu(udzialy[kod], ustawienia, przepisy))
            for kod in powiazanie.wskazniki
            if udzialy.get(kod) is not None
        )
        if not skladniki:
            continue
        srednia = Fraction(sum(skladnik.ocena for skladnik in skladniki), len(skladniki))
        wskazania.append(
            Wskazanie(kryterium, _najblizsza_ocena(srednia, przepisy.skala), skladniki, powiazanie.uzasadnienie)
        )
    return wskazania
