"""Wymaganie: automatyczne wyliczanie terminów oceny i wyznaczenia kryteriów.

Źródła: art. 81 ust. 4, 7, 9 u.s.c.; § 7 rozp.; Poradnik KPRM 2016 s. 8-14; przypisy 6 i 7 do części II
arkusza (wzór B - zał. nr 3 do rozp.); schemat pól formularza („Termin sporządzenia oceny” wyliczany
domyślnie wg kalendarza - 24 miesiące od początku cyklu).
"""

import dataclasses

import pytest

from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.nieobecnosci import Nieobecnosc
from asystent_ocen.terminy import (
    data_ponownej_oceny_po_negatywnej,
    okres_podlegania_ocenie,
    termin_oceny,
    termin_wyznaczenia_kryteriow,
)
from stale import d


def test_ocene_sporzadza_sie_co_24_miesiace_od_poprzedniej_oceny():
    """art. 81 ust. 4 u.s.c.; Poradnik s. 9: poprzednia ocena 4.12.2013 -> termin 4.12.2015."""
    assert termin_oceny(d(2013, 12, 4)) == d(2015, 12, 4)


def test_termin_oceny_przypadajacy_w_sobote_przesuwa_sie_na_poniedzialek():
    """art. 115 KC: 21.11.2024 + 24 miesiące = sobota 21.11.2026 -> 23.11.2026."""
    assert termin_oceny(d(2024, 11, 21)) == d(2026, 11, 23)


def test_dluga_nieobecnosc_przedluza_termin_oceny_o_czas_nieobecnosci():
    """art. 81 ust. 7 u.s.c.; Poradnik s. 11: termin 8.05.2015 + 44 dni = 21.06.2015 (niedziela) -> 22.06.2015.
    Poradnik podaje tylko „XI-XII 2014 r., łącznie 44 dni, nieobecność ciągła” - daty 10.11-23.12.2014 przyjęto."""
    nieobecnosc = [Nieobecnosc(d(2014, 11, 10), d(2014, 12, 23), "zwolnienie lekarskie")]
    assert termin_oceny(d(2013, 5, 8), nieobecnosci=nieobecnosc) == d(2015, 6, 22)


def test_krotka_nieobecnosc_nie_zmienia_terminu_oceny():
    nieobecnosc = [Nieobecnosc(d(2014, 11, 10), d(2014, 11, 29))]
    assert termin_oceny(d(2013, 5, 8), nieobecnosci=nieobecnosc) == d(2015, 5, 8)


def test_nieobecnosc_przed_zapoznaniem_z_kryteriami_tez_przedluza_termin():
    """Poradnik s. 12: przedłużenie dotyczy także nieobecności między początkiem obowiązku oceny
    a zapoznaniem z kryteriami. Zatrudnienie 2.03.2026, nieobecność 3.03-2.06.2026 (92 dni):
    2.03.2028 + 92 dni = 2.06.2028 (piątek)."""
    nieobecnosc = [Nieobecnosc(d(2026, 3, 3), d(2026, 6, 2), "urlop macierzyński")]
    assert termin_oceny(d(2026, 3, 2), nieobecnosci=nieobecnosc) == d(2028, 6, 2)


@pytest.mark.decyzja_projektowa
def test_ponowna_ocena_po_negatywnej_przypada_w_pierwszym_dniu_roboczym_po_uplywie_6_miesiecy():
    """art. 81 ust. 9 u.s.c.; decyzja zespołu z 21.11.2026: ponowna ocena w dniu roboczym.
    Zapoznanie 15.02.2015 -> 6 miesięcy upływa 15.08.2015 -> 16.08.2015 to niedziela -> 17.08.2015 (poniedziałek).
    Poradnik KPRM s. 13 podaje dla tego przykładu 16.08.2015 (bez przesunięcia)."""
    assert data_ponownej_oceny_po_negatywnej(d(2015, 2, 15)) == d(2015, 8, 17)


def test_ponowna_ocena_po_negatywnej_w_dniu_roboczym_nie_jest_przesuwana():
    """Zapoznanie 17.11.2026 -> 6 miesięcy upływa 17.05.2027 -> 18.05.2027 (wtorek)."""
    assert data_ponownej_oceny_po_negatywnej(d(2026, 11, 17)) == d(2027, 5, 18)


def test_przesuniecie_ponownej_oceny_na_dzien_roboczy_mozna_wylaczyc_w_konfiguracji():
    """Przełącznik `ponowna_ocena_w_dniu_roboczym = false` daje datę z Poradnika KPRM s. 13: 16.08.2015."""
    bez_przesuniecia = dataclasses.replace(wczytaj_przepisy(), ponowna_ocena_w_dniu_roboczym=False)
    assert data_ponownej_oceny_po_negatywnej(d(2015, 2, 15), przepisy=bez_przesuniecia) == d(2015, 8, 16)


def test_termin_ponownej_oceny_po_negatywnej_nie_przedluza_sie_o_nieobecnosc():
    """Poradnik s. 14: art. 81 ust. 7 dotyczy wyłącznie terminu z ust. 4 (24 miesiące)."""
    nieobecnosc = [Nieobecnosc(d(2015, 3, 2), d(2015, 5, 29), "zwolnienie lekarskie")]
    assert data_ponownej_oceny_po_negatywnej(d(2015, 2, 15), nieobecnosci=nieobecnosc) == d(2015, 8, 17)


def test_kryteria_wyznacza_sie_w_30_dni_od_poczatku_cyklu():
    """§ 7 pkt 1 rozp.; Poradnik s. 9: zatrudnienie 4.09.2015 -> do 4.10.2015 (niedziela) -> 5.10.2015."""
    assert termin_wyznaczenia_kryteriow(d(2015, 9, 4)) == d(2015, 10, 5)


def test_po_ocenie_negatywnej_kryteria_wyznacza_sie_w_7_dni():
    """§ 7 pkt 2 rozp.: negatywna ocena sporządzona 16.11.2026 -> kryteria do 23.11.2026."""
    assert termin_wyznaczenia_kryteriow(d(2026, 11, 16), po_negatywnej=True) == d(2026, 11, 23)


def test_okres_oceny_trwa_od_zapoznania_z_kryteriami_do_sporzadzenia_oceny():
    """Przypisy 6 i 7 do części II arkusza B. Przykładowy arkusz B z Poradnika (naczelnik wydziału):
    okres od 24.08.2016 r. do 22.08.2018 r."""
    assert okres_podlegania_ocenie(d(2016, 8, 24), d(2018, 8, 22)) == (d(2016, 8, 24), d(2018, 8, 22))


def test_okres_oceny_przy_zmianie_stanowiska_konczy_sie_ostatnim_dniem_na_stanowisku():
    """Przypis 7 do części II arkusza B (art. 81 ust. 6 u.s.c.): ocena niesporządzona przed zmianą
    stanowiska - w polu „do” wpisuje się ostatni dzień pracy na zajmowanym stanowisku."""
    assert okres_podlegania_ocenie(
        d(2025, 3, 10), d(2026, 2, 20), ostatni_dzien_na_stanowisku=d(2026, 1, 31)
    ) == (d(2025, 3, 10), d(2026, 1, 31))
