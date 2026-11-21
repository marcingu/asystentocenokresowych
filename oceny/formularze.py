"""Odczyt danych z formularzy HTML.

Sprawdzana jest tylko postać danych (data, liczba, wartość z listy). Reguły prawne sprawdza rdzeń.
"""

from __future__ import annotations

from datetime import date

from asystent_ocen.bledy import Blad, BladWalidacji
from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.kryteria import kryteria_obowiazkowe
from asystent_ocen.przebieg import ProcesOceny
from asystent_ocen.walidacja import NIE, TAK
from asystent_ocen.wynik import NEGATYWNA, POZYTYWNA

MAX_DLUGOSC_TEKSTU = 10_000


def tekst(post, nazwa: str) -> str:
    return str(post.get(nazwa, "")).strip()[:MAX_DLUGOSC_TEKSTU]


def data_lub_none(post, nazwa: str) -> date | None:
    surowa = str(post.get(nazwa, "")).strip()
    if not surowa:
        return None
    try:
        return date.fromisoformat(surowa)
    except ValueError:
        return None


def wymagana_data(post, nazwa: str, opis: str) -> date:
    """Data z pola formularza (RRRR-MM-DD z pola typu „data”). Brak albo błędna postać -> BladWalidacji."""
    dzien = data_lub_none(post, nazwa)
    if dzien is None:
        raise BladWalidacji([Blad("BLEDNA_DATA", f"Podaj datę: {opis}.")])
    return dzien


def nazwy_kryteriow(proces: ProcesOceny) -> list[str]:
    """Kryteria w kolejności arkusza: obowiązkowe, potem dodatkowe. Numer na liście jest numerem pola formularza."""
    return kryteria_obowiazkowe(proces.arkusz) + list(proces.kryteria_dodatkowe)


def oceny_czastkowe(post, proces: ProcesOceny) -> dict[str, int]:
    """Oceny cząstkowe z pól `ocena_<numer>`. Pola puste albo nieliczbowe są pomijane - braki zgłasza rdzeń."""
    oceny: dict[str, int] = {}
    for numer, nazwa in enumerate(nazwy_kryteriow(proces)):
        surowa = str(post.get(f"ocena_{numer}", "")).strip()
        if surowa.isdigit():
            oceny[nazwa] = int(surowa)
    return oceny


def kryteria_dodatkowe(post) -> list[str]:
    """Wybrane kryteria dodatkowe z list rozwijanych `kryterium_<numer>` (puste pola pominięte)."""
    limit = wczytaj_przepisy().max_kryteriow_dodatkowych
    # Jedno pole ponad limit pozwala rdzeniowi zgłosić przekroczenie zamiast po cichu je obciąć.
    wybrane = (tekst(post, f"kryterium_{numer}") for numer in range(1, limit + 2))
    return [nazwa for nazwa in wybrane if nazwa]


def czesc_II(post, proces: ProcesOceny) -> dict:
    """Zawartość formularza części II (i III) jako słownik szkicu - bez sprawdzania kompletności."""
    przepisy = wczytaj_przepisy()
    wniosek = tekst(post, "wniosek_o_stopien").upper()
    poprzednia_ocena = tekst(post, "poprzednia_ocena").upper()
    poprzedni_poziom = tekst(post, "poprzednia_poziom")
    poprzednia_data = data_lub_none(post, "poprzednia_data")
    poprzednia = None
    if poprzednia_ocena in (POZYTYWNA, NEGATYWNA):
        poprzednia = {
            "ocena": poprzednia_ocena,
            "poziom": poprzedni_poziom if poprzedni_poziom in {poziom.nazwa for poziom in przepisy.poziomy} else "",
            "data": poprzednia_data.isoformat() if poprzednia_data else "",
        }
    data_rozmowy = data_lub_none(post, "data_rozmowy")
    return {
        "data_rozmowy": data_rozmowy.isoformat() if data_rozmowy else "",
        "oceny": oceny_czastkowe(post, proces),
        "uzasadnienie": tekst(post, "uzasadnienie"),
        "wnioski_iprz": tekst(post, "wnioski_iprz"),
        "wniosek_o_stopien": wniosek if wniosek in (TAK, NIE) else None,
        "umotywowanie_wniosku": tekst(post, "umotywowanie_wniosku"),
        "poprzednia": poprzednia,
    }
