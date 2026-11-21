"""Sugestia ocen cząstkowych: model językowy podpowiada oceniającemu ocenę w każdym kryterium na podstawie jego
własnych notatek, zapisanych osiągnięć pracownika i wyniku egzaminu.

Wymaganie: decyzja prowadzącego projekt z 21.11.2026 - model językowy ma podpowiadać oceniającemu oceny cząstkowe.
Klasyfikacja: funkcja wysokiego ryzyka - zał. III pkt 4 lit. b AI Act (rejestr `zgodnosc.toml`, kod
PROPOZYCJA_OCENY). Decyzje projektowe ponad to wymaganie, oznaczone markerem: model nie dostaje danych z EZD RP
(architektura v4 zespołu), bez notatek niczego nie sugeruje, a brak podstaw w notatkach zgłasza zamiast zgadywać.
Skala ocen: § 11 ust. 1 pkt 1 rozp.; opisy kryteriów: załącznik nr 1 do rozp.

Funkcja jest wyłączona w rejestrze z pakietu - testy włączają ją plikiem decyzji pokazu (`decyzje-ai-pokaz.toml`).
Próby na żywym modelu z 21.11.2026 (PLLuM-12B): z jednej notatki o dwutygodniowym zastępstwie model zasugerował
ocenę 9 - stąd minimalna liczba notatek i ostrzeżenie przy ocenie skrajnej.
"""

import dataclasses
import inspect
import json
from pathlib import Path

import pytest

from asystent_ocen.asystent_ai import (
    FUNKCJA_PROPOZYCJI_OCENY,
    MIN_NOTATEK_DO_SUGESTII,
    ODMOWA_BRAK_NOTATEK,
    ODMOWA_ZA_MALO_NOTATEK,
    ZASADY_SUGESTII,
    BladModelu,
    zasugeruj_oceny,
)
from asystent_ocen.zgodnosc import BladZgodnosci, wczytaj_wymogi

RZETELNOSC = "Rzetelność"
WSPOLPRACA = "Współpraca"
KOMUNIKACJA = "Komunikacja"
KRYTERIA = [RZETELNOSC, WSPOLPRACA, KOMUNIKACJA]
NOTATKI = [
    "W drugim kwartale załatwiła 12 spraw, żadna nie przekroczyła terminu.",
    "Dodatkowe osiągnięcie: przeprowadziła szkolenie dla nowych pracowników wydziału.",
    "Na prośby innych wydziałów odpowiada tego samego dnia.",
]
# Rejestr z funkcją włączoną decyzją urzędu - tak jak w pokazie.
WYMOGI = wczytaj_wymogi(decyzje=Path(__file__).resolve().parents[1] / "decyzje-ai-pokaz.toml")


def sugeruj(notatki, kryteria, **parametry):
    """Sugestia przy funkcji włączonej decyzją urzędu."""
    parametry.setdefault("wymogi", WYMOGI)
    return zasugeruj_oceny(notatki, kryteria, **parametry)


def odpowiedz(**oceny) -> str:
    """Odpowiedź modelu w ustalonej postaci: kryterium -> uzasadnienie i ocena (0 = brak podstaw w notatkach)."""
    nazwy = {"rzetelnosc": RZETELNOSC, "wspolpraca": WSPOLPRACA, "komunikacja": KOMUNIKACJA}
    return json.dumps(
        {nazwy.get(klucz, klucz): {"uzasadnienie": f"Notatki o: {klucz}.", "ocena": ocena} for klucz, ocena in oceny.items()},
        ensure_ascii=False,
    )


class ModelAtrapa:
    """Zapamiętuje wiadomości i schemat odpowiedzi; zwraca ustaloną odpowiedź."""

    def __init__(self, tresc: str | None = None):
        self.tresc = tresc if tresc is not None else odpowiedz(rzetelnosc=7, wspolpraca=7, komunikacja=0)
        self.wiadomosci: list[list[dict]] = []
        self.schematy: list[dict | None] = []

    def __call__(self, wiadomosci: list[dict], schemat: dict | None = None) -> str:
        self.wiadomosci.append(wiadomosci)
        self.schematy.append(schemat)
        return self.tresc

    @property
    def wyslane(self) -> str:
        return "\n".join(wiadomosc["content"] for rozmowa in self.wiadomosci for wiadomosc in rozmowa)


def oceny(wynik) -> dict:
    return {sugestia.kryterium: sugestia.ocena for sugestia in wynik.sugestie}


# --- co dostaje model ---

def test_model_dostaje_notatki_kryteria_z_opisami_i_skale():
    model = ModelAtrapa()

    sugeruj(NOTATKI, KRYTERIA, model=model)

    assert len(model.wiadomosci) == 1
    assert model.wiadomosci[0][0] == {"role": "system", "content": ZASADY_SUGESTII}
    assert all(notatka in model.wyslane for notatka in NOTATKI)
    assert all(kryterium in model.wyslane for kryterium in KRYTERIA)
    assert "Dotrzymywanie zobowiązań" in model.wyslane  # opis kryterium „Rzetelność” z załącznika nr 1
    assert "znacznie poniżej oczekiwań" in model.wyslane and "znacznie powyżej oczekiwań" in model.wyslane


@pytest.mark.decyzja_projektowa
def test_funkcja_nie_ma_wejscia_na_dane_z_ezd_szkic_ani_wynik():
    """Gwarancja konstrukcyjna (architektura v4: model bez wskaźników z EZD RP): sugestia powstaje wyłącznie
    z tego, co oceniający sam zapisał."""
    parametry = set(inspect.signature(zasugeruj_oceny).parameters)
    assert parametry == {"notatki", "kryteria", "model", "wymogi", "osoby"}


def test_schemat_wymusza_wpis_dla_kazdego_kryterium_i_oceny_ze_skali():
    model = ModelAtrapa()

    sugeruj(NOTATKI, KRYTERIA, model=model)

    schemat = model.schematy[0]
    assert schemat["required"] == KRYTERIA
    wpis = schemat["properties"][RZETELNOSC]
    assert wpis["properties"]["ocena"]["enum"] == [0, 1, 3, 5, 7, 9]
    assert list(wpis["properties"]) == ["uzasadnienie", "ocena"]  # najpierw powód, potem liczba


def test_zasady_kaza_trzymac_sie_notatek_i_zglaszac_brak_podstaw():
    zasady = ZASADY_SUGESTII.lower()
    assert "wyłącznie" in zasady and "notat" in zasady
    assert "nie zgaduj" in zasady
    assert "przełożony" in zasady  # o ocenie decyduje człowiek


@pytest.mark.decyzja_projektowa
def test_dane_osobowe_nie_trafiaja_do_modelu_a_wracaja_w_uzasadnieniu():
    notatki = ["Anna Nowak (PESEL 90010112345) przeprowadziła szkolenie z EZD RP.", *NOTATKI[:2]]
    model = ModelAtrapa(json.dumps({RZETELNOSC: {"uzasadnienie": "[OSOBA_1] przeprowadziła szkolenie.", "ocena": 7}}))

    wynik = sugeruj(notatki, [RZETELNOSC], model=model, osoby=["Anna Nowak"])

    assert "Anna Nowak" not in model.wyslane and "90010112345" not in model.wyslane
    assert wynik.sugestie[0].uzasadnienie == "Anna Nowak przeprowadziła szkolenie."


# --- co wraca do oceniającego ---

def test_sugestia_podaje_ocene_i_uzasadnienie_dla_kazdego_kryterium():
    wynik = sugeruj(NOTATKI, KRYTERIA, model=ModelAtrapa())

    assert not wynik.odmowa
    assert [sugestia.kryterium for sugestia in wynik.sugestie] == KRYTERIA
    assert oceny(wynik) == {RZETELNOSC: 7, WSPOLPRACA: 7, KOMUNIKACJA: None}
    assert wynik.sugestie[0].uzasadnienie == "Notatki o: rzetelnosc."
    assert wynik.ostrzezenia == ()


@pytest.mark.decyzja_projektowa
def test_brak_podstaw_w_notatkach_nie_jest_ocena():
    """Ocena 0 w odpowiedzi modelu znaczy „notatki nic o tym nie mówią” - oceniający nie dostaje wtedy liczby."""
    wynik = sugeruj(NOTATKI, KRYTERIA, model=ModelAtrapa(odpowiedz(rzetelnosc=0, wspolpraca=0, komunikacja=0)))
    assert set(oceny(wynik).values()) == {None}


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize("notatki", [[], ["", "   "]], ids=["brak", "same puste"])
def test_bez_notatek_model_nie_jest_pytany(notatki):
    model = ModelAtrapa()

    wynik = sugeruj(notatki, KRYTERIA, model=model)

    assert (wynik.odmowa, wynik.powod, wynik.sugestie) == (True, ODMOWA_BRAK_NOTATEK, ())
    assert model.wiadomosci == []


def test_funkcja_wylaczona_w_rejestrze_nie_wywoluje_modelu():
    wymogi = WYMOGI
    bez_sugestii = dataclasses.replace(
        wymogi,
        funkcje_ai=tuple(
            dataclasses.replace(f, wlaczona=False) if f.kod == FUNKCJA_PROPOZYCJI_OCENY else f
            for f in wymogi.funkcje_ai
        ),
    )
    model = ModelAtrapa()

    with pytest.raises(BladZgodnosci):
        zasugeruj_oceny(NOTATKI, KRYTERIA, model=model, wymogi=bez_sugestii)
    assert model.wiadomosci == []


# --- kontrola odpowiedzi modelu regułami ---

def test_ocena_spoza_skali_jest_odrzucana_z_ostrzezeniem():
    wynik = sugeruj(NOTATKI, KRYTERIA, model=ModelAtrapa(odpowiedz(rzetelnosc=8, wspolpraca=7, komunikacja=5)))

    assert oceny(wynik) == {RZETELNOSC: None, WSPOLPRACA: 7, KOMUNIKACJA: 5}
    assert len(wynik.ostrzezenia) == 1 and RZETELNOSC in wynik.ostrzezenia[0]


def test_kryterium_pominiete_przez_model_zostaje_bez_sugestii():
    wynik = sugeruj(NOTATKI, KRYTERIA, model=ModelAtrapa(odpowiedz(rzetelnosc=7)))

    assert oceny(wynik) == {RZETELNOSC: 7, WSPOLPRACA: None, KOMUNIKACJA: None}
    assert any(WSPOLPRACA in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


def test_kryterium_spoza_listy_jest_pomijane():
    tresc = odpowiedz(rzetelnosc=7, wspolpraca=5, komunikacja=5, **{"Kreatywność": 9})
    wynik = sugeruj(NOTATKI, KRYTERIA, model=ModelAtrapa(tresc))

    assert [sugestia.kryterium for sugestia in wynik.sugestie] == KRYTERIA


def test_liczba_spoza_notatek_w_uzasadnieniu_daje_ostrzezenie():
    tresc = json.dumps(
        {RZETELNOSC: {"uzasadnienie": "Załatwiła 40 spraw w terminie.", "ocena": 9}}, ensure_ascii=False
    )
    wynik = sugeruj(NOTATKI, [RZETELNOSC], model=ModelAtrapa(tresc))

    assert any("40" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


@pytest.mark.parametrize("tresc", ["to nie jest JSON", "[1, 2]", '"tekst"'], ids=["tekst", "lista", "napis"])
def test_odpowiedz_w_nieznanej_postaci_jest_bledem_modelu(tresc):
    with pytest.raises(BladModelu):
        sugeruj(NOTATKI, KRYTERIA, model=ModelAtrapa(tresc))


# --- bezpieczne ustawienia domyślne i kontrole ponad odpowiedź modelu ---

def test_bez_decyzji_urzedu_funkcja_jest_zablokowana_i_model_nie_jest_pytany():
    """Rejestr z pakietu ma sugestię ocen wyłączoną - system po instalacji jej nie uruchomi."""
    model = ModelAtrapa()

    with pytest.raises(BladZgodnosci):
        zasugeruj_oceny(NOTATKI, KRYTERIA, model=model)
    assert model.wiadomosci == []


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize("ile", range(1, MIN_NOTATEK_DO_SUGESTII))
def test_ponizej_minimalnej_liczby_notatek_model_nie_jest_pytany(ile):
    """Jedna albo dwie notatki nie pokazują pracy z całego okresu oceny, a model potrafi wyprowadzić z nich
    ocenę skrajną (próba z 21.11.2026). Próg jest decyzją zespołu, nie przepisem."""
    model = ModelAtrapa()

    wynik = sugeruj(NOTATKI[:ile], KRYTERIA, model=model)

    assert (wynik.odmowa, wynik.powod, wynik.sugestie) == (True, ODMOWA_ZA_MALO_NOTATEK, ())
    assert model.wiadomosci == []


def test_minimalna_liczba_notatek_wystarcza():
    assert MIN_NOTATEK_DO_SUGESTII == 3
    assert not sugeruj(NOTATKI[:MIN_NOTATEK_DO_SUGESTII], KRYTERIA, model=ModelAtrapa()).odmowa


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize("ocena", [1, 9], ids=["najniższa", "najwyższa"])
def test_ocena_skrajna_daje_ostrzezenie(ocena):
    """Oceny z krańców skali (§ 11 ust. 1 pkt 1 rozp.) mają najdalej idące skutki, więc oceniający dostaje
    wyraźną prośbę o sprawdzenie, czy notatki je uzasadniają."""
    wynik = sugeruj(NOTATKI, KRYTERIA, model=ModelAtrapa(odpowiedz(rzetelnosc=ocena, wspolpraca=5, komunikacja=7)))

    assert oceny(wynik)[RZETELNOSC] == ocena
    assert [o for o in wynik.ostrzezenia if RZETELNOSC in o and "skrajn" in o], wynik.ostrzezenia
    assert not [o for o in wynik.ostrzezenia if WSPOLPRACA in o or KOMUNIKACJA in o]
