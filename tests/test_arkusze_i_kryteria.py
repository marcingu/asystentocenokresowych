"""Wymaganie: wybór właściwego arkusza (A/B/C) i kryteriów oceny (maks. 3 dodatkowe).

Źródła: art. 81 ust. 1 u.s.c.; § 2-5 rozp. i załącznik nr 1; schemat pól formularza KPRM (lista rozwijana
kryteriów dodatkowych bez powtórzeń); arkusz XLSX KPRM „Arkusz B - wersja zautomatyzowana”
(lista kryteriów dodatkowych dla arkusza B); Poradnik KPRM s. 7 i 21-22.
"""

import pytest

from asystent_ocen.kryteria import (
    bledy_kryteriow_dodatkowych,
    czy_podlega_ocenie,
    kryteria_dodatkowe_do_wyboru,
    kryteria_obowiazkowe,
    wybierz_arkusz,
)
from stale import KATALOG, OBOWIAZKOWE_A, OBOWIAZKOWE_B, OBOWIAZKOWE_C


def kody(bledy):
    return {b.kod for b in bledy}


# --- kto podlega ocenie ---

@pytest.mark.parametrize(
    "rodzaj, podlega",
    [
        ("mianowanie", True),
        ("umowa_na_czas_nieokreslony", True),
        ("umowa_na_czas_okreslony", False),
        ("wyzsze_stanowisko", False),
    ],
)
def test_ocenie_podlega_urzednik_i_pracownik_na_czas_nieokreslony(rodzaj, podlega):
    """art. 81 ust. 1 u.s.c.; Poradnik s. 7 (nie podlegają m.in. wyższe stanowiska i umowy na czas określony)."""
    assert czy_podlega_ocenie(rodzaj_zatrudnienia=rodzaj) is podlega


# --- wybór arkusza ---

def test_kierownik_urzedu_jest_oceniany_na_arkuszu_a():
    """§ 3 ust. 2 rozp. - arkusz A ma pierwszeństwo także wtedy, gdy kierownik urzędu kieruje ludźmi."""
    assert wybierz_arkusz(kierownik_urzedu=True, kieruje_bezposrednio_pracownikami=True) == "A"


def test_bezposrednio_kierujacy_pracownikami_jest_oceniany_na_arkuszu_b():
    """§ 3 ust. 3 rozp."""
    assert wybierz_arkusz(kierownik_urzedu=False, kieruje_bezposrednio_pracownikami=True) == "B"


def test_pozostali_sa_oceniani_na_arkuszu_c():
    """§ 3 ust. 4 rozp."""
    assert wybierz_arkusz(kierownik_urzedu=False, kieruje_bezposrednio_pracownikami=False) == "C"


# --- kryteria obowiązkowe ---

@pytest.mark.parametrize("arkusz, oczekiwane", [("A", OBOWIAZKOWE_A), ("B", OBOWIAZKOWE_B), ("C", OBOWIAZKOWE_C)])
def test_kazdy_arkusz_ma_kryteria_obowiazkowe_z_rozporzadzenia(arkusz, oczekiwane):
    """§ 4 ust. 1-3 rozp."""
    assert kryteria_obowiazkowe(arkusz) == oczekiwane


# --- lista kryteriów dodatkowych ---

def test_lista_kryteriow_dodatkowych_dla_arkusza_b_odpowiada_arkuszowi_xlsx_kprm():
    """Arkusz XLSX KPRM, 'listy i obliczenia'!B2:B10 - 9 kryteriów spoza obowiązkowych dla B."""
    assert set(kryteria_dodatkowe_do_wyboru("B")) == {
        "Kreatywność",
        "Myślenie analityczne",
        "Negocjowanie",
        "Orientacja na klienta/interesanta",
        "Radzenie sobie w sytuacjach kryzysowych",
        "Rzetelność",
        "Wykorzystywanie wiedzy i doskonalenie zawodowe",
        "Wystąpienia publiczne",
        "Zarządzanie strategiczne",
    }


@pytest.mark.parametrize("arkusz, obowiazkowe", [("A", OBOWIAZKOWE_A), ("B", OBOWIAZKOWE_B), ("C", OBOWIAZKOWE_C)])
def test_kryteria_dodatkowe_to_wykaz_bez_kryteriow_obowiazkowych_arkusza(arkusz, obowiazkowe):
    assert set(kryteria_dodatkowe_do_wyboru(arkusz)) == set(KATALOG) - set(obowiazkowe)


def test_kryterium_wybrane_w_jednym_polu_znika_z_listy_w_pozostalych_polach():
    """Schemat pól formularza: „pozycje na liście nie mogą się powtarzać”."""
    lista = kryteria_dodatkowe_do_wyboru("C", wybrane=["Kreatywność"])
    assert "Kreatywność" not in lista
    assert len(lista) == 8


# --- walidacja wyboru kryteriów dodatkowych ---

def test_brak_kryteriow_dodatkowych_jest_dopuszczalny():
    """Poradnik s. 22: można w ogóle nie wybierać kryteriów dodatkowych."""
    assert bledy_kryteriow_dodatkowych("C", []) == []


def test_wiecej_niz_3_kryteria_dodatkowe_sa_bledem():
    """§ 5 ust. 2 rozp."""
    wybrane = ["Kreatywność", "Negocjowanie", "Myślenie analityczne", "Wystąpienia publiczne"]
    assert "ZA_DUZO_KRYTERIOW_DODATKOWYCH" in kody(bledy_kryteriow_dodatkowych("C", wybrane))


def test_powtorzone_kryterium_dodatkowe_jest_bledem():
    assert "POWTORZONE_KRYTERIUM" in kody(bledy_kryteriow_dodatkowych("C", ["Kreatywność", "Kreatywność"]))


def test_kryterium_spoza_wykazu_jest_bledem():
    """Przykładowy arkusz KPRM nr 13 (dyrektor departamentu) zawiera „Negocjacje” - w wykazie jest
    „Negocjowanie” (zał. nr 1 do rozp.)."""
    assert "KRYTERIUM_SPOZA_WYKAZU" in kody(bledy_kryteriow_dodatkowych("B", ["Negocjacje"]))


def test_kryterium_obowiazkowe_nie_moze_byc_wybrane_jako_dodatkowe():
    assert "KRYTERIUM_OBOWIAZKOWE_JAKO_DODATKOWE" in kody(bledy_kryteriow_dodatkowych("B", ["Komunikacja"]))


def test_nazwy_kryteriow_sa_porownywane_bez_rozrozniania_wielkosci_liter():
    """Przykładowe arkusze KPRM zapisują nazwy kryteriów różną wielkością liter."""
    assert bledy_kryteriow_dodatkowych("C", ["myślenie analityczne"]) == []
