"""Wymaganie: terminy liczone zgodnie z Kodeksem cywilnym (art. 111, 112, 115 KC).

Źródła: dokument KPRM „liczenie terminów” (materiały dodatkowe), Poradnik KPRM „Oceny okresowe
w służbie cywilnej” (2016), s. 8-9.
"""

import pytest

from asystent_ocen.kalendarz import (
    dodaj_miesiace,
    koniec_terminu_dni,
    koniec_terminu_miesiecy,
    przesun_na_dzien_roboczy,
    uplynelo_wiecej_niz_miesiecy,
)
from stale import d


@pytest.mark.parametrize(
    "poczatek, miesiace, koniec, zrodlo",
    [
        (d(2024, 3, 16), 24, d(2026, 3, 16), "KPRM liczenie terminów: 24 miesiące od 16.03.2024"),
        (d(2024, 1, 31), 13, d(2025, 2, 28), "KPRM liczenie terminów: brak 31 lutego -> ostatni dzień miesiąca"),
        (d(2024, 1, 31), 1, d(2024, 2, 29), "KPRM liczenie terminów: rok przestępny"),
        (d(2013, 12, 4), 24, d(2015, 12, 4), "Poradnik KPRM s. 9"),
        (d(2026, 11, 30), 3, d(2027, 2, 28), "art. 112 KC - brak 30 lutego"),
    ],
)
def test_termin_w_miesiacach_konczy_sie_w_dniu_odpowiadajacym_dniowi_poczatkowemu(poczatek, miesiace, koniec, zrodlo):
    """art. 112 KC"""
    assert dodaj_miesiace(poczatek, miesiace) == koniec, zrodlo


def test_termin_w_dniach_nie_obejmuje_dnia_zdarzenia_i_konczy_sie_w_dniu_roboczym():
    """Poradnik KPRM s. 9: zatrudnienie 4.09.2015 + 30 dni = 4.10.2015 (niedziela) -> 5.10.2015."""
    assert koniec_terminu_dni(d(2015, 9, 4), 30) == d(2015, 10, 5)


def test_dni_wolne_w_srodku_terminu_wliczaja_sie_do_jego_biegu():
    """Poradnik KPRM s. 9: dni wolne w środku terminu są liczone do biegu terminu."""
    # 2.11.2026 (pon.) + 7 dni = 9.11.2026 (pon.) - weekend 7-8.11 nie wydłuża terminu
    assert koniec_terminu_dni(d(2026, 11, 2), 7) == d(2026, 11, 9)


@pytest.mark.parametrize(
    "koniec, po_przesunieciu, opis",
    [
        (d(2026, 11, 21), d(2026, 11, 23), "sobota -> poniedziałek (art. 115 KC)"),
        (d(2015, 6, 21), d(2015, 6, 22), "niedziela -> poniedziałek (Poradnik KPRM s. 11)"),
        (d(2026, 11, 11), d(2026, 11, 12), "Narodowe Święto Niepodległości (środa) -> czwartek"),
        (d(2026, 6, 4), d(2026, 6, 5), "Boże Ciało (czwartek) -> piątek"),
        (d(2026, 4, 6), d(2026, 4, 7), "Drugi dzień Wielkiej Nocy -> wtorek"),
        (d(2026, 1, 6), d(2026, 1, 7), "Święto Trzech Króli -> środa"),
        (d(2026, 12, 24), d(2026, 12, 28), "Wigilia, dwa dni świąt (26.12 to sobota) i niedziela -> poniedziałek"),
        (d(2026, 11, 20), d(2026, 11, 20), "piątek roboczy - bez zmian"),
    ],
)
def test_koniec_terminu_w_dzien_wolny_lub_sobote_przesuwa_sie_na_nastepny_dzien_roboczy(koniec, po_przesunieciu, opis):
    """art. 115 KC; dokument KPRM „liczenie terminów”."""
    assert przesun_na_dzien_roboczy(koniec) == po_przesunieciu, opis


def test_koniec_terminu_miesiecznego_tez_przesuwa_sie_z_soboty():
    """art. 112 + art. 115 KC: 21.11.2024 + 24 miesiące = 21.11.2026 (sobota) -> 23.11.2026."""
    assert koniec_terminu_miesiecy(d(2024, 11, 21), 24) == d(2026, 11, 23)


@pytest.mark.interpretacja
def test_szesc_miesiecy_uplywa_z_koncem_dnia_odpowiadajacego_dniowi_poczatkowemu():
    """art. 81 ust. 8 u.s.c. („upłynęło więcej niż 6 miesięcy”) w związku z art. 112 KC:
    od 15.01.2026 sześć miesięcy upływa z końcem 15.07.2026, więc „więcej niż” dopiero 16.07.2026."""
    assert uplynelo_wiecej_niz_miesiecy(d(2026, 1, 15), d(2026, 7, 15), 6) is False
    assert uplynelo_wiecej_niz_miesiecy(d(2026, 1, 15), d(2026, 7, 16), 6) is True
