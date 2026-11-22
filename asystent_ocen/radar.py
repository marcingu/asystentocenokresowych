"""Radar Dobrostanu i Doceniania: neutralne karty obserwacji z liczb o pracy jednej osoby.

Źródłem są liczby z systemu kadrowego (urlopy, godziny nadliczbowe, zastępstwa) i z EZD RP (sprawy, pisma) -
bez treści spraw. Karta podaje fakt, źródło i podstawę: przepis Kodeksu pracy albo próg ustalony przez urząd
w `radar.toml`. Te same karty widzi pracownik i jego bezpośredni przełożony.

Czego tu nie ma - celowo: punktów, sumy, rankingu, porównań między osobami (jedyne porównanie to mediana
komórki) i jakichkolwiek wniosków o zdrowiu albo emocjach. Karty liczy zwykły kod - to nie jest system AI.

Osobno: `zaproponuj_pytania` - model językowy układa do kart pytania otwarte dla przełożonego. Model dostaje
liczby o pracy konkretnej osoby, więc to funkcja wysokiego ryzyka (zał. III pkt 4 lit. b AI Act: monitorowanie
i ocena wydajności i zachowania): po instalacji wyłączona, włącza ją wyłącznie decyzja urzędu.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, fields
from datetime import date
from functools import lru_cache
from pathlib import Path

from .asystent_ai import BladModelu, Model, _liczby, _normalizuj, _zapytaj
from .kalendarz import dodaj_miesiace
from .przygotowanie_rozmowy import _dotyczy_spraw_prywatnych
from .zasady_hr import polecenie_dla_modelu
from .zgodnosc import Wymogi, wymagaj_dozwolonej_funkcji_ai

DOBROSTAN = "dobrostan"
DOCENIENIE = "docenienie"
FUNKCJA_RADARU = "RADAR_PYTANIA_DO_KART"
KADRY = "system kadrowy"
EZD = "EZD RP"
_PLIK_PROGOW = Path(__file__).with_name("radar.toml")
_USTAWIENIE = "ustawienie urzędu (radar.toml)"


@dataclass(frozen=True)
class ProgiRadaru:
    """Zawartość `radar.toml` - progi ustalone przez urząd."""

    miesiace_bez_wypoczynku_14_dni: int
    nadgodziny_w_roku_h: int
    sprawy_w_toku_procent_mediany: int
    czynnosci_poza_godzinami_3_mies: int
    terminowosc_procent: int
    pisma_bez_poprawek_procent: int
    sprawy_przejete_po_nieobecnych: int
    dni_zastepstw: int
    min_licznosc: int


def wczytaj_progi(plik: str | Path | None = None) -> ProgiRadaru:
    """Progi z `radar.toml` (domyślnie plik z pakietu). Brak klucza albo wartość, która nie jest liczbą
    dodatnią -> ValueError."""
    return _progi_domyslne() if plik is None else _wczytaj_progi(Path(plik))


@lru_cache(maxsize=1)
def _progi_domyslne() -> ProgiRadaru:
    return _wczytaj_progi(_PLIK_PROGOW)


def _wczytaj_progi(plik: Path) -> ProgiRadaru:
    with plik.open("rb") as strumien:
        dane = tomllib.load(strumien)
    wszystkie = {**dane.get("dobrostan", {}), **dane.get("docenienie", {})}
    wartosci = {}
    for pole in fields(ProgiRadaru):
        wartosc = wszystkie.get(pole.name)
        if isinstance(wartosc, bool) or not isinstance(wartosc, int) or wartosc < 1:
            raise ValueError(f"Progi radaru ({plik.name}): brak klucza `{pole.name}` albo wartość nie jest liczbą dodatnią.")
        wartosci[pole.name] = wartosc
    return ProgiRadaru(**wartosci)


@dataclass(frozen=True)
class DaneRadaru:
    """Liczby o pracy jednej osoby na dzień `stan_na`. Brak danych o wypoczynku albo medianie to None."""

    stan_na: date
    # system kadrowy
    urlop_zalegly_dni: int = 0
    koniec_ostatniego_wypoczynku_14_dni: date | None = None
    nadgodziny_w_roku_h: int = 0
    dni_zastepstw_12_mies: int = 0
    # EZD RP
    sprawy_w_toku: int = 0
    sprawy_w_toku_mediana_komorki: int | None = None
    czynnosci_poza_godzinami_3_mies: int = 0
    sprawy_zakonczone_12_mies: int = 0
    sprawy_w_terminie_12_mies: int = 0
    sprawy_przejete_po_nieobecnych_12_mies: int = 0
    pisma_12_mies: int = 0
    pisma_bez_poprawek_12_mies: int = 0


@dataclass(frozen=True)
class KartaObserwacji:
    kod: str
    rodzaj: str      # DOBROSTAN albo DOCENIENIE
    tytul: str
    fakt: str        # zdanie z liczbami - bez oceny
    zrodlo: str      # skąd pochodzą liczby
    podstawa: str    # przepis albo ustawienie urzędu, z którego wynika próg
    do_rozmowy: str  # neutralny temat do rozmowy


def _dni(liczba: int) -> str:
    return "1 dzień" if liczba == 1 else f"{liczba} dni"


def _procent(licznik: int, mianownik: int) -> int:
    """Udział w procentach, zaokrąglony arytmetycznie."""
    return (2 * 100 * licznik + mianownik) // (2 * mianownik)


def _pelne_miesiace(od: date, do: date) -> int:
    miesiace = (do.year - od.year) * 12 + do.month - od.month
    return miesiace if dodaj_miesiace(od, miesiace) <= do else miesiace - 1


def karty_obserwacji(dane: DaneRadaru, progi: ProgiRadaru | None = None) -> tuple[KartaObserwacji, ...]:
    """Karty obserwacji w stałej kolejności: najpierw dobrostan, potem docenienie. Karta powstaje tylko wtedy,
    gdy liczba osiąga próg; udział procentowy liczy się od `min_licznosc` zdarzeń."""
    progi = progi or wczytaj_progi()
    dzien = dane.stan_na
    karty: list[KartaObserwacji] = []

    if dane.urlop_zalegly_dni > 0:
        termin = date(dzien.year, 9, 30)
        karty.append(KartaObserwacji(
            "URLOP_ZALEGLY", DOBROSTAN, "Urlop zaległy",
            f"Urlop zaległy: {_dni(dane.urlop_zalegly_dni)}. Termin udzielenia urlopu zaległego: {termin:%d.%m.%Y}"
            f"{' - termin minął' if dzien > termin else ''}.",
            KADRY, "art. 168 KP w zw. z art. 9 ust. 1 u.s.c.", "Do ustalenia: termin wykorzystania urlopu zaległego.",
        ))
    if dane.koniec_ostatniego_wypoczynku_14_dni is not None:
        miesiace = _pelne_miesiace(dane.koniec_ostatniego_wypoczynku_14_dni, dzien)
        if miesiace >= progi.miesiace_bez_wypoczynku_14_dni:
            karty.append(KartaObserwacji(
                "DLUGI_WYPOCZYNEK", DOBROSTAN, "Dłuższy wypoczynek",
                "Ostatni wypoczynek trwający co najmniej 14 kolejnych dni kalendarzowych zakończył się "
                f"{dane.koniec_ostatniego_wypoczynku_14_dni:%d.%m.%Y}. Pełnych miesięcy od tego dnia: {miesiace}.",
                KADRY, f"art. 162 KP; próg {progi.miesiace_bez_wypoczynku_14_dni} mies. - {_USTAWIENIE}",
                "Do omówienia: plan urlopu z częścią trwającą co najmniej 14 kolejnych dni.",
            ))
    if dane.nadgodziny_w_roku_h >= progi.nadgodziny_w_roku_h:
        karty.append(KartaObserwacji(
            "NADGODZINY", DOBROSTAN, "Godziny nadliczbowe",
            f"Praca w godzinach nadliczbowych w tym roku kalendarzowym: {dane.nadgodziny_w_roku_h} h. "
            f"Próg informacyjny urzędu: {progi.nadgodziny_w_roku_h} h.",
            KADRY, f"{_USTAWIENIE}; czas pracy w służbie cywilnej: art. 97 u.s.c.",
            "Do omówienia: przyczyny pracy w godzinach nadliczbowych i podział zadań.",
        ))
    mediana = dane.sprawy_w_toku_mediana_komorki
    if mediana and dane.sprawy_w_toku * 100 >= mediana * progi.sprawy_w_toku_procent_mediany:
        karty.append(KartaObserwacji(
            "SPRAWY_W_TOKU", DOBROSTAN, "Sprawy w toku",
            f"Sprawy w toku: {dane.sprawy_w_toku}. Mediana w komórce organizacyjnej: {mediana}.",
            EZD, f"próg {progi.sprawy_w_toku_procent_mediany}% mediany - {_USTAWIENIE}",
            "Do omówienia: podział spraw w komórce organizacyjnej.",
        ))
    if dane.czynnosci_poza_godzinami_3_mies >= progi.czynnosci_poza_godzinami_3_mies:
        karty.append(KartaObserwacji(
            "PRACA_POZA_GODZINAMI", DOBROSTAN, "Praca poza godzinami urzędu",
            "Czynności w EZD RP zarejestrowane poza godzinami pracy urzędu w ostatnich 3 miesiącach: "
            f"{dane.czynnosci_poza_godzinami_3_mies}.",
            EZD, f"próg {progi.czynnosci_poza_godzinami_3_mies} czynności - {_USTAWIENIE}",
            "Do omówienia: organizacja pracy i terminy zadań.",
        ))

    zakonczone, w_terminie = dane.sprawy_zakonczone_12_mies, dane.sprawy_w_terminie_12_mies
    if zakonczone >= progi.min_licznosc and _procent(w_terminie, zakonczone) >= progi.terminowosc_procent:
        karty.append(KartaObserwacji(
            "TERMINOWOSC", DOCENIENIE, "Terminowość",
            f"Sprawy zakończone w terminie w ostatnich 12 miesiącach: {w_terminie} z {zakonczone} "
            f"({_procent(w_terminie, zakonczone)}%).",
            EZD, f"próg {progi.terminowosc_procent}% - {_USTAWIENIE}", "Warto o tym powiedzieć w rozmowie.",
        ))
    if dane.sprawy_przejete_po_nieobecnych_12_mies >= progi.sprawy_przejete_po_nieobecnych:
        karty.append(KartaObserwacji(
            "PRZEJETE_SPRAWY", DOCENIENIE, "Sprawy przejęte po nieobecnych",
            "Sprawy przejęte po nieobecnych współpracownikach w ostatnich 12 miesiącach: "
            f"{dane.sprawy_przejete_po_nieobecnych_12_mies}.",
            EZD, f"próg {progi.sprawy_przejete_po_nieobecnych} spraw - {_USTAWIENIE}", "Warto za to podziękować.",
        ))
    pisma, bez_poprawek = dane.pisma_12_mies, dane.pisma_bez_poprawek_12_mies
    if pisma >= progi.min_licznosc and _procent(bez_poprawek, pisma) >= progi.pisma_bez_poprawek_procent:
        karty.append(KartaObserwacji(
            "PISMA_BEZ_POPRAWEK", DOCENIENIE, "Pisma bez poprawek",
            f"Projekty pism zaakceptowane bez poprawek w ostatnich 12 miesiącach: {bez_poprawek} z {pisma} "
            f"({_procent(bez_poprawek, pisma)}%).",
            EZD, f"próg {progi.pisma_bez_poprawek_procent}% - {_USTAWIENIE}", "Warto o tym powiedzieć w rozmowie.",
        ))
    if dane.dni_zastepstw_12_mies >= progi.dni_zastepstw:
        karty.append(KartaObserwacji(
            "ZASTEPSTWA", DOCENIENIE, "Zastępstwa",
            f"Dni zastępowania nieobecnych współpracowników w ostatnich 12 miesiącach: {dane.dni_zastepstw_12_mies}.",
            KADRY, f"próg {_dni(progi.dni_zastepstw)} - {_USTAWIENIE}", "Warto za to podziękować.",
        ))
    return tuple(karty)


# --- pytania do kart układane przez model językowy (funkcja wysokiego ryzyka) ---

ZASADY_RADARU = (
    f"{polecenie_dla_modelu()} "
    "Zadanie: pomagasz przełożonemu przygotować rozmowę z pracownikiem. Dostajesz karty obserwacji: "
    "każda ma kod, tytuł i fakt z liczbami. Do każdej karty ułóż jedno pytanie otwarte, które przełożony zada "
    "pracownikowi. Pytanie ma dotyczyć organizacji pracy, planów albo wsparcia, kończyć się znakiem zapytania "
    "i zwracać się w formie „Pani/Pan”. Nie pytaj o zdrowie, emocje, rodzinę ani inne sprawy prywatne. Nie stawiaj "
    "diagnoz, nie oceniaj pracownika i nie dodawaj liczb ani faktów, których nie ma na kartach."
)
_WZOR_KARTY = (
    "Karty obserwacji:\n- SPRAWY_W_TOKU: Sprawy w toku - Sprawy w toku: 24. Mediana w komórce organizacyjnej: 15.\n"
    "- TERMINOWOSC: Terminowość - Sprawy zakończone w terminie w ostatnich 12 miesiącach: 40 z 41 (98%)."
)
_WZOR_PYTANIA = [
    {"kod": "SPRAWY_W_TOKU", "pytanie": "Jak ocenia Pani/Pan obecny podział spraw i co warto w nim zmienić?"},
    {"kod": "TERMINOWOSC", "pytanie": "Co pomaga Pani/Panu kończyć sprawy w terminie i czym warto podzielić się z zespołem?"},
]
# Radar nie wnioskuje o emocjach ani zdrowiu. Wzorce działają na tekście bez znaków diakrytycznych.
_EMOCJE_I_DIAGNOZY = tuple(
    re.compile(wzorzec) for wzorzec in (
        r"\bwypal", r"\bstres", r"\bdepres", r"\bemocj", r"\bpsychi", r"\bprzemecz", r"\bwyczerpan",
        # pytania o stan osoby zamiast o organizację pracy (obserwacja z pokazu na lokalnym modelu)
        r"\bodczuc", r"\bodczuw", r"\bsamopoczuc", r"\bczuj", r"\bczuc", r"\bregenerac", r"\bzmecz", r"\bnastroj",
    )
)


@dataclass(frozen=True)
class PytanieDoKarty:
    kod: str
    pytanie: str


@dataclass(frozen=True)
class PropozycjaPytan:
    """Podpowiedź modelu dla przełożonego. Pytania wybiera i zadaje przełożony."""

    pytania: tuple[PytanieDoKarty, ...] = ()
    ostrzezenia: tuple[str, ...] = ()


def _niedozwolony_temat(tekst: str) -> bool:
    znormalizowany = _normalizuj(tekst)
    return _dotyczy_spraw_prywatnych(tekst) or any(wzorzec.search(znormalizowany) for wzorzec in _EMOCJE_I_DIAGNOZY)


def zaproponuj_pytania(
    karty: Sequence[KartaObserwacji], *, model: Model, wymogi: Wymogi | None = None
) -> PropozycjaPytan:
    """Pytania otwarte do kart obserwacji - po jednym na kartę.

    Funkcja wysokiego ryzyka: wyłączona w rejestrze -> BladZgodnosci. Model dostaje wyłącznie kody, tytuły i fakty
    z kart - bez imienia, nazwiska i jakichkolwiek innych danych osoby. Odpowiedź sprawdzają reguły: pytanie do
    karty, której nie ma, zdanie bez pytajnika oraz pytanie o zdrowie, emocje albo sprawy prywatne są pomijane;
    liczba spoza kart daje ostrzeżenie. Bez kart model nie jest pytany.
    Niedostępny model albo odpowiedź w nieznanej postaci -> BladModelu.
    """
    wymagaj_dozwolonej_funkcji_ai(FUNKCJA_RADARU, wymogi)
    karty = tuple(karty)
    if not karty:
        return PropozycjaPytan()
    zrodlo = "\n".join(f"- {karta.kod}: {karta.tytul} - {karta.fakt}" for karta in karty)
    schemat = {
        "type": "object",
        "properties": {"pytania": {
            "type": "array", "maxItems": len(karty),
            "items": {
                "type": "object",
                "properties": {"kod": {"type": "string", "enum": [karta.kod for karta in karty]}, "pytanie": {"type": "string"}},
                "required": ["kod", "pytanie"],
            },
        }},
        "required": ["pytania"],
    }
    wiadomosci = [
        {"role": "system", "content": ZASADY_RADARU},
        {"role": "user", "content": _WZOR_KARTY},
        {"role": "assistant", "content": json.dumps({"pytania": _WZOR_PYTANIA}, ensure_ascii=False)},
        {"role": "user", "content": f"Karty obserwacji:\n{zrodlo}"},
    ]
    surowa = _zapytaj(model, wiadomosci, schemat)
    try:
        odpowiedz = json.loads(surowa)
    except ValueError as blad:
        raise BladModelu("Model językowy zwrócił pytania do kart w nieznanej postaci.") from blad
    if not isinstance(odpowiedz, dict) or not isinstance(odpowiedz.get("pytania"), list):
        raise BladModelu("Model językowy zwrócił pytania do kart w nieznanej postaci.")

    znane = {karta.kod for karta in karty}
    ostrzezenia: list[str] = []
    pytania: dict[str, PytanieDoKarty] = {}
    for pozycja in odpowiedz["pytania"]:
        if not isinstance(pozycja, dict):
            continue
        kod, pytanie = str(pozycja.get("kod") or ""), " ".join(str(pozycja.get("pytanie") or "").split())
        if not pytanie or kod in pytania:
            continue
        if kod not in znane:
            ostrzezenia.append(f"Model podał pytanie do karty, której nie ma ({kod or 'bez kodu'}) - pominięto je.")
            continue
        if not pytanie.endswith("?"):
            ostrzezenia.append(f"Model podał zdanie, które nie jest pytaniem - pominięto je: „{pytanie}”.")
            continue
        if _niedozwolony_temat(pytanie):
            # Treści odrzuconego pytania nie powtarzamy - przełożony nie powinien jej dostać nawet w ostrzeżeniu.
            ostrzezenia.append("Model zaproponował pytanie dotyczące zdrowia, emocji albo spraw prywatnych - pominięto je.")
            continue
        pytania[kod] = PytanieDoKarty(kod, pytanie)
    wynik = tuple(pytania[karta.kod] for karta in karty if karta.kod in pytania)
    znane_liczby = set(_liczby(zrodlo))
    tekst = " ".join(pozycja.pytanie for pozycja in wynik)
    obce = [liczba for liczba in dict.fromkeys(_liczby(tekst)) if len(liczba) > 1 and liczba not in znane_liczby]
    if obce:
        ostrzezenia.append(f"Pytanie zawiera liczbę, której nie ma na kartach ({', '.join(obce)}) - sprawdź, skąd pochodzi.")
    return PropozycjaPytan(pytania=wynik, ostrzezenia=tuple(ostrzezenia))
