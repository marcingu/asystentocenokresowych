"""Wymaganie: każda funkcja AI ma jawną klasyfikację według AI Act. Funkcji zakazanych nie da się włączyć,
a funkcję wysokiego ryzyka włącza wyłącznie decyzja urzędu zapisana w osobnym pliku wdrożenia.

Źródła: rozporządzenie (UE) 2024/1689 w wersji skonsolidowanej z 27.07.2026 - art. 5 ust. 1 lit. f,
art. 6 ust. 2-4, załącznik III pkt 4 lit. b, art. 49 ust. 2, art. 50 ust. 1, motywy 12 i 53;
art. 4 pkt 4 RODO (profilowanie); dokumentacja/analiza-prawna-ai-act-kp-rodo.md.
Decyzje prowadzącego projekt z 21.11.2026: model sugeruje oceniającemu oceny cząstkowe (funkcja wysokiego ryzyka);
w repozytorium funkcja jest wyłączona, a włącza ją tylko pokaz na danych fikcyjnych.
"""

import dataclasses
from pathlib import Path

import pytest

from asystent_ocen.zgodnosc import (
    BladZgodnosci,
    FunkcjaAI,
    rejestr_funkcji_ai,
    sprawdz_rejestr_funkcji_ai,
    wczytaj_wymogi,
    wymagaj_dozwolonej_funkcji_ai,
)

KATALOG = Path(__file__).resolve().parents[1]
REJESTR = KATALOG / "asystent_ocen" / "zgodnosc.toml"
DECYZJE_POKAZU = KATALOG / "decyzje-ai-pokaz.toml"
SUGESTIA = "PROPOZYCJA_OCENY"
NISKIE_RYZYKO = {"PYTANIA_O_PROCEDURE", "KOREKTA_JEZYKOWA_UZASADNIENIA", "REDAKCJA_NOTATEK_OCENIAJACEGO"}

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


def plik_decyzji(katalog, *wpisy: tuple[str, str]) -> Path:
    """Plik decyzji urzędu z wpisami (kod funkcji, opis decyzji)."""
    plik = katalog / "decyzje-ai.toml"
    tresc = "".join(f'[[decyzje]]\nkod = "{kod}"\ndecyzja_wlaczenia = "{opis}"\n\n' for kod, opis in wpisy)
    plik.write_text(tresc or "decyzje = []\n", encoding="utf-8")
    return plik


# --- rejestr z pakietu ---

def test_rejestr_zawiera_klasyfikacje_wszystkich_funkcji_ai():
    assert {f.kod: f.klasyfikacja for f in rejestr_funkcji_ai()} == KLASYFIKACJE


def test_kazda_funkcja_ai_ma_opis_i_podstawe_klasyfikacji():
    assert all(f.opis.strip() and f.podstawa.strip() for f in rejestr_funkcji_ai())


def test_w_rejestrze_z_pakietu_wlaczone_sa_tylko_funkcje_spoza_wysokiego_ryzyka():
    """Ocena wydajności i zachowania pracownika to zał. III pkt 4 lit. b AI Act, a ocena efektów pracy jest
    profilowaniem (art. 4 pkt 4 RODO), więc wyjątek z art. 6 ust. 3 nie działa - to funkcje wysokiego ryzyka.

    Redakcja notatek oceniającego (moduł HR Copilot z architektury zespołu) jest włączona jako zadanie
    przygotowawcze: model składa w tekst notatki napisane przez człowieka, bez ocen i bez danych z EZD RP.
    System po instalacji nie ma włączonej żadnej funkcji wysokiego ryzyka.
    """
    assert {f.kod for f in rejestr_funkcji_ai() if f.wlaczona} == NISKIE_RYZYKO


@pytest.mark.decyzja_projektowa
def test_sugestia_ocen_jest_w_rejestrze_opisana_jako_wysokie_ryzyko_i_wylaczona():
    """Model nie dostaje danych z EZD RP (architektura v4 zespołu) - sugestia powstaje z notatek oceniającego."""
    sugestia = next(f for f in rejestr_funkcji_ai() if f.kod == SUGESTIA)
    assert (sugestia.klasyfikacja, sugestia.wlaczona, sugestia.decyzja_wlaczenia) == ("wysokie_ryzyko", False, "")
    assert "III pkt 4 lit. b" in sugestia.podstawa
    assert "EZD RP" in sugestia.opis and "notat" in sugestia.opis


@pytest.mark.decyzja_projektowa
def test_redakcja_notatek_ma_w_rejestrze_opisane_granice():
    """Kwalifikacja robocza z 21.11.2026 (art. 6 ust. 3 lit. d AI Act: „zadania przygotowawcze w kontekście oceny”)
    - do potwierdzenia przez prawnika przed wdrożeniem produkcyjnym."""
    funkcja = next(f for f in rejestr_funkcji_ai() if f.kod == "REDAKCJA_NOTATEK_OCENIAJACEGO")
    assert "6 ust. 3 lit. d" in funkcja.podstawa
    assert "EZD RP" in funkcja.opis and "ocen" in funkcja.opis


def test_w_pliku_rejestru_nie_da_sie_wlaczyc_funkcji_wysokiego_ryzyka(tmp_path):
    """Rejestr opisuje funkcje i ich klasyfikację. O włączeniu funkcji wysokiego ryzyka mówi osobny plik decyzji
    urzędu - opis decyzji dopisany do rejestru niczego nie włącza."""
    tresc = REJESTR.read_text(encoding="utf-8")
    wpis = f'kod = "{SUGESTIA}"'
    poczatek = tresc.index(wpis)
    koniec = tresc.index("wlaczona = false", poczatek)
    zmieniona = tresc[:koniec] + 'wlaczona = true\ndecyzja_wlaczenia = "Zarządzenie DG nr 7/2027."' + tresc[koniec + len("wlaczona = false"):]
    plik = tmp_path / "zgodnosc.toml"
    plik.write_text(zmieniona, encoding="utf-8")

    with pytest.raises(BladZgodnosci):
        wczytaj_wymogi(str(plik))


# --- kontrola rejestru ---

def test_funkcji_zakazanej_nie_da_sie_wlaczyc_nawet_z_opisana_decyzja():
    """Art. 5 AI Act: praktyki zakazanej nie legalizuje żadna decyzja urzędu."""
    with pytest.raises(BladZgodnosci):
        sprawdz_rejestr_funkcji_ai([funkcja(klasyfikacja="zakazana", wlaczona=True, decyzja_wlaczenia="Decyzja DG.")])


@pytest.mark.parametrize("decyzja", ["", "   "], ids=["brak", "same odstępy"])
def test_funkcja_wysokiego_ryzyka_wlaczona_bez_opisanej_decyzji_jest_odrzucana(decyzja):
    """Samo `wlaczona = true` nie wystarcza - urząd musi zapisać, kto i na jakich warunkach włącza funkcję."""
    with pytest.raises(BladZgodnosci):
        sprawdz_rejestr_funkcji_ai([funkcja(klasyfikacja="wysokie_ryzyko", wlaczona=True, decyzja_wlaczenia=decyzja)])


def test_funkcja_wysokiego_ryzyka_z_opisana_decyzja_moze_byc_wlaczona():
    sprawdz_rejestr_funkcji_ai(
        [funkcja(klasyfikacja="wysokie_ryzyko", wlaczona=True, decyzja_wlaczenia="Zarządzenie DG nr 7/2027.")]
    )


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


# --- użycie funkcji ---

@pytest.mark.parametrize("kod", sorted(NISKIE_RYZYKO))
def test_dozwolona_funkcja_ai_jest_zwracana(kod):
    assert wymagaj_dozwolonej_funkcji_ai(kod).kod == kod


@pytest.mark.parametrize(
    "kod", [SUGESTIA, "PODSUMOWANIE_PRACY_PRACOWNIKA", "REKOMENDACJA_KADROWA", "ANALIZA_EMOCJI", "NIEZNANA"]
)
def test_uzycie_niedozwolonej_albo_nieznanej_funkcji_ai_jest_blokowane(kod):
    """Bez pliku decyzji urzędu zablokowana jest także sugestia ocen cząstkowych."""
    with pytest.raises(BladZgodnosci):
        wymagaj_dozwolonej_funkcji_ai(kod)


def _wymogi_ze_zmieniona_funkcja(kod: str, **zmiany):
    wymogi = wczytaj_wymogi()
    return dataclasses.replace(
        wymogi,
        funkcje_ai=tuple(dataclasses.replace(f, **zmiany) if f.kod == kod else f for f in wymogi.funkcje_ai),
    )


def test_funkcja_wysokiego_ryzyka_bez_opisanej_decyzji_jest_blokowana_takze_przy_uzyciu():
    """Rejestr zbudowany z pominięciem kontroli pliku też nie przepuści funkcji wysokiego ryzyka bez decyzji."""
    bez_decyzji = _wymogi_ze_zmieniona_funkcja(SUGESTIA, wlaczona=True, decyzja_wlaczenia="")
    with pytest.raises(BladZgodnosci) as blad:
        wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=bez_decyzji)
    assert "nie ma opisanej decyzji" in str(blad.value)
    assert "III pkt 4 lit. b" in str(blad.value)


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


# --- plik decyzji urzędu o funkcjach wysokiego ryzyka ---

def test_decyzja_urzedu_wlacza_funkcje_wysokiego_ryzyka_i_nie_zmienia_jej_klasyfikacji(tmp_path):
    plik = plik_decyzji(tmp_path, (SUGESTIA, "Zarządzenie DG nr 7/2027; nadzór: naczelnik wydziału kadr."))

    wymogi = wczytaj_wymogi(decyzje=plik)

    wlaczona = wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=wymogi)
    assert (wlaczona.klasyfikacja, wlaczona.wlaczona) == ("wysokie_ryzyko", True)
    assert wlaczona.decyzja_wlaczenia == "Zarządzenie DG nr 7/2027; nadzór: naczelnik wydziału kadr."
    assert {f.kod for f in wymogi.funkcje_ai if f.wlaczona} == NISKIE_RYZYKO | {SUGESTIA}


def test_decyzja_urzedu_nie_zmienia_rejestru_z_pakietu(tmp_path):
    """Włączenie dotyczy tylko wymogów wczytanych z plikiem decyzji - nie zostaje w pamięci programu."""
    wczytaj_wymogi(decyzje=plik_decyzji(tmp_path, (SUGESTIA, "Zarządzenie DG nr 7/2027.")))

    with pytest.raises(BladZgodnosci):
        wymagaj_dozwolonej_funkcji_ai(SUGESTIA)


@pytest.mark.decyzja_projektowa
def test_usuniecie_wpisu_z_pliku_decyzji_wylacza_funkcje_od_razu(tmp_path):
    """Plik decyzji jest czytany przy każdym wczytaniu wymogów: urząd wyłącza funkcję wysokiego ryzyka bez
    ponownego uruchamiania systemu, a reszta funkcji działa dalej."""
    plik = plik_decyzji(tmp_path, (SUGESTIA, "Zarządzenie DG nr 7/2027."))
    assert wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=wczytaj_wymogi(decyzje=plik)).wlaczona

    plik_decyzji(tmp_path)

    po_zmianie = wczytaj_wymogi(decyzje=plik)
    with pytest.raises(BladZgodnosci):
        wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=po_zmianie)
    assert wymagaj_dozwolonej_funkcji_ai("REDAKCJA_NOTATEK_OCENIAJACEGO", wymogi=po_zmianie).wlaczona


@pytest.mark.parametrize(
    "wpisy",
    [
        [(SUGESTIA, "")],
        [(SUGESTIA, "   ")],
        [("ANALIZA_EMOCJI", "Decyzja DG.")],
        [("PYTANIA_O_PROCEDURE", "Decyzja DG.")],
        [("NIEZNANA", "Decyzja DG.")],
        [(SUGESTIA, "Decyzja DG."), (SUGESTIA, "Druga decyzja DG.")],
    ],
    ids=["brak opisu", "same odstępy", "funkcja zakazana", "funkcja niskiego ryzyka", "nieznany kod", "powtórzony kod"],
)
def test_bledny_plik_decyzji_jest_odrzucany(tmp_path, wpisy):
    """Art. 5 AI Act: funkcji zakazanej nie włącza żadna decyzja. Funkcje niskiego ryzyka włącza i wyłącza rejestr."""
    with pytest.raises(BladZgodnosci):
        wczytaj_wymogi(decyzje=plik_decyzji(tmp_path, *wpisy))


@pytest.mark.parametrize(
    "tresc",
    ["", "decyzje = 5\n", '[[decyzje]]\nkod = "PROPOZYCJA_OCENY"\n', "[[decyzje]]\nkod = 7\n", "to nie jest TOML ["],
    ids=["pusty plik", "zły typ", "bez opisu decyzji", "kod nie jest napisem", "błąd składni"],
)
def test_plik_decyzji_o_zlej_budowie_jest_odrzucany(tmp_path, tresc):
    plik = tmp_path / "decyzje-ai.toml"
    plik.write_text(tresc, encoding="utf-8")
    with pytest.raises(BladZgodnosci):
        wczytaj_wymogi(decyzje=plik)


def test_brak_wskazanego_pliku_decyzji_jest_bledem_a_nie_cichym_wylaczeniem(tmp_path):
    with pytest.raises(BladZgodnosci):
        wczytaj_wymogi(decyzje=tmp_path / "nie-ma-takiego-pliku.toml")


@pytest.mark.decyzja_projektowa
def test_plik_decyzji_pokazu_wlacza_tylko_sugestie_ocen_i_wymienia_obowiazki_urzedu():
    """Decyzja prowadzącego projekt z 21.11.2026: sugestię ocen włącza tylko pokaz na danych fikcyjnych.
    Opis decyzji mówi, kto i po co ją podjął, jakie obowiązki ma urząd i od kiedy się je stosuje
    (dokumentacja/analiza-prawna-ai-act-kp-rodo.md, pkt 3.1, 3.7 i 4)."""
    wymogi = wczytaj_wymogi(decyzje=DECYZJE_POKAZU)

    assert {f.kod for f in wymogi.funkcje_ai if f.wlaczona} == NISKIE_RYZYKO | {SUGESTIA}
    decyzja = wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=wymogi).decyzja_wlaczenia
    for fragment in ("21.11.2026", "art. 14", "art. 26 ust. 7", "art. 27 ust. 1", "2.12.2027", "art. 35"):
        assert fragment in decyzja
