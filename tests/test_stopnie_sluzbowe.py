"""Wymaganie: wniosek o kolejny stopień służbowy i obligatoryjne przyznanie stopnia.

Źródła: art. 86 ust. 1 i art. 89 u.s.c.; § 11 ust. 5 rozp.; przypadki użycia i ich warunki brzegowe;
schemat pól formularza (część III, komunikat przy dziewiątym stopniu); Poradnik KPRM s. 29-30, 35.
"""

import pytest

from asystent_ocen.stopnie import (
    OcenaHistoryczna,
    czy_mozna_zlozyc_wniosek_o_stopien,
    czy_przysluguje_stopien_obligatoryjny,
    kolejny_stopien_slownie,
    komunikat_dla_stopnia,
)
from asystent_ocen.terminy import termin_przyznania_stopnia_obligatoryjnego
from asystent_ocen.wynik import NEGATYWNA, POZYTYWNA
from stale import d

POWYZEJ = "powyżej oczekiwań"
ZNACZNIE_POWYZEJ = "znacznie powyżej oczekiwań"
NA_POZIOMIE = "na poziomie oczekiwań"
PONIZEJ = "poniżej oczekiwań"


# --- wniosek fakultatywny (art. 89 ust. 1) ---

def test_urzednik_z_ocena_pozytywna_moze_otrzymac_wniosek_o_kolejny_stopien():
    assert czy_mozna_zlozyc_wniosek_o_stopien(urzednik=True, ocena=POZYTYWNA, posiadany_stopien=3) is True


def test_pracownik_sluzby_cywilnej_nie_otrzymuje_wniosku_o_stopien():
    """Stopnie służbowe przysługują wyłącznie urzędnikom SC (mianowanym)."""
    assert czy_mozna_zlozyc_wniosek_o_stopien(urzednik=False, ocena=POZYTYWNA, posiadany_stopien=0) is False


def test_przy_ocenie_negatywnej_nie_mozna_zlozyc_wniosku_o_stopien():
    assert czy_mozna_zlozyc_wniosek_o_stopien(urzednik=True, ocena=NEGATYWNA, posiadany_stopien=3) is False


def test_przy_najwyzszym_stopniu_nie_mozna_zlozyc_wniosku():
    """art. 86 ust. 1 u.s.c. - dziewięć stopni służbowych."""
    assert czy_mozna_zlozyc_wniosek_o_stopien(urzednik=True, ocena=POZYTYWNA, posiadany_stopien=9) is False


@pytest.mark.parametrize("posiadany, slownie", [(1, "drugiego"), (2, "trzeciego"), (5, "szóstego"), (8, "dziewiątego")])
def test_wniosek_wskazuje_kolejny_stopien_slownie(posiadany, slownie):
    """Schemat pól części III: pole wypełniane automatycznie kolejnym, wyższym stopniem."""
    assert kolejny_stopien_slownie(posiadany) == slownie


def test_nie_ma_stopnia_wyzszego_niz_dziewiaty():
    with pytest.raises(ValueError):
        kolejny_stopien_slownie(9)


def test_przy_dziewiatym_stopniu_system_wyswietla_komunikat_ze_schematu_kprm():
    assert komunikat_dla_stopnia(9) == (
        "Ocenianemu nie można przyznać kolejnego stopnia służbowego. "
        "Oceniany posiada już najwyższy możliwy stopień służbowy"
    )
    assert komunikat_dla_stopnia(4) is None


# --- stopień obligatoryjny (art. 89 ust. 2) ---

def test_dwie_kolejne_oceny_na_dwoch_najwyzszych_poziomach_daja_stopien_z_mocy_prawa():
    historia = [
        OcenaHistoryczna(d(2024, 5, 10), POZYTYWNA, POWYZEJ),
        OcenaHistoryczna(d(2026, 5, 12), POZYTYWNA, ZNACZNIE_POWYZEJ),
    ]
    assert czy_przysluguje_stopien_obligatoryjny(
        urzednik=True, historia=historia, data_ostatniego_stopnia=d(2023, 1, 2)
    ) is True


def test_ocena_na_poziomie_oczekiwan_nie_liczy_sie_do_stopnia_obligatoryjnego():
    historia = [
        OcenaHistoryczna(d(2024, 5, 10), POZYTYWNA, POWYZEJ),
        OcenaHistoryczna(d(2026, 5, 12), POZYTYWNA, NA_POZIOMIE),
    ]
    assert czy_przysluguje_stopien_obligatoryjny(
        urzednik=True, historia=historia, data_ostatniego_stopnia=d(2023, 1, 2)
    ) is False


def test_licza_sie_tylko_oceny_uzyskane_po_otrzymaniu_ostatniego_stopnia():
    historia = [
        OcenaHistoryczna(d(2022, 3, 1), POZYTYWNA, POWYZEJ),  # przed ostatnim stopniem
        OcenaHistoryczna(d(2025, 3, 3), POZYTYWNA, POWYZEJ),
    ]
    assert czy_przysluguje_stopien_obligatoryjny(
        urzednik=True, historia=historia, data_ostatniego_stopnia=d(2023, 1, 2)
    ) is False


def test_oceny_musza_nastepowac_bezposrednio_po_sobie():
    historia = [
        OcenaHistoryczna(d(2023, 6, 1), POZYTYWNA, POWYZEJ),
        OcenaHistoryczna(d(2025, 6, 2), NEGATYWNA, PONIZEJ),
        OcenaHistoryczna(d(2026, 1, 5), POZYTYWNA, POWYZEJ),
    ]
    assert czy_przysluguje_stopien_obligatoryjny(
        urzednik=True, historia=historia, data_ostatniego_stopnia=d(2023, 1, 2)
    ) is False


def test_ocena_negatywna_na_wysokim_poziomie_sredniej_nie_liczy_sie():
    """Poziom „powyżej oczekiwań” z oceną cząstkową 1 daje ocenę negatywną (§ 11 ust. 1 pkt 4 rozp.)."""
    historia = [
        OcenaHistoryczna(d(2024, 5, 10), NEGATYWNA, POWYZEJ),
        OcenaHistoryczna(d(2026, 5, 12), POZYTYWNA, POWYZEJ),
    ]
    assert czy_przysluguje_stopien_obligatoryjny(
        urzednik=True, historia=historia, data_ostatniego_stopnia=d(2023, 1, 2)
    ) is False


def test_stopien_obligatoryjny_nie_dotyczy_pracownika_sluzby_cywilnej():
    historia = [
        OcenaHistoryczna(d(2024, 5, 10), POZYTYWNA, ZNACZNIE_POWYZEJ),
        OcenaHistoryczna(d(2026, 5, 12), POZYTYWNA, ZNACZNIE_POWYZEJ),
    ]
    assert czy_przysluguje_stopien_obligatoryjny(
        urzednik=False, historia=historia, data_ostatniego_stopnia=d(2023, 1, 2)
    ) is False


def test_stopien_obligatoryjny_nie_przysluguje_przy_dziewiatym_stopniu():
    """art. 86 ust. 1 u.s.c. - nie ma stopnia wyższego niż dziewiąty."""
    historia = [
        OcenaHistoryczna(d(2024, 5, 10), POZYTYWNA, ZNACZNIE_POWYZEJ),
        OcenaHistoryczna(d(2026, 5, 12), POZYTYWNA, ZNACZNIE_POWYZEJ),
    ]
    assert czy_przysluguje_stopien_obligatoryjny(
        urzednik=True, historia=historia, data_ostatniego_stopnia=d(2023, 1, 2), posiadany_stopien=9
    ) is False


def test_stopien_obligatoryjny_przyznaje_sie_w_30_dni_od_zapoznania_z_ocena():
    """art. 89 ust. 2 u.s.c.: zapoznanie 20.11.2026 + 30 dni = 20.12.2026 (niedziela) -> 21.12.2026."""
    assert termin_przyznania_stopnia_obligatoryjnego(d(2026, 11, 20)) == d(2026, 12, 21)
