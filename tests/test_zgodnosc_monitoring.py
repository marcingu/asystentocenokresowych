"""Wymaganie: integrację z EZD RP (dane o pracy pracownika) można uruchomić dopiero po spełnieniu wymogów
Kodeksu pracy dla „innej formy monitoringu”.

Źródła: art. 22[3] § 3-4 w zw. z art. 22[2] § 6-7 Kodeksu pracy (t.j. Dz. U. z 2026 r. poz. 1245);
art. 9 ust. 1 u.s.c. (Kodeks pracy stosuje się w sprawach nieuregulowanych w ustawie o służbie cywilnej);
dokumentacja/analiza-prawna-ai-act-kp-rodo.md.
"""

import dataclasses

import pytest

from asystent_ocen.zgodnosc import (
    UstaleniaMonitoringu,
    bledy_uruchomienia_monitoringu,
    najwczesniejsze_uruchomienie_monitoringu,
    wczytaj_wymogi,
)
from stale import d

KOMPLETNE = UstaleniaMonitoringu(
    podstawa="Regulamin pracy urzędu, § 14a (zarządzenie nr 12/2026 dyrektora generalnego)",
    cele="Organizacja pracy umożliwiająca pełne wykorzystanie czasu pracy; rzetelna ocena okresowa.",
    zakres="Metadane spraw i akceptacji dokumentów w EZD RP: daty, terminy, statusy, wyniki akceptacji.",
    sposob="Odczyt przez Integrator API w dniu przygotowania oceny; bez treści pism i korespondencji.",
    data_poinformowania=d(2026, 11, 2),
)


def kody(ustalenia, dzien):
    return [b.kod for b in bledy_uruchomienia_monitoringu(ustalenia, dzien=dzien)]


def test_monitoring_mozna_uruchomic_najwczesniej_2_tygodnie_po_poinformowaniu_pracownikow():
    """art. 22[2] § 7 KP: „nie później niż 2 tygodnie przed jego uruchomieniem”. Poniedziałek 2.11.2026
    -> poniedziałek 16.11.2026."""
    assert najwczesniejsze_uruchomienie_monitoringu(d(2026, 11, 2)) == d(2026, 11, 16)


def test_wyprzedzenie_informacji_o_monitoringu_pochodzi_z_konfiguracji():
    dluzsze = dataclasses.replace(wczytaj_wymogi(), monitoring_wyprzedzenie_informacji_dni=21)
    assert najwczesniejsze_uruchomienie_monitoringu(d(2026, 11, 2), wymogi=dluzsze) == d(2026, 11, 23)


def test_kompletne_ustalenia_po_uplywie_2_tygodni_pozwalaja_uruchomic_integracje():
    assert kody(KOMPLETNE, d(2026, 11, 16)) == []


def test_uruchomienie_przed_uplywem_2_tygodni_od_poinformowania_jest_blokowane():
    assert kody(KOMPLETNE, d(2026, 11, 15)) == ["MONITORING_ZA_WCZESNIE"]


@pytest.mark.parametrize(
    "pole, kod",
    [
        ("podstawa", "BRAK_PODSTAWY_MONITORINGU"),
        ("cele", "BRAK_CELOW_MONITORINGU"),
        ("zakres", "BRAK_ZAKRESU_MONITORINGU"),
        ("sposob", "BRAK_SPOSOBU_MONITORINGU"),
    ],
)
def test_brak_ustalen_z_art_22_2_par_6_blokuje_uruchomienie(pole, kod):
    """art. 22[2] § 6 KP: cele, zakres i sposób zastosowania monitoringu ustala się w układzie zbiorowym pracy,
    regulaminie pracy albo obwieszczeniu."""
    assert kody(dataclasses.replace(KOMPLETNE, **{pole: "  "}), d(2026, 12, 1)) == [kod]


def test_brak_poinformowania_pracownikow_blokuje_uruchomienie():
    bez_informacji = dataclasses.replace(KOMPLETNE, data_poinformowania=None)
    assert kody(bez_informacji, d(2026, 12, 1)) == ["BRAK_POINFORMOWANIA_PRACOWNIKOW"]


def test_puste_ustalenia_zglaszaja_wszystkie_braki_naraz():
    puste = UstaleniaMonitoringu(podstawa="", cele="", zakres="", sposob="", data_poinformowania=None)
    assert set(kody(puste, d(2026, 12, 1))) == {
        "BRAK_PODSTAWY_MONITORINGU",
        "BRAK_CELOW_MONITORINGU",
        "BRAK_ZAKRESU_MONITORINGU",
        "BRAK_SPOSOBU_MONITORINGU",
        "BRAK_POINFORMOWANIA_PRACOWNIKOW",
    }


def test_kazda_przeszkoda_wskazuje_przepis_kodeksu_pracy():
    puste = UstaleniaMonitoringu(podstawa="", cele="", zakres="", sposob="", data_poinformowania=None)
    bledy = bledy_uruchomienia_monitoringu(puste, dzien=d(2026, 12, 1))
    bledy += bledy_uruchomienia_monitoringu(KOMPLETNE, dzien=d(2026, 11, 3))
    assert len(bledy) == 6
    assert all("art. 22" in b.podstawa and b.komunikat for b in bledy)
