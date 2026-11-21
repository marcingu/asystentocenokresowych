"""Wymaganie: przepisy jako konfiguracja - zmiana prawa nie wymaga przebudowy systemu.

Źródło: treść wyzwania KPRM, pkt 5 („elastyczne i otwarte na modyfikacje wynikające ze zmian przepisów
(...) zmiana częstotliwości ocen, zasad wyznaczania terminów czy elementów oceny nie powinny stanowić
bariery”) oraz kryterium oceny „potencjał wdrożeniowy (możliwość aktualizacji)” - 30%.
"""

import dataclasses

from asystent_ocen.kalendarz import czy_dzien_ustawowo_wolny, przesun_na_dzien_roboczy
from asystent_ocen.konfiguracja import Swieto, wczytaj_przepisy
from asystent_ocen.terminy import termin_oceny
from stale import KATALOG, OBOWIAZKOWE_A, OBOWIAZKOWE_B, OBOWIAZKOWE_C, d


def test_domyslne_terminy_odpowiadaja_ustawie_i_rozporzadzeniu():
    """art. 81 ust. 4, 7, 8, 9 i art. 83, 89 u.s.c.; § 7 i § 9 rozp."""
    p = wczytaj_przepisy()
    assert p.cykl_oceny_miesiace == 24
    assert p.termin_kryteriow_dni == 30
    assert p.termin_kryteriow_po_negatywnej_dni == 7
    assert p.ponowna_ocena_po_negatywnej_miesiace == 6
    assert p.min_miesiecy_do_zmiany_terminu == 6
    assert p.prog_nieobecnosci_miesiace == 1
    assert p.zmiana_stanowiska_najwczesniej_dni_przed == 7
    assert p.zmiana_stanowiska_najpozniej_dni_po == 30
    assert p.sprzeciw_dni == 7
    assert p.rozpatrzenie_sprzeciwu_dni == 14
    assert p.odwolanie_do_sadu_dni == 14
    assert p.stopien_obligatoryjny_dni == 30


def test_domyslna_skala_i_limity_odpowiadaja_rozporzadzeniu():
    """§ 11 ust. 1 pkt 1 i § 5 ust. 2 rozp.; art. 86 ust. 1 u.s.c. (dziewięć stopni)."""
    p = wczytaj_przepisy()
    assert tuple(p.skala) == (1, 3, 5, 7, 9)
    assert p.max_kryteriow_dodatkowych == 3
    assert p.max_stopien_sluzbowy == 9


def test_rozstrzygniecia_interpretacyjne_sa_jawnymi_przelacznikami_w_konfiguracji():
    """Decyzje zespołu z 21.11.2026 w miejscach, w których źródła KPRM są rozbieżne albo przepisy milczą."""
    p = wczytaj_przepisy()
    assert p.pierwsza_ocena_6_miesiecy_od == "nawiazanie_stosunku_pracy"
    assert p.ponowna_ocena_w_dniu_roboczym is True
    assert p.miejsca_po_przecinku_sredniej == 1


def test_domyslne_arkusze_i_wykaz_kryteriow_odpowiadaja_rozporzadzeniu():
    """§ 4 rozp. i załącznik nr 1 do rozp."""
    p = wczytaj_przepisy()
    assert list(p.arkusze["A"]) == OBOWIAZKOWE_A
    assert list(p.arkusze["B"]) == OBOWIAZKOWE_B
    assert list(p.arkusze["C"]) == OBOWIAZKOWE_C
    assert sorted(p.katalog_kryteriow) == sorted(KATALOG)


def test_zmiana_czestotliwosci_ocen_w_konfiguracji_zmienia_termin_bez_zmiany_kodu():
    """Przykład z przypisu 3 treści wyzwania: zmiana częstotliwości ocen."""
    p12 = dataclasses.replace(wczytaj_przepisy(), cykl_oceny_miesiace=12)
    assert termin_oceny(d(2026, 3, 16), przepisy=p12) == d(2027, 3, 16)


def test_nowe_swieto_dodane_w_konfiguracji_przesuwa_koniec_terminu():
    p = wczytaj_przepisy()
    nowe = dataclasses.replace(p, swieta=tuple(p.swieta) + (Swieto(nazwa="Nowe święto", data="03-16"),))
    # 16.03.2026 to poniedziałek - bez nowego święta termin się nie przesuwa
    assert przesun_na_dzien_roboczy(d(2026, 3, 16), przepisy=p) == d(2026, 3, 16)
    assert przesun_na_dzien_roboczy(d(2026, 3, 16), przepisy=nowe) == d(2026, 3, 17)


def test_swieto_obowiazuje_dopiero_od_roku_wskazanego_w_konfiguracji():
    """Wigilia jest dniem wolnym od 2025 r. (ustawa z 6.12.2024 r., Dz. U. poz. 1965)."""
    assert czy_dzien_ustawowo_wolny(d(2024, 12, 24)) is False
    assert czy_dzien_ustawowo_wolny(d(2025, 12, 24)) is True


def test_przepisy_mozna_wczytac_z_innego_pliku(tmp_path):
    """Urząd lub KPRM może dostarczyć zaktualizowany plik przepisów bez zmiany kodu."""
    from asystent_ocen.konfiguracja import DOMYSLNY_PLIK

    tresc = DOMYSLNY_PLIK.read_text(encoding="utf-8").replace(
        "cykl_oceny_miesiace = 24", "cykl_oceny_miesiace = 36"
    )
    plik = tmp_path / "przepisy_po_nowelizacji.toml"
    plik.write_text(tresc, encoding="utf-8")
    assert wczytaj_przepisy(plik).cykl_oceny_miesiace == 36
