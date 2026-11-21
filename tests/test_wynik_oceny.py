"""Wymaganie: wyliczenie średniej, ogólnego poziomu i oceny pozytywnej/negatywnej.

Źródła: § 11 ust. 1 pkt 1-4 rozp.; przypisy 10 i 11 do części II arkusza B (definicje oceny POZYTYWNEJ
i NEGATYWNEJ); schemat pól formularza (średnia i znak „X” wstawiane automatycznie); Poradnik KPRM s. 25-27
(rozdz. 6.2.5.1-6.2.5.2).
"""

import dataclasses
from fractions import Fraction

import pytest

from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.wynik import (
    NEGATYWNA,
    POZYTYWNA,
    bledy_ocen_czastkowych,
    formatuj_srednia,
    niespojnosci_arkusza,
    oblicz_wynik,
    poziom_dla_sredniej,
)
from stale import OBOWIAZKOWE_C


def kody(bledy):
    return {b.kod for b in bledy}


@pytest.mark.parametrize("ocena_spoza_skali", [0, 2, 4, 6, 8, 10])
def test_ocena_czastkowa_spoza_skali_1_3_5_7_9_jest_odrzucana(ocena_spoza_skali):
    """§ 11 ust. 1 pkt 1 rozp."""
    with pytest.raises(ValueError):
        oblicz_wynik([5, 5, 5, 5, ocena_spoza_skali])


def test_brak_ocen_czastkowych_jest_odrzucany():
    with pytest.raises(ValueError):
        oblicz_wynik([])


def test_srednia_jest_liczona_dokladnie_jako_ulamek():
    """Dokładna średnia eliminuje błędy zaokrągleń na granicach przedziałów."""
    assert oblicz_wynik([5, 1, 5, 5, 5]).srednia == Fraction(21, 5)


@pytest.mark.parametrize(
    "oceny, poziom",
    [
        ([1, 1, 1, 1, 1], "znacznie poniżej oczekiwań"),
        ([3, 3, 3, 1, 1, 1], "znacznie poniżej oczekiwań"),  # średnia 2,0 - górna granica przedziału
        ([5, 5, 5, 3, 3, 3], "poniżej oczekiwań"),           # średnia 4,0 - górna granica
        ([5, 5, 5, 5, 3, 3], "na poziomie oczekiwań"),       # 4,33
        ([7, 7, 7, 5, 5, 5], "na poziomie oczekiwań"),       # 6,0 - górna granica
        ([9, 9, 9, 7, 7, 7], "powyżej oczekiwań"),           # 8,0 - górna granica
        ([9, 9, 9, 9, 9, 7], "znacznie powyżej oczekiwań"),  # 8,67
        ([9, 9, 9, 9, 9], "znacznie powyżej oczekiwań"),     # 9,0
    ],
)
def test_ogolny_poziom_wynika_z_przedzialow_sredniej(oceny, poziom):
    """§ 11 ust. 1 pkt 2 rozp.: od 1 do 2, powyżej 2 do 4, powyżej 4 do 6, powyżej 6 do 8, powyżej 8 do 9."""
    assert oblicz_wynik(oceny).poziom == poziom


@pytest.mark.parametrize(
    "srednia, poziom",
    [
        (Fraction(2), "znacznie poniżej oczekiwań"),
        (Fraction(4), "poniżej oczekiwań"),
        (Fraction(6), "na poziomie oczekiwań"),
        (Fraction(8), "powyżej oczekiwań"),
        (Fraction(37, 9), "na poziomie oczekiwań"),
    ],
)
def test_granica_przedzialu_nalezy_do_nizszego_poziomu(srednia, poziom):
    assert poziom_dla_sredniej(srednia) == poziom


@pytest.mark.parametrize(
    "oceny, ocena",
    [
        ([5, 5, 5, 5, 5], POZYTYWNA),
        ([5, 5, 5, 3, 3, 3], NEGATYWNA),   # poniżej oczekiwań
        ([5, 5, 5, 5, 3, 3], POZYTYWNA),   # na poziomie oczekiwań, bez oceny 1
        ([7, 9, 7, 7, 5, 7], POZYTYWNA),
    ],
)
def test_ocena_jest_pozytywna_od_poziomu_na_poziomie_oczekiwan(oceny, ocena):
    """§ 11 ust. 1 pkt 3-4 rozp."""
    assert oblicz_wynik(oceny).ocena == ocena


def test_choc_jedna_ocena_czastkowa_1_daje_ocene_negatywna_mimo_wysokiej_sredniej():
    """§ 11 ust. 1 pkt 4 rozp.: średnia 7,67 (powyżej oczekiwań), ale jedna ocena „znacznie poniżej”."""
    wynik = oblicz_wynik([9, 9, 9, 9, 9, 1])
    assert wynik.poziom == "powyżej oczekiwań"
    assert wynik.ocena == NEGATYWNA


def test_oceny_mozna_podac_jako_slownik_kryterium_ocena():
    oceny = dict(zip(OBOWIAZKOWE_C, [5, 1, 5, 5, 5]))
    assert oblicz_wynik(oceny) == oblicz_wynik([5, 1, 5, 5, 5])


# --- kompletność i poprawność ocen cząstkowych ---

def test_kazde_kryterium_obowiazkowe_musi_otrzymac_ocene():
    oceny = dict(zip(OBOWIAZKOWE_C[:4], [5, 5, 5, 5]))  # brak oceny „Komunikacja”
    assert "BRAK_OCENY_KRYTERIUM" in kody(bledy_ocen_czastkowych("C", [], oceny))


def test_kazde_wybrane_kryterium_dodatkowe_musi_otrzymac_ocene():
    oceny = dict(zip(OBOWIAZKOWE_C, [5, 5, 5, 5, 5]))
    assert "BRAK_OCENY_KRYTERIUM" in kody(bledy_ocen_czastkowych("C", ["Kreatywność"], oceny))


def test_nie_mozna_ocenic_kryterium_ktore_nie_zostalo_wybrane():
    oceny = dict(zip(OBOWIAZKOWE_C, [5, 5, 5, 5, 5])) | {"Kreatywność": 7}
    assert "OCENA_NIEWYBRANEGO_KRYTERIUM" in kody(bledy_ocen_czastkowych("C", [], oceny))


def test_ocena_czastkowa_spoza_skali_jest_bledem_formularza():
    oceny = dict(zip(OBOWIAZKOWE_C, [5, 5, 5, 5, 6]))
    assert "OCENA_SPOZA_SKALI" in kody(bledy_ocen_czastkowych("C", [], oceny))


def test_komplet_poprawnych_ocen_nie_daje_bledow():
    oceny = dict(zip(OBOWIAZKOWE_C, [5, 7, 5, 5, 5])) | {"Kreatywność": 7}
    assert bledy_ocen_czastkowych("C", ["Kreatywność"], oceny) == []


# --- kontrola arkusza wypełnionego ręcznie (import, przegląd przez kadry) ---

def test_bledny_poziom_wpisany_w_arkuszu_jest_wykrywany():
    """Średnia 4,2 to „na poziomie oczekiwań” (§ 11 ust. 1 pkt 2 lit. c rozp.), nie „poniżej oczekiwań”."""
    bledy = niespojnosci_arkusza([5, 1, 5, 5, 5], srednia_wpisana="4,2", poziom_wpisany="poniżej oczekiwań",
                                 wynik_wpisany=NEGATYWNA)
    assert {b.kod for b in bledy} == {"BLEDNY_POZIOM"}


def test_ocena_pozytywna_mimo_oceny_czastkowej_1_jest_wykrywana():
    """§ 11 ust. 1 pkt 4 rozp. - typowy błąd: ocena cząstkowa 1 przy średniej „na poziomie oczekiwań”."""
    bledy = niespojnosci_arkusza([5, 1, 5, 5, 5], srednia_wpisana="4,2", poziom_wpisany="na poziomie oczekiwań",
                                 wynik_wpisany=POZYTYWNA)
    assert {b.kod for b in bledy} == {"BLEDNY_WYNIK"}


@pytest.mark.parametrize("srednia_wpisana", ["3,8", "3,86", "3,9", "3,857"])
def test_srednia_zaokraglona_lub_obcieta_do_zapisanej_precyzji_jest_zgodna(srednia_wpisana):
    """27/7 = 3,857...: zgodne są „3,8” (obcięcie, jak w arkuszu KPRM nr 12), „3,9” i „3,86” (zaokrąglenie)."""
    assert niespojnosci_arkusza([5, 5, 5, 3, 3, 3, 3], srednia_wpisana=srednia_wpisana) == []


@pytest.mark.parametrize("srednia_wpisana", ["3,7", "3,87", "5"])
def test_srednia_niezgodna_z_ocenami_jest_wykrywana(srednia_wpisana):
    """27/7 = 3,857...: „3,7” i „3,87” nie są ani zaokrągleniem, ani obcięciem; „5” to inna wartość."""
    assert {b.kod for b in niespojnosci_arkusza([5, 5, 5, 3, 3, 3, 3], srednia_wpisana=srednia_wpisana)} == {
        "BLEDNA_SREDNIA"
    }


# --- prezentacja ---

@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize(
    "srednia, tekst",
    [
        (Fraction(21, 5), "4,2"),
        (Fraction(5), "5,0"),
        (Fraction(27, 7), "3,9"),
        (Fraction(19, 3), "6,3"),
        (Fraction(25, 4), "6,3"),
        (Fraction(27, 4), "6,8"),
    ],
)
def test_srednia_jest_prezentowana_z_przecinkiem_i_jednym_miejscem_po_przecinku(srednia, tekst):
    """Decyzja zespołu z 21.11.2026: jedno miejsce po przecinku, zaokrąglenie arytmetyczne (6,25 -> „6,3”).
    Rozporządzenie nie określa precyzji; poziom ustala się zawsze z dokładnej średniej."""
    assert formatuj_srednia(srednia) == tekst


def test_liczbe_miejsc_po_przecinku_mozna_zmienic_w_konfiguracji():
    dwa_miejsca = dataclasses.replace(wczytaj_przepisy(), miejsca_po_przecinku_sredniej=2)
    assert formatuj_srednia(Fraction(27, 7), przepisy=dwa_miejsca) == "3,86"
