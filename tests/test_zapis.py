"""Wymaganie: stan procesu oceny jest zapisywany w bazie jako JSON i odtwarzany bez strat.

Źródło: dokumentacja/architektura.md, pkt 1.2 („Jedno źródło stanu procesu”) i pkt 4 („Zapis procesu”):
daty jako RRRR-MM-DD, wyliczenia jako wartości, ułamek jako napis „licznik/mianownik”, pole `przepisy`
nie jest zapisywane, a `proces_ze_slownika(proces_do_slownika(p)) == p` dla procesu na każdym etapie.

Procesy są budowane wyłącznie metodami rdzenia - tak jak w tests/test_przebieg_procesu.py.
"""

import dataclasses
import json
from datetime import date
from fractions import Fraction

import pytest

from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.przebieg import Dokument, Etap, Notatka, ProcesOceny, Rola
from asystent_ocen.walidacja import Formularz
from asystent_ocen.wynik import WynikOceny
from asystent_ocen.zapis import WERSJA_ZAPISU, proces_do_slownika, proces_ze_slownika
from stale import OBOWIAZKOWE_B, OBOWIAZKOWE_C, d

KRYTERIA_C = [*OBOWIAZKOWE_C, "Kreatywność"]
OCENY_POZYTYWNE = dict(zip(KRYTERIA_C, [5, 7, 5, 5, 5, 7]))  # średnia 34/6 = 17/3
OCENY_NEGATYWNE = dict(zip(KRYTERIA_C, [5, 1, 5, 5, 5, 5]))  # średnia 26/6 = 13/3


# --- procesy na kolejnych etapach ---

def proces_nowy():
    return ProcesOceny(arkusz="C", urzednik=False, poczatek_cyklu=d(2026, 1, 12))


def proces_do_potwierdzenia_kryteriow():
    p = proces_nowy()
    p.wyznacz_kryteria(Rola.OCENIAJACY, ["Kreatywność"], termin=d(2028, 1, 12), data=d(2026, 1, 20))
    p.dodaj_notatke(Rola.OCENIAJACY, "Rozmowa o kryteriach przebiegła sprawnie.", data=d(2026, 1, 20))
    return p


def proces_w_trakcie_oceniania():
    """Etap oceniania z kompletem zdarzeń pobocznych: notatki, wniosek, zmiana terminu i oceniającego."""
    p = proces_do_potwierdzenia_kryteriow()
    p.potwierdz_kryteria(Rola.OCENIANY, data=d(2026, 1, 21))
    p.dodaj_notatke(Rola.OCENIAJACY, "Terminowo przygotował raport roczny.", data=d(2026, 6, 30))
    p.zloz_wniosek_o_zmiane_terminu(Rola.OCENIANY, data=d(2026, 7, 13))
    p.zmien_oceniajacego(Rola.ZARZADZAJACY, data=d(2027, 2, 1))
    p.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="NIEOBECNOSC_OCENIAJACEGO")
    return p


def proces_z_ocena_do_zapoznania(oceny=OCENY_POZYTYWNE, uzasadnienie=""):
    p = proces_w_trakcie_oceniania()
    p.sporzadz_ocene(
        Rola.OCENIAJACY, data=d(2027, 8, 30), data_rozmowy=d(2027, 8, 25), oceny=oceny,
        wnioski_iprz="Szkolenie z analizy danych.", uzasadnienie=uzasadnienie,
    )
    return p


def proces_zakonczony():
    p = proces_z_ocena_do_zapoznania()
    p.potwierdz_zapoznanie(Rola.OCENIANY, data=d(2027, 8, 31))
    return p


def proces_zakonczony_fikcja_zapoznania():
    p = proces_z_ocena_do_zapoznania(OCENY_NEGATYWNE, uzasadnienie="Liczne błędy w dokumentach.")
    p.stwierdz_fikcje_zapoznania(Rola.ZARZADZAJACY, data=d(2027, 9, 7))
    return p


def proces_po_sprzeciwie_z_anulowana_ocena():
    """Art. 83 ust. 4 u.s.c.: ponowne sporządzenie - ocena trafia do anulowanych, proces wraca do oceniania."""
    p = proces_zakonczony()
    p.uwzglednij_sprzeciw(Rola.DYREKTOR_GENERALNY, tryb="ponowne_sporzadzenie", data=d(2027, 9, 10))
    return p


def proces_po_zmianie_oceny_po_sprzeciwie():
    p = proces_zakonczony_fikcja_zapoznania()
    wyzsze = dict(OCENY_NEGATYWNE) | {"Rzetelność": 3}
    p.uwzglednij_sprzeciw(Rola.DYREKTOR_GENERALNY, tryb="zmiana", data=d(2027, 9, 20), nowe_oceny=wyzsze)
    return p


def proces_urzednika_z_wnioskiem_o_stopien():
    """Arkusz B, urzędnik: formularz z wnioskiem o stopień służbowy (art. 89 ust. 1 u.s.c.)."""
    p = ProcesOceny(arkusz="B", urzednik=True, poczatek_cyklu=d(2026, 3, 2))
    p.wyznacz_kryteria(Rola.OCENIAJACY, [], termin=d(2028, 3, 2), data=d(2026, 3, 10))
    p.potwierdz_kryteria(Rola.OCENIANY, data=d(2026, 3, 11))
    p.sporzadz_ocene(
        Rola.OCENIAJACY, data=d(2028, 3, 1), data_rozmowy=d(2028, 2, 28),
        oceny=dict(zip(OBOWIAZKOWE_B, [9, 7, 9, 7, 9])), wnioski_iprz="Studia podyplomowe.",
        wniosek_o_stopien="TAK", umotywowanie_wniosku="Wzorowe kierowanie wydziałem.", posiadany_stopien=3,
    )
    return p


PROCESY = [
    proces_nowy,
    proces_do_potwierdzenia_kryteriow,
    proces_w_trakcie_oceniania,
    proces_z_ocena_do_zapoznania,
    proces_zakonczony,
    proces_zakonczony_fikcja_zapoznania,
    proces_po_sprzeciwie_z_anulowana_ocena,
    proces_po_zmianie_oceny_po_sprzeciwie,
    proces_urzednika_z_wnioskiem_o_stopien,
]
IDS = [budowa.__name__ for budowa in PROCESY]


# --- przejście tam i z powrotem ---

def test_przyklady_obejmuja_kazdy_etap_procesu():
    assert {budowa().etap for budowa in PROCESY} == set(Etap)


@pytest.mark.parametrize("budowa", PROCESY, ids=IDS)
def test_zapis_i_odczyt_odtwarza_proces_na_kazdym_etapie(budowa):
    proces = budowa()
    assert proces_ze_slownika(proces_do_slownika(proces)) == proces


@pytest.mark.parametrize("budowa", PROCESY, ids=IDS)
def test_zapis_przechodzi_przez_json_bez_dodatkowych_koderow(budowa):
    """Baza przechowuje stan jako JSON: po zapisie do tekstu i odczycie proces jest ten sam."""
    proces = budowa()
    slownik = proces_do_slownika(proces)
    tekst = json.dumps(slownik)
    assert json.loads(tekst) == slownik
    assert proces_ze_slownika(json.loads(tekst)) == proces


@pytest.mark.parametrize("budowa", PROCESY, ids=IDS)
def test_odczyt_przywraca_typy_a_nie_same_napisy(budowa):
    """`Rola` i `Etap` są napisami, więc samo porównanie `==` nie odróżni wyliczenia od jego wartości."""
    odtworzony = proces_ze_slownika(json.loads(json.dumps(proces_do_slownika(budowa()))))
    assert type(odtworzony.etap) is Etap
    assert type(odtworzony.poczatek_cyklu) is date
    assert odtworzony.fikcje_stwierdzil is None or type(odtworzony.fikcje_stwierdzil) is Rola
    assert all(type(dokument) is Dokument and type(dokument.adresat) is Rola for dokument in odtworzony.dokumenty)
    assert all(type(dokument.data) is date for dokument in odtworzony.dokumenty)
    assert all(type(notatka) is Notatka and type(notatka.data) is date for notatka in odtworzony.notatki)
    assert all(type(dzien) is date for dzien in odtworzony.daty_zmiany_oceniajacego)
    assert all(type(wynik) is WynikOceny for wynik in odtworzony.oceny_anulowane)
    if odtworzony.wynik is not None:
        assert type(odtworzony.wynik) is WynikOceny
        assert type(odtworzony.wynik.srednia) is Fraction
        assert type(odtworzony.formularz) is Formularz
        assert all(type(punkty) is int for punkty in odtworzony.oceny.values())


# --- postać zapisu (pkt 4 architektury) ---

def test_slownik_zawiera_wersje_zapisu():
    assert WERSJA_ZAPISU == 1
    assert proces_do_slownika(proces_nowy())["wersja"] == WERSJA_ZAPISU


def test_daty_sa_zapisywane_jako_rrrr_mm_dd():
    slownik = proces_do_slownika(proces_zakonczony())
    assert slownik["poczatek_cyklu"] == "2026-01-12"
    assert slownik["termin"] == "2027-09-01"
    assert slownik["data_zapoznania_z_ocena"] == "2027-08-31"
    assert slownik["notatki"][0]["data"] == "2026-01-20"
    assert slownik["daty_zmiany_oceniajacego"] == ["2027-02-01"]


def test_brak_daty_jest_zapisywany_jako_null():
    slownik = proces_do_slownika(proces_nowy())
    assert slownik["termin"] is None
    assert slownik["wynik"] is None
    assert slownik["formularz"] is None


def test_wyliczenia_sa_zapisywane_jako_wartosci():
    slownik = proces_do_slownika(proces_zakonczony_fikcja_zapoznania())
    assert slownik["etap"] == "zakończona"
    assert slownik["fikcje_stwierdzil"] == "zarządzający"
    assert {dokument["adresat"] for dokument in slownik["dokumenty"]} == {"oceniający", "oceniany"}
    assert all(type(dokument["adresat"]) is str for dokument in slownik["dokumenty"])
    assert type(slownik["etap"]) is str


def test_srednia_jest_zapisywana_jako_napis_licznik_mianownik():
    slownik = proces_do_slownika(proces_po_sprzeciwie_z_anulowana_ocena())
    assert slownik["oceny_anulowane"][0]["srednia"] == "17/3"
    assert proces_do_slownika(proces_urzednika_z_wnioskiem_o_stopien())["wynik"]["srednia"] == "41/5"


def test_srednia_calkowita_tez_ma_mianownik():
    p = proces_nowy()
    p.wyznacz_kryteria(Rola.OCENIAJACY, [], termin=d(2028, 1, 12), data=d(2026, 1, 20))
    p.potwierdz_kryteria(Rola.OCENIANY, data=d(2026, 1, 21))
    p.sporzadz_ocene(Rola.OCENIAJACY, data=d(2028, 1, 10), data_rozmowy=d(2028, 1, 5),
                     oceny=dict(zip(OBOWIAZKOWE_C, [5, 5, 5, 5, 5])), wnioski_iprz="Szkolenie.")
    assert proces_do_slownika(p)["wynik"]["srednia"] == "5/1"


def test_zagniezdzony_formularz_zachowuje_tresc_arkusza():
    slownik = proces_do_slownika(proces_urzednika_z_wnioskiem_o_stopien())
    assert slownik["formularz"]["wniosek_o_stopien"] == "TAK"
    assert slownik["formularz"]["posiadany_stopien"] == 3
    assert slownik["formularz"]["oceny"] == dict(zip(OBOWIAZKOWE_B, [9, 7, 9, 7, 9]))


def test_przepisy_nie_sa_zapisywane():
    """Po wczytaniu pole `przepisy` ma wartość None, czyli obowiązują przepisy domyślne."""
    proces = ProcesOceny(arkusz="C", urzednik=False, poczatek_cyklu=d(2026, 1, 12), przepisy=wczytaj_przepisy())
    slownik = proces_do_slownika(proces)
    assert "przepisy" not in slownik
    assert proces_ze_slownika(slownik).przepisy is None


def test_zapis_obejmuje_wszystkie_pola_procesu():
    """Strażnik: nowe pole dodane do rdzenia nie może po cichu wypaść z zapisu."""
    def pola(typ):
        return {pole.name for pole in dataclasses.fields(typ)}

    slownik = proces_do_slownika(proces_po_zmianie_oceny_po_sprzeciwie())
    assert set(slownik) == (pola(ProcesOceny) - {"przepisy"}) | {"wersja"}
    assert set(slownik["wynik"]) == pola(WynikOceny)
    assert set(slownik["formularz"]) == pola(Formularz)
    assert set(slownik["notatki"][0]) == pola(Notatka)
    assert set(slownik["dokumenty"][0]) == pola(Dokument)


def test_slownik_nie_wspoldzieli_danych_z_procesem():
    proces = proces_z_ocena_do_zapoznania()
    slownik = proces_do_slownika(proces)
    slownik["kryteria_dodatkowe"].append("Negocjowanie")
    slownik["oceny"]["Rzetelność"] = 1
    slownik["formularz"]["oceny"]["Rzetelność"] = 1
    assert proces.kryteria_dodatkowe == ["Kreatywność"]
    assert proces.oceny["Rzetelność"] == 7
    assert proces.formularz.oceny["Rzetelność"] == 7


# --- wersja zapisu ---

@pytest.mark.parametrize("wersja", [WERSJA_ZAPISU + 1, 0, "1", None])
def test_nieznana_wersja_zapisu_jest_odrzucana(wersja):
    dane = proces_do_slownika(proces_nowy())
    dane["wersja"] = wersja
    with pytest.raises(ValueError):
        proces_ze_slownika(dane)


def test_zapis_bez_wersji_jest_odrzucany():
    dane = proces_do_slownika(proces_nowy())
    del dane["wersja"]
    with pytest.raises(ValueError):
        proces_ze_slownika(dane)
