"""Sprawdzian modelu językowego - pytania kontrolne przed włączeniem asystenta AI.

Wymaganie zadania KPRM: prosta instalacja i możliwość pracy na infrastrukturze urzędu. Urząd może wybrać inny
model niż domyślny, dlatego wymiana modelu ma własny test odbiorczy: zestaw pytań z wymaganymi informacjami,
zakazanymi zmyśleniami i oczekiwaną podstawą prawną.
"""

from dataclasses import replace

import pytest

from asystent_ocen.asystent_ai import BladModelu, OdpowiedzAI, dolacz_odeslania, znajdz_fragmenty
from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.sprawdzian_modelu import (
    PytanieKontrolne,
    main,
    sprawdz_model,
    sprawdz_odpowiedz,
    wczytaj_pytania_kontrolne,
)

SPRZECIW = PytanieKontrolne(
    pytanie="W jakim terminie mogę wnieść sprzeciw od oceny okresowej i do kogo?",
    wymagane=("7 dni", "dyrektor"),
    zakazane=("14 dni",),
    podstawa="art. 83 ust. 1 u.s.c.",
)
DOBRA = OdpowiedzAI(
    tekst="Sprzeciw wnosi się w terminie 7 dni do dyrektora generalnego urzędu (art. 83 ust. 1 u.s.c.).",
    zrodla=("art. 83 ust. 1 u.s.c.", "art. 83 ust. 3 u.s.c."),
    powolane=("art. 83 ust. 1 u.s.c.",),
)


def _wzorcowy_model(wiadomosci):
    """Atrapa: odpowiada dosłownym brzmieniem podanych przepisów z oznaczeniem każdego z nich."""
    przepisy = wiadomosci[-1]["content"].split("\n\nPytanie:")[0].removeprefix("Przepisy:\n")
    zdania = []
    for wiersz in przepisy.splitlines():
        oznaczenie, tresc = wiersz[1:].split("] ", 1)
        zdania.append(f"{tresc.rstrip('.')} ({oznaczenie}).")
    return " ".join(zdania)


# --- pytania kontrolne ---

def test_zestaw_zawiera_pytania_o_przepisy_i_pytania_do_odmowy():
    pytania = wczytaj_pytania_kontrolne()

    assert len(pytania) >= 10
    assert {pytanie.odmowa for pytanie in pytania} >= {"", "ocena_osoby", "brak_przepisu"}
    assert all(pytanie.wymagane and pytanie.podstawa for pytanie in pytania if not pytanie.odmowa)


def test_wymagane_liczby_pochodza_z_przepisow():
    """Zmiana parametru w przepisach zmienia oczekiwaną odpowiedź - sprawdzian nie utrwala starego prawa."""
    domyslne = {p.pytanie: p for p in wczytaj_pytania_kontrolne()}
    zmienione = {
        p.pytanie: p for p in wczytaj_pytania_kontrolne(przepisy=replace(wczytaj_przepisy(), sprzeciw_dni=10))
    }

    assert "7 dni" in domyslne[SPRZECIW.pytanie].wymagane
    assert "10 dni" in zmienione[SPRZECIW.pytanie].wymagane


def test_do_kazdego_pytania_kontrolnego_wyszukiwanie_znajduje_oczekiwany_przepis():
    for pytanie in wczytaj_pytania_kontrolne():
        if pytanie.odmowa:
            continue
        podane = [fragment.zrodlo for fragment in dolacz_odeslania(znajdz_fragmenty(pytanie.pytanie))]
        assert pytanie.podstawa in podane, pytanie.pytanie


# --- ocena pojedynczej odpowiedzi ---

def test_dobra_odpowiedz_nie_ma_uwag():
    assert sprawdz_odpowiedz(SPRZECIW, DOBRA) == ()


def test_brak_wymaganej_informacji_daje_uwage():
    odpowiedz = replace(DOBRA, tekst="Sprzeciw wnosi się do dyrektora generalnego urzędu (art. 83 ust. 1 u.s.c.).")

    assert any("7 dni" in uwaga for uwaga in sprawdz_odpowiedz(SPRZECIW, odpowiedz))


def test_zakazana_informacja_daje_uwage():
    odpowiedz = replace(DOBRA, tekst=DOBRA.tekst + " Termin można przedłużyć do 14 dni.")

    assert any("14 dni" in uwaga for uwaga in sprawdz_odpowiedz(SPRZECIW, odpowiedz))


def test_wielkosc_liter_nie_ma_znaczenia():
    assert sprawdz_odpowiedz(SPRZECIW, replace(DOBRA, tekst=DOBRA.tekst.upper())) == ()


def test_brak_oczekiwanej_podstawy_daje_uwage():
    odpowiedz = replace(DOBRA, powolane=("art. 83 ust. 3 u.s.c.",))

    assert any("art. 83 ust. 1 u.s.c." in uwaga for uwaga in sprawdz_odpowiedz(SPRZECIW, odpowiedz))


def test_ostrzezenia_asystenta_sa_uwagami():
    odpowiedz = replace(DOBRA, ostrzezenia=("Odpowiedź zawiera liczbę, której nie ma w podanych przepisach (21).",))

    assert any("21" in uwaga for uwaga in sprawdz_odpowiedz(SPRZECIW, odpowiedz))


def test_nieoczekiwana_odmowa_daje_uwage():
    odpowiedz = OdpowiedzAI(tekst="Nie odpowiem.", odmowa=True, powod="ocena_osoby")

    assert any("odmow" in uwaga for uwaga in sprawdz_odpowiedz(SPRZECIW, odpowiedz))


def test_pytanie_do_odmowy_wymaga_odmowy_z_wlasciwym_powodem():
    pytanie = PytanieKontrolne(pytanie="Jaką ocenę wystawić Janowi?", odmowa="ocena_osoby")

    assert sprawdz_odpowiedz(pytanie, OdpowiedzAI(tekst="Nie odpowiem.", odmowa=True, powod="ocena_osoby")) == ()
    assert sprawdz_odpowiedz(pytanie, DOBRA) != ()
    assert sprawdz_odpowiedz(pytanie, OdpowiedzAI(tekst="Brak.", odmowa=True, powod="brak_przepisu")) != ()


# --- cały sprawdzian ---

def test_model_cytujacy_przepisy_zalicza_caly_sprawdzian():
    wyniki = sprawdz_model(_wzorcowy_model)

    assert [wynik.pytanie.pytanie for wynik in wyniki if not wynik.zaliczone] == []
    assert len(wyniki) == len(wczytaj_pytania_kontrolne())


def test_model_bez_wiedzy_nie_zalicza_pytan_o_przepisy_ale_odmowy_dzialaja_bez_modelu():
    wyniki = sprawdz_model(lambda wiadomosci: "Nie wiem.")

    for wynik in wyniki:
        assert wynik.zaliczone is bool(wynik.pytanie.odmowa), wynik.pytanie.pytanie


def test_niedostepny_model_nie_przerywa_sprawdzianu():
    def model(wiadomosci):
        raise BladModelu("brak połączenia")

    wyniki = sprawdz_model(model)

    assert len(wyniki) == len(wczytaj_pytania_kontrolne())
    niezaliczone = [wynik for wynik in wyniki if not wynik.zaliczone]
    assert niezaliczone and all("brak połączenia" in wynik.uwagi[0] for wynik in niezaliczone)
    assert all(wynik.odpowiedz is None for wynik in niezaliczone)


# --- uruchomienie z wiersza poleceń ---

def test_polecenie_zwraca_zero_gdy_model_zaliczyl_sprawdzian(capsys):
    assert main([], model=_wzorcowy_model) == 0
    wyjscie = capsys.readouterr().out
    liczba = len(wczytaj_pytania_kontrolne())
    assert f"Zaliczone: {liczba}/{liczba}" in wyjscie


def test_polecenie_zwraca_jeden_i_wypisuje_uwagi_gdy_model_nie_zaliczyl(capsys):
    assert main([], model=lambda wiadomosci: "Nie wiem.") == 1
    wyjscie = capsys.readouterr().out
    assert "NIEZALICZONE" in wyjscie
    assert "brak wymaganej informacji" in wyjscie


def test_polecenie_odrzuca_adres_inny_niz_http():
    with pytest.raises(SystemExit):
        main(["--adres", "file:///etc/passwd"])
