"""Harmonogram przypomnień (tor SCHEDULER w modelu BPMN KPRM)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .konfiguracja import Przepisy, _ustal_przepisy
from .przebieg import Rola


@dataclass(frozen=True)
class Przypomnienie:
    adresat: Rola
    typ: str  # TERMIN_KRYTERIOW, TERMIN_OCENY, STOPIEN_OBLIGATORYJNY
    termin: date


def przypomnienia_na_dzien(
    dzis: date,
    *,
    termin_oceny: date | None = None,
    termin_kryteriow: date | None = None,
    kryteria_potwierdzone: bool = False,
    termin_stopnia_obligatoryjnego: date | None = None,
    przepisy: Przepisy | None = None,
) -> list[Przypomnienie]:
    """Przypomnienia wysyłane w danym dniu; wyprzedzenia z `przypomnienia_dni_przed` w konfiguracji."""
    przepisy = _ustal_przepisy(przepisy)

    def przypada_dzis(termin: date | None) -> bool:
        return termin is not None and (termin - dzis).days in przepisy.przypomnienia_dni_przed

    przypomnienia: list[Przypomnienie] = []
    if not kryteria_potwierdzone and przypada_dzis(termin_kryteriow):
        przypomnienia.append(Przypomnienie(Rola.OCENIAJACY, "TERMIN_KRYTERIOW", termin_kryteriow))
    if przypada_dzis(termin_oceny):
        # Model BPMN: przypomnienie o zbliżającym się terminie oceny otrzymują obie strony.
        przypomnienia.append(Przypomnienie(Rola.OCENIAJACY, "TERMIN_OCENY", termin_oceny))
        przypomnienia.append(Przypomnienie(Rola.OCENIANY, "TERMIN_OCENY", termin_oceny))
    if przypada_dzis(termin_stopnia_obligatoryjnego):
        przypomnienia.append(
            Przypomnienie(Rola.ZARZADZAJACY, "STOPIEN_OBLIGATORYJNY", termin_stopnia_obligatoryjnego)
        )
    return przypomnienia
