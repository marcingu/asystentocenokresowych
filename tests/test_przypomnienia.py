"""Wymaganie: przypominanie o terminach (scheduler).

Źródła: treść wyzwania KPRM pkt 3.2 („przypominać o terminach”); przypadki użycia: „(scheduler)
przypomnienie o wyznaczeniu kryteriów”, „(scheduler) przypomnienie o zbliżającym się terminie oceny”,
„(scheduler) wysyła przypomnienie o obowiązku przyznania kolejnego stopnia”; model BPMN (tor SCHEDULER).
Wyprzedzenia przypomnień (30, 14, 3 dni) to decyzja projektowa zapisana w konfiguracji.
"""

import pytest

from asystent_ocen.przebieg import Rola
from asystent_ocen.przypomnienia import przypomnienia_na_dzien
from stale import d

TERMIN_OCENY = d(2026, 12, 15)


@pytest.mark.parametrize("dzis", [d(2026, 11, 15), d(2026, 12, 1), d(2026, 12, 12)])
def test_przypomnienie_o_terminie_oceny_trafia_do_oceniajacego_i_ocenianego(dzis):
    """Model BPMN: obie strony otrzymują przypomnienie o zbliżającym się terminie oceny."""
    adresaci = {p.adresat for p in przypomnienia_na_dzien(dzis, termin_oceny=TERMIN_OCENY) if p.typ == "TERMIN_OCENY"}
    assert adresaci == {Rola.OCENIAJACY, Rola.OCENIANY}


def test_w_pozostale_dni_przypomnienie_o_terminie_oceny_nie_jest_wysylane():
    assert przypomnienia_na_dzien(d(2026, 12, 2), termin_oceny=TERMIN_OCENY) == []


def test_przypomnienie_o_wyznaczeniu_kryteriow_trafia_do_oceniajacego():
    przypomnienia = przypomnienia_na_dzien(d(2026, 2, 8), termin_kryteriow=d(2026, 2, 11))
    assert [(p.adresat, p.typ) for p in przypomnienia] == [(Rola.OCENIAJACY, "TERMIN_KRYTERIOW")]


def test_po_potwierdzeniu_kryteriow_przypomnienie_o_nich_nie_jest_wysylane():
    assert przypomnienia_na_dzien(d(2026, 2, 8), termin_kryteriow=d(2026, 2, 11), kryteria_potwierdzone=True) == []


def test_kadry_dostaja_przypomnienie_o_obowiazku_przyznania_stopnia():
    """Przypadek użycia: obligatoryjne przyznanie kolejnego stopnia - przypomnienie dla ZARZĄDZAJĄCEGO."""
    przypomnienia = przypomnienia_na_dzien(d(2026, 12, 7), termin_stopnia_obligatoryjnego=d(2026, 12, 21))
    assert (Rola.ZARZADZAJACY, "STOPIEN_OBLIGATORYJNY") in {(p.adresat, p.typ) for p in przypomnienia}
