"""Wymaganie: pracownik może przeprowadzić symulację swojej oceny i zobaczyć, na jaką ocenę cząstkową wskazują
fakty z EZD RP. To przypuszczenie - ocenę wystawia przełożony, także na podstawie informacji spoza EZD RP.

Źródła: decyzja zespołu z 21.11.2026; § 11 ust. 1 rozp. (skala ocen cząstkowych); załącznik nr 1 do rozp. - opis
kryterium „Rzetelność”: „Wykonywanie zadań zgodnie z obowiązującymi standardami (przepisami, zasadami,
procedurami) oraz dbałość o jakość rezultatów” i „Dotrzymywanie zobowiązań (realizacja zadań) w wyznaczonym
czasie”. Progi procentowe nie wynikają z przepisów - są ustawieniem urzędu w `symulacja.toml`.
"""

from datetime import date
from fractions import Fraction

import pytest

from asystent_ocen.symulacja import WSKAZNIKI_PROCENTOWE, ocena_dla_udzialu, wczytaj_ustawienia, wskazania_z_ezd
from asystent_ocen.wskazniki_pracy import wskazniki_pracy
from stale import KATALOG, OBOWIAZKOWE_C

RZETELNOSC = "Rzetelność"


def procent(wartosc: int | str) -> Fraction:
    return Fraction(str(wartosc)) / 100


def ustawienia_z(tmp_path, tresc: str):
    plik = tmp_path / "symulacja.toml"
    plik.write_text(tresc, encoding="utf-8")
    return wczytaj_ustawienia(plik)


PROGI = "[progi_procentowe]\n9 = 95\n7 = 85\n5 = 70\n3 = 50\n"
POWIAZANIE = (
    '[[powiazania]]\nkryterium = "Rzetelność"\nwskazniki = ["TERMINOWOSC"]\nuzasadnienie = "terminowość zadań"\n'
)


# --- progi ---

@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize(
    ("udzial", "ocena"),
    [(100, 9), (95, 9), ("94.9", 7), (85, 7), ("84.9", 5), (70, 5), ("69.9", 3), (50, 3), ("49.9", 1), (0, 1)],
)
def test_udzial_wskazuje_na_ocene_czastkowa_wedlug_progow_urzedu(udzial, ocena):
    """Progi domyślne: co najmniej 95% - 9, 85% - 7, 70% - 5, 50% - 3, mniej - 1."""
    assert ocena_dla_udzialu(procent(udzial)) == ocena


def test_zmiana_progow_w_konfiguracji_zmienia_wskazanie_bez_zmiany_kodu(tmp_path):
    lagodne = ustawienia_z(tmp_path, "[progi_procentowe]\n9 = 80\n7 = 60\n5 = 40\n3 = 20\n" + POWIAZANIE)
    assert ocena_dla_udzialu(procent(68)) == 3
    assert ocena_dla_udzialu(procent(68), lagodne) == 7


# --- wskazania dla kryteriów ---

def test_wskazanie_dla_kryterium_laczy_wszystkie_powiazane_fakty():
    """68% spraw w terminie -> 3, 67% projektów przyjętych za pierwszym razem -> 3, 40% rozstrzygnięć
    utrzymanych -> 1; średnia 7/3 leży najbliżej oceny 3."""
    udzialy = {
        "TERMINOWOSC": procent(68),
        "PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM": procent(67),
        "ROZSTRZYGNIECIA_UTRZYMANE": procent(40),
    }
    (wskazanie,) = wskazania_z_ezd(OBOWIAZKOWE_C, udzialy)

    assert (wskazanie.kryterium, wskazanie.ocena) == (RZETELNOSC, 3)
    assert [(s.kod, s.ocena) for s in wskazanie.skladniki] == [
        ("TERMINOWOSC", 3), ("PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM", 3), ("ROZSTRZYGNIECIA_UTRZYMANE", 1),
    ]


@pytest.mark.decyzja_projektowa
def test_remis_miedzy_dwiema_ocenami_rozstrzyga_sie_w_dol():
    """100% -> 9 i 90% -> 7 dają średnią 8, równo między 7 a 9; symulacja nie obiecuje więcej, niż wynika z danych."""
    udzialy = {"TERMINOWOSC": procent(100), "PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM": procent(90)}
    assert wskazania_z_ezd([RZETELNOSC], udzialy)[0].ocena == 7


def test_fakt_ktorego_nie_policzono_jest_pomijany():
    """Wskaźnik bez wartości (za mało zdarzeń) nie wpływa na wskazanie."""
    (wskazanie,) = wskazania_z_ezd([RZETELNOSC], {"TERMINOWOSC": procent(100), "ROZSTRZYGNIECIA_UTRZYMANE": None})
    assert wskazanie.ocena == 9
    assert [s.kod for s in wskazanie.skladniki] == ["TERMINOWOSC"]


def test_kryteria_o_ktorych_ezd_rp_nic_nie_mowi_nie_dostaja_wskazania():
    """Współpraca, komunikacja czy wykorzystywanie wiedzy nie mają odpowiednika w danych o sprawach."""
    wskazania = wskazania_z_ezd(OBOWIAZKOWE_C, {"TERMINOWOSC": procent(100)})
    assert [w.kryterium for w in wskazania] == [RZETELNOSC]


def test_bez_danych_nie_ma_wskazan():
    assert wskazania_z_ezd(OBOWIAZKOWE_C, {}) == []
    assert wskazania_z_ezd(["Współpraca", "Komunikacja"], {"TERMINOWOSC": procent(100)}) == []


def test_wskazanie_podaje_uzasadnienie_powiazania_z_kryterium():
    (wskazanie,) = wskazania_z_ezd([RZETELNOSC], {"TERMINOWOSC": procent(100)})
    assert "w wyznaczonym czasie" in wskazanie.uzasadnienie


# --- konfiguracja ---

def test_domyslna_konfiguracja_wiaze_fakty_tylko_z_kryteriami_z_wykazu():
    ustawienia = wczytaj_ustawienia()
    assert {powiazanie.kryterium for powiazanie in ustawienia.powiazania} <= set(KATALOG)
    assert all(set(powiazanie.wskazniki) <= set(WSKAZNIKI_PROCENTOWE) for powiazanie in ustawienia.powiazania)


def test_symulacja_korzysta_tylko_ze_wskaznikow_procentowych_rdzenia():
    """Liczba spraw czy mediana dni nie mają naturalnej skali, więc nie da się ich uczciwie przełożyć na ocenę."""
    wszystkie = wskazniki_pracy(sprawy=[], od=date(2026, 1, 1), do=date(2026, 12, 31))
    assert set(WSKAZNIKI_PROCENTOWE) == {wskaznik.kod for wskaznik in wszystkie if wskaznik.jednostka == "%"}


@pytest.mark.parametrize(
    "tresc",
    [
        "[progi_procentowe]\n9 = 95\n7 = 85\n5 = 70\n" + POWIAZANIE,
        "[progi_procentowe]\n9 = 95\n7 = 85\n5 = 70\n3 = 50\n1 = 10\n" + POWIAZANIE,
        "[progi_procentowe]\n9 = 95\n7 = 85\n5 = 70\n3 = 50\n4 = 60\n" + POWIAZANIE,
        "[progi_procentowe]\n9 = 70\n7 = 85\n5 = 95\n3 = 50\n" + POWIAZANIE,
        "[progi_procentowe]\n9 = 195\n7 = 85\n5 = 70\n3 = 50\n" + POWIAZANIE,
        PROGI + POWIAZANIE.replace("Rzetelność", "Punktualność"),
        PROGI + POWIAZANIE.replace("TERMINOWOSC", "SPRAWY_ZAKONCZONE"),
        PROGI + POWIAZANIE + POWIAZANIE,
        POWIAZANIE,
    ],
    ids=[
        "brak progu dla oceny ze skali", "próg dla najniższej oceny", "próg dla oceny spoza skali",
        "progi nie rosną z oceną", "próg powyżej 100", "kryterium spoza wykazu", "wskaźnik nieprocentowy",
        "kryterium powtórzone", "brak progów",
    ],
)
def test_niespojna_konfiguracja_symulacji_jest_odrzucana(tmp_path, tresc):
    with pytest.raises(ValueError):
        ustawienia_z(tmp_path, tresc)
