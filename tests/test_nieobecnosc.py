"""Wymaganie: rozpoznawanie usprawiedliwionej nieobecności ciągłej dłuższej niż miesiąc.

Źródła: art. 81 ust. 7 u.s.c.; dokument KPRM „liczenie terminów” (Nieobecności);
Poradnik KPRM 2016, s. 11-12; warunki brzegowe przypadków użycia („nieobecność usprawiedliwiona,
ciągła, trwająca dłużej niż miesiąc”).
"""

import pytest

from asystent_ocen.nieobecnosci import (
    Nieobecnosc,
    OkresNieobecnosci,
    czy_dluzsza_niz_miesiac,
    dni_przedluzenia_terminu,
    scal_nieobecnosci_ciagle,
)
from stale import d


def test_weekend_miedzy_zwolnieniem_lekarskim_a_urlopem_nie_przerywa_ciaglosci():
    """Przykład KPRM: L4 5-16.10.2026 i urlop 19.10-6.11.2026 to jedna nieobecność 5.10-6.11.2026."""
    okresy = scal_nieobecnosci_ciagle([
        Nieobecnosc(d(2026, 10, 5), d(2026, 10, 16), "zwolnienie lekarskie"),
        Nieobecnosc(d(2026, 10, 19), d(2026, 11, 6), "urlop wypoczynkowy"),
    ])
    assert okresy == [OkresNieobecnosci(d(2026, 10, 5), d(2026, 11, 6), 33)]


def test_nieobecnosc_z_przykladu_kprm_trwa_dluzej_niz_miesiac():
    assert czy_dluzsza_niz_miesiac(OkresNieobecnosci(d(2026, 10, 5), d(2026, 11, 6), 33)) is True


def test_dzien_roboczy_obecnosci_przerywa_ciaglosc_nieobecnosci():
    """Piątek 16.10.2026 w pracy - to dwie osobne nieobecności."""
    okresy = scal_nieobecnosci_ciagle([
        Nieobecnosc(d(2026, 10, 5), d(2026, 10, 15), "zwolnienie lekarskie"),
        Nieobecnosc(d(2026, 10, 19), d(2026, 11, 6), "urlop wypoczynkowy"),
    ])
    assert len(okresy) == 2


def test_swieto_miedzy_nieobecnosciami_nie_przerywa_ciaglosci():
    """11.11.2026 (środa, święto) między nieobecnościami do 10.11 i od 12.11."""
    okresy = scal_nieobecnosci_ciagle([
        Nieobecnosc(d(2026, 10, 12), d(2026, 11, 10)),
        Nieobecnosc(d(2026, 11, 12), d(2026, 11, 20)),
    ])
    assert okresy == [OkresNieobecnosci(d(2026, 10, 12), d(2026, 11, 20), 40)]


def test_ciaglosc_nie_zalezy_od_przyczyny_nieobecnosci():
    """Poradnik s. 12: urlop od 9.09.2014, potem L4 do 19.10.2014 - jedna nieobecność, 41 dni."""
    okresy = scal_nieobecnosci_ciagle([
        Nieobecnosc(d(2014, 9, 9), d(2014, 10, 13), "urlop wypoczynkowy"),
        Nieobecnosc(d(2014, 10, 14), d(2014, 10, 19), "zwolnienie lekarskie"),
    ])
    assert okresy == [OkresNieobecnosci(d(2014, 9, 9), d(2014, 10, 19), 41)]


def test_nieobecnosc_nieusprawiedliwiona_nie_jest_brana_pod_uwage():
    okresy = scal_nieobecnosci_ciagle([Nieobecnosc(d(2026, 1, 5), d(2026, 2, 27), usprawiedliwiona=False)])
    assert okresy == []


@pytest.mark.interpretacja
def test_nieobecnosc_rowna_dokladnie_miesiacowi_nie_jest_dluzsza_niz_miesiac():
    """Poradnik s. 12: miesiąc nieobecności rozpoczętej 9.09 upływa 9.10 - dopiero nieobecność
    obejmująca kolejny dzień jest „dłuższa niż miesiąc”. Do potwierdzenia z mentorami KPRM."""
    assert czy_dluzsza_niz_miesiac(OkresNieobecnosci(d(2026, 10, 5), d(2026, 11, 5), 32)) is False


def test_termin_przedluza_sie_o_wszystkie_dni_nieobecnosci_dluzszej_niz_miesiac():
    """Poradnik s. 11: 44 dni ciągłej nieobecności w XI-XII 2014 r. przedłużają termin o 44 dni."""
    nieobecnosci = [Nieobecnosc(d(2014, 11, 10), d(2014, 12, 23))]
    assert dni_przedluzenia_terminu(nieobecnosci, d(2013, 5, 8), d(2015, 5, 8)) == 44


def test_krotka_nieobecnosc_nie_przedluza_terminu():
    nieobecnosci = [Nieobecnosc(d(2014, 11, 10), d(2014, 11, 29))]
    assert dni_przedluzenia_terminu(nieobecnosci, d(2013, 5, 8), d(2015, 5, 8)) == 0


def test_kilka_dlugich_nieobecnosci_sumuje_sie():
    nieobecnosci = [
        Nieobecnosc(d(2025, 1, 6), d(2025, 2, 9)),   # 35 dni
        Nieobecnosc(d(2025, 9, 1), d(2025, 10, 10)),  # 40 dni
    ]
    assert dni_przedluzenia_terminu(nieobecnosci, d(2024, 6, 1), d(2026, 6, 1)) == 75


def test_nieobecnosc_poza_okresem_cyklu_nie_przedluza_terminu():
    nieobecnosci = [Nieobecnosc(d(2023, 1, 2), d(2023, 3, 31))]
    assert dni_przedluzenia_terminu(nieobecnosci, d(2024, 6, 1), d(2026, 6, 1)) == 0
