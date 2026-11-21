"""Wymaganie: terminy sprzeciwu i odwołania od oceny okresowej.

Źródła: art. 83 u.s.c.; pouczenie w arkuszach B i C; Poradnik KPRM s. 32-33.
"""

from asystent_ocen.terminy import termin_odwolania_do_sadu, termin_rozpatrzenia_sprzeciwu, termin_sprzeciwu
from stale import d


def test_sprzeciw_wnosi_sie_w_7_dni_od_zapoznania_z_ocena():
    """art. 83 ust. 1 u.s.c.: zapoznanie 12.10.2026 -> sprzeciw do 19.10.2026."""
    assert termin_sprzeciwu(d(2026, 10, 12)) == d(2026, 10, 19)


def test_termin_sprzeciwu_przypadajacy_w_swieto_przesuwa_sie():
    """art. 115 KC: zapoznanie 4.11.2026 + 7 dni = 11.11.2026 (święto) -> 12.11.2026."""
    assert termin_sprzeciwu(d(2026, 11, 4)) == d(2026, 11, 12)


def test_sprzeciw_rozpatruje_sie_w_14_dni_od_wniesienia():
    """art. 83 ust. 3 u.s.c."""
    assert termin_rozpatrzenia_sprzeciwu(d(2026, 11, 12)) == d(2026, 11, 26)


def test_odwolanie_do_sadu_pracy_przysluguje_w_14_dni_od_doreczenia_decyzji():
    """art. 83 ust. 5 u.s.c."""
    assert termin_odwolania_do_sadu(data_doreczenia_decyzji=d(2026, 11, 25)) == d(2026, 12, 9)


def test_przy_nierozpatrzeniu_sprzeciwu_14_dni_liczy_sie_od_uplywu_terminu_na_rozpatrzenie():
    """art. 83 ust. 5 u.s.c.: wniesienie 12.11.2026 -> rozpatrzenie do 26.11.2026 -> odwołanie do 10.12.2026."""
    assert termin_odwolania_do_sadu(data_wniesienia_sprzeciwu=d(2026, 11, 12)) == d(2026, 12, 10)
