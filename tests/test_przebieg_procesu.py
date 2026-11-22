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
    p.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="NIEOBECNOSC_OCENIAJACEGO")
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

def test_sprzeciw_rozstrzyga_dyrektor_generalny_a_nie_komorka_kadr():
    """Art. 83 ust. 1 u.s.c.: sprzeciw służy do dyrektora generalnego urzędu. Decyzja prowadzącego projekt
    z 21.11.2026: rozstrzygnięcie wprowadza w systemie dyrektor generalny, a nie komórka kadr w jego imieniu
    (inaczej niż w torze ZARZĄDZAJĄCY modelu BPMN)."""
    p = proces_z_ocena()
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    for rola in (Rola.OCENIAJACY, Rola.ZARZADZAJACY, Rola.OCENIANY, Rola.ADMIN):
        with pytest.raises(BladUprawnien):
            p.uwzglednij_sprzeciw(rola, tryb="ponowne_sporzadzenie", data=d(2028, 1, 20))
    p.uwzglednij_sprzeciw(Rola.DYREKTOR_GENERALNY, tryb="ponowne_sporzadzenie", data=d(2028, 1, 20))
    assert p.etap == Etap.OCENIANIE


def test_ponowne_sporzadzenie_oceny_anuluje_ocene_i_wraca_do_etapu_oceniania():
    """Przypadek użycia: „anulowanie oceny i powrót do etapu rozmowa oceniająca i dokonanie oceny”."""
    p = proces_z_ocena()
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    p.uwzglednij_sprzeciw(Rola.DYREKTOR_GENERALNY, tryb="ponowne_sporzadzenie", data=d(2028, 1, 20))
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
        p.uwzglednij_sprzeciw(Rola.DYREKTOR_GENERALNY, tryb="zmiana", data=d(2028, 1, 20), nowe_oceny=nizsze)


def test_zmiana_oceny_po_sprzeciwie_aktualizuje_wynik():
    p = proces_z_ocena(OCENY_NEGATYWNE, uzasadnienie="Liczne błędy w dokumentach.")
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2028, 1, 11))
    wyzsze = dict(OCENY_NEGATYWNE) | {"Rzetelność": 3}
    p.uwzglednij_sprzeciw(Rola.DYREKTOR_GENERALNY, tryb="zmiana", data=d(2028, 1, 20), nowe_oceny=wyzsze)
    assert p.wynik.ocena == POZYTYWNA
    assert p.oceny == wyzsze


# --- zmiana terminu tylko w przypadkach z art. 81 ust. 8 u.s.c. ---
# Ustawa wymienia cztery przypadki; inna przyczyna nie daje podstawy do zmiany terminu.

def test_ustawa_zna_cztery_przypadki_zmiany_terminu():
    from asystent_ocen.przebieg import PRZYPADKI_ZMIANY_TERMINU

    assert list(PRZYPADKI_ZMIANY_TERMINU) == [
        "ZMIANA_OCENIAJACEGO", "NIEOBECNOSC_OCENIANEGO", "NIEOBECNOSC_OCENIAJACEGO", "WNIOSEK_OCENIANEGO",
    ]
    assert [przypadek.podstawa for przypadek in PRZYPADKI_ZMIANY_TERMINU.values()] == [
        f"art. 81 ust. 8 pkt {punkt} u.s.c." for punkt in (1, 2, 3, 4)
    ]


def test_zmiana_terminu_z_przyczyna_spoza_ustawy_jest_odrzucana():
    p = proces_z_potwierdzonymi_kryteriami()
    for przyczyna in ("reorganizacja wydziału", "", None):
        with pytest.raises(BladWalidacji) as blad:
            p.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna=przyczyna)
        assert "NIEZNANY_PRZYPADEK_ZMIANY_TERMINU" in blad.value.kody
    assert p.termin == d(2028, 1, 12)


def test_zmiana_terminu_z_powodu_zmiany_oceniajacego_wymaga_odnotowanej_zmiany():
    """art. 81 ust. 8 pkt 1 u.s.c.: „zmiany na stanowisku oceniającego w trakcie okresu, w którym oceniany podlega ocenie”."""
    p = proces_z_potwierdzonymi_kryteriami()
    with pytest.raises(BladWalidacji) as blad:
        p.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="ZMIANA_OCENIAJACEGO")
    assert "BRAK_ZMIANY_OCENIAJACEGO" in blad.value.kody

    p.zmien_oceniajacego(Rola.ZARZADZAJACY, data=d(2027, 2, 1))
    p.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="ZMIANA_OCENIAJACEGO")

    assert p.termin == d(2027, 9, 1)


def test_zmiana_terminu_na_wniosek_wymaga_wniosku_ocenianego():
    """art. 81 ust. 8 pkt 4 u.s.c."""
    p = proces_z_potwierdzonymi_kryteriami()
    with pytest.raises(BladWalidacji) as blad:
        p.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="WNIOSEK_OCENIANEGO")
    assert "BRAK_WNIOSKU_OCENIANEGO" in blad.value.kody

    p.zloz_wniosek_o_zmiane_terminu(Rola.OCENIANY, data=d(2027, 2, 20))
    p.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="WNIOSEK_OCENIANEGO")

    assert p.termin == d(2027, 9, 1)


def test_nowy_termin_nie_moze_byc_przeszly_ani_taki_sam_jak_dotychczasowy():
    p = proces_z_potwierdzonymi_kryteriami()
    for nowy, kod in ((d(2027, 2, 28), "NOWY_TERMIN_W_PRZESZLOSCI"), (d(2028, 1, 12), "TERMIN_BEZ_ZMIANY")):
        with pytest.raises(BladWalidacji) as blad:
            p.zmien_termin(Rola.OCENIAJACY, nowy_termin=nowy, data=d(2027, 3, 1), przyczyna="NIEOBECNOSC_OCENIANEGO")
        assert kod in blad.value.kody
    assert p.termin == d(2028, 1, 12)


def test_zawiadomienie_o_nowym_terminie_podaje_przypadek_z_ustawy_i_uwagi_oceniajacego():
    """§ 8 rozp.: oceniający niezwłocznie zawiadamia pisemnie ocenianego o nowym terminie."""
    p = proces_z_potwierdzonymi_kryteriami()

    p.zmien_termin(
        Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="NIEOBECNOSC_OCENIANEGO",
        opis="Urlop rodzicielski od maja.",
    )

    zawiadomienie = next(dok for dok in p.dokumenty if dok.rodzaj == "zawiadomienie o nowym terminie oceny")
    assert zawiadomienie.adresat == Rola.OCENIANY
    for fragment in ("art. 81 ust. 8 pkt 2 u.s.c.", "nieobecność w pracy ocenianego", "Urlop rodzicielski od maja."):
        assert fragment in zawiadomienie.opis
    assert p.termin_zmieniony_przez_oceniajacego is True


def test_termin_wpisany_do_czesci_I_nie_jest_zmiana_terminu():
    assert proces_z_potwierdzonymi_kryteriami().termin_zmieniony_przez_oceniajacego is False


# --- przedłużenie terminu z mocy ustawy (art. 81 ust. 7 u.s.c.) ---

def test_przedluzenie_terminu_o_nieobecnosc_nie_jest_zmiana_terminu_przez_oceniajacego():
    p = proces_z_potwierdzonymi_kryteriami()

    p.przedluz_termin_o_nieobecnosc(Rola.ZARZADZAJACY, nowy_termin=d(2028, 2, 25), data=d(2027, 3, 1))

    assert p.termin == d(2028, 2, 25)
    assert p.termin_zmieniony_przez_oceniajacego is False
    assert p.etap == Etap.OCENIANIE


def test_przedluzenie_nie_skraca_terminu_i_nie_dziala_po_sporzadzeniu_oceny():
    with pytest.raises(BladWalidacji):
        proces_z_potwierdzonymi_kryteriami().przedluz_termin_o_nieobecnosc(Rola.ZARZADZAJACY, nowy_termin=d(2028, 1, 11), data=d(2027, 3, 1))
    with pytest.raises(BladEtapu):
        proces_z_ocena().przedluz_termin_o_nieobecnosc(Rola.ZARZADZAJACY, nowy_termin=d(2028, 2, 25), data=d(2028, 1, 11))


# --- zmiana stanowiska z istotną zmianą zakresu obowiązków (art. 81 ust. 6 u.s.c., § 9 ust. 1-2 rozp.) ---
# Proces wzorcowy: początek cyklu 12.01.2026 (pierwsza ocena), kryteria potwierdzone 21.01.2026, termin 12.01.2028.

def _zmiana(p, dzien, **pola):
    return p.zmien_stanowisko(Rola.ZARZADZAJACY, data_zmiany=dzien, data=dzien, stanowisko="specjalista", **pola)


def test_zmiana_stanowiska_po_6_miesiacach_wyznacza_ocene_w_oknie_wokol_dnia_zmiany():
    """Art. 81 ust. 6 u.s.c., § 9 ust. 2 rozp.: nie wcześniej niż 7 dni przed zmianą, nie później niż 30 dni po niej."""
    p = proces_z_potwierdzonymi_kryteriami()

    skutek = _zmiana(p, d(2026, 9, 1))

    assert skutek.wymagana_ocena is True
    assert p.etap == Etap.OCENIANIE
    assert (p.zmiana_stanowiska, p.ocena_najwczesniej, p.termin) == (d(2026, 9, 1), d(2026, 8, 25), d(2026, 10, 1))
    assert (p.stanowisko_przed_zmiana, p.ponowne_kryteria_do) == ("specjalista", None)
    assert p.termin_zmieniony_przez_oceniajacego is False


def test_oceny_w_zwiazku_ze_zmiana_stanowiska_nie_sporzadza_sie_wczesniej_niz_7_dni_przed_zmiana():
    p = proces_z_potwierdzonymi_kryteriami()
    _zmiana(p, d(2026, 9, 1))
    dane = dict(oceny=OCENY_POZYTYWNE, wnioski_iprz="Szkolenie z analizy danych.")

    with pytest.raises(BladWalidacji) as blad:
        p.sporzadz_ocene(Rola.OCENIAJACY, data=d(2026, 8, 24), data_rozmowy=d(2026, 8, 21), **dane)
    assert "OCENA_PRZED_ZMIANA_STANOWISKA_ZA_WCZESNIE" in blad.value.kody

    p.sporzadz_ocene(Rola.OCENIAJACY, data=d(2026, 8, 25), data_rozmowy=d(2026, 8, 24), **dane)
    assert p.etap == Etap.OCENA_DO_ZAPOZNANIA


def test_zmiana_stanowiska_przed_uplywem_6_miesiecy_wymaga_nowych_kryteriow_a_termin_zostaje():
    """§ 9 ust. 1 rozp.: w 30 dni ponownie rozmowa i zapoznanie z kryteriami; termin sporządzenia oceny bez zmian."""
    p = proces_z_potwierdzonymi_kryteriami()

    skutek = _zmiana(p, d(2026, 5, 4))

    assert skutek.wymagana_ocena is False
    assert (p.etap, p.termin, p.ponowne_kryteria_do) == (Etap.KRYTERIA_DO_WYZNACZENIA, d(2028, 1, 12), d(2026, 6, 3))
    assert (p.data_zapoznania_z_kryteriami, p.kryteria_dodatkowe, p.ocena_najwczesniej) == (None, [], None)

    p.wyznacz_kryteria(Rola.OCENIAJACY, ["Kreatywność"], termin=d(2028, 1, 12), data=d(2026, 5, 20))
    p.potwierdz_kryteria(Rola.OCENIANY, data=d(2026, 5, 21))
    assert (p.etap, p.data_zapoznania_z_kryteriami) == (Etap.OCENIANIE, d(2026, 5, 21))


def test_przy_kolejnej_ocenie_6_miesiecy_liczy_sie_od_sporzadzenia_poprzedniej():
    p = proces_z_potwierdzonymi_kryteriami()

    skutek = _zmiana(p, d(2026, 9, 1), data_ostatniej_oceny=d(2026, 4, 1))

    assert skutek.wymagana_ocena is False
    assert p.etap == Etap.KRYTERIA_DO_WYZNACZENIA


def test_zmiana_stanowiska_bez_potwierdzonych_kryteriow_wymaga_tylko_kryteriow():
    """Bez zapoznania z kryteriami nie ma okresu podlegającego ocenie, więc nie ma czego oceniać."""
    p = nowy_proces()

    skutek = _zmiana(p, d(2026, 9, 1))

    assert skutek.wymagana_ocena is False
    assert (p.etap, p.ponowne_kryteria_do, p.ocena_najwczesniej) == (Etap.KRYTERIA_DO_WYZNACZENIA, d(2026, 10, 1), None)


def test_zmiane_stanowiska_odnotowuje_komorka_kadr_i_tylko_przed_sporzadzeniem_oceny():
    with pytest.raises(BladUprawnien):
        proces_z_potwierdzonymi_kryteriami().zmien_stanowisko(
            Rola.OCENIAJACY, data_zmiany=d(2026, 9, 1), data=d(2026, 9, 1), stanowisko="specjalista"
        )
    with pytest.raises(BladEtapu):
        _zmiana(proces_z_ocena(), d(2028, 1, 11))


def test_stan_po_zmianie_stanowiska_przechodzi_przez_zapis_a_stare_zapisy_sie_odczytuja():
    from asystent_ocen.zapis import proces_do_slownika, proces_ze_slownika

    p = proces_z_potwierdzonymi_kryteriami()
    _zmiana(p, d(2026, 9, 1))

    slownik = proces_do_slownika(p)
    assert proces_ze_slownika(slownik) == p

    for pole in ("zmiana_stanowiska", "ocena_najwczesniej", "ponowne_kryteria_do", "stanowisko_przed_zmiana"):
        del slownik[pole]
    stary = proces_ze_slownika(slownik)
    assert (stary.zmiana_stanowiska, stary.ocena_najwczesniej, stary.ponowne_kryteria_do, stary.stanowisko_przed_zmiana) == (None, None, None, "")


def test_terminu_oceny_w_zwiazku_ze_zmiana_stanowiska_oceniajacy_nie_zmienia():
    """Art. 81 ust. 8 u.s.c. pozwala zmienić termin z ust. 4, a nie termin oceny z ust. 6."""
    p = proces_z_potwierdzonymi_kryteriami()
    _zmiana(p, d(2026, 9, 1))

    with pytest.raises(BladWalidacji) as blad:
        p.zmien_termin(Rola.OCENIAJACY, d(2026, 10, 30), d(2026, 9, 2), "NIEOBECNOSC_OCENIANEGO", None)

    assert "TERMIN_OCENY_PO_ZMIANIE_STANOWISKA" in blad.value.kody
    assert p.termin == d(2026, 10, 1)


def test_kalendarz_po_zmianie_stanowiska_podaje_terminy_i_podstawe_z_paragrafu_9():
    from asystent_ocen.ics import wydarzenia_procesu

    ocena = proces_z_potwierdzonymi_kryteriami()
    _zmiana(ocena, d(2026, 9, 1))
    (termin,) = [w for w in wydarzenia_procesu(ocena, kto="", identyfikator="x") if w.uid.startswith("x-termin-oceny")]
    assert termin.data == d(2026, 10, 1)
    assert "zmianą stanowiska" in termin.opis and "§ 9 ust. 2" in termin.opis and "24 mies." not in termin.opis

    kryteria = proces_z_potwierdzonymi_kryteriami()
    _zmiana(kryteria, d(2026, 5, 4))
    (rozmowa,) = [w for w in wydarzenia_procesu(kryteria, kto="", identyfikator="x") if w.uid.startswith("x-kryteria")]
    assert rozmowa.data == d(2026, 6, 3)
    assert "zmianie stanowiska" in rozmowa.opis and "§ 9 ust. 1" in rozmowa.opis
