"""Stopnie służbowe urzędników służby cywilnej (u.s.c. art. 86, 89)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .konfiguracja import Przepisy, _ustal_przepisy
from .kryteria import _klucz
from .wynik import POZYTYWNA

# Komunikat ze schematów pól formularza KPRM (pole „Posiadany stopień służbowy”).
_KOMUNIKAT_NAJWYZSZEGO_STOPNIA = (
    "Ocenianemu nie można przyznać kolejnego stopnia służbowego. "
    "Oceniany posiada już najwyższy możliwy stopień służbowy"
)

# Liczebniki porządkowe w dopełniaczu („wnioskuję o przyznanie ... stopnia służbowego”).
_JEDNOSCI = (
    "", "pierwszego", "drugiego", "trzeciego", "czwartego", "piątego", "szóstego", "siódmego", "ósmego",
    "dziewiątego",
)
_NASTKI = (
    "dziesiątego", "jedenastego", "dwunastego", "trzynastego", "czternastego", "piętnastego", "szesnastego",
    "siedemnastego", "osiemnastego", "dziewiętnastego",
)
_DZIESIATKI = (
    "", "", "dwudziestego", "trzydziestego", "czterdziestego", "pięćdziesiątego", "sześćdziesiątego",
    "siedemdziesiątego", "osiemdziesiątego", "dziewięćdziesiątego",
)


@dataclass(frozen=True)
class OcenaHistoryczna:
    data_zapoznania: date
    ocena: str  # POZYTYWNA / NEGATYWNA
    poziom: str  # np. "powyżej oczekiwań"


def _liczebnik_porzadkowy_w_dopelniaczu(liczba: int) -> str:
    if not 1 <= liczba <= 99:
        raise ValueError(f"Brak słownego zapisu stopnia służbowego nr {liczba}")
    if liczba < 10:
        return _JEDNOSCI[liczba]
    if liczba < 20:
        return _NASTKI[liczba - 10]
    dziesiatki, jednosci = divmod(liczba, 10)
    return f"{_DZIESIATKI[dziesiatki]} {_JEDNOSCI[jednosci]}".strip()


def czy_mozna_zlozyc_wniosek_o_stopien(
    *, urzednik: bool, ocena: str, posiadany_stopien: int, przepisy: Przepisy | None = None
) -> bool:
    """Art. 89 ust. 1: wniosek tylko dla urzędnika SC z oceną pozytywną; nie dla najwyższego stopnia."""
    przepisy = _ustal_przepisy(przepisy)
    return bool(urzednik) and ocena == POZYTYWNA and 1 <= posiadany_stopien < przepisy.max_stopien_sluzbowy


def kolejny_stopien_slownie(posiadany_stopien: int, przepisy: Przepisy | None = None) -> str:
    """Treść do wniosku: „wnioskuję o przyznanie ___ stopnia służbowego” (np. 1 -> "drugiego")."""
    przepisy = _ustal_przepisy(przepisy)
    if not 1 <= posiadany_stopien < przepisy.max_stopien_sluzbowy:
        raise ValueError(
            f"Nie ma stopnia służbowego kolejnego po stopniu {posiadany_stopien} "
            f"(stopnie: od 1 do {przepisy.max_stopien_sluzbowy})"
        )
    return _liczebnik_porzadkowy_w_dopelniaczu(posiadany_stopien + 1)


def komunikat_dla_stopnia(posiadany_stopien: int, przepisy: Przepisy | None = None) -> str | None:
    """Komunikat ze schematu pól formularza KPRM dla najwyższego (dziewiątego) stopnia, inaczej None."""
    przepisy = _ustal_przepisy(przepisy)
    if posiadany_stopien >= przepisy.max_stopien_sluzbowy:
        return _KOMUNIKAT_NAJWYZSZEGO_STOPNIA
    return None


def czy_przysluguje_stopien_obligatoryjny(
    *,
    urzednik: bool,
    historia: Sequence[OcenaHistoryczna],
    data_ostatniego_stopnia: date,
    posiadany_stopien: int | None = None,
    przepisy: Przepisy | None = None,
) -> bool:
    """Art. 89 ust. 2: dwie kolejne, następujące po sobie oceny pozytywne na jednym z dwóch najwyższych
    poziomów, uzyskane od otrzymania ostatniego stopnia służbowego. Nie przysługuje przy najwyższym
    (dziewiątym) stopniu - art. 86 ust. 1.

    Bada się najnowsze oceny (tyle, ile wymagają przepisy), z którymi zapoznano urzędnika po dniu otrzymania
    ostatniego stopnia; ocena z dnia otrzymania stopnia nie liczy się ponownie.
    """
    przepisy = _ustal_przepisy(przepisy)
    if not urzednik:
        return False
    if posiadany_stopien is not None and posiadany_stopien >= przepisy.max_stopien_sluzbowy:
        return False
    po_stopniu = sorted(
        (ocena for ocena in historia if ocena.data_zapoznania > data_ostatniego_stopnia),
        key=lambda ocena: ocena.data_zapoznania,
    )
    wymagane = przepisy.stopien_obligatoryjny_liczba_ocen
    if len(po_stopniu) < wymagane:
        return False
    najwyzsze_poziomy = {_klucz(poziom.nazwa) for poziom in przepisy.poziomy if poziom.najwyzszy}
    return all(
        ocena.ocena == POZYTYWNA and _klucz(ocena.poziom) in najwyzsze_poziomy
        for ocena in po_stopniu[-wymagane:]
    )
