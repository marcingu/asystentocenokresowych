"""Wymaganie: każda funkcja AI ma jawną klasyfikację według AI Act, a funkcji wysokiego ryzyka i zakazanych
nie da się włączyć w tej wersji systemu.

Źródła: rozporządzenie (UE) 2024/1689 w wersji skonsolidowanej z 27.07.2026 - art. 5 ust. 1 lit. f,
art. 6 ust. 2-4, załącznik III pkt 4 lit. b, art. 49 ust. 2, art. 50 ust. 1, motywy 12 i 53;
art. 4 pkt 4 RODO (profilowanie); dokumentacja/analiza-prawna-ai-act-kp-rodo.md.
"""

import dataclasses

import pytest

from asystent_ocen.zgodnosc import (
    BladZgodnosci,
    FunkcjaAI,
    rejestr_funkcji_ai,
    sprawdz_rejestr_funkcji_ai,
    wczytaj_wymogi,
    wymagaj_dozwolonej_funkcji_ai,
)

KLASYFIKACJE = {
    "PYTANIA_O_PROCEDURE": "poza_zalacznikiem_III",
    "KOREKTA_JEZYKOWA_UZASADNIENIA": "wyjatek_art_6_ust_3",
    "REDAKCJA_NOTATEK_OCENIAJACEGO": "wyjatek_art_6_ust_3",
    "PROPOZYCJA_OCENY": "wysokie_ryzyko",
    "PODSUMOWANIE_PRACY_PRACOWNIKA": "wysokie_ryzyko",
    "REKOMENDACJA_KADROWA": "wysokie_ryzyko",
    "ANALIZA_EMOCJI": "zakazana",
}


def funkcja(**zmiany):
    wzor = FunkcjaAI(
        kod="TESTOWA", opis="Funkcja testowa.", klasyfikacja="poza_zalacznikiem_III", podstawa="art. X", wlaczona=True
    )
    return dataclasses.replace(wzor, **zmiany)


def test_rejestr_zawiera_klasyfikacje_wszystkich_funkcji_ai():
    assert {f.kod: f.klasyfikacja for f in rejestr_funkcji_ai()} == KLASYFIKACJE


def test_kazda_funkcja_ai_ma_opis_i_podstawe_klasyfikacji():
    assert all(f.opis.strip() and f.podstawa.strip() for f in rejestr_funkcji_ai())


def test_wlaczone_sa_tylko_funkcje_spoza_wysokiego_ryzyka():
    """Ocena wydajności i zachowania pracownika to zał. III pkt 4 lit. b AI Act, a ocena efektów pracy jest
    profilowaniem (art. 4 pkt 4 RODO), więc wyjątek z art. 6 ust. 3 nie działa - takich funkcji nie włączamy.

    Redakcja notatek oceniającego (moduł HR Copilot z architektury zespołu) jest włączona jako zadanie
    przygotowawcze: model składa w tekst notatki napisane przez człowieka, bez ocen i bez danych z EZD RP.
    """
    wlaczone = {f.kod for f in rejestr_funkcji_ai() if f.wlaczona}
    assert wlaczone == {"PYTANIA_O_PROCEDURE", "KOREKTA_JEZYKOWA_UZASADNIENIA", "REDAKCJA_NOTATEK_OCENIAJACEGO"}


@pytest.mark.decyzja_projektowa
def test_redakcja_notatek_ma_w_rejestrze_opisane_granice():
    """Kwalifikacja robocza z 21.11.2026 (art. 6 ust. 3 lit. d AI Act: „zadania przygotowawcze w kontekście oceny”)
    - do potwierdzenia przez prawnika przed wdrożeniem produkcyjnym."""
    funkcja = next(f for f in rejestr_funkcji_ai() if f.kod == "REDAKCJA_NOTATEK_OCENIAJACEGO")
    assert "6 ust. 3 lit. d" in funkcja.podstawa
    assert "EZD RP" in funkcja.opis and "ocen" in funkcja.opis


@pytest.mark.parametrize("klasyfikacja", ["wysokie_ryzyko", "zakazana"])
def test_konfiguracja_wlaczajaca_funkcje_wysokiego_ryzyka_lub_zakazana_jest_odrzucana(klasyfikacja):
    with pytest.raises(BladZgodnosci):
        sprawdz_rejestr_funkcji_ai([funkcja(klasyfikacja=klasyfikacja, wlaczona=True)])


def test_wylaczona_funkcja_wysokiego_ryzyka_moze_byc_opisana_w_rejestrze():
    sprawdz_rejestr_funkcji_ai([funkcja(klasyfikacja="wysokie_ryzyko", wlaczona=False)])


@pytest.mark.parametrize(
    "zmiany",
    [{"klasyfikacja": "niskie_ryzyko"}, {"podstawa": "  "}],
    ids=["nieznana klasyfikacja", "brak podstawy"],
)
def test_funkcja_bez_poprawnej_klasyfikacji_albo_podstawy_jest_odrzucana(zmiany):
    with pytest.raises(BladZgodnosci):
        sprawdz_rejestr_funkcji_ai([funkcja(**zmiany)])


def test_powtorzony_kod_funkcji_jest_odrzucany():
    with pytest.raises(BladZgodnosci):
        sprawdz_rejestr_funkcji_ai([funkcja(), funkcja()])


@pytest.mark.parametrize(
    "kod", ["PYTANIA_O_PROCEDURE", "KOREKTA_JEZYKOWA_UZASADNIENIA", "REDAKCJA_NOTATEK_OCENIAJACEGO"]
)
def test_dozwolona_funkcja_ai_jest_zwracana(kod):
    assert wymagaj_dozwolonej_funkcji_ai(kod).kod == kod


@pytest.mark.parametrize(
    "kod", ["PROPOZYCJA_OCENY", "PODSUMOWANIE_PRACY_PRACOWNIKA", "REKOMENDACJA_KADROWA", "ANALIZA_EMOCJI", "NIEZNANA"]
)
def test_uzycie_niedozwolonej_albo_nieznanej_funkcji_ai_jest_blokowane(kod):
    with pytest.raises(BladZgodnosci):
        wymagaj_dozwolonej_funkcji_ai(kod)


def test_wylaczona_w_konfiguracji_funkcja_niskiego_ryzyka_tez_jest_blokowana():
    """Urząd może wyłączyć każdą funkcję AI (wariant bez AI dla małych urzędów)."""
    wymogi = wczytaj_wymogi()
    bez_ai = dataclasses.replace(
        wymogi, funkcje_ai=tuple(dataclasses.replace(f, wlaczona=False) for f in wymogi.funkcje_ai)
    )
    with pytest.raises(BladZgodnosci):
        wymagaj_dozwolonej_funkcji_ai("PYTANIA_O_PROCEDURE", wymogi=bez_ai)


def test_odmowa_podaje_podstawe_klasyfikacji():
    with pytest.raises(BladZgodnosci) as blad:
        wymagaj_dozwolonej_funkcji_ai("ANALIZA_EMOCJI")
    assert "5 ust. 1 lit. f" in str(blad.value)
