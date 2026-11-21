"""Wymaganie: obsługa sytuacji kadrowych zmieniających termin oceny.

Źródła: art. 81 ust. 6 i 8 u.s.c.; § 8 i § 9 rozp.; Poradnik KPRM 2016 s. 10-15; przypadki użycia
(„zmiana terminu oceny na wniosek ocenianego” - warunek brzegowy: „upłynęło 6 miesięcy od poprzedniej
oceny / nawiązania stosunku pracy na czas nieokreślony”); decyzje zespołu z 21.11.2026.
"""

import dataclasses

import pytest

from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.terminy import czy_dopuszczalna_zmiana_terminu, skutek_zmiany_stanowiska
from stale import d


# --- zmiana terminu (art. 81 ust. 8) ---

@pytest.mark.interpretacja
def test_zmiana_terminu_jest_niedopuszczalna_gdy_nie_uplynelo_wiecej_niz_6_miesiecy_od_ostatniej_oceny():
    """art. 81 ust. 8 in fine u.s.c. („upłynęło więcej niż 6 miesięcy”) w zw. z art. 112 KC."""
    assert czy_dopuszczalna_zmiana_terminu(d(2026, 7, 15), data_ostatniej_oceny=d(2026, 1, 15)) is False


@pytest.mark.interpretacja
def test_zmiana_terminu_jest_dopuszczalna_gdy_uplynelo_wiecej_niz_6_miesiecy_od_ostatniej_oceny():
    assert czy_dopuszczalna_zmiana_terminu(d(2026, 7, 16), data_ostatniej_oceny=d(2026, 1, 15)) is True


@pytest.mark.decyzja_projektowa
def test_przy_pierwszej_ocenie_6_miesiecy_liczy_sie_od_nawiazania_stosunku_pracy():
    """Decyzja zespołu z 21.11.2026, zgodna z warunkami brzegowymi przypadków użycia KPRM.
    Zatrudnienie 1.12.2025, kryteria 20.12.2025: 6 miesięcy od zatrudnienia upływa 1.06.2026."""
    daty = dict(data_nawiazania_stosunku_pracy=d(2025, 12, 1), data_zapoznania_z_kryteriami=d(2025, 12, 20))
    assert czy_dopuszczalna_zmiana_terminu(d(2026, 6, 1), **daty) is False
    assert czy_dopuszczalna_zmiana_terminu(d(2026, 6, 2), **daty) is True


def test_poczatek_6_miesiecy_przy_pierwszej_ocenie_mozna_przelaczyc_w_konfiguracji():
    """Alternatywa z Poradnika KPRM s. 10 i § 9 ust. 1 rozp.: od zapoznania z kryteriami
    (20.12.2025 -> 6 miesięcy upływa 20.06.2026)."""
    od_kryteriow = dataclasses.replace(wczytaj_przepisy(), pierwsza_ocena_6_miesiecy_od="zapoznanie_z_kryteriami")
    daty = dict(
        data_nawiazania_stosunku_pracy=d(2025, 12, 1),
        data_zapoznania_z_kryteriami=d(2025, 12, 20),
        przepisy=od_kryteriow,
    )
    assert czy_dopuszczalna_zmiana_terminu(d(2026, 6, 2), **daty) is False
    assert czy_dopuszczalna_zmiana_terminu(d(2026, 6, 21), **daty) is True


def test_bez_daty_poczatkowej_nie_da_sie_ocenic_dopuszczalnosci_zmiany_terminu():
    with pytest.raises(ValueError):
        czy_dopuszczalna_zmiana_terminu(d(2026, 6, 2))


# --- zmiana stanowiska (art. 81 ust. 6, § 9 rozp.) ---

@pytest.mark.interpretacja
def test_zmiana_stanowiska_z_istotna_zmiana_zakresu_po_6_miesiacach_wymaga_oceny():
    """art. 81 ust. 6 u.s.c., § 9 ust. 2 rozp.; Poradnik s. 10: zatrudnienie i rozmowa o kryteriach 15.05.2015,
    zmiana 28.11.2015 -> ocena nie wcześniej niż 7 dni przed zmianą i nie później niż 30 dni od zmiany.
    Granicę „7 dni przed” liczono wstecz od dnia zmiany (28.11 - 7 dni = 21.11.2015)."""
    skutek = skutek_zmiany_stanowiska(
        d(2015, 11, 28),
        istotna_zmiana_zakresu=True,
        data_nawiazania_stosunku_pracy=d(2015, 5, 15),
        data_zapoznania_z_kryteriami=d(2015, 5, 15),
    )
    assert skutek.wymagana_ocena is True
    assert skutek.ocena_najwczesniej == d(2015, 11, 21)
    assert skutek.ocena_najpozniej == d(2015, 12, 28)


@pytest.mark.decyzja_projektowa
def test_przy_pierwszej_ocenie_zmiana_stanowiska_liczy_6_miesiecy_od_nawiazania_stosunku_pracy():
    """Ten sam przełącznik co przy zmianie terminu. Zatrudnienie 2.02.2026, kryteria 27.02.2026, zmiana
    stanowiska 10.08.2026: od zatrudnienia upłynęło więcej niż 6 miesięcy (upływ 2.08.2026), więc ocena
    jest wymagana - najwcześniej 3.08.2026, najpóźniej 9.09.2026."""
    skutek = skutek_zmiany_stanowiska(
        d(2026, 8, 10),
        istotna_zmiana_zakresu=True,
        data_nawiazania_stosunku_pracy=d(2026, 2, 2),
        data_zapoznania_z_kryteriami=d(2026, 2, 27),
    )
    assert skutek.wymagana_ocena is True
    assert skutek.ocena_najwczesniej == d(2026, 8, 3)
    assert skutek.ocena_najpozniej == d(2026, 9, 9)


def test_zmiana_stanowiska_przed_uplywem_6_miesiecy_wymaga_ponownego_ustalenia_kryteriow_w_30_dni():
    """§ 9 ust. 1 rozp.: ponownie rozmowa i kryteria w 30 dni od zmiany; termin oceny bez zmian."""
    skutek = skutek_zmiany_stanowiska(
        d(2026, 7, 15), istotna_zmiana_zakresu=True, data_ostatniej_oceny=d(2026, 3, 2)
    )
    assert skutek.wymagana_ocena is False
    assert skutek.ponowne_kryteria_do == d(2026, 8, 14)
    assert skutek.termin_oceny_bez_zmian is True


def test_zmiana_stanowiska_bez_istotnej_zmiany_zakresu_obowiazkow_nie_ma_skutkow():
    """art. 81 ust. 6 u.s.c. i § 9 ust. 1-2 rozp. dotyczą wyłącznie zmiany stanowiska „wiążącej się z istotną
    zmianą zakresu obowiązków”; por. Poradnik s. 10 (powierzenie innej pracy z art. 42 § 4 KP to nie zmiana stanowiska)."""
    skutek = skutek_zmiany_stanowiska(
        d(2026, 7, 15), istotna_zmiana_zakresu=False, data_ostatniej_oceny=d(2025, 3, 2)
    )
    assert skutek.wymagana_ocena is False
    assert skutek.ponowne_kryteria_do is None
    assert skutek.termin_oceny_bez_zmian is True
