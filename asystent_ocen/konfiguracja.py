"""Wczytywanie parametrów prawnych z pliku konfiguracyjnego (przepisy.toml)."""

from __future__ import annotations

import os
import re
import tomllib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import date
from functools import lru_cache
from pathlib import Path

DOMYSLNY_PLIK = Path(__file__).with_name("przepisy.toml")

# Dopuszczalne wartości przełącznika `pierwsza_ocena_6_miesiecy_od` (sekcja [interpretacje]).
OD_NAWIAZANIA_STOSUNKU_PRACY = "nawiazanie_stosunku_pracy"
OD_ZAPOZNANIA_Z_KRYTERIAMI = "zapoznanie_z_kryteriami"


@dataclass(frozen=True)
class Poziom:
    """Przedział ogólnego poziomu spełniania kryteriów (§ 11 ust. 1 pkt 2 rozp.)."""

    nazwa: str
    do: int  # górna granica przedziału średniej (włącznie)
    pozytywny: bool  # czy poziom pozwala na ocenę pozytywną (§ 11 ust. 1 pkt 3 rozp.)
    najwyzszy: bool = False  # jeden z dwóch najwyższych poziomów (art. 89 ust. 2 u.s.c.)


@dataclass(frozen=True)
class Swieto:
    """Dzień ustawowo wolny od pracy (ustawa o dniach wolnych od pracy)."""

    nazwa: str
    data: str | None = None  # "MM-DD" dla świąt o stałej dacie
    dni_od_wielkanocy: int | None = None  # dla świąt ruchomych
    od_roku: int | None = None  # pierwszy rok obowiązywania


@dataclass(frozen=True)
class Przepisy:
    cykl_oceny_miesiace: int
    termin_kryteriow_dni: int
    termin_kryteriow_po_negatywnej_dni: int
    ponowna_ocena_po_negatywnej_miesiace: int
    min_miesiecy_do_zmiany_terminu: int
    prog_nieobecnosci_miesiace: int
    zmiana_stanowiska_najwczesniej_dni_przed: int
    zmiana_stanowiska_najpozniej_dni_po: int
    sprzeciw_dni: int
    rozpatrzenie_sprzeciwu_dni: int
    odwolanie_do_sadu_dni: int
    stopien_obligatoryjny_dni: int
    przypomnienia_dni_przed: tuple[int, ...]
    sobota_konczy_termin_jak_dzien_wolny: bool
    pierwsza_ocena_6_miesiecy_od: str  # "nawiazanie_stosunku_pracy" albo "zapoznanie_z_kryteriami"
    ponowna_ocena_w_dniu_roboczym: bool
    miejsca_po_przecinku_sredniej: int
    skala: tuple[int, ...]
    max_kryteriow_dodatkowych: int
    max_stopien_sluzbowy: int
    poziomy: tuple[Poziom, ...]
    katalog_kryteriow: tuple[str, ...]
    arkusze: dict[str, tuple[str, ...]]  # arkusz -> kryteria obowiązkowe
    swieta: tuple[Swieto, ...]
    # Parametry dopisane w fazie GREEN (podstawy prawne w przepisy.toml):
    sobota_nie_przerywa_ciaglosci_nieobecnosci: bool  # art. 81 ust. 7 u.s.c., dokument KPRM „liczenie terminów”
    ocena_czastkowa_wykluczajaca_pozytywna: int  # § 11 ust. 1 pkt 3 i 4 rozp.
    stopien_obligatoryjny_liczba_ocen: int  # art. 89 ust. 2 u.s.c.
    rodzaje_zatrudnienia_podlegajace_ocenie: tuple[str, ...]  # art. 81 ust. 1 u.s.c.
    rodzaje_zatrudnienia_niepodlegajace_ocenie: tuple[str, ...]  # Poradnik KPRM s. 7


_aktywne = ContextVar("przepisy_urzedu", default=None)


@lru_cache(maxsize=4)
def przepisy_z_tekstu(tresc: str) -> Przepisy:
    return _zbuduj_przepisy(tomllib.loads(tresc), "przepisy.toml")


@contextmanager
def stosuj_przepisy(tresc: str):
    """Jeden spójny zestaw parametrów na całe żądanie, także przy równoległej edycji."""
    token = _aktywne.set(przepisy_z_tekstu(tresc) if tresc else None)
    try:
        yield
    finally:
        _aktywne.reset(token)


def wczytaj_przepisy(sciezka: Path | str | None = None) -> Przepisy:
    """Wczytuje przepisy z pliku TOML (domyślnie `przepisy.toml` obok modułu).

    Wynik jest przechowywany w pamięci podręcznej do czasu zmiany pliku (ścieżka, czas modyfikacji, rozmiar),
    więc podmiana pliku przepisów działa bez restartu aplikacji. Niepoprawny plik -> ValueError.
    """
    if sciezka is None and (aktywne := _aktywne.get()) is not None:
        return replace(aktywne, arkusze=dict(aktywne.arkusze))
    plik = os.path.abspath(sciezka if sciezka is not None else DOMYSLNY_PLIK)
    stan = os.stat(plik)
    wzorzec = _wczytaj_z_pliku(plik, stan.st_mtime_ns, stan.st_size)
    # Kopia słownika arkuszy chroni pamięć podręczną przed przypadkową modyfikacją przez wywołującego.
    return replace(wzorzec, arkusze=dict(wzorzec.arkusze))


def _ustal_przepisy(przepisy: Przepisy | None) -> Przepisy:
    """Przekazany obiekt przepisów ma pierwszeństwo; przy None - przepisy domyślne (z pamięci podręcznej)."""
    return przepisy if przepisy is not None else wczytaj_przepisy()


@lru_cache(maxsize=8)
def _wczytaj_z_pliku(plik: str, czas_modyfikacji_ns: int, rozmiar: int) -> Przepisy:
    with open(plik, "rb") as uchwyt:
        try:
            dane = tomllib.load(uchwyt)
        except tomllib.TOMLDecodeError as blad:
            raise ValueError(f"Plik przepisów {plik} nie jest poprawnym plikiem TOML: {blad}") from blad
    return _zbuduj_przepisy(dane, plik)


def _zbuduj_przepisy(dane: dict, zrodlo: str) -> Przepisy:
    def blad(opis: str) -> ValueError:
        return ValueError(f"Plik przepisów {zrodlo}: {opis}")

    def wez(sekcja: str, klucz: str):
        try:
            return dane[sekcja][klucz]
        except (KeyError, TypeError):
            raise blad(f"brak parametru [{sekcja}] {klucz}") from None

    def calkowita(wartosc, nazwa: str, minimum: int | None = None) -> int:
        if isinstance(wartosc, bool) or not isinstance(wartosc, int):
            raise blad(f"parametr {nazwa} musi być liczbą całkowitą (jest: {wartosc!r})")
        if minimum is not None and wartosc < minimum:
            raise blad(f"parametr {nazwa} nie może być mniejszy niż {minimum} (jest: {wartosc})")
        return wartosc

    def liczba(sekcja: str, klucz: str, minimum: int | None = 1) -> int:
        return calkowita(wez(sekcja, klucz), f"[{sekcja}] {klucz}", minimum)

    def flaga(wartosc, nazwa: str) -> bool:
        if not isinstance(wartosc, bool):
            raise blad(f"parametr {nazwa} musi mieć wartość true albo false (jest: {wartosc!r})")
        return wartosc

    def lista(wartosc, nazwa: str) -> list:
        if not isinstance(wartosc, list):
            raise blad(f"parametr {nazwa} musi być listą (jest: {wartosc!r})")
        return wartosc

    def napisy(wartosc, nazwa: str, niepusta: bool = True) -> tuple[str, ...]:
        elementy = lista(wartosc, nazwa)
        if not all(isinstance(element, str) and element.strip() for element in elementy):
            raise blad(f"parametr {nazwa} musi być listą niepustych napisów")
        if niepusta and not elementy:
            raise blad(f"parametr {nazwa} nie może być pustą listą")
        return tuple(elementy)

    # --- skala ocen i poziomy (§ 11 ust. 1 rozp.) ---
    skala = tuple(calkowita(punkty, "[ocena] skala") for punkty in lista(wez("ocena", "skala"), "[ocena] skala"))
    if not skala or len(set(skala)) != len(skala):
        raise blad("parametr [ocena] skala musi być niepustą listą różnych liczb całkowitych")

    poziomy = []
    for pozycja in lista(wez("ocena", "poziomy"), "[[ocena.poziomy]]"):
        try:
            nazwa, gorna_granica = pozycja["nazwa"], pozycja["do"]
            pozytywny = flaga(pozycja["pozytywny"], "[[ocena.poziomy]] pozytywny")
        except (KeyError, TypeError):
            raise blad("każdy [[ocena.poziomy]] wymaga pól: nazwa, do, pozytywny") from None
        if not isinstance(nazwa, str) or not nazwa.strip():
            raise blad("pole nazwa w [[ocena.poziomy]] musi być niepustym napisem")
        if isinstance(gorna_granica, bool) or not isinstance(gorna_granica, (int, float)):
            raise blad(f"pole do w [[ocena.poziomy]] musi być liczbą (jest: {gorna_granica!r})")
        najwyzszy = flaga(pozycja.get("najwyzszy", False), "[[ocena.poziomy]] najwyzszy")
        poziomy.append(Poziom(nazwa=nazwa, do=gorna_granica, pozytywny=pozytywny, najwyzszy=najwyzszy))
    if not poziomy or any(nizszy.do >= wyzszy.do for nizszy, wyzszy in zip(poziomy, poziomy[1:])):
        raise blad("[[ocena.poziomy]] muszą być podane od najniższego, z rosnącą górną granicą `do`")

    # --- wykaz kryteriów i arkusze (§ 3-5 rozp., załącznik nr 1) ---
    katalog = napisy(wez("kryteria", "katalog"), "[kryteria] katalog")
    znane_kryteria = {" ".join(nazwa.split()).casefold() for nazwa in katalog}
    if len(znane_kryteria) != len(katalog):
        raise blad("parametr [kryteria] katalog zawiera powtórzone kryterium")
    arkusze: dict[str, tuple[str, ...]] = {}
    sekcja_arkuszy = dane.get("arkusze")
    if not isinstance(sekcja_arkuszy, dict) or not sekcja_arkuszy:
        raise blad("brak sekcji [arkusze.<symbol>] z kryteriami obowiązkowymi")
    for symbol, opis in sekcja_arkuszy.items():
        if not isinstance(opis, dict) or "obowiazkowe" not in opis:
            raise blad(f"brak parametru [arkusze.{symbol}] obowiazkowe")
        obowiazkowe = napisy(opis["obowiazkowe"], f"[arkusze.{symbol}] obowiazkowe")
        spoza_wykazu = [k for k in obowiazkowe if " ".join(k.split()).casefold() not in znane_kryteria]
        if spoza_wykazu:
            raise blad(f"kryteria obowiązkowe arkusza {symbol} spoza wykazu [kryteria] katalog: {spoza_wykazu}")
        arkusze[symbol] = obowiazkowe

    # --- dni ustawowo wolne od pracy ---
    swieta = []
    sekcja_swiat = dane.get("swieta", {})
    if not isinstance(sekcja_swiat, dict):
        raise blad("sekcja swieta musi zawierać tablice [[swieta.stale]] i [[swieta.ruchome]]")
    for rodzaj, pole in (("stale", "data"), ("ruchome", "dni_od_wielkanocy")):
        for pozycja in lista(sekcja_swiat.get(rodzaj, []), f"[[swieta.{rodzaj}]]"):
            if not isinstance(pozycja, dict) or "nazwa" not in pozycja or pole not in pozycja:
                raise blad(f"każde [[swieta.{rodzaj}]] wymaga pól: nazwa, {pole}")
            od_roku = pozycja.get("od_roku")
            if od_roku is not None:
                calkowita(od_roku, f"[[swieta.{rodzaj}]] od_roku")
            if rodzaj == "stale":
                dzien = pozycja["data"]
                if not isinstance(dzien, str) or not _czy_poprawny_dzien_roku(dzien):
                    raise blad(f"pole data w [[swieta.stale]] musi mieć postać \"MM-DD\" (jest: {dzien!r})")
                swieta.append(Swieto(nazwa=str(pozycja["nazwa"]), data=dzien, od_roku=od_roku))
            else:
                przesuniecie = calkowita(pozycja["dni_od_wielkanocy"], "[[swieta.ruchome]] dni_od_wielkanocy")
                swieta.append(Swieto(nazwa=str(pozycja["nazwa"]), dni_od_wielkanocy=przesuniecie, od_roku=od_roku))

    # --- przełączniki interpretacyjne ---
    poczatek_6_miesiecy = wez("interpretacje", "pierwsza_ocena_6_miesiecy_od")
    if poczatek_6_miesiecy not in (OD_NAWIAZANIA_STOSUNKU_PRACY, OD_ZAPOZNANIA_Z_KRYTERIAMI):
        raise blad(
            "parametr [interpretacje] pierwsza_ocena_6_miesiecy_od musi mieć wartość "
            f"\"{OD_NAWIAZANIA_STOSUNKU_PRACY}\" albo \"{OD_ZAPOZNANIA_Z_KRYTERIAMI}\" (jest: {poczatek_6_miesiecy!r})"
        )

    przypomnienia = lista(wez("terminy", "przypomnienia_dni_przed"), "[terminy] przypomnienia_dni_przed")

    return Przepisy(
        cykl_oceny_miesiace=liczba("terminy", "cykl_oceny_miesiace"),
        termin_kryteriow_dni=liczba("terminy", "termin_kryteriow_dni"),
        termin_kryteriow_po_negatywnej_dni=liczba("terminy", "termin_kryteriow_po_negatywnej_dni"),
        ponowna_ocena_po_negatywnej_miesiace=liczba("terminy", "ponowna_ocena_po_negatywnej_miesiace"),
        min_miesiecy_do_zmiany_terminu=liczba("terminy", "min_miesiecy_do_zmiany_terminu", minimum=0),
        prog_nieobecnosci_miesiace=liczba("terminy", "prog_nieobecnosci_miesiace"),
        zmiana_stanowiska_najwczesniej_dni_przed=liczba("terminy", "zmiana_stanowiska_najwczesniej_dni_przed", 0),
        zmiana_stanowiska_najpozniej_dni_po=liczba("terminy", "zmiana_stanowiska_najpozniej_dni_po"),
        sprzeciw_dni=liczba("terminy", "sprzeciw_dni"),
        rozpatrzenie_sprzeciwu_dni=liczba("terminy", "rozpatrzenie_sprzeciwu_dni"),
        odwolanie_do_sadu_dni=liczba("terminy", "odwolanie_do_sadu_dni"),
        stopien_obligatoryjny_dni=liczba("terminy", "stopien_obligatoryjny_dni"),
        przypomnienia_dni_przed=tuple(
            calkowita(dni, "[terminy] przypomnienia_dni_przed", minimum=0) for dni in przypomnienia
        ),
        sobota_konczy_termin_jak_dzien_wolny=flaga(
            wez("kalendarz", "sobota_konczy_termin_jak_dzien_wolny"), "[kalendarz] sobota_konczy_termin_jak_dzien_wolny"
        ),
        pierwsza_ocena_6_miesiecy_od=poczatek_6_miesiecy,
        ponowna_ocena_w_dniu_roboczym=flaga(
            wez("interpretacje", "ponowna_ocena_w_dniu_roboczym"), "[interpretacje] ponowna_ocena_w_dniu_roboczym"
        ),
        miejsca_po_przecinku_sredniej=liczba("interpretacje", "miejsca_po_przecinku_sredniej", minimum=0),
        skala=skala,
        max_kryteriow_dodatkowych=liczba("ocena", "max_kryteriow_dodatkowych", minimum=0),
        max_stopien_sluzbowy=liczba("ocena", "max_stopien_sluzbowy"),
        poziomy=tuple(poziomy),
        katalog_kryteriow=katalog,
        arkusze=arkusze,
        swieta=tuple(swieta),
        sobota_nie_przerywa_ciaglosci_nieobecnosci=flaga(
            wez("kalendarz", "sobota_nie_przerywa_ciaglosci_nieobecnosci"),
            "[kalendarz] sobota_nie_przerywa_ciaglosci_nieobecnosci",
        ),
        ocena_czastkowa_wykluczajaca_pozytywna=liczba("ocena", "ocena_czastkowa_wykluczajaca_pozytywna", None),
        stopien_obligatoryjny_liczba_ocen=liczba("ocena", "stopien_obligatoryjny_liczba_ocen"),
        rodzaje_zatrudnienia_podlegajace_ocenie=napisy(
            wez("zatrudnienie", "podlega_ocenie"), "[zatrudnienie] podlega_ocenie"
        ),
        rodzaje_zatrudnienia_niepodlegajace_ocenie=napisy(
            wez("zatrudnienie", "nie_podlega_ocenie"), "[zatrudnienie] nie_podlega_ocenie", niepusta=False
        ),
    )


def _czy_poprawny_dzien_roku(tekst: str) -> bool:
    """Czy napis ma postać "MM-DD" i oznacza istniejący dzień (29 lutego jest dopuszczalny)."""
    if not re.fullmatch(r"\d{2}-\d{2}", tekst):
        return False
    try:
        date(2000, int(tekst[:2]), int(tekst[3:]))  # rok przestępny - dopuszcza 29 lutego
    except ValueError:
        return False
    return True
