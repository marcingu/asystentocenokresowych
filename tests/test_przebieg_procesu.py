"""Wymaganie: proces oceny prowadzony krok po kroku, z rolami i blokadą pól po zatwierdzeniu.

Źródła: przypadki użycia KPRM (opis, warunki brzegowe, diagram A3); model BPMN KPRM (tory:
ZARZĄDZAJĄCY, OCENIAJĄCY, OCENIANY, ADMIN, SCHEDULER); schematy pól formularza („zablokowane do edycji
/do zmiany wyłącznie w trybie korekty błędów przez administratora/”); § 5, § 6, § 8, § 9 ust. 3, § 12 rozp.;
art. 83 ust. 4 u.s.c.; Poradnik KPRM s. 32 (uwzględnienie sprzeciwu nie może pogorszyć oceny).
"""

import pytest

from asystent_ocen.bledy import BladWalidacji
from asystent_ocen.przebieg import BladEtapu, BladUprawnien, Etap, ProcesOceny, Rola
from asystent_ocen.wynik import POZYTYWNA
from stale import OBOWIAZKOWE_C, d

OCENY_POZYTYWNE = dict(zip(OBOWIAZKOWE_C, [5, 7, 5, 5, 5]))
OCENY_NEGATYWNE = dict(zip(OBOWIAZKOWE_C, [5, 1, 5, 5, 5]))


def nowy_proces():
    return ProcesOceny(arkusz="C", urzednik=False, poczatek_cyklu=d(2026, 1, 12))


def proces_z_potwierdzonymi_kryteriami():
    p = nowy_proces()
    p.wyznacz_kryteria(Rola.OCENIAJACY, [], termin=d(2028, 1, 12), data=d(2026, 1, 20))
    p.potwierdz_kryteria(Rola.OCENIANY, data=d(2026, 1, 21))
    return p


def proces_z_ocena(oceny=OCENY_POZYTYWNE, uzasadnienie=""):
    p = proces_z_potwierdzonymi_kryteriami()
    p.sporzadz_ocene(Rola.OCENIAJACY, data=d(2028, 1, 10), data_rozmowy=d(2028, 1, 5), oceny=oceny,
                     wnioski_iprz="Szkolenie z analizy danych.", uzasadnienie=uzasadnienie)
    return p


# --- etap I: kryteria ---

def test_nowy_proces_zaczyna_sie_od_wyznaczenia_kryteriow():
    assert nowy_proces().etap == Etap.KRYTERIA_DO_WYZNACZENIA


def test_kryteria_wyznacza_wylacznie_oceniajacy():
    """Warunki brzegowe: „wprowadza OCENIAJĄCY”."""
    with pytest.raises(BladUprawnien):
        nowy_proces().wyznacz_kryteria(Rola.OCENIANY, [], termin=d(2028, 1, 12), data=d(2026, 1, 20))


def test_wyznaczenie_kryteriow_przekazuje_je_ocenianemu_do_potwierdzenia():
    p = nowy_proces()
    p.wyznacz_kryteria(Rola.OCENIAJACY, ["Kreatywność"], termin=d(2028, 1, 12), data=d(2026, 1, 20))
    assert p.etap == Etap.KRYTERIA_DO_POTWIERDZENIA


def test_odbycie_rozmowy_i_zapoznanie_z_kryteriami_potwierdza_wylacznie_oceniany():
    """§ 6 ust. 2 rozp.; warunki brzegowe: „potwierdza OCENIANY”."""
    p = nowy_proces()
    p.wyznacz_kryteria(Rola.OCENIAJACY, [], termin=d(2028, 1, 12), data=d(2026, 1, 20))
    with pytest.raises(BladUprawnien):
        p.potwierdz_kryteria(Rola.OCENIAJACY, data=d(2026, 1, 21))


def test_potwierdzenie_kryteriow_rozpoczyna_okres_oceny():
    """Przypis 5 do części II arkusza: data „od” = data zapoznania z kryteriami."""
    p = proces_z_potwierdzonymi_kryteriami()
    assert p.etap == Etap.OCENIANIE
    assert p.data_zapoznania_z_kryteriami == d(2026, 1, 21)


def test_po_potwierdzeniu_kryteria_sa_zablokowane_do_edycji():
    with pytest.raises(BladEtapu):
        proces_z_potwierdzonymi_kryteriami().zmien_kryteria(Rola.OCENIAJACY, ["Kreatywność"])


def test_administrator_moze_poprawic_kryteria_w_trybie_korekty_bledow():
    p = proces_z_potwierdzonymi_kryteriami()
    p.zmien_kryteria(Rola.ADMIN, ["Kreatywność"], tryb_korekty=True)
    assert p.kryteria_dodatkowe == ["Kreatywność"]


def test_wybor_kryteriow_niezgodny_z_rozporzadzeniem_jest_odrzucany():
    with pytest.raises(BladWalidacji) as blad:
        nowy_proces().wyznacz_kryteria(
            Rola.OCENIAJACY, ["Kreatywność", "Negocjowanie", "Myślenie analityczne", "Wystąpienia publiczne"],
            termin=d(2028, 1, 12), data=d(2026, 1, 20),
        )
    assert "ZA_DUZO_KRYTERIOW_DODATKOWYCH" in blad.value.kody


# --- sytuacje kadrowe w trakcie okresu oceny ---

def test_zmiana_terminu_przez_oceniajacego_tworzy_pisemne_zawiadomienie_dla_ocenianego():
    """§ 8 rozp.: zawiadomienie pisemne o nowym terminie, kopia dołączana do arkusza."""
    p = proces_z_potwierdzonymi_kryteriami()
    p.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="zmiana oceniającego")
    assert p.termin == d(2027, 9, 1)
    assert any(dok.adresat == Rola.OCENIANY and "termin" in dok.rodzaj for dok in p.dokumenty)


def test_wniosek_ocenianego_o_zmiane_terminu_przed_uplywem_6_miesiecy_jest_odrzucany():
    """art. 81 ust. 8 pkt 4 in fine u.s.c.; warunki brzegowe przypadków użycia."""
    p = proces_z_potwierdzonymi_kryteriami()
    with pytest.raises(BladWalidacji):
        p.zloz_wniosek_o_zmiane_terminu(Rola.OCENIANY, data=d(2026, 5, 4), data_ostatniej_oceny=d(2026, 1, 12))


@pytest.mark.decyzja_projektowa
def test_przy_pierwszej_ocenie_wniosek_o_zmiane_terminu_liczy_6_miesiecy_od_poczatku_cyklu():
    """Decyzja zespołu z 21.11.2026: przy pierwszej ocenie 6 miesięcy liczy się od nawiązania stosunku pracy
    (początek cyklu 12.01.2026 -> 6 miesięcy upływa 12.07.2026, wniosek dopuszczalny od 13.07.2026)."""
    p = proces_z_potwierdzonymi_kryteriami()
    with pytest.raises(BladWalidacji):
        p.zloz_wniosek_o_zmiane_terminu(Rola.OCENIANY, data=d(2026, 7, 12))


def test_dopuszczalny_wniosek_o_zmiane_terminu_trafia_do_oceniajacego():
    """Warunki brzegowe przypadków użycia: wniosek składa OCENIANY, rozpatruje OCENIAJĄCY."""
    p = proces_z_potwierdzonymi_kryteriami()
    p.zloz_wniosek_o_zmiane_terminu(Rola.OCENIANY, data=d(2026, 7, 13))
    assert any(dok.adresat == Rola.OCENIAJACY and "wniosek" in dok.rodzaj for dok in p.dokumenty)


def test_wniosek_o_zmiane_terminu_sklada_wylacznie_oceniany():
    p = proces_z_potwierdzonymi_kryteriami()
    with pytest.raises(BladUprawnien):
        p.zloz_wniosek_o_zmiane_terminu(Rola.OCENIAJACY, data=d(2026, 7, 13))


def test_zmiana_oceniajacego_nie_zmienia_wybranych_kryteriow():
    """§ 9 ust. 3 rozp.: ocena sporządzana na podstawie wybranych wcześniej kryteriów."""
    p = nowy_proces()
    p.wyznacz_kryteria(Rola.OCENIAJACY, ["Kreatywność"], termin=d(2028, 1, 12), data=d(2026, 1, 20))
    p.potwierdz_kryteria(Rola.OCENIANY, data=d(2026, 1, 21))
    p.zmien_oceniajacego(Rola.ZARZADZAJACY, data=d(2027, 2, 1))
    assert p.kryteria_dodatkowe == ["Kreatywność"]


# --- notatki z obserwacji ---

def test_oceniajacy_zapisuje_notatki_z_obserwacji_wykorzystywane_przed_rozmowa_oceniajaca():
    """Treść wyzwania: zapisywanie notatek i obserwacji w okresie oceny (co do zasady 24 miesiące)."""
    p = proces_z_potwierdzonymi_kryteriami()
    p.dodaj_notatke(Rola.OCENIAJACY, "Terminowo przygotował raport roczny.", data=d(2026, 6, 30))
    p.dodaj_notatke(Rola.OCENIAJACY, "Notatka sprzed okresu oceny.", data=d(2025, 12, 1))
    notatki = p.notatki_z_okresu(Rola.OCENIAJACY, od=d(2026, 1, 21), do=d(2028, 1, 12))
    assert [n.tresc for n in notatki] == ["Terminowo przygotował raport roczny."]


@pytest.mark.decyzja_projektowa
def test_oceniany_nie_ma_wgladu_w_robocze_notatki_oceniajacego():
    """Decyzja zespołu z 21.11.2026: oceniany nie widzi notatek przełożonego (nie są częścią arkusza)."""
    p = proces_z_potwierdzonymi_kryteriami()
    with pytest.raises(BladUprawnien):
        p.notatki_z_okresu(Rola.OCENIANY, od=d(2026, 1, 21), do=d(2028, 1, 12))


# --- etap II: ocena ---

def test_nie_mozna_sporzadzic_oceny_przed_potwierdzeniem_kryteriow():
    p = nowy_proces()
    with pytest.raises(BladEtapu):
        p.sporzadz_ocene(Rola.OCENIAJACY, data=d(2028, 1, 10), data_rozmowy=d(2028, 1, 5),
                         oceny=OCENY_POZYTYWNE, wnioski_iprz="x")


def test_ocene_sporzadza_wylacznie_oceniajacy():
    p = proces_z_potwierdzonymi_kryteriami()
    with pytest.raises(BladUprawnien):
        p.sporzadz_ocene(Rola.OCENIANY, data=d(2028, 1, 10), data_rozmowy=d(2028, 1, 5),
                         oceny=OCENY_POZYTYWNE, wnioski_iprz="x")


def test_sporzadzenie_oceny_wylicza_wynik_i_przekazuje_ja_do_zapoznania():
    p = proces_z_ocena()
    assert p.wynik.ocena == POZYTYWNA
    assert p.etap == Etap.OCENA_DO_ZAPOZNANIA


def test_ocena_negatywna_bez_uzasadnienia_nie_zostaje_sporzadzona():
    with pytest.raises(BladWalidacji) as blad:
        proces_z_ocena(OCENY_NEGATYWNE, uzasadnienie="")
    assert "BRAK_UZASADNIENIA_NEGATYWNEJ" in blad.value.kody


def test_zapoznanie_z_ocena_potwierdza_oceniany_i_konczy_proces():
    """§ 12 ust. 1 rozp.; przypadek użycia „potwierdzenie zapoznania się z oceną”."""
    p = proces_z_ocena()
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    assert p.etap == Etap.ZAKONCZONA
    assert p.data_zapoznania_z_ocena == d(2028, 1, 11)


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize("rola", [Rola.OCENIAJACY, Rola.OCENIANY, Rola.ZARZADZAJACY])
def test_fikcje_zapoznania_z_ocena_moze_stwierdzic_kazda_ze_stron(rola):
    """Przypadek użycia „stwierdzenie fikcji zapoznania z oceną”; decyzja zespołu z 21.11.2026: stwierdzają
    wszystkie strony (oceniany - jako odmowę potwierdzenia zapoznania)."""
    p = proces_z_ocena()
    p.stwierdz_fikcje_zapoznania(rola, data=d(2028, 1, 18))
    assert p.etap == Etap.ZAKONCZONA
    assert p.zapoznanie_fikcyjne is True
    assert p.fikcje_stwierdzil == rola


@pytest.mark.decyzja_projektowa
def test_data_stwierdzenia_fikcji_jest_data_zapoznania_z_ocena():
    """Od tej daty biegną terminy sprzeciwu (art. 83 ust. 1 u.s.c.) i ponownej oceny (art. 81 ust. 9 u.s.c.)."""
    p = proces_z_ocena()
    p.stwierdz_fikcje_zapoznania(Rola.OCENIAJACY, data=d(2028, 1, 18))
    assert p.data_zapoznania_z_ocena == d(2028, 1, 18)


@pytest.mark.decyzja_projektowa
def test_administrator_nie_jest_strona_i_nie_stwierdza_fikcji_zapoznania():
    with pytest.raises(BladUprawnien):
        proces_z_ocena().stwierdz_fikcje_zapoznania(Rola.ADMIN, data=d(2028, 1, 18))


def test_po_zapoznaniu_ocena_jest_zablokowana_dla_oceniajacego():
    p = proces_z_ocena()
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    with pytest.raises(BladEtapu):
        p.sporzadz_ocene(Rola.OCENIAJACY, data=d(2028, 1, 12), data_rozmowy=d(2028, 1, 5),
                         oceny=OCENY_POZYTYWNE, wnioski_iprz="x")


# --- sprzeciw (art. 83 ust. 4) ---

def test_uwzglednienie_sprzeciwu_wprowadza_zarzadzajacy_w_imieniu_dyrektora_generalnego():
    """Model BPMN: „[dyrektor generalny] wprowadza zmianę w formularzu oceny” (tor ZARZĄDZAJĄCY)."""
    p = proces_z_ocena()
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    with pytest.raises(BladUprawnien):
        p.uwzglednij_sprzeciw(Rola.OCENIAJACY, tryb="ponowne_sporzadzenie", data=d(2028, 1, 20))


def test_ponowne_sporzadzenie_oceny_anuluje_ocene_i_wraca_do_etapu_oceniania():
    """Przypadek użycia: „anulowanie oceny i powrót do etapu rozmowa oceniająca i dokonanie oceny”."""
    p = proces_z_ocena()
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    p.uwzglednij_sprzeciw(Rola.ZARZADZAJACY, tryb="ponowne_sporzadzenie", data=d(2028, 1, 20))
    assert p.etap == Etap.OCENIANIE
    assert p.wynik is None
    assert len(p.oceny_anulowane) == 1


@pytest.mark.interpretacja
def test_zmiana_oceny_po_sprzeciwie_nie_moze_obnizyc_ocen():
    """Poradnik KPRM s. 32: uwzględnienie sprzeciwu nie może prowadzić do obniżenia oceny."""
    p = proces_z_ocena()
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    nizsze = dict(OCENY_POZYTYWNE) | {"Rzetelność": 5}  # było 7
    with pytest.raises(BladWalidacji):
        p.uwzglednij_sprzeciw(Rola.ZARZADZAJACY, tryb="zmiana", data=d(2028, 1, 20), nowe_oceny=nizsze)


def test_zmiana_oceny_po_sprzeciwie_aktualizuje_wynik():
    p = proces_z_ocena(OCENY_NEGATYWNE, uzasadnienie="Liczne błędy w dokumentach.")
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    wyzsze = dict(OCENY_NEGATYWNE) | {"Rzetelność": 3}
    p.uwzglednij_sprzeciw(Rola.ZARZADZAJACY, tryb="zmiana", data=d(2028, 1, 20), nowe_oceny=wyzsze)
    assert p.wynik.ocena == POZYTYWNA
    assert p.oceny == wyzsze
