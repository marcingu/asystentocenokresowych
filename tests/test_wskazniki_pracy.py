"""Wymaganie: z danych EZD RP system wylicza jawne, sprawdzalne wskaźniki pracy (bez AI) - kartę faktów
dla oceniającego i ocenianego: szybkość i terminowość załatwiania spraw, uwagi przełożonych do projektów pism,
utrzymanie rozstrzygnięć po odwołaniu.

Źródła: art. 81 ust. 3 u.s.c. (ocena dotyczy wykonywania obowiązków wynikających z opisu stanowiska);
art. 94 pkt 9 Kodeksu pracy (obiektywne i sprawiedliwe kryteria oceny pracowników oraz wyników ich pracy);
pola Integrator API v2 EZD RP v2.11.5 (dataWszczecia, terminZalatwienia, status, akceptacje dokumentu);
decyzje projektowe: mediana zamiast średniej, minimalna liczność 5, brak oceny zbiorczej i rankingu.
"""

import dataclasses
from fractions import Fraction

import pytest

from asystent_ocen.wskazniki_pracy import (
    KODY_WSKAZNIKOW,
    AkceptacjaEzd,
    Odwolanie,
    SprawaEzd,
    formatuj_wskaznik,
    wskazniki_pracy,
)
from asystent_ocen.zgodnosc import wczytaj_wymogi
from stale import d

OD, DO = d(2025, 1, 1), d(2026, 12, 31)


def sprawa(nr, rok, wszczecie, termin, zakonczenie, status=None):
    return SprawaEzd(
        id=f"s{nr}",
        znak=f"DA.III.4000.{nr}.{rok}",
        tytul=f"Sprawa nr {nr}",
        status=status or ("zakończona" if zakonczenie else "w toku"),
        data_wszczecia=wszczecie,
        termin_zalatwienia=termin,
        data_zakonczenia=zakonczenie,
    )


# czasy załatwienia spraw 1-5: 17, 30, 44, 10 i 20 dni; po terminie zakończono tylko sprawę nr 3
SPRAWY = [
    sprawa(1, 2025, d(2025, 2, 3), d(2025, 3, 5), d(2025, 2, 20)),
    sprawa(2, 2025, d(2025, 3, 10), d(2025, 4, 9), d(2025, 4, 9)),
    sprawa(3, 2025, d(2025, 4, 1), d(2025, 5, 1), d(2025, 5, 15)),
    sprawa(4, 2025, d(2025, 6, 2), d(2025, 7, 2), d(2025, 6, 12)),
    sprawa(5, 2025, d(2025, 9, 1), d(2025, 10, 1), d(2025, 9, 21)),
    sprawa(6, 2026, d(2026, 10, 1), d(2026, 10, 31), None),  # w toku, po terminie
    sprawa(7, 2026, d(2026, 12, 15), d(2027, 1, 14), None),  # w toku, w terminie
    sprawa(8, 2024, d(2024, 10, 1), d(2024, 10, 31), d(2024, 12, 20)),  # zakończona przed okresem
    sprawa(9, 2026, d(2026, 9, 1), d(2026, 10, 1), None, status="zawieszona"),  # termin nie biegnie
]

AKCEPTACJE = [
    AkceptacjaEzd("dok-A", "odrzucony", d(2025, 2, 10), "Ewa Lis", "Brak podstawy prawnej w rozstrzygnięciu.", "1"),
    AkceptacjaEzd("dok-A", "zaakceptowany", d(2025, 2, 12), "Ewa Lis", "", "2"),
    AkceptacjaEzd("dok-B", "zaakceptowany", d(2025, 4, 1), "Ewa Lis"),
    AkceptacjaEzd("dok-C", "zaakceptowany", d(2025, 6, 3), "Ewa Lis"),
    AkceptacjaEzd("dok-D", "zaakceptowany", d(2025, 9, 9), "Ewa Lis"),
    AkceptacjaEzd("dok-E", "zaakceptowany", d(2025, 10, 6), "Ewa Lis", "", "2"),
    AkceptacjaEzd("dok-E", "odrzucony", d(2025, 10, 2), "Ewa Lis", "Uzupełnić uzasadnienie faktyczne.", "1"),
    AkceptacjaEzd("dok-F", "do akceptacji", d(2026, 12, 30), "Ewa Lis"),  # jeszcze bez rozstrzygnięcia
    AkceptacjaEzd("dok-G", "anulowany", d(2026, 3, 3), "Ewa Lis"),  # anulowanie nie jest oceną projektu
    AkceptacjaEzd("dok-H", "odrzucony", d(2024, 11, 5), "Ewa Lis", "Poza okresem."),  # przed okresem
]

ODWOLANIA = [
    Odwolanie("DA.III.4000.1.2025", "utrzymana", d(2025, 6, 30)),
    Odwolanie("DA.III.4000.2.2025", "utrzymana", d(2025, 8, 4)),
    Odwolanie("DA.III.4000.3.2025", "uchylona", d(2025, 9, 15)),
    Odwolanie("DA.III.4000.4.2025", "utrzymana", d(2025, 10, 20)),
    Odwolanie("DA.III.4000.5.2025", "utrzymana", d(2026, 1, 12)),
    Odwolanie("DA.III.4000.6.2026", "w toku", None),
    Odwolanie("DA.III.4000.8.2024", "uchylona", d(2024, 12, 30)),  # rozstrzygnięte przed okresem
]


def karta(sprawy=SPRAWY, akceptacje=AKCEPTACJE, odwolania=ODWOLANIA, **kw):
    wynik = wskazniki_pracy(sprawy=sprawy, akceptacje=akceptacje, odwolania=odwolania, od=OD, do=DO, **kw)
    return {w.kod: w for w in wynik}


# --- zakres karty faktów ---

def test_karta_faktow_zawiera_wylacznie_zdefiniowane_wskazniki_w_stalej_kolejnosci():
    """Zamknięta lista: bez oceny zbiorczej, rankingu i propozycji ocen (te byłyby profilowaniem służącym
    ocenie - patrz analiza prawna)."""
    wynik = wskazniki_pracy(sprawy=SPRAWY, akceptacje=AKCEPTACJE, odwolania=ODWOLANIA, od=OD, do=DO)
    assert tuple(w.kod for w in wynik) == KODY_WSKAZNIKOW
    assert KODY_WSKAZNIKOW == (
        "SPRAWY_ZAKONCZONE",
        "MEDIANA_CZASU_ZALATWIENIA",
        "TERMINOWOSC",
        "SPRAWY_W_TOKU_PO_TERMINIE",
        "PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM",
        "PROJEKTY_ODRZUCONE",
        "ROZSTRZYGNIECIA_UTRZYMANE",
    )


def test_kazdy_wskaznik_ma_nazwe_i_jednostke():
    assert all(w.nazwa.strip() and w.jednostka in ("szt.", "dni", "%") for w in karta().values())


# --- szybkość i terminowość spraw ---

def test_liczba_spraw_zakonczonych_w_okresie_z_lista_znakow_do_sprawdzenia():
    w = karta()["SPRAWY_ZAKONCZONE"]
    assert (w.wartosc, w.jednostka, w.licznosc) == (5, "szt.", 5)
    assert w.zrodla == (
        "DA.III.4000.1.2025",
        "DA.III.4000.2.2025",
        "DA.III.4000.3.2025",
        "DA.III.4000.4.2025",
        "DA.III.4000.5.2025",
    )


def test_mediana_czasu_zalatwienia_w_dniach_kalendarzowych():
    """Czasy 17, 30, 44, 10 i 20 dni -> mediana 20 dni."""
    w = karta()["MEDIANA_CZASU_ZALATWIENIA"]
    assert (w.wartosc, w.jednostka, w.licznosc) == (20, "dni", 5)


def test_mediana_przy_parzystej_liczbie_spraw_jest_srednia_dwoch_srodkowych():
    """Dochodzi sprawa załatwiona w 14 dni: 10, 14, 17, 20, 30, 44 -> (17 + 20) / 2 = 18,5."""
    szosta = sprawa(10, 2026, d(2026, 3, 2), d(2026, 4, 1), d(2026, 3, 16))
    w = karta(sprawy=SPRAWY + [szosta])["MEDIANA_CZASU_ZALATWIENIA"]
    assert w.wartosc == Fraction(37, 2)
    assert formatuj_wskaznik(w) == "18,5 dni"


def test_terminowosc_to_udzial_spraw_zakonczonych_najpozniej_w_dniu_terminu():
    """Sprawa nr 2 zakończona w dniu terminu liczy się jako terminowa; po terminie tylko sprawa nr 3."""
    w = karta()["TERMINOWOSC"]
    assert (w.wartosc, w.jednostka, w.licznosc) == (Fraction(4, 5), "%", 5)
    assert len(w.szczegoly) == 1 and "DA.III.4000.3.2025" in w.szczegoly[0]


def test_sprawy_bez_terminu_zalatwienia_nie_wchodza_do_terminowosci():
    bez_terminu = sprawa(11, 2026, d(2026, 5, 4), None, d(2026, 5, 20))
    w = karta(sprawy=SPRAWY + [bez_terminu])
    assert w["TERMINOWOSC"].licznosc == 5
    assert w["SPRAWY_ZAKONCZONE"].wartosc == 6


def test_sprawy_w_toku_po_terminie_na_koniec_okresu():
    """Sprawa nr 6: termin 31.10.2026, niezakończona. Nr 7 jest w terminie, nr 9 zawieszona."""
    w = karta()["SPRAWY_W_TOKU_PO_TERMINIE"]
    assert (w.wartosc, w.jednostka) == (1, "szt.")
    assert w.zrodla == ("DA.III.4000.6.2026",)


def test_sprawa_zakonczona_po_okresie_liczy_sie_jako_bedaca_w_toku_na_koniec_okresu():
    pozniej = sprawa(12, 2026, d(2026, 11, 2), d(2026, 12, 2), d(2027, 1, 20))
    w = karta(sprawy=SPRAWY + [pozniej])
    # kolejność: od najdawniej przeterminowanej (termin 31.10.2026 przed 2.12.2026)
    assert w["SPRAWY_W_TOKU_PO_TERMINIE"].zrodla == ("DA.III.4000.6.2026", "DA.III.4000.12.2026")
    assert w["SPRAWY_ZAKONCZONE"].wartosc == 5


# --- uwagi przełożonych do projektów pism ---

def test_udzial_projektow_zaakceptowanych_za_pierwszym_razem():
    """Dokumenty A-E mają rozstrzygnięcie w okresie; A i E najpierw odrzucono -> 3 z 5. Kolejność rekordów
    wejściowych nie ma znaczenia (dok-E podano od końca)."""
    w = karta()["PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM"]
    assert (w.wartosc, w.jednostka, w.licznosc) == (Fraction(3, 5), "%", 5)
    assert w.zrodla == ("dok-A", "dok-B", "dok-C", "dok-D", "dok-E")


def test_odrzucone_projekty_sa_podane_razem_z_uwagami_przelozonego():
    w = karta()["PROJEKTY_ODRZUCONE"]
    assert (w.wartosc, w.jednostka) == (2, "szt.")
    assert len(w.szczegoly) == 2
    assert "Brak podstawy prawnej w rozstrzygnięciu." in w.szczegoly[0] and "Ewa Lis" in w.szczegoly[0]
    assert "Uzupełnić uzasadnienie faktyczne." in w.szczegoly[1]


# --- prawidłowość merytoryczna: odwołania ---

def test_udzial_rozstrzygniec_utrzymanych_po_odwolaniu():
    """5 odwołań rozstrzygniętych w okresie, 4 utrzymane. Odwołanie w toku i rozstrzygnięte przed okresem
    nie są liczone."""
    w = karta()["ROZSTRZYGNIECIA_UTRZYMANE"]
    assert (w.wartosc, w.jednostka, w.licznosc) == (Fraction(4, 5), "%", 5)
    assert "DA.III.4000.3.2025" in w.zrodla and "DA.III.4000.6.2026" not in w.zrodla


def test_decyzja_zmieniona_przez_organ_odwolawczy_nie_jest_utrzymana():
    zmieniona = Odwolanie("DA.III.4000.9.2026", "zmieniona", d(2026, 11, 3))
    w = karta(odwolania=ODWOLANIA + [zmieniona])["ROZSTRZYGNIECIA_UTRZYMANE"]
    assert (w.wartosc, w.licznosc) == (Fraction(4, 6), 6)


# --- ostrożność statystyczna ---

@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize(
    "kod", ["MEDIANA_CZASU_ZALATWIENIA", "TERMINOWOSC", "PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM", "ROZSTRZYGNIECIA_UTRZYMANE"]
)
def test_przy_zbyt_malej_liczbie_zdarzen_wskaznik_nie_jest_liczony(kod):
    """Minimalna liczność 5: z czterech spraw, czterech dokumentów i czterech odwołań nie liczymy mediany
    ani udziałów - pojedyncze zdarzenie przesądzałoby o wyniku."""
    w = karta(
        sprawy=SPRAWY[:4],
        akceptacje=[a for a in AKCEPTACJE if a.id_dokumentu != "dok-E"],
        odwolania=ODWOLANIA[:4],
    )[kod]
    assert w.wartosc is None and w.licznosc == 4
    assert "za mało danych" in w.uwaga and "4" in w.uwaga and "5" in w.uwaga
    assert formatuj_wskaznik(w) == w.uwaga


def test_liczniki_sa_podawane_takze_przy_malej_liczbie_zdarzen():
    w = karta(sprawy=SPRAWY[:4], akceptacje=[], odwolania=[])
    assert w["SPRAWY_ZAKONCZONE"].wartosc == 4
    assert w["PROJEKTY_ODRZUCONE"].wartosc == 0
    assert w["ROZSTRZYGNIECIA_UTRZYMANE"].wartosc is None and w["ROZSTRZYGNIECIA_UTRZYMANE"].licznosc == 0


def test_minimalna_licznosc_pochodzi_z_konfiguracji():
    luzniejsze = dataclasses.replace(wczytaj_wymogi(), min_licznosc_wskaznika=3)
    w = karta(sprawy=SPRAWY[:4], wymogi=luzniejsze)["MEDIANA_CZASU_ZALATWIENIA"]
    assert w.wartosc == Fraction(47, 2)  # 10, 17, 30, 44 -> (17 + 30) / 2


# --- prezentacja ---

def test_prezentacja_wskaznikow_na_karcie_faktow():
    w = karta()
    assert formatuj_wskaznik(w["SPRAWY_ZAKONCZONE"]) == "5"
    assert formatuj_wskaznik(w["MEDIANA_CZASU_ZALATWIENIA"]) == "20 dni"
    assert formatuj_wskaznik(w["TERMINOWOSC"]) == "80%"
    assert formatuj_wskaznik(w["PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM"]) == "60%"


def test_procenty_sa_zaokraglane_arytmetycznie_do_pelnych():
    """4 z 6 = 66,67% -> „67%”."""
    zmieniona = Odwolanie("DA.III.4000.9.2026", "zmieniona", d(2026, 11, 3))
    w = karta(odwolania=ODWOLANIA + [zmieniona])["ROZSTRZYGNIECIA_UTRZYMANE"]
    assert formatuj_wskaznik(w) == "67%"
