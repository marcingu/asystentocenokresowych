"""Wirtualny HR partner: pytania do rozmowy oceniającej i propozycja kierunków do IPRZ z notatek oceniającego.

Wymaganie (decyzja prowadzącego projekt z 21.11.2026, wieczorem): w widoku rozmowy oceniającej lokalny model
językowy układa - wyłącznie z notatek przełożonego, tak jak przy projekcie uzasadnienia - listę 3-5 pytań do
rozmowy oraz propozycję kierunków do indywidualnego programu rozwoju zawodowego (IPRZ).

Źródła:
- § 10 rozporządzenia - w trakcie rozmowy oceniającej omawia się obowiązki i sposób ich realizacji
  z uwzględnieniem kryteriów, realizację celów oraz kierunki rozwoju zawodowego i potrzeby szkoleniowe;
- § 11 ust. 1 pkt 5 rozporządzenia i art. 81 ust. 5 u.s.c. - wnioski dotyczące IPRZ są częścią oceny;
- Poradnik KPRM, pkt 6.2.4 (s. 25) - rozmowa ma być dialogiem, a nie monologiem oceniającego;
- AI Act: pytania to zadanie przygotowawcze (art. 6 ust. 3 lit. d - kwalifikacja robocza); wskazanie potrzeb
  rozwojowych konkretnej osoby to ocena czynników osobowych, więc funkcja wysokiego ryzyka (zał. III pkt 4
  lit. b, art. 6 ust. 3 akapit trzeci) - po instalacji wyłączona, włącza ją decyzja urzędu.

Decyzje projektowe: model dostaje wyłącznie notatki bez danych osobowych; pytania o zdrowie i sprawy prywatne
są odrzucane; propozycja kierunków wymaga co najmniej 3 notatek, tak jak sugestia ocen.
"""

import dataclasses
import json
from pathlib import Path

import pytest

from asystent_ocen.asystent_ai import ODMOWA_BRAK_NOTATEK, BladModelu
from asystent_ocen.przygotowanie_rozmowy import (
    FUNKCJA_KIERUNKOW_IPRZ,
    FUNKCJA_PYTAN_DO_ROZMOWY,
    MAX_KIERUNKOW,
    MAX_PYTAN,
    MIN_PYTAN,
    przygotuj_rozmowe,
)
from asystent_ocen.zgodnosc import BladZgodnosci, rejestr_funkcji_ai, wczytaj_wymogi

DECYZJE_POKAZU = Path(__file__).resolve().parents[1] / "decyzje-ai-pokaz.toml"
NOTATKI = [
    "Przygotowała projekt procedury obiegu korespondencji; wdrożona bez poprawek.",
    "Sprawy z zakresu skarg załatwia przed terminem.",
    "2 projekty pism do ministerstwa wymagały poprawek stylistycznych.",
]
PYTANIA = [
    "Co pomogło Pani/Panu przygotować procedurę obiegu korespondencji bez poprawek?",
    "Jak Pani/Pan organizuje pracę, żeby załatwiać skargi przed terminem?",
    "Jakiego wsparcia potrzebuje Pani/Pan przy redagowaniu pism do ministerstwa?",
]
KIERUNKI = [{"kierunek": "Szkolenie z redagowania pism urzędowych", "podstawa": "Projekty pism wymagały poprawek stylistycznych."}]


class Model:
    """Atrapa lokalnego modelu: zapamiętuje wiadomości i schemat, zwraca przygotowaną odpowiedź."""

    def __init__(self, pytania=PYTANIA, kierunki=KIERUNKI, surowa: str | None = None):
        self.odpowiedz = surowa if surowa is not None else json.dumps(
            {"pytania": list(pytania), "kierunki_iprz": list(kierunki)}, ensure_ascii=False
        )
        self.wiadomosci: list[list[dict]] = []
        self.schematy: list[dict | None] = []

    def __call__(self, wiadomosci, schemat=None):
        self.wiadomosci.append(wiadomosci)
        self.schematy.append(schemat)
        return self.odpowiedz

    @property
    def wyslane(self) -> str:
        return "\n".join(w["content"] for rozmowa in self.wiadomosci for w in rozmowa)


@pytest.fixture
def pokaz():
    """Rejestr z funkcją kierunków IPRZ włączoną tak jak w pokazie - decyzją pokazową."""
    return wczytaj_wymogi(decyzje=DECYZJE_POKAZU, tryb_pokazu=True)


# --- rejestr funkcji AI ---

def test_pytania_do_rozmowy_dzialaja_po_instalacji_a_kierunki_iprz_sa_funkcja_wysokiego_ryzyka():
    rejestr = {f.kod: f for f in rejestr_funkcji_ai()}

    assert rejestr[FUNKCJA_PYTAN_DO_ROZMOWY].klasyfikacja == "wyjatek_art_6_ust_3"
    assert rejestr[FUNKCJA_PYTAN_DO_ROZMOWY].wlaczona is True
    assert rejestr[FUNKCJA_KIERUNKOW_IPRZ].klasyfikacja == "wysokie_ryzyko"
    assert rejestr[FUNKCJA_KIERUNKOW_IPRZ].wlaczona is False


# --- pytania ---

def test_model_dostaje_tylko_notatki_a_wynik_to_pytania_do_rozmowy():
    model = Model()

    wynik = przygotuj_rozmowe(NOTATKI, model=model)

    assert list(wynik.pytania) == PYTANIA
    assert not wynik.odmowa and wynik.ostrzezenia == ()
    assert all(notatka in model.wyslane for notatka in NOTATKI)
    assert "dialog" in model.wiadomosci[0][0]["content"]  # zasady: rozmowa jest dialogiem (Poradnik, pkt 6.2.4)


def test_po_instalacji_model_nie_proponuje_kierunkow_iprz():
    """Funkcja kierunków jest wyłączona, więc schemat odpowiedzi ich nie zawiera, a odpowiedź modelu jest pomijana."""
    model = Model()

    wynik = przygotuj_rozmowe(NOTATKI, model=model)

    assert wynik.z_kierunkami is False and wynik.kierunki_iprz == ()
    assert "kierunki_iprz" not in model.schematy[0]["properties"]
    assert "IPRZ" not in model.wyslane and "indywidualn" not in model.wyslane


def test_schemat_odpowiedzi_wymusza_od_3_do_5_pytan():
    model = Model()

    przygotuj_rozmowe(NOTATKI, model=model)

    pytania = model.schematy[0]["properties"]["pytania"]
    assert (pytania["minItems"], pytania["maxItems"]) == (MIN_PYTAN, MAX_PYTAN) == (3, 5)


def test_bez_notatek_model_nie_jest_pytany():
    model = Model()

    wynik = przygotuj_rozmowe(["", "  "], model=model)

    assert wynik.odmowa and wynik.powod == ODMOWA_BRAK_NOTATEK
    assert model.wiadomosci == []


def test_nadmiarowe_pytania_sa_obcinane_z_ostrzezeniem():
    siedem = [f"Jak przebiegała praca nad zadaniem numer {n}?" for n in range(1, 8)]

    wynik = przygotuj_rozmowe(NOTATKI, model=Model(pytania=siedem))

    assert len(wynik.pytania) == MAX_PYTAN
    assert any("więcej niż 5" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_za_malo_pytan_daje_ostrzezenie():
    wynik = przygotuj_rozmowe(NOTATKI, model=Model(pytania=PYTANIA[:2]))

    assert len(wynik.pytania) == 2
    assert any("mniej niż 3" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_zdanie_ktore_nie_jest_pytaniem_jest_pomijane():
    wynik = przygotuj_rozmowe(NOTATKI, model=Model(pytania=[*PYTANIA, "Pracownik powinien poprawić styl pism."]))

    assert list(wynik.pytania) == PYTANIA
    assert any("nie jest pytaniem" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize(
    "pytanie",
    [
        "Czy stan zdrowia pozwala Pani/Panu brać dodatkowe zadania?",
        "Czy planuje Pani ciążę w najbliższym roku?",
        "Jak sytuacja rodzinna wpływa na Pani/Pana pracę?",
        "Czy należy Pani/Pan do związku zawodowego?",
    ],
)
def test_pytanie_o_zdrowie_albo_sprawy_prywatne_jest_odrzucane(pytanie):
    """Rozmowa oceniająca dotyczy obowiązków, celów i rozwoju (§ 10 rozp.) - model nie podsuwa pytań o zdrowie,
    rodzinę ani przekonania."""
    wynik = przygotuj_rozmowe(NOTATKI, model=Model(pytania=[*PYTANIA, pytanie]))

    assert pytanie not in wynik.pytania and len(wynik.pytania) == 3
    assert any("spraw prywatnych" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_pytanie_ze_sformulowaniem_o_ocenie_daje_ostrzezenie():
    """Model nie ocenia: pytanie z poziomem albo wynikiem oceny, którego nie ma w notatkach, wymaga uwagi."""
    pytanie = "Dlaczego Pani/Pana praca zasługuje na ocenę negatywną?"

    wynik = przygotuj_rozmowe(NOTATKI, model=Model(pytania=[*PYTANIA, pytanie]))

    assert any("o ocenie" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_liczba_spoza_notatek_daje_ostrzezenie():
    pytanie = "Co sprawiło, że 17 spraw załatwiono po terminie?"

    wynik = przygotuj_rozmowe(NOTATKI, model=Model(pytania=[*PYTANIA[:2], pytanie]))

    assert any("17" in ostrzezenie and "nie ma w notatkach" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_dane_osobowe_nie_trafiaja_do_modelu_a_wracaja_w_wyniku():
    notatki = ["Anna Nowak przygotowała procedurę obiegu korespondencji.", *NOTATKI[1:]]
    model = Model(pytania=["Co pomogło [OSOBA_1] przygotować procedurę?", *PYTANIA[1:]])

    wynik = przygotuj_rozmowe(notatki, model=model, osoby=["Anna Nowak"])

    assert "Anna" not in model.wyslane and "Nowak" not in model.wyslane
    assert wynik.pytania[0] == "Co pomogło Anna Nowak przygotować procedurę?"


def test_funkcja_wylaczona_w_rejestrze_nie_wywoluje_modelu():
    wymogi = wczytaj_wymogi()
    bez_pytan = dataclasses.replace(wymogi, funkcje_ai=tuple(
        dataclasses.replace(f, wlaczona=f.kod != FUNKCJA_PYTAN_DO_ROZMOWY and f.wlaczona) for f in wymogi.funkcje_ai
    ))
    model = Model()

    with pytest.raises(BladZgodnosci):
        przygotuj_rozmowe(NOTATKI, model=model, wymogi=bez_pytan)
    assert model.wiadomosci == []


@pytest.mark.parametrize("surowa", ["to nie jest JSON", "[1, 2]", '{"pytania": "jedno"}'])
def test_odpowiedz_w_nieznanej_postaci_to_blad_modelu(surowa):
    with pytest.raises(BladModelu):
        przygotuj_rozmowe(NOTATKI, model=Model(surowa=surowa))


# --- kierunki do IPRZ (funkcja wysokiego ryzyka) ---

def test_po_decyzji_urzedu_model_proponuje_kierunki_iprz_z_podstawa_w_notatkach(pokaz):
    model = Model()

    wynik = przygotuj_rozmowe(NOTATKI, model=model, wymogi=pokaz)

    assert wynik.z_kierunkami is True
    assert [(k.kierunek, k.podstawa) for k in wynik.kierunki_iprz] == [(KIERUNKI[0]["kierunek"], KIERUNKI[0]["podstawa"])]
    assert model.schematy[0]["properties"]["kierunki_iprz"]["maxItems"] == MAX_KIERUNKOW == 3
    assert "indywidualnego programu rozwoju zawodowego" in model.wyslane


@pytest.mark.decyzja_projektowa
def test_przy_mniej_niz_3_notatkach_kierunkow_nie_ma_nawet_po_decyzji_urzedu(pokaz):
    """Jedna albo dwie notatki nie pokazują pracy z całego okresu oceny - próg jak przy sugestii ocen."""
    model = Model()

    wynik = przygotuj_rozmowe(NOTATKI[:2], model=model, wymogi=pokaz)

    assert wynik.pytania and wynik.z_kierunkami is False and wynik.kierunki_iprz == ()
    assert "kierunki_iprz" not in model.schematy[0]["properties"]


def test_kierunek_bez_wskazanej_podstawy_daje_ostrzezenie_a_nadmiarowe_sa_obcinane(pokaz):
    kierunki = [{"kierunek": f"Szkolenie numer {n}", "podstawa": "" if n == 1 else "Sprawy z zakresu skarg."} for n in range(1, 6)]

    wynik = przygotuj_rozmowe(NOTATKI, model=Model(kierunki=kierunki), wymogi=pokaz)

    assert len(wynik.kierunki_iprz) == MAX_KIERUNKOW
    assert any("nie wskazał notatki" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_pusta_lista_kierunkow_jest_poprawna_odpowiedzia(pokaz):
    wynik = przygotuj_rozmowe(NOTATKI, model=Model(kierunki=[]), wymogi=pokaz)

    assert wynik.z_kierunkami is True and wynik.kierunki_iprz == ()
