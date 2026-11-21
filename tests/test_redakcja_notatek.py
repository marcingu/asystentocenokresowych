"""Redakcja notatek oceniającego: model składa własne notatki przełożonego w projekt tekstu uzasadnienia.

Wymaganie zespołu (architektura v3 i v4, moduł HR Copilot): asystent czyta notatki oceniającego i proponuje tekst,
który oceniający sam przenosi do formularza. Granice funkcji: model nie dostaje ocen cząstkowych, wyniku oceny
ani danych z EZD RP i nie proponuje ocen. Podstawy: zał. III pkt 4 lit. b oraz art. 6 ust. 3 lit. d AI Act
(zadanie przygotowawcze), rozporządzenie (UE) 2024/1689 w wersji skonsolidowanej z 27.07.2026.
"""

import dataclasses
import inspect

import pytest

from asystent_ocen.asystent_ai import (
    FUNKCJA_REDAKCJI,
    ODMOWA_BRAK_NOTATEK,
    ZASADY_REDAKCJI,
    BladModelu,
    zredaguj_notatki,
)
from asystent_ocen.zgodnosc import BladZgodnosci, wczytaj_wymogi

NOTATKI = [
    "Przygotowała projekt procedury obiegu korespondencji; wdrożony bez poprawek.",
    "W drugim kwartale załatwiła 12 spraw, żadna nie przekroczyła terminu.",
]


class ModelAtrapa:
    """Zapamiętuje wiadomości i zwraca ustaloną odpowiedź."""

    def __init__(self, odpowiedz: str = "Tekst zredagowany."):
        self.odpowiedz = odpowiedz
        self.wiadomosci: list[list[dict]] = []

    def __call__(self, wiadomosci: list[dict]) -> str:
        self.wiadomosci.append(wiadomosci)
        return self.odpowiedz

    @property
    def wyslane(self) -> str:
        return "\n".join(wiadomosc["content"] for rozmowa in self.wiadomosci for wiadomosc in rozmowa)


def test_model_dostaje_notatki_i_zasady_redakcji():
    model = ModelAtrapa("Przygotowała projekt procedury obiegu korespondencji, wdrożony bez poprawek.")

    wynik = zredaguj_notatki(NOTATKI, model=model)

    assert wynik.propozycja == "Przygotowała projekt procedury obiegu korespondencji, wdrożony bez poprawek."
    assert not wynik.odmowa
    rozmowa = model.wiadomosci[0]
    assert rozmowa[0] == {"role": "system", "content": ZASADY_REDAKCJI}
    assert all(notatka in rozmowa[-1]["content"] for notatka in NOTATKI)


def test_funkcja_nie_ma_wejscia_na_oceny_wynik_ani_dane_z_ezd():
    """Gwarancja konstrukcyjna: do modelu nie da się przekazać ocen cząstkowych ani wskaźników pracy."""
    parametry = set(inspect.signature(zredaguj_notatki).parameters)
    assert parametry == {"notatki", "model", "wymogi", "osoby"}


def test_zasady_zakazuja_proponowania_ocen_i_dopisywania_faktow():
    zasady = ZASADY_REDAKCJI.lower()
    assert "nie proponuj ocen" in zasady
    assert "wyłącznie" in zasady and "notat" in zasady
    assert "nie dodawaj" in zasady


def test_dane_osobowe_nie_trafiaja_do_modelu_a_wracaja_w_propozycji():
    notatki = ["Anna Nowak (PESEL 90010112345) przeprowadziła szkolenie z EZD RP."]
    model = ModelAtrapa("[OSOBA_1] przeprowadziła szkolenie z EZD RP.")

    wynik = zredaguj_notatki(notatki, model=model, osoby=["Anna Nowak"])

    assert "Anna Nowak" not in model.wyslane
    assert "90010112345" not in model.wyslane
    assert wynik.propozycja == "Anna Nowak przeprowadziła szkolenie z EZD RP."


@pytest.mark.parametrize("notatki", [[], ["", "   "]], ids=["brak", "same puste"])
def test_bez_notatek_asystent_odmawia_bez_wywolania_modelu(notatki):
    """Bez notatek model musiałby zmyślać - uzasadnienie pisze wtedy oceniający."""
    model = ModelAtrapa()

    wynik = zredaguj_notatki(notatki, model=model)

    assert (wynik.odmowa, wynik.powod, wynik.propozycja) == (True, ODMOWA_BRAK_NOTATEK, "")
    assert model.wiadomosci == []


def test_liczba_spoza_notatek_daje_ostrzezenie():
    model = ModelAtrapa("W drugim kwartale załatwiła 15 spraw w terminie.")

    wynik = zredaguj_notatki(NOTATKI, model=model)

    assert any("15" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


@pytest.mark.parametrize(
    "tekst",
    [
        "Praca zasługuje na ocenę powyżej oczekiwań.",
        "Proponuję ocenę pozytywną.",
        "Wykonuje obowiązki znacznie poniżej oczekiwań.",
        "Za kryterium rzetelność należy przyznać 7 punktów.",
    ],
)
def test_sformulowanie_o_ocenie_albo_poziomie_daje_ostrzezenie(tekst):
    """Ocenę i poziom ustala wyłącznie oceniający - tekst modelu nie może ich podsuwać."""
    wynik = zredaguj_notatki(NOTATKI, model=ModelAtrapa(tekst))

    assert any("ocen" in ostrzezenie.lower() for ostrzezenie in wynik.ostrzezenia)


def test_tekst_wyraznie_dluzszy_niz_notatki_daje_ostrzezenie():
    model = ModelAtrapa("Zdanie spoza notatek. " * 40)

    wynik = zredaguj_notatki(NOTATKI, model=model)

    assert any("dłuższy" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_wierna_redakcja_nie_ma_ostrzezen():
    model = ModelAtrapa(
        "Przygotowała projekt procedury obiegu korespondencji, który wdrożono bez poprawek. "
        "W drugim kwartale załatwiła 12 spraw i żadna nie przekroczyła terminu."
    )

    assert zredaguj_notatki(NOTATKI, model=model).ostrzezenia == ()


def test_pole_do_uzupelnienia_w_projekcie_daje_ostrzezenie():
    """Sprawdzian na lokalnym modelu (21.11.2026): model potrafi zostawić szablon z polami w nawiasach
    kwadratowych zamiast treści z notatek."""
    model = ModelAtrapa("W okresie od [DATA_OD] załatwiła 12 spraw w terminie.")

    wynik = zredaguj_notatki(NOTATKI, model=model)

    assert any("[DATA_OD]" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_liczba_z_notatek_pominieta_w_projekcie_daje_ostrzezenie():
    model = ModelAtrapa("Przygotowała projekt procedury obiegu korespondencji. Sprawy załatwiała w terminie.")

    wynik = zredaguj_notatki(NOTATKI, model=model)

    assert any("12" in ostrzezenie and "brakuje" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_miesiac_slownie_i_mala_liczba_slownie_nie_daja_ostrzezenia():
    """Wierny projekt może zapisać „12.03.2026” jako „12 marca 2026 r.”, a „3 osoby” jako „trzy osoby”."""
    notatki = ["12.03.2026 przeszkoliła 3 osoby z obsługi rejestru."]
    model = ModelAtrapa("12 marca 2026 r. przeszkoliła trzy osoby z obsługi rejestru.")

    assert zredaguj_notatki(notatki, model=model).ostrzezenia == ()


def test_o_znacznikach_model_dowiaduje_sie_tylko_gdy_notatki_zawieraja_dane_osobowe():
    """Sprawdzian na lokalnym modelu (21.11.2026): wzmianka o znacznikach bez potrzeby skłania model do
    wymyślania własnych pól w nawiasach kwadratowych."""
    bez_danych, z_danymi = ModelAtrapa(), ModelAtrapa("[OSOBA_1] prowadzi rejestr.")

    zredaguj_notatki(NOTATKI, model=bez_danych)
    zredaguj_notatki(["Anna Nowak prowadzi rejestr."], model=z_danymi, osoby=["Anna Nowak"])

    assert "[" not in bez_danych.wyslane
    assert "[OSOBA_1]" in z_danymi.wyslane


def test_funkcja_wylaczona_w_rejestrze_nie_wywoluje_modelu():
    """Urząd może wyłączyć redakcję notatek jedną zmianą w zgodnosc.toml."""
    wymogi = wczytaj_wymogi()
    bez_redakcji = dataclasses.replace(
        wymogi,
        funkcje_ai=tuple(
            dataclasses.replace(funkcja, wlaczona=funkcja.kod != FUNKCJA_REDAKCJI) for funkcja in wymogi.funkcje_ai
        ),
    )
    model = ModelAtrapa()

    with pytest.raises(BladZgodnosci):
        zredaguj_notatki(NOTATKI, model=model, wymogi=bez_redakcji)
    assert model.wiadomosci == []


def test_pusta_odpowiedz_modelu_jest_bledem_a_nie_pusta_propozycja():
    with pytest.raises(BladModelu):
        zredaguj_notatki(NOTATKI, model=ModelAtrapa("   "))
