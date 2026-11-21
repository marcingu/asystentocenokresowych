"""Wymaganie: każda funkcja AI ma jawną klasyfikację według AI Act. Funkcji zakazanych nie da się włączyć,
a funkcję wysokiego ryzyka włącza wyłącznie decyzja urzędu zapisana w osobnym pliku wdrożenia.

Źródła: rozporządzenie (UE) 2024/1689 w wersji skonsolidowanej z 27.07.2026 - art. 5 ust. 1 lit. f,
art. 6 ust. 2-4, załącznik III pkt 4 lit. b, art. 49 ust. 2, art. 50 ust. 1, motywy 12 i 53;
art. 4 pkt 4 RODO (profilowanie); dokumentacja/analiza-prawna-ai-act-kp-rodo.md.
Decyzje prowadzącego projekt z 21.11.2026: model sugeruje oceniającemu oceny cząstkowe (funkcja wysokiego ryzyka);
w repozytorium funkcja jest wyłączona, a włącza ją tylko pokaz na danych fikcyjnych. Urząd przed włączeniem
funkcji wysokiego ryzyka przygotowuje analizy i sam decyduje o włączeniu - decyzja wskazuje organ, datę
i dokument każdej analizy.

Źródła listy analiz i czynności (wersja skonsolidowana AI Act z 27.07.2026): art. 27 ust. 1 - ocena skutków dla
praw podstawowych przed wdrożeniem, obowiązek podmiotów prawa publicznego; art. 26 ust. 9 AI Act i art. 35 RODO -
ocena skutków dla ochrony danych; art. 26 ust. 2 - powierzenie nadzoru ze strony człowieka; art. 26 ust. 7 -
poinformowanie pracowników i ich przedstawicieli przed użyciem systemu w miejscu pracy; art. 49 ust. 3 i art. 26
ust. 8 - organ publiczny przed wykorzystaniem systemu rejestruje jego użycie w bazie danych UE, a systemu,
którego nie zarejestrował dostawca, nie stosuje.
Daty: art. 113 lit. c ppkt (i) - rozdział III sekcje 1-3 (w tym art. 14, 26 i 27) stosuje się do systemów
z załącznika III od 2.12.2027; art. 49 leży w sekcji 5, której ten przepis nie wymienia.
"""

import dataclasses
import re
from datetime import date
from pathlib import Path

import pytest

from asystent_ocen.zgodnosc import (
    BladZgodnosci,
    DokumentWarunku,
    FunkcjaAI,
    rejestr_funkcji_ai,
    sprawdz_rejestr_funkcji_ai,
    wczytaj_wymogi,
    wymagaj_dozwolonej_funkcji_ai,
)

KATALOG = Path(__file__).resolve().parents[1]
REJESTR = KATALOG / "asystent_ocen" / "zgodnosc.toml"
DECYZJE_POKAZU = KATALOG / "decyzje-ai-pokaz.toml"
WZOR_DECYZJI = KATALOG / "decyzje-ai-wzor.toml"
SUGESTIA = "PROPOZYCJA_OCENY"
NISKIE_RYZYKO = {
    "PYTANIA_O_PROCEDURE", "KOREKTA_JEZYKOWA_UZASADNIENIA", "REDAKCJA_NOTATEK_OCENIAJACEGO",
    "PYTANIA_DO_ROZMOWY_OCENIAJACEJ",
}
# Funkcje wysokiego ryzyka, które włącza pokaz na danych fikcyjnych (decyzje-ai-pokaz.toml).
W_POKAZIE = {SUGESTIA, "PROPOZYCJA_KIERUNKOW_IPRZ", "RADAR_PYTANIA_DO_KART"}
ORGAN = "Dyrektor Generalny Urzędu"
DATA_DECYZJI = date(2027, 12, 6)
# Analizy i czynności wymagane przed włączeniem funkcji wysokiego ryzyka - w kolejności z rejestru.
WARUNKI = (
    "OCENA_SKUTKOW_DLA_PRAW_PODSTAWOWYCH",
    "OCENA_SKUTKOW_DLA_OCHRONY_DANYCH",
    "NADZOR_CZLOWIEKA",
    "POINFORMOWANIE_PRACOWNIKOW",
    "REJESTRACJA_W_BAZIE_UE",
)
BRAK = object()  # wpis decyzji bez tabeli dokumentów

KLASYFIKACJE = {
    "PYTANIA_O_PROCEDURE": "poza_zalacznikiem_III",
    "KOREKTA_JEZYKOWA_UZASADNIENIA": "wyjatek_art_6_ust_3",
    "REDAKCJA_NOTATEK_OCENIAJACEGO": "wyjatek_art_6_ust_3",
    "PYTANIA_DO_ROZMOWY_OCENIAJACEJ": "wyjatek_art_6_ust_3",
    "PROPOZYCJA_OCENY": "wysokie_ryzyko",
    "PROPOZYCJA_KIERUNKOW_IPRZ": "wysokie_ryzyko",
    "RADAR_PYTANIA_DO_KART": "wysokie_ryzyko",
    "PODSUMOWANIE_PRACY_PRACOWNIKA": "wysokie_ryzyko",
    "REKOMENDACJA_KADROWA": "wysokie_ryzyko",
    "ANALIZA_EMOCJI": "zakazana",
}


def funkcja(**zmiany):
    wzor = FunkcjaAI(
        kod="TESTOWA", opis="Funkcja testowa.", klasyfikacja="poza_zalacznikiem_III", podstawa="art. X", wlaczona=True
    )
    return dataclasses.replace(wzor, **zmiany)


def dokumenty(**zmiany) -> dict:
    """Dokument dla każdej analizy i czynności z rejestru; `zmiany` podmieniają pozycję, a None ją usuwa."""
    wynik = {kod: f"Dokument {numer}/2027" for numer, kod in enumerate(WARUNKI, start=1)}
    wynik.update(zmiany)
    return {kod: dokument for kod, dokument in wynik.items() if dokument is not None}


def wpis_decyzji(
    kod: str = SUGESTIA, opis: str = "Zarządzenie DG nr 7/2027.", *, organ=ORGAN, data="2027-12-06", dok=None,
    pokaz=None,
) -> str:
    """Wpis pliku decyzji urzędu, domyślnie pełny: organ, data i dokument każdej analizy. `data` i `pokaz` to
    zapis TOML wstawiany bez zmian; None pomija pole, a `dok=BRAK` pomija tabelę dokumentów."""
    linie = ["[[decyzje]]", f'kod = "{kod}"', f'decyzja_wlaczenia = "{opis}"']
    if pokaz is not None:
        linie.append(f"pokaz = {pokaz}")
    if organ is not None:
        linie.append(f'organ = "{organ}"')
    if data is not None:
        linie.append(f"data = {data}")
    if dok is not BRAK:
        linie.append("[decyzje.dokumenty]")
        for klucz, wartosc in (dokumenty() if dok is None else dok).items():
            linie.append(f'{klucz} = "{wartosc}"' if isinstance(wartosc, str) else f"{klucz} = {wartosc}")
    return "\n".join(linie) + "\n\n"


def plik_decyzji(katalog, *wpisy: tuple[str, str]) -> Path:
    """Plik decyzji urzędu z pełnymi wpisami dla par (kod funkcji, opis decyzji)."""
    return plik_z_trescia(katalog, "".join(wpis_decyzji(kod, opis) for kod, opis in wpisy) or "decyzje = []\n")


def plik_z_trescia(katalog, tresc: str) -> Path:
    plik = katalog / "decyzje-ai.toml"
    plik.write_text(tresc, encoding="utf-8")
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


PELNA_DECYZJA = {
    "klasyfikacja": "wysokie_ryzyko", "wlaczona": True, "decyzja_wlaczenia": "Zarządzenie DG nr 7/2027.",
    "decyzja_organ": ORGAN, "decyzja_data": DATA_DECYZJI,
}


def test_funkcja_wysokiego_ryzyka_z_decyzja_podajaca_organ_i_date_moze_byc_wlaczona():
    sprawdz_rejestr_funkcji_ai([funkcja(**PELNA_DECYZJA)])


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize(
    "zmiany", [{"decyzja_organ": ""}, {"decyzja_organ": "  "}, {"decyzja_data": None}],
    ids=["bez organu", "organ z samych odstępów", "bez daty"],
)
def test_funkcja_wysokiego_ryzyka_z_samym_opisem_decyzji_jest_odrzucana(zmiany):
    """O włączeniu decyduje urząd: decyzja musi mówić, kto i kiedy ją podjął."""
    with pytest.raises(BladZgodnosci):
        sprawdz_rejestr_funkcji_ai([funkcja(**{**PELNA_DECYZJA, **zmiany})])


@pytest.mark.decyzja_projektowa
def test_decyzja_pokazowa_nie_potrzebuje_organu_ani_daty():
    """Pokaz na danych fikcyjnych nie jest decyzją urzędu - mówi to znacznik, nie zmyślony organ."""
    sprawdz_rejestr_funkcji_ai([
        funkcja(klasyfikacja="wysokie_ryzyko", wlaczona=True, decyzja_wlaczenia="Pokaz.", decyzja_pokazowa=True)
    ])


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
    "kod",
    [SUGESTIA, "PROPOZYCJA_KIERUNKOW_IPRZ", "RADAR_PYTANIA_DO_KART", "PODSUMOWANIE_PRACY_PRACOWNIKA", "REKOMENDACJA_KADROWA", "ANALIZA_EMOCJI",
     "NIEZNANA"],
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


@pytest.mark.decyzja_projektowa
def test_funkcja_wysokiego_ryzyka_bez_dokumentow_analiz_jest_blokowana_takze_przy_uzyciu():
    """Rejestr zbudowany z pominięciem pliku decyzji też nie przepuści funkcji, dla której urząd nie wskazał
    dokumentu każdej analizy."""
    bez_analiz = _wymogi_ze_zmieniona_funkcja(SUGESTIA, **{**PELNA_DECYZJA, "klasyfikacja": "wysokie_ryzyko"})
    with pytest.raises(BladZgodnosci) as blad:
        wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=bez_analiz)
    assert "ocena skutków dla praw podstawowych" in str(blad.value)
    assert "art. 27 ust. 1" in str(blad.value)


@pytest.mark.decyzja_projektowa
def test_funkcja_wysokiego_ryzyka_z_dokumentami_wszystkich_analiz_jest_dopuszczona_przy_uzyciu():
    wymogi = wczytaj_wymogi()
    komplet = tuple(
        DokumentWarunku(kod=w.kod, nazwa=w.nazwa, podstawa=w.podstawa, dokument="Dokument 1/2027")
        for w in wymogi.warunki_wlaczenia
    )
    z_analizami = _wymogi_ze_zmieniona_funkcja(SUGESTIA, **PELNA_DECYZJA, decyzja_dokumenty=komplet)
    assert wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=z_analizami).decyzja_organ == ORGAN


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
def test_plik_decyzji_pokazu_wlacza_tylko_funkcje_pokazu_i_wymienia_obowiazki_urzedu():
    """Decyzje prowadzącego projekt z 21.11.2026: funkcje wysokiego ryzyka włącza tylko pokaz na danych fikcyjnych.
    Opis decyzji mówi, kto i po co ją podjął, jakie obowiązki ma urząd i od kiedy się je stosuje
    (dokumentacja/analiza-prawna-ai-act-kp-rodo.md, pkt 3.1, 3.7 i 4)."""
    wymogi = wczytaj_wymogi(decyzje=DECYZJE_POKAZU, tryb_pokazu=True)

    assert {f.kod for f in wymogi.funkcje_ai if f.wlaczona} == NISKIE_RYZYKO | W_POKAZIE
    assert all(f.decyzja_pokazowa and "nie wykonano" in f.decyzja_wlaczenia for f in wymogi.funkcje_ai if f.kod in W_POKAZIE)
    sugestia = wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=wymogi)
    for fragment in (
        "21.11.2026", "art. 14", "art. 26 ust. 7", "art. 27 ust. 1", "art. 49 ust. 3", "art. 35",
        "2.12.2027", "art. 113 lit. c",
    ):
        assert fragment in sugestia.decyzja_wlaczenia
    assert sugestia.decyzja_pokazowa and sugestia.decyzja_dokumenty == ()
    assert "nie wykonano" in sugestia.decyzja_wlaczenia


@pytest.mark.decyzja_projektowa
def test_plik_decyzji_pokazu_niczego_nie_wlacza_poza_trybem_pokazu():
    """Plik pokazu nie zastąpi decyzji urzędu: bez analiz działa tylko na danych fikcyjnych."""
    with pytest.raises(BladZgodnosci) as blad:
        wczytaj_wymogi(decyzje=DECYZJE_POKAZU)
    assert "trybie demonstracyjnym" in str(blad.value)


# --- analizy i czynności przed włączeniem funkcji wysokiego ryzyka ---

def test_rejestr_wymienia_analizy_i_czynnosci_wymagane_przed_wlaczeniem():
    """Lista jest w konfiguracji, z podstawą prawną każdej pozycji (źródła w nagłówku pliku)."""
    warunki = {w.kod: w for w in wczytaj_wymogi().warunki_wlaczenia}

    assert tuple(warunki) == WARUNKI
    assert all(w.nazwa.strip() and w.podstawa.strip() for w in warunki.values())
    przepisy = {
        "OCENA_SKUTKOW_DLA_PRAW_PODSTAWOWYCH": "art. 27 ust. 1 AI Act",
        "OCENA_SKUTKOW_DLA_OCHRONY_DANYCH": "art. 35 RODO",
        "NADZOR_CZLOWIEKA": "art. 26 ust. 2 AI Act",
        "POINFORMOWANIE_PRACOWNIKOW": "art. 26 ust. 7 AI Act",
        "REJESTRACJA_W_BAZIE_UE": "art. 49 ust. 3",
    }
    for kod, przepis in przepisy.items():
        assert przepis in warunki[kod].podstawa


@pytest.mark.decyzja_projektowa
def test_rejestr_bez_listy_analiz_jest_odrzucany(tmp_path):
    """Usunięcie listy z konfiguracji nie może znieść wymogu analiz."""
    tresc = REJESTR.read_text(encoding="utf-8")
    bez_listy = re.sub(r"(?ms)^\[\[warunki_wlaczenia_wysokiego_ryzyka\]\]\n.*?(?=^\[|\Z)", "", tresc)
    assert "[[warunki_wlaczenia_wysokiego_ryzyka]]" in tresc and "[[warunki_wlaczenia_wysokiego_ryzyka]]" not in bez_listy
    plik = tmp_path / "zgodnosc.toml"
    plik.write_text(bez_listy, encoding="utf-8")

    with pytest.raises(BladZgodnosci):
        wczytaj_wymogi(str(plik))


@pytest.mark.decyzja_projektowa
def test_decyzja_urzedu_podaje_kto_i_kiedy_zdecydowal_oraz_dokument_kazdej_analizy(tmp_path):
    plik = plik_z_trescia(tmp_path, wpis_decyzji())

    sugestia = wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=wczytaj_wymogi(decyzje=plik))

    assert (sugestia.decyzja_organ, sugestia.decyzja_data, sugestia.decyzja_pokazowa) == (ORGAN, DATA_DECYZJI, False)
    assert {d.kod: d.dokument for d in sugestia.decyzja_dokumenty} == dokumenty()
    assert [d.kod for d in sugestia.decyzja_dokumenty] == list(WARUNKI)
    assert all(d.nazwa.strip() and d.podstawa.strip() for d in sugestia.decyzja_dokumenty)


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize(
    "zmiany",
    [
        {"organ": None},
        {"organ": "   "},
        {"data": None},
        {"data": '"2027-12-06"'},
        {"data": "2027-12-06T10:00:00"},
        {"dok": BRAK},
        {"dok": dokumenty(OCENA_SKUTKOW_DLA_PRAW_PODSTAWOWYCH=None)},
        {"dok": dokumenty(NADZOR_CZLOWIEKA="  ")},
        {"dok": dokumenty(POINFORMOWANIE_PRACOWNIKOW=5)},
        {"dok": dokumenty(INNA_ANALIZA="Dokument 9/2027")},
    ],
    ids=[
        "bez organu", "organ z samych odstępów", "bez daty", "data napisem", "data z godziną", "bez dokumentów",
        "bez jednej analizy", "pusty dokument", "dokument nie jest napisem", "analiza spoza rejestru",
    ],
)
def test_decyzja_bez_organu_daty_albo_dokumentu_analizy_niczego_nie_wlacza(tmp_path, zmiany):
    with pytest.raises(BladZgodnosci):
        wczytaj_wymogi(decyzje=plik_z_trescia(tmp_path, wpis_decyzji(**zmiany)))


@pytest.mark.decyzja_projektowa
def test_odmowa_wymienia_brakujace_analizy_z_podstawa_prawna(tmp_path):
    """Urząd ma wiedzieć, czego brakuje - bez czytania kodu."""
    niepelne = dokumenty(OCENA_SKUTKOW_DLA_PRAW_PODSTAWOWYCH=None, POINFORMOWANIE_PRACOWNIKOW=None)

    with pytest.raises(BladZgodnosci) as blad:
        wczytaj_wymogi(decyzje=plik_z_trescia(tmp_path, wpis_decyzji(dok=niepelne)))

    komunikat = str(blad.value)
    assert "ocena skutków dla praw podstawowych (art. 27 ust. 1 AI Act)" in komunikat
    assert "poinformowanie pracowników" in komunikat
    assert "ocena skutków dla ochrony danych" not in komunikat


@pytest.mark.decyzja_projektowa
def test_decyzja_pokazowa_bez_analiz_dziala_tylko_w_trybie_pokazu(tmp_path):
    """Pokaz działa na danych fikcyjnych, więc nie wymaga analiz - ale poza trybem pokazu niczego nie włącza."""
    plik = plik_z_trescia(tmp_path, wpis_decyzji(pokaz="true", organ=None, data=None, dok=BRAK))

    with pytest.raises(BladZgodnosci) as blad:
        wczytaj_wymogi(decyzje=plik)
    assert "trybie demonstracyjnym" in str(blad.value)

    w_pokazie = wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=wczytaj_wymogi(decyzje=plik, tryb_pokazu=True))
    assert (w_pokazie.wlaczona, w_pokazie.decyzja_pokazowa, w_pokazie.decyzja_dokumenty) == (True, True, ())
    assert w_pokazie.klasyfikacja == "wysokie_ryzyko"


def test_pelna_decyzja_urzedu_dziala_takze_w_trybie_pokazu(tmp_path):
    wymogi = wczytaj_wymogi(decyzje=plik_z_trescia(tmp_path, wpis_decyzji(pokaz="false")), tryb_pokazu=True)

    sugestia = wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=wymogi)
    assert (sugestia.decyzja_pokazowa, sugestia.decyzja_organ) == (False, ORGAN)


def test_wzor_decyzji_w_niezmienionej_postaci_niczego_nie_wlacza():
    with pytest.raises(BladZgodnosci):
        wczytaj_wymogi(decyzje=WZOR_DECYZJI)


def test_wzor_decyzji_po_wypelnieniu_jest_pelna_decyzja(tmp_path):
    """Wzór po usunięciu znaków komentarza z wpisu podaje wszystko, czego wymaga rejestr - także po zmianie
    listy analiz w konfiguracji."""
    linie = WZOR_DECYZJI.read_text(encoding="utf-8").splitlines()
    poczatek = linie.index("# [[decyzje]]")
    wpis = "\n".join(linia.removeprefix("# ") for linia in linie[poczatek:])

    sugestia = wymagaj_dozwolonej_funkcji_ai(SUGESTIA, wymogi=wczytaj_wymogi(decyzje=plik_z_trescia(tmp_path, wpis)))

    assert [d.kod for d in sugestia.decyzja_dokumenty] == list(WARUNKI)
    assert sugestia.decyzja_organ and sugestia.decyzja_data and not sugestia.decyzja_pokazowa


@pytest.mark.parametrize("pokaz", ['"tak"', "1"], ids=["napis", "liczba"])
def test_znacznik_pokazu_musi_byc_wartoscia_logiczna(tmp_path, pokaz):
    with pytest.raises(BladZgodnosci):
        wczytaj_wymogi(decyzje=plik_z_trescia(tmp_path, wpis_decyzji(pokaz=pokaz)), tryb_pokazu=True)
