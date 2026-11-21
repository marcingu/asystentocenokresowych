"""Wymaganie: minimalizacja błędów formalnych - blokada zatwierdzenia niekompletnej oceny.

Źródła: art. 81 ust. 5 i art. 89 ust. 1 u.s.c.; § 11 ust. 1 pkt 5, ust. 3-5 rozp.; przypisy do części II
i III arkusza; schematy pól formularza A/B/C (KPRM) - „system przypomina o obowiązku uzupełnienia pola
i blokuje zatwierdzenie”.
"""

import pytest

from asystent_ocen.walidacja import (
    NIE,
    NIE_DOTYCZY,
    TAK,
    Formularz,
    bledy_przed_zatwierdzeniem,
    czy_aktywna_sekcja_poprzedniej_oceny,
    czy_drukowac_czesc_III,
    domyslna_odpowiedz_o_wniosek,
    pouczenie_o_sprzeciwie,
)
from asystent_ocen.wynik import NEGATYWNA, POZYTYWNA
from stale import OBOWIAZKOWE_C


def kody(formularz):
    return {b.kod for b in bledy_przed_zatwierdzeniem(formularz)}


def formularz(oceny_c, **pola):
    dane = dict(arkusz="C", urzednik=False, oceny=dict(zip(OBOWIAZKOWE_C, oceny_c)), wnioski_iprz="Szkolenie z X.")
    dane.update(pola)
    return Formularz(**dane)


POZYTYWNE = [5, 7, 5, 5, 5]
NEGATYWNE = [5, 1, 5, 5, 5]


def test_poprawny_formularz_mozna_zatwierdzic():
    assert kody(formularz(POZYTYWNE, wniosek_o_stopien=NIE_DOTYCZY)) == set()


def test_ocena_negatywna_wymaga_uzasadnienia():
    """§ 11 ust. 3 rozp.; schemat pól: blokada zatwierdzenia do czasu uzupełnienia uzasadnienia."""
    assert "BRAK_UZASADNIENIA_NEGATYWNEJ" in kody(formularz(NEGATYWNE, uzasadnienie=""))


def test_uzasadnienie_samych_spacji_nie_jest_uzasadnieniem():
    assert "BRAK_UZASADNIENIA_NEGATYWNEJ" in kody(formularz(NEGATYWNE, uzasadnienie="   "))


def test_ocena_pozytywna_nie_wymaga_uzasadnienia():
    """§ 11 ust. 4 rozp. - uzasadnienie oceny pozytywnej jest fakultatywne."""
    assert "BRAK_UZASADNIENIA_NEGATYWNEJ" not in kody(formularz(POZYTYWNE, uzasadnienie=""))


def test_kazda_ocena_wymaga_wnioskow_do_iprz():
    """art. 81 ust. 5 u.s.c.; § 11 ust. 1 pkt 5 rozp."""
    assert "BRAK_WNIOSKOW_IPRZ" in kody(formularz(POZYTYWNE, wnioski_iprz=""))


def test_wniosek_o_stopien_nie_dotyczy_pracownika_sluzby_cywilnej():
    assert "WNIOSEK_O_STOPIEN_NIE_DLA_PRACOWNIKA" in kody(
        formularz(POZYTYWNE, urzednik=False, wniosek_o_stopien=TAK, umotywowanie_wniosku="Bardzo dobre wyniki.")
    )


def test_wniosek_o_stopien_jest_niedozwolony_przy_ocenie_negatywnej():
    """§ 11 ust. 5 rozp.; art. 89 ust. 1 u.s.c."""
    assert "WNIOSEK_O_STOPIEN_PRZY_NEGATYWNEJ" in kody(
        formularz(NEGATYWNE, urzednik=True, uzasadnienie="Uzasadnienie.", wniosek_o_stopien=TAK,
                  umotywowanie_wniosku="x", posiadany_stopien=2)
    )


def test_wniosek_o_stopien_wymaga_umotywowania():
    """art. 89 ust. 1 u.s.c. - „umotywowany wniosek”; schemat pól części III."""
    assert "BRAK_UMOTYWOWANIA_WNIOSKU" in kody(
        formularz(POZYTYWNE, urzednik=True, wniosek_o_stopien=TAK, umotywowanie_wniosku="", posiadany_stopien=2)
    )


def test_wniosek_o_stopien_jest_niedozwolony_przy_dziewiatym_stopniu():
    assert "NAJWYZSZY_STOPIEN" in kody(
        formularz(POZYTYWNE, urzednik=True, wniosek_o_stopien=TAK, umotywowanie_wniosku="x", posiadany_stopien=9)
    )


def test_blad_w_ocenach_czastkowych_blokuje_zatwierdzenie():
    """Walidacja formularza obejmuje kompletność i skalę ocen cząstkowych."""
    assert "OCENA_SPOZA_SKALI" in kody(formularz([5, 5, 5, 5, 4]))


# --- wartości domyślne i widoczność sekcji (schematy pól formularza KPRM) ---

@pytest.mark.parametrize(
    "urzednik, ocena, oczekiwana",
    [(False, POZYTYWNA, NIE_DOTYCZY), (False, NEGATYWNA, NIE_DOTYCZY), (True, NEGATYWNA, NIE), (True, POZYTYWNA, None)],
)
def test_domyslna_odpowiedz_na_pytanie_o_wniosek_o_stopien(urzednik, ocena, oczekiwana):
    assert domyslna_odpowiedz_o_wniosek(urzednik=urzednik, ocena=ocena) == oczekiwana


@pytest.mark.parametrize(
    "urzednik, wniosek, drukowac",
    [(False, NIE_DOTYCZY, False), (True, NIE, False), (True, TAK, True)],
)
def test_czesc_iii_drukuje_sie_tylko_przy_wniosku_dla_urzednika(urzednik, wniosek, drukowac):
    """Przypis do części III arkusza: nie drukuje się jej dla pracownika SC i przy braku wniosku."""
    assert czy_drukowac_czesc_III(urzednik=urzednik, wniosek_o_stopien=wniosek) is drukowac


def test_dane_o_poprzedniej_ocenie_dotycza_tylko_urzednika():
    assert czy_aktywna_sekcja_poprzedniej_oceny(urzednik=True) is True
    assert czy_aktywna_sekcja_poprzedniej_oceny(urzednik=False) is False


# --- pouczenie o sprzeciwie ---

@pytest.mark.parametrize("arkusz", ["B", "C"])
def test_pouczenie_w_arkuszach_b_i_c_wskazuje_dyrektora_generalnego(arkusz):
    assert pouczenie_o_sprzeciwie(arkusz).endswith("sprzeciw do dyrektora generalnego urzędu.")


def test_w_urzedzie_bez_dyrektora_generalnego_sprzeciw_kieruje_sie_do_kierownika_urzedu():
    """Przypis 17 do arkuszy B i C."""
    assert "kierownika urzędu" in pouczenie_o_sprzeciwie("C", urzad_ma_dyrektora_generalnego=False)


def test_w_arkuszu_a_adresata_sprzeciwu_wpisuje_oceniajacy():
    """Schemat pól arkusza A: pole adresata sprzeciwu do wypełnienia przez oceniającego."""
    assert pouczenie_o_sprzeciwie("A", adresat="Organu X").endswith("sprzeciw do Organu X.")
