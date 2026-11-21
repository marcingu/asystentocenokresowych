"""Skutki sporządzonej oceny - zadania i alerty dla oceniającego, kadr i ocenianego.

Kody skutków:
- PONOWNA_OCENA (art. 81 ust. 9 u.s.c.) - po ocenie negatywnej,
- NOWE_KRYTERIA (§ 7 rozp.) - termin rozmowy i zapoznania z kryteriami w nowym cyklu,
- TERMIN_KOLEJNEJ_OCENY (art. 81 ust. 4 u.s.c.) - po ocenie pozytywnej,
- STOPIEN_OBLIGATORYJNY (art. 89 ust. 2 u.s.c.),
- ROZWIAZANIE_STOSUNKU_PRACY (art. 71 ust. 1 pkt 1 u.s.c.) - druga kolejna negatywna ocena urzędnika,
- IPRZ (art. 108 u.s.c.) - indywidualny program rozwoju zawodowego z uwzględnieniem wniosków z oceny.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .konfiguracja import Przepisy, _ustal_przepisy
from .kryteria import _klucz
from .stopnie import OcenaHistoryczna, czy_przysluguje_stopien_obligatoryjny
from .terminy import (
    data_ponownej_oceny_po_negatywnej,
    termin_oceny,
    termin_przyznania_stopnia_obligatoryjnego,
    termin_wyznaczenia_kryteriow,
)
from .wynik import NEGATYWNA, POZYTYWNA


@dataclass(frozen=True)
class Skutek:
    kod: str
    termin: date | None
    podstawa: str = ""


def skutki_oceny(
    *,
    ocena: str,
    poziom: str,
    urzednik: bool,
    data_sporzadzenia: date,
    data_zapoznania: date,
    poprzednia_ocena: str | None = None,
    historia_od_ostatniego_stopnia: Sequence[OcenaHistoryczna] = (),
    data_ostatniego_stopnia: date | None = None,
    posiadany_stopien: int | None = None,
    przepisy: Przepisy | None = None,
) -> list[Skutek]:
    """Zwraca listę skutków oceny. `historia_od_ostatniego_stopnia` zawiera także bieżącą ocenę.

    Gdy nie podano `data_ostatniego_stopnia`, cała przekazana historia jest traktowana jako uzyskana
    po otrzymaniu ostatniego stopnia. Ocena inna niż POZYTYWNA/NEGATYWNA -> ValueError.
    """
    przepisy = _ustal_przepisy(przepisy)
    if ocena not in (POZYTYWNA, NEGATYWNA):
        raise ValueError(f"Nieznana ocena: {ocena!r} (dopuszczalne: {POZYTYWNA}, {NEGATYWNA})")

    skutki: list[Skutek] = []
    if ocena == NEGATYWNA:
        skutki.append(Skutek(
            "PONOWNA_OCENA",
            data_ponownej_oceny_po_negatywnej(data_zapoznania, przepisy=przepisy),
            "art. 81 ust. 9 u.s.c.",
        ))
        skutki.append(Skutek(
            "NOWE_KRYTERIA",
            termin_wyznaczenia_kryteriow(data_sporzadzenia, po_negatywnej=True, przepisy=przepisy),
            "§ 7 pkt 2 rozp.",
        ))
        if urzednik and poprzednia_ocena == NEGATYWNA:
            skutki.append(Skutek("ROZWIAZANIE_STOSUNKU_PRACY", None, "art. 71 ust. 1 pkt 1 u.s.c."))
    else:
        skutki.append(Skutek(
            "NOWE_KRYTERIA",
            termin_wyznaczenia_kryteriow(data_sporzadzenia, przepisy=przepisy),
            "§ 7 pkt 1 rozp.",
        ))
        skutki.append(Skutek(
            "TERMIN_KOLEJNEJ_OCENY", termin_oceny(data_sporzadzenia, przepisy=przepisy), "art. 81 ust. 4 u.s.c."
        ))
        # Bieżąca ocena sama musi spełniać warunki art. 89 ust. 2 - chroni przed niepełną historią.
        najwyzsze_poziomy = {_klucz(p.nazwa) for p in przepisy.poziomy if p.najwyzszy}
        if _klucz(poziom) in najwyzsze_poziomy and czy_przysluguje_stopien_obligatoryjny(
            urzednik=urzednik,
            historia=historia_od_ostatniego_stopnia,
            data_ostatniego_stopnia=data_ostatniego_stopnia if data_ostatniego_stopnia is not None else date.min,
            posiadany_stopien=posiadany_stopien,
            przepisy=przepisy,
        ):
            skutki.append(Skutek(
                "STOPIEN_OBLIGATORYJNY",
                termin_przyznania_stopnia_obligatoryjnego(data_zapoznania, przepisy),
                "art. 89 ust. 2 u.s.c.",
            ))
    # Przepisy nie określają terminu przygotowania IPRZ (Poradnik KPRM s. 34).
    skutki.append(Skutek("IPRZ", None, "art. 108 u.s.c."))
    return skutki
