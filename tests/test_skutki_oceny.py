"""Wymaganie: asystent wskazuje skutki oceny (zadania, terminy, ryzyka) - wsparcie kadr i HR partnera.

Źródła: art. 71 ust. 1 pkt 1, art. 81 ust. 4 i 9, art. 89 ust. 2, art. 108 u.s.c.; § 7 rozp.;
Poradnik KPRM s. 34-35 („Konsekwencje oceny okresowej”).
"""

from asystent_ocen.skutki import skutki_oceny
from asystent_ocen.stopnie import OcenaHistoryczna
from asystent_ocen.wynik import NEGATYWNA, POZYTYWNA
from stale import d


def po_kodzie(skutki):
    return {s.kod: s for s in skutki}


def test_ocena_negatywna_uruchamia_ponowna_ocene_po_6_miesiacach():
    """art. 81 ust. 9 u.s.c.; zapoznanie 15.02.2015 -> 16.08.2015 (niedziela) -> dzień roboczy 17.08.2015
    (decyzja zespołu z 21.11.2026; Poradnik s. 13 podaje 16.08.2015)."""
    skutki = po_kodzie(skutki_oceny(
        ocena=NEGATYWNA, poziom="poniżej oczekiwań", urzednik=False,
        data_sporzadzenia=d(2015, 2, 13), data_zapoznania=d(2015, 2, 15),
    ))
    assert skutki["PONOWNA_OCENA"].termin == d(2015, 8, 17)


def test_po_ocenie_negatywnej_nowe_kryteria_trzeba_ustalic_w_7_dni():
    """§ 7 pkt 2 rozp.: sporządzenie 16.11.2026 -> 23.11.2026."""
    skutki = po_kodzie(skutki_oceny(
        ocena=NEGATYWNA, poziom="poniżej oczekiwań", urzednik=False,
        data_sporzadzenia=d(2026, 11, 16), data_zapoznania=d(2026, 11, 17),
    ))
    assert skutki["NOWE_KRYTERIA"].termin == d(2026, 11, 23)


def test_po_ocenie_pozytywnej_kolejna_ocena_za_24_miesiace_a_kryteria_w_30_dni():
    """art. 81 ust. 4 u.s.c. i § 7 pkt 1 rozp.: sporządzenie 15.04.2026 -> kryteria do 15.05.2026,
    kolejna ocena 15.04.2028 (sobota); 16.04 to Wielkanoc, 17.04 Poniedziałek Wielkanocny -> 18.04.2028."""
    skutki = po_kodzie(skutki_oceny(
        ocena=POZYTYWNA, poziom="na poziomie oczekiwań", urzednik=False,
        data_sporzadzenia=d(2026, 4, 15), data_zapoznania=d(2026, 4, 16),
    ))
    assert skutki["NOWE_KRYTERIA"].termin == d(2026, 5, 15)
    assert skutki["TERMIN_KOLEJNEJ_OCENY"].termin == d(2028, 4, 18)
    assert "PONOWNA_OCENA" not in skutki


def test_druga_kolejna_ocena_negatywna_urzednika_sygnalizuje_rozwiazanie_stosunku_pracy():
    """art. 71 ust. 1 pkt 1 u.s.c. - dwukrotna, następująca po sobie negatywna ocena."""
    skutki = po_kodzie(skutki_oceny(
        ocena=NEGATYWNA, poziom="poniżej oczekiwań", urzednik=True,
        data_sporzadzenia=d(2026, 11, 16), data_zapoznania=d(2026, 11, 17), poprzednia_ocena=NEGATYWNA,
    ))
    assert "ROZWIAZANIE_STOSUNKU_PRACY" in skutki


def test_pierwsza_ocena_negatywna_urzednika_nie_sygnalizuje_rozwiazania_stosunku_pracy():
    skutki = po_kodzie(skutki_oceny(
        ocena=NEGATYWNA, poziom="poniżej oczekiwań", urzednik=True,
        data_sporzadzenia=d(2026, 11, 16), data_zapoznania=d(2026, 11, 17), poprzednia_ocena=POZYTYWNA,
    ))
    assert "ROZWIAZANIE_STOSUNKU_PRACY" not in skutki


def test_art_71_nie_dotyczy_pracownika_sluzby_cywilnej():
    """art. 71 u.s.c. reguluje stosunek pracy urzędnika służby cywilnej."""
    skutki = po_kodzie(skutki_oceny(
        ocena=NEGATYWNA, poziom="poniżej oczekiwań", urzednik=False,
        data_sporzadzenia=d(2026, 11, 16), data_zapoznania=d(2026, 11, 17), poprzednia_ocena=NEGATYWNA,
    ))
    assert "ROZWIAZANIE_STOSUNKU_PRACY" not in skutki


def test_spelnienie_warunkow_art_89_ust_2_tworzy_zadanie_przyznania_stopnia_dla_kadr():
    historia = [
        OcenaHistoryczna(d(2024, 11, 18), POZYTYWNA, "powyżej oczekiwań"),
        OcenaHistoryczna(d(2026, 11, 20), POZYTYWNA, "znacznie powyżej oczekiwań"),
    ]
    skutki = po_kodzie(skutki_oceny(
        ocena=POZYTYWNA, poziom="znacznie powyżej oczekiwań", urzednik=True,
        data_sporzadzenia=d(2026, 11, 19), data_zapoznania=d(2026, 11, 20),
        historia_od_ostatniego_stopnia=historia, data_ostatniego_stopnia=d(2023, 1, 2),
    ))
    assert skutki["STOPIEN_OBLIGATORYJNY"].termin == d(2026, 12, 21)


def test_kazda_ocena_konczy_sie_zadaniem_przygotowania_iprz():
    """art. 108 u.s.c. - IPRZ uwzględnia wnioski z oceny; przepisy nie określają terminu (Poradnik s. 34)."""
    for ocena, poziom in [(POZYTYWNA, "na poziomie oczekiwań"), (NEGATYWNA, "poniżej oczekiwań")]:
        skutki = po_kodzie(skutki_oceny(
            ocena=ocena, poziom=poziom, urzednik=False,
            data_sporzadzenia=d(2026, 4, 15), data_zapoznania=d(2026, 4, 16),
        ))
        assert "IPRZ" in skutki
        assert skutki["IPRZ"].termin is None
