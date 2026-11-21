"""Usprawiedliwione nieobecności i ich wpływ na termin oceny (art. 81 ust. 7 u.s.c.).

Zasady (dokument KPRM „liczenie terminów”, Poradnik KPRM 2016 s. 11-12):
- nieobecność ciągła trwa od pierwszego do ostatniego dnia następujących po sobie
  usprawiedliwionych nieobecności, niezależnie od ich przyczyny,
- dni wolne od pracy (sobota, niedziela, święta) między okresami nieobecności nie przerywają ciągłości,
- termin oceny przedłuża się o czas nieobecności ciągłej trwającej dłużej niż miesiąc.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .kalendarz import _DZIEN, _SOBOTA, czy_dzien_ustawowo_wolny, dodaj_miesiace
from .konfiguracja import Przepisy, _ustal_przepisy


@dataclass(frozen=True)
class Nieobecnosc:
    od: date
    do: date  # włącznie
    rodzaj: str = "inna"  # np. "urlop wypoczynkowy", "zwolnienie lekarskie", "urlop macierzyński"
    usprawiedliwiona: bool = True


@dataclass(frozen=True)
class OkresNieobecnosci:
    od: date
    do: date  # włącznie
    dni: int  # liczba dni kalendarzowych, włącznie z pierwszym i ostatnim


def scal_nieobecnosci_ciagle(
    nieobecnosci: Iterable[Nieobecnosc], przepisy: Przepisy | None = None
) -> list[OkresNieobecnosci]:
    """Łączy usprawiedliwione nieobecności przedzielone wyłącznie dniami wolnymi od pracy."""
    przepisy = _ustal_przepisy(przepisy)
    usprawiedliwione = sorted(
        (nieobecnosc for nieobecnosc in nieobecnosci if nieobecnosc.usprawiedliwiona),
        key=lambda nieobecnosc: (nieobecnosc.od, nieobecnosc.do),
    )
    okresy: list[tuple[date, date]] = []
    for nieobecnosc in usprawiedliwione:
        if nieobecnosc.do < nieobecnosc.od:
            raise ValueError(
                f"Nieobecność kończy się ({nieobecnosc.do}) przed swoim początkiem ({nieobecnosc.od})"
            )
        if okresy and _tylko_dni_wolne_miedzy(okresy[-1][1], nieobecnosc.od, przepisy):
            poczatek, koniec = okresy[-1]
            okresy[-1] = (poczatek, max(koniec, nieobecnosc.do))
        else:
            okresy.append((nieobecnosc.od, nieobecnosc.do))
    return [OkresNieobecnosci(od, do, (do - od).days + 1) for od, do in okresy]


def _tylko_dni_wolne_miedzy(koniec_poprzedniej: date, poczatek_nastepnej: date, przepisy: Przepisy) -> bool:
    """Czy między dwiema nieobecnościami nie ma ani jednego dnia pracy (także gdy się stykają lub nakładają)."""
    dzien = koniec_poprzedniej + _DZIEN
    while dzien < poczatek_nastepnej:
        wolna_sobota = przepisy.sobota_nie_przerywa_ciaglosci_nieobecnosci and dzien.weekday() == _SOBOTA
        if not (wolna_sobota or czy_dzien_ustawowo_wolny(dzien, przepisy)):
            return False
        dzien += _DZIEN
    return True


def czy_dluzsza_niz_miesiac(okres: OkresNieobecnosci, przepisy: Przepisy | None = None) -> bool:
    """Czy nieobecność ciągła trwa dłużej niż miesiąc (próg z przepisów).

    Miesiąc nieobecności rozpoczętej dnia D upływa w dniu odpowiadającym mu datą (art. 112 KC, Poradnik
    KPRM s. 12: od 9.09 do 9.10), więc „dłużej niż miesiąc” trwa nieobecność obejmująca kolejny dzień.
    """
    przepisy = _ustal_przepisy(przepisy)
    return okres.do > dodaj_miesiace(okres.od, przepisy.prog_nieobecnosci_miesiace)


def dni_przedluzenia_terminu(
    nieobecnosci: Iterable[Nieobecnosc], od: date, do: date, przepisy: Przepisy | None = None
) -> int:
    """Suma dni nieobecności ciągłych dłuższych niż miesiąc, przypadających w okresie od-do.

    O tym, czy nieobecność jest dłuższa niż miesiąc, decyduje cała nieobecność ciągła. Nieobecność zaczęta
    przed dniem `od` liczy się od dnia `od`; nieobecność zaczęta w okresie i trwająca po dniu `do` liczy się
    do swojego końca, bo termin przedłuża się „o czas tej nieobecności” (art. 81 ust. 7 u.s.c.).
    """
    przepisy = _ustal_przepisy(przepisy)
    suma = 0
    for okres in scal_nieobecnosci_ciagle(nieobecnosci, przepisy):
        poza_okresem = okres.do < od or okres.od > do
        if poza_okresem or not czy_dluzsza_niz_miesiac(okres, przepisy):
            continue
        suma += (okres.do - max(okres.od, od)).days + 1
    return suma
