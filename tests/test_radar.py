"""Radar Dobrostanu i Doceniania: neutralne karty obserwacji z liczb z systemu kadrowego i EZD RP.

Wymaganie (decyzja prowadzącego projekt z 21.11.2026): radar pokazuje pracownikowi i jego przełożonemu neutralne
karty obserwacji zbudowane z liczb z EZD RP i systemu kadrowego; korzysta też z modelu językowego.

Podstawy kart o urlopie: art. 168 KP (urlop zaległy - najpóźniej do 30 września następnego roku) i art. 162 KP
(co najmniej jedna część wypoczynku nie krótsza niż 14 kolejnych dni kalendarzowych). Pozostałe progi to
ustawienia urzędu z `radar.toml`, nie przepisy.

Decyzje projektowe: karta podaje fakt z liczbami i źródło, bez punktów, sumy, rankingu i bez wniosków o zdrowiu
albo emocjach (wnioskowanie o emocjach w miejscu pracy jest w rejestrze funkcją zakazaną); udziały procentowe
są liczone dopiero od minimalnej liczby zdarzeń; propozycja pytań przez model to funkcja wysokiego ryzyka,
wyłączona po instalacji, a model dostaje same karty - bez danych osobowych.
"""

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from asystent_ocen.asystent_ai import BladModelu
from asystent_ocen.radar import (
    DOBROSTAN,
    DOCENIENIE,
    FUNKCJA_RADARU,
    DaneRadaru,
    karty_obserwacji,
    wczytaj_progi,
    zaproponuj_pytania,
)
from asystent_ocen.zgodnosc import BladZgodnosci, rejestr_funkcji_ai, wczytaj_wymogi

DZIEN = date(2026, 11, 21)
DECYZJE_POKAZU = Path(__file__).resolve().parents[1] / "decyzje-ai-pokaz.toml"
SLOWA_OCENIAJACE = (
    "wypalen", "stres", "zmęcz", "przemęcz", "depres", "emocj", "zagroż", "ryzyk", "słab", "zły", "zła", "niepokoj",
    "alarm", "problem", "punkt", "ranking", "wynik oceny",
)


def dane(**pola) -> DaneRadaru:
    return DaneRadaru(stan_na=DZIEN, **pola)


def kody(karty) -> list[str]:
    return [karta.kod for karta in karty]


def karta(karty, kod):
    return next(pozycja for pozycja in karty if pozycja.kod == kod)


# --- progi ---

def test_progi_sa_ustawieniami_urzedu_w_osobnym_pliku():
    progi = wczytaj_progi()

    assert progi.miesiace_bez_wypoczynku_14_dni == 12
    assert progi.nadgodziny_w_roku_h == 80
    assert progi.sprawy_w_toku_procent_mediany == 150
    assert progi.terminowosc_procent == 95
    assert progi.min_licznosc == 5


def test_brak_klucza_w_pliku_progow_jest_bledem(tmp_path):
    plik = tmp_path / "radar.toml"
    plik.write_text("[dobrostan]\nnadgodziny_w_roku_h = 80\n", encoding="utf-8")

    with pytest.raises(ValueError, match="radar"):
        wczytaj_progi(plik)


# --- karty ---

def test_bez_przekroczonych_progow_nie_ma_kart():
    assert karty_obserwacji(dane()) == ()


def test_urlop_zalegly_daje_karte_z_terminem_z_kodeksu_pracy():
    wynik = karty_obserwacji(dane(urlop_zalegly_dni=9))

    pozycja = karta(wynik, "URLOP_ZALEGLY")
    assert pozycja.rodzaj == DOBROSTAN
    assert "9 dni" in pozycja.fakt and "30.09.2026" in pozycja.fakt
    assert "art. 168 KP" in pozycja.podstawa
    assert pozycja.zrodlo == "system kadrowy"


def test_po_30_wrzesnia_karta_urlopu_zaleglego_mowi_ze_termin_minal():
    """Urlop zaległy z roku poprzedniego należało udzielić do 30.09 - po tym dniu karta podaje ten sam termin."""
    przed = karta(karty_obserwacji(DaneRadaru(stan_na=date(2026, 6, 1), urlop_zalegly_dni=1)), "URLOP_ZALEGLY")
    po = karta(karty_obserwacji(dane(urlop_zalegly_dni=1)), "URLOP_ZALEGLY")

    assert "1 dzień" in przed.fakt and "termin minął" not in przed.fakt
    assert "termin minął" in po.fakt


def test_dlugi_wypoczynek_karta_dopiero_po_progu_miesiecy():
    dawno = karty_obserwacji(dane(koniec_ostatniego_wypoczynku_14_dni=date(2025, 8, 12)))
    niedawno = karty_obserwacji(dane(koniec_ostatniego_wypoczynku_14_dni=date(2026, 7, 20)))

    pozycja = karta(dawno, "DLUGI_WYPOCZYNEK")
    assert "12.08.2025" in pozycja.fakt and "15" in pozycja.fakt
    assert "art. 162 KP" in pozycja.podstawa
    assert "DLUGI_WYPOCZYNEK" not in kody(niedawno)


def test_nadgodziny_i_praca_poza_godzinami_wedlug_progow_urzedu():
    wynik = karty_obserwacji(dane(nadgodziny_w_roku_h=96, czynnosci_poza_godzinami_3_mies=27))

    assert "96 h" in karta(wynik, "NADGODZINY").fakt and "80 h" in karta(wynik, "NADGODZINY").fakt
    assert "ustawienie urzędu" in karta(wynik, "NADGODZINY").podstawa
    assert "27" in karta(wynik, "PRACA_POZA_GODZINAMI").fakt
    assert karta(wynik, "PRACA_POZA_GODZINAMI").zrodlo == "EZD RP"
    assert kody(karty_obserwacji(dane(nadgodziny_w_roku_h=79, czynnosci_poza_godzinami_3_mies=19))) == []


def test_sprawy_w_toku_porownuje_sie_z_mediana_komorki_a_nie_z_osobami():
    wynik = karty_obserwacji(dane(sprawy_w_toku=31, sprawy_w_toku_mediana_komorki=18))

    pozycja = karta(wynik, "SPRAWY_W_TOKU")
    assert "31" in pozycja.fakt and "18" in pozycja.fakt
    assert kody(karty_obserwacji(dane(sprawy_w_toku=26, sprawy_w_toku_mediana_komorki=18))) == []
    assert kody(karty_obserwacji(dane(sprawy_w_toku=31, sprawy_w_toku_mediana_komorki=None))) == []


def test_karty_doceniania():
    wynik = karty_obserwacji(dane(
        sprawy_zakonczone_12_mies=35, sprawy_w_terminie_12_mies=34, sprawy_przejete_po_nieobecnych_12_mies=7,
        pisma_12_mies=30, pisma_bez_poprawek_12_mies=28, dni_zastepstw_12_mies=14,
    ))

    assert kody(wynik) == ["TERMINOWOSC", "PRZEJETE_SPRAWY", "PISMA_BEZ_POPRAWEK", "ZASTEPSTWA"]
    assert all(pozycja.rodzaj == DOCENIENIE for pozycja in wynik)
    assert "34 z 35 (97%)" in karta(wynik, "TERMINOWOSC").fakt
    assert "28 z 30 (93%)" in karta(wynik, "PISMA_BEZ_POPRAWEK").fakt


@pytest.mark.decyzja_projektowa
def test_udzial_procentowy_nie_jest_liczony_z_kilku_zdarzen():
    """4 sprawy z 4 w terminie to 100%, ale z tak małej liczby nie wyciąga się wniosków."""
    wynik = karty_obserwacji(dane(
        sprawy_zakonczone_12_mies=4, sprawy_w_terminie_12_mies=4, pisma_12_mies=3, pisma_bez_poprawek_12_mies=3,
    ))

    assert wynik == ()


def test_karty_maja_stala_kolejnosc_najpierw_dobrostan_potem_docenienie():
    wynik = karty_obserwacji(dane(
        urlop_zalegly_dni=3, nadgodziny_w_roku_h=120, sprawy_zakonczone_12_mies=20, sprawy_w_terminie_12_mies=20,
    ))

    assert kody(wynik) == ["URLOP_ZALEGLY", "NADGODZINY", "TERMINOWOSC"]


@pytest.mark.decyzja_projektowa
def test_karty_sa_neutralne_bez_ocen_diagnoz_punktow_i_rankingu():
    pelne = karty_obserwacji(dane(
        urlop_zalegly_dni=9, koniec_ostatniego_wypoczynku_14_dni=date(2025, 8, 12), nadgodziny_w_roku_h=96,
        sprawy_w_toku=31, sprawy_w_toku_mediana_komorki=18, czynnosci_poza_godzinami_3_mies=27,
        sprawy_zakonczone_12_mies=35, sprawy_w_terminie_12_mies=34, sprawy_przejete_po_nieobecnych_12_mies=7,
        pisma_12_mies=30, pisma_bez_poprawek_12_mies=28, dni_zastepstw_12_mies=14,
    ))

    assert len(pelne) == 9
    for pozycja in pelne:
        tekst = f"{pozycja.tytul} {pozycja.fakt} {pozycja.do_rozmowy}".lower()
        assert not [slowo for slowo in SLOWA_OCENIAJACE if slowo in tekst], pozycja.kod
        assert pozycja.fakt and pozycja.zrodlo and pozycja.podstawa and pozycja.do_rozmowy
    assert not {pole.name for pole in dataclasses.fields(pelne[0])} & {"punkty", "waga", "ocena", "poziom"}


# --- propozycja pytań przez model (funkcja wysokiego ryzyka) ---

KARTY = karty_obserwacji(dane(urlop_zalegly_dni=9, nadgodziny_w_roku_h=96))
PYTANIA = [
    {"kod": "URLOP_ZALEGLY", "pytanie": "Kiedy chciałaby Pani/chciałby Pan wykorzystać 9 dni urlopu zaległego?"},
    {"kod": "NADGODZINY", "pytanie": "Co sprawia, że część zadań wymaga pracy w godzinach nadliczbowych?"},
]


class Model:
    def __init__(self, pytania=PYTANIA, surowa: str | None = None):
        self.odpowiedz = surowa if surowa is not None else json.dumps({"pytania": list(pytania)}, ensure_ascii=False)
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
    return wczytaj_wymogi(decyzje=DECYZJE_POKAZU, tryb_pokazu=True)


def test_funkcja_radaru_jest_w_rejestrze_funkcja_wysokiego_ryzyka_wylaczona_po_instalacji():
    funkcja = {f.kod: f for f in rejestr_funkcji_ai()}[FUNKCJA_RADARU]

    assert funkcja.klasyfikacja == "wysokie_ryzyko" and funkcja.wlaczona is False
    with pytest.raises(BladZgodnosci):
        zaproponuj_pytania(KARTY, model=Model())


def test_po_decyzji_urzedu_model_dostaje_same_karty_i_proponuje_pytanie_do_kazdej(pokaz):
    model = Model()

    wynik = zaproponuj_pytania(KARTY, model=model, wymogi=pokaz)

    assert [(p.kod, p.pytanie) for p in wynik.pytania] == [(p["kod"], p["pytanie"]) for p in PYTANIA]
    assert wynik.ostrzezenia == ()
    assert "9 dni" in model.wyslane and "96 h" in model.wyslane
    assert model.schematy[0]["properties"]["pytania"]["maxItems"] == len(KARTY)


def test_bez_kart_model_nie_jest_pytany(pokaz):
    model = Model()

    wynik = zaproponuj_pytania((), model=model, wymogi=pokaz)

    assert wynik.pytania == () and model.wiadomosci == []


@pytest.mark.parametrize(
    "pytanie",
    [
        "Czy czuje się Pani/Pan wypalona zawodowo?",
        "Czy nadgodziny wynikają z problemów zdrowotnych?",
        "Czy stres w pracy wpływa na Pani/Pana rodzinę?",
        "Czy ma Pani/Pan depresję?",
        # pytania, które lokalny model ułożył w pokazie 22.11.2026 - o stan osoby, a nie o organizację pracy
        "Jak Pani/Pan ocenia swój poziom regeneracji po ostatnim dłuższym wypoczynku?",
        "Jakie są Pani/Pana odczucia związane z częstymi zastępstwami i jak można wesprzeć Panią/Pana w tej roli?",
        "Jak się Pani/Pan czuje przy tylu sprawach w toku?",
        "Jakie jest Pani/Pana samopoczucie po ostatnim kwartale?",
        "Czy odczuwa Pani/Pan zmęczenie pracą w godzinach nadliczbowych?",
    ],
)
def test_pytanie_o_zdrowie_emocje_albo_sprawy_prywatne_jest_odrzucane(pokaz, pytanie):
    """Radar nie wnioskuje o emocjach ani zdrowiu - takie pytanie modelu nie trafia do przełożonego."""
    model = Model(pytania=[PYTANIA[0], {"kod": "NADGODZINY", "pytanie": pytanie}])

    wynik = zaproponuj_pytania(KARTY, model=model, wymogi=pokaz)

    assert [p.kod for p in wynik.pytania] == ["URLOP_ZALEGLY"]
    assert any("zdrowia, emocji albo spraw prywatnych" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)
    assert not any(pytanie in ostrzezenie for ostrzezenie in wynik.ostrzezenia)  # treść odrzuconego pytania nie wraca


def test_pytanie_do_nieznanej_karty_zdanie_bez_pytajnika_i_obca_liczba(pokaz):
    model = Model(pytania=[
        {"kod": "URLOP_ZALEGLY", "pytanie": "Pracownik powinien wziąć urlop."},
        {"kod": "INNA_KARTA", "pytanie": "Jak ocenia Pani/Pan podział zadań?"},
        {"kod": "NADGODZINY", "pytanie": "Skąd wzięło się 250 godzin nadliczbowych?"},
    ])

    wynik = zaproponuj_pytania(KARTY, model=model, wymogi=pokaz)

    assert [p.kod for p in wynik.pytania] == ["NADGODZINY"]
    assert any("nie jest pytaniem" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)
    assert any("250" in ostrzezenie and "nie ma na kartach" in ostrzezenie for ostrzezenie in wynik.ostrzezenia)


@pytest.mark.parametrize("surowa", ["to nie jest JSON", "[]", '{"pytania": "jedno"}'])
def test_odpowiedz_w_nieznanej_postaci_to_blad_modelu(pokaz, surowa):
    with pytest.raises(BladModelu):
        zaproponuj_pytania(KARTY, model=Model(surowa=surowa), wymogi=pokaz)
