"""Termin oceny wynikający z ustawy - jedno miejsce dla karty oceny i dla czynności procesu.

Art. 81 ust. 4 u.s.c.: 24 miesiące od początku cyklu; ust. 7: przedłużenie o usprawiedliwioną nieobecność dłuższą
niż miesiąc; ust. 9: ponowna ocena po ocenie negatywnej po upływie 6 miesięcy od zapoznania się z nią (ten termin
nie jest przedłużany - Poradnik KPRM, s. 14).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from asystent_ocen import terminy


@dataclass(frozen=True)
class TerminUstawowy:
    data: date
    bez_nieobecnosci: date
    podstawa: str
    po_negatywnej: bool

    @property
    def przedluzony(self) -> bool:
        return self.data > self.bez_nieobecnosci


def nieobecnosci_rdzenia(pracownik) -> list:
    return [nieobecnosc.do_rdzenia() for nieobecnosc in pracownik.nieobecnosci.all()]


def termin_ustawowy(ocena, poczatek_cyklu: date, nieobecnosci: list | None = None) -> TerminUstawowy:
    """Termin, w którym ocena ma być sporządzona z mocy ustawy."""
    if nieobecnosci is None:
        nieobecnosci = nieobecnosci_rdzenia(ocena.oceniany)
    if ocena.po_negatywnej and ocena.poprzednia.data_zapoznania:
        termin = terminy.data_ponownej_oceny_po_negatywnej(ocena.poprzednia.data_zapoznania)
        return TerminUstawowy(termin, termin, "art. 81 ust. 9 u.s.c.", True)
    termin = terminy.termin_oceny(poczatek_cyklu, nieobecnosci)
    bez = terminy.termin_oceny(poczatek_cyklu)
    podstawa = "art. 81 ust. 4 u.s.c." + ("; art. 81 ust. 7 u.s.c." if termin > bez else "")
    return TerminUstawowy(termin, bez, podstawa, False)
