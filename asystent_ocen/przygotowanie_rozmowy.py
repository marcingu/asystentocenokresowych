"""Wirtualny HR partner: przygotowanie rozmowy oceniającej z notatek oceniającego.

Dwie funkcje z rejestru funkcji AI (`zgodnosc.toml`):

- PYTANIA_DO_ROZMOWY_OCENIAJACEJ - lista 3-5 pytań do rozmowy oceniającej (§ 10 rozp.). Model układa pytania
  z notatek napisanych przez oceniającego; nie ocenia pracownika i nie proponuje ocen. Po instalacji włączona
  (zadanie przygotowawcze, art. 6 ust. 3 lit. d AI Act - kwalifikacja robocza).
- PROPOZYCJA_KIERUNKOW_IPRZ - propozycja kierunków rozwoju do indywidualnego programu rozwoju zawodowego
  (§ 11 ust. 1 pkt 5 rozp.). Wskazanie potrzeb rozwojowych konkretnej osoby to ocena czynników osobowych,
  więc funkcja wysokiego ryzyka: po instalacji wyłączona, włącza ją wyłącznie decyzja urzędu.

Model dostaje tylko notatki, bez danych osobowych. Nie dostaje ocen cząstkowych, szkicu, wyniku oceny ani danych
z EZD RP. Pytania wybiera i zadaje oceniający, a wnioski do IPRZ wpisuje sam - wynik jest podpowiedzią.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .anonimizacja import anonimizuj, przywroc
from .asystent_ai import (
    _O_ZNACZNIKACH,
    MIN_NOTATEK_DO_SUGESTII,
    ODMOWA_BRAK_NOTATEK,
    BladModelu,
    Model,
    _liczby,
    _normalizuj,
    _sformulowania_o_ocenie,
    _zapytaj,
)
from .zgodnosc import BladZgodnosci, Wymogi, wymagaj_dozwolonej_funkcji_ai

FUNKCJA_PYTAN_DO_ROZMOWY = "PYTANIA_DO_ROZMOWY_OCENIAJACEJ"
FUNKCJA_KIERUNKOW_IPRZ = "PROPOZYCJA_KIERUNKOW_IPRZ"
MIN_PYTAN = 3
MAX_PYTAN = 5
MAX_KIERUNKOW = 3

ZASADY_ROZMOWY = (
    "Pomagasz przełożonemu przygotować rozmowę oceniającą w służbie cywilnej. Rozmowa ma być dialogiem, a nie "
    "monologiem przełożonego. Omawia się w niej obowiązki pracownika i sposób ich realizacji, realizację celów "
    "oraz kierunki rozwoju zawodowego i potrzeby szkoleniowe. Na podstawie wyłącznie notatek przełożonego ułóż "
    "od 3 do 5 pytań otwartych, które przełożony zada pracownikowi. Każde pytanie ma dotyczyć pracy opisanej "
    "w notatkach, zachęcać pracownika do własnej oceny tej pracy albo do rozmowy o rozwoju i kończyć się znakiem "
    "zapytania. Zwracaj się do pracownika w formie „Pani/Pan”. Nie pytaj o zdrowie, rodzinę, poglądy ani inne "
    "sprawy prywatne. Nie oceniaj pracownika, nie proponuj ocen ani punktów i nie dodawaj faktów, liczb ani dat, "
    "których nie ma w notatkach."
)
ZASADY_KIERUNKOW = (
    " Zaproponuj też najwyżej 3 kierunki rozwoju do indywidualnego programu rozwoju zawodowego, na przykład "
    "szkolenie, samokształcenie, nowe zadanie albo wymianę doświadczeń. Przy każdym kierunku wskaż krótko notatkę, "
    "z której wynika. Jeżeli notatki nie dają podstaw, zwróć pustą listę kierunków - nie zgaduj."
)

# Przykład oczekiwanej postaci odpowiedzi. Dane są zmyślone.
_WZOR_NOTATKI = (
    "Notatki przełożonego:\n- prowadzi rejestr umów na bieżąco, bez zaległości\n- marzec 2025: nowy wzór "
    "zestawienia kwartalnego, używa go cały wydział\n- 2 razy sprawozdanie po terminie (3 i 5 dni)"
)
_WZOR_PYTANIA = [
    "Co pomaga Pani/Panu prowadzić rejestr umów bez zaległości?",
    "Jak powstał nowy wzór zestawienia kwartalnego i co warto w nim jeszcze poprawić?",
    "Co utrudniło przekazanie sprawozdań w terminie i co pomogłoby tego uniknąć?",
    "Jakie zadania chce Pani/Pan rozwijać w kolejnym okresie?",
]
_WZOR_KIERUNKI = [
    {"kierunek": "Szkolenie z planowania pracy i terminów sprawozdawczych",
     "podstawa": "Sprawozdanie przekazano po terminie 2 razy."},
    {"kierunek": "Poprowadzenie krótkiego szkolenia wewnętrznego z nowego wzoru zestawienia",
     "podstawa": "Nowy wzór zestawienia kwartalnego stosuje cały wydział."},
]

# Rozmowa oceniająca dotyczy obowiązków, celów i rozwoju (§ 10 rozp.). Pytania o zdrowie, rodzinę i przekonania
# odrzucamy - decyzja projektowa. Wzorce działają na tekście bez znaków diakrytycznych.
_TEMATY_PRYWATNE = tuple(
    re.compile(wzorzec)
    for wzorzec in (
        r"\bzdrow", r"\bchor(?:ob|uj|y\b|a\b|ego\b)", r"\bzwolnieni\w* lekarsk", r"\bniepelnosprawn", r"\bciaz",
        r"\brodzin", r"\bdziec", r"\bmalzen", r"\bwyznan", r"\breligi", r"\bpoglad\w* polityczn", r"\bparti",
        r"zwiazk\w* zawodow", r"\borientacj\w* seksualn", r"\bnarodowosc",
    )
)


@dataclass(frozen=True)
class KierunekIprz:
    kierunek: str
    podstawa: str = ""  # notatka, z której model wyprowadził kierunek


@dataclass(frozen=True)
class PrzygotowanieRozmowy:
    """Podpowiedź modelu do rozmowy oceniającej. Pytania zadaje, a wnioski do IPRZ wpisuje oceniający."""

    pytania: tuple[str, ...] = ()
    kierunki_iprz: tuple[KierunekIprz, ...] = ()
    z_kierunkami: bool = False  # czy model był pytany o kierunki IPRZ (funkcja wysokiego ryzyka)
    odmowa: bool = False
    powod: str = ""  # przy odmowie: ODMOWA_BRAK_NOTATEK
    ostrzezenia: tuple[str, ...] = ()


def _schemat(z_kierunkami: bool) -> dict:
    wlasciwosci: dict = {
        "pytania": {"type": "array", "items": {"type": "string"}, "minItems": MIN_PYTAN, "maxItems": MAX_PYTAN}
    }
    if z_kierunkami:
        wlasciwosci["kierunki_iprz"] = {
            "type": "array",
            "maxItems": MAX_KIERUNKOW,
            "items": {
                "type": "object",
                "properties": {"kierunek": {"type": "string"}, "podstawa": {"type": "string"}},
                "required": ["kierunek", "podstawa"],
            },
        }
    return {"type": "object", "properties": wlasciwosci, "required": list(wlasciwosci)}


def _dotyczy_spraw_prywatnych(tekst: str) -> bool:
    znormalizowany = _normalizuj(tekst)
    return any(wzorzec.search(znormalizowany) for wzorzec in _TEMATY_PRYWATNE)


def _kierunki_wlaczone(wymogi: Wymogi | None) -> bool:
    try:
        wymagaj_dozwolonej_funkcji_ai(FUNKCJA_KIERUNKOW_IPRZ, wymogi)
    except BladZgodnosci:
        return False
    return True


def przygotuj_rozmowe(
    notatki: Iterable[str], *, model: Model, wymogi: Wymogi | None = None, osoby: Sequence[str] = ()
) -> PrzygotowanieRozmowy:
    """Pytania do rozmowy oceniającej i - gdy urząd włączył tę funkcję - propozycja kierunków do IPRZ.

    Model dostaje wyłącznie notatki oceniającego, bez danych osobowych (`osoby` to imiona i nazwiska do ukrycia).
    Odpowiedź sprawdzają reguły: zdanie, które nie jest pytaniem, oraz pytanie o zdrowie albo sprawy prywatne są
    pomijane; pytania ponad limit są obcinane; liczba spoza notatek i sformułowanie o ocenie dają ostrzeżenie.
    Kierunki IPRZ model proponuje tylko wtedy, gdy funkcja wysokiego ryzyka jest włączona decyzją urzędu, a notatek
    jest co najmniej `MIN_NOTATEK_DO_SUGESTII`.
    Brak notatek -> odmowa bez wywołania modelu. Funkcja pytań wyłączona w rejestrze -> BladZgodnosci.
    Niedostępny model albo odpowiedź w nieznanej postaci -> BladModelu.
    """
    wymagaj_dozwolonej_funkcji_ai(FUNKCJA_PYTAN_DO_ROZMOWY, wymogi)
    if isinstance(notatki, str):
        notatki = [notatki]
    tresci = [str(notatka).strip() for notatka in notatki if str(notatka or "").strip()]
    if not tresci:
        return PrzygotowanieRozmowy(odmowa=True, powod=ODMOWA_BRAK_NOTATEK)
    z_kierunkami = len(tresci) >= MIN_NOTATEK_DO_SUGESTII and _kierunki_wlaczone(wymogi)
    zrodlo = "\n".join(f"- {tresc}" for tresc in tresci)
    zanonimizowane = anonimizuj(zrodlo, osoby)
    polecenie = f"Notatki przełożonego:\n{zanonimizowane.tekst}"
    if zanonimizowane.mapa:
        polecenie += f"\n\n{_O_ZNACZNIKACH}"
    wzor = {"pytania": _WZOR_PYTANIA}
    if z_kierunkami:
        wzor["kierunki_iprz"] = _WZOR_KIERUNKI
    wiadomosci = [
        {"role": "system", "content": ZASADY_ROZMOWY + (ZASADY_KIERUNKOW if z_kierunkami else "")},
        {"role": "user", "content": _WZOR_NOTATKI},
        {"role": "assistant", "content": json.dumps(wzor, ensure_ascii=False)},
        {"role": "user", "content": polecenie},
    ]
    surowa = _zapytaj(model, wiadomosci, _schemat(z_kierunkami))
    try:
        odpowiedz = json.loads(surowa)
    except ValueError as blad:
        raise BladModelu("Model językowy zwrócił przygotowanie rozmowy w nieznanej postaci.") from blad
    if not isinstance(odpowiedz, dict) or not isinstance(odpowiedz.get("pytania"), list):
        raise BladModelu("Model językowy zwrócił przygotowanie rozmowy w nieznanej postaci.")

    ostrzezenia: list[str] = []
    pytania: list[str] = []
    for pozycja in odpowiedz["pytania"]:
        if not isinstance(pozycja, str) or not pozycja.strip():
            continue
        pytanie = przywroc(" ".join(pozycja.split()), zanonimizowane.mapa)
        if pytanie in pytania:
            continue
        if not pytanie.endswith("?"):
            ostrzezenia.append(f"Model podał zdanie, które nie jest pytaniem - pominięto je: „{pytanie}”.")
            continue
        if _dotyczy_spraw_prywatnych(pytanie):
            ostrzezenia.append(f"Pominięto pytanie dotyczące zdrowia albo spraw prywatnych: „{pytanie}”.")
            continue
        pytania.append(pytanie)
    if len(pytania) > MAX_PYTAN:
        ostrzezenia.append(f"Model podał więcej niż {MAX_PYTAN} pytań - pokazano pierwszych {MAX_PYTAN}.")
        pytania = pytania[:MAX_PYTAN]
    if len(pytania) < MIN_PYTAN:
        ostrzezenia.append(f"Model podał mniej niż {MIN_PYTAN} pytania nadające się do rozmowy - dopisz własne.")

    kierunki: list[KierunekIprz] = []
    if z_kierunkami:
        for pozycja in odpowiedz.get("kierunki_iprz") or []:
            if not isinstance(pozycja, dict) or not str(pozycja.get("kierunek") or "").strip():
                continue
            kierunek = przywroc(" ".join(str(pozycja["kierunek"]).split()), zanonimizowane.mapa)
            podstawa = przywroc(" ".join(str(pozycja.get("podstawa") or "").split()), zanonimizowane.mapa)
            if _dotyczy_spraw_prywatnych(kierunek) or any(kierunek == przyjety.kierunek for przyjety in kierunki):
                continue
            if len(kierunki) == MAX_KIERUNKOW:
                break
            if not podstawa:
                ostrzezenia.append(
                    f"Model nie wskazał notatki, z której wynika kierunek „{kierunek}” - sprawdź, czy ma podstawy."
                )
            kierunki.append(KierunekIprz(kierunek, podstawa))

    caly_tekst = " ".join([*pytania, *(f"{kierunek.kierunek} {kierunek.podstawa}" for kierunek in kierunki)])
    znane_liczby = set(_liczby(zrodlo))
    obce = [liczba for liczba in dict.fromkeys(_liczby(caly_tekst)) if len(liczba) > 1 and liczba not in znane_liczby]
    if obce:
        ostrzezenia.append(
            f"Podpowiedź zawiera liczbę, której nie ma w notatkach ({', '.join(obce)}) - sprawdź, skąd pochodzi."
        )
    o_ocenie = _sformulowania_o_ocenie(caly_tekst, zrodlo)
    if o_ocenie:
        cytaty = ", ".join(f"„{fragment}”" for fragment in o_ocenie)
        ostrzezenia.append(
            f"Podpowiedź zawiera sformułowanie o ocenie albo poziomie spełniania kryteriów ({cytaty}), którego nie ma "
            "w notatkach - ocenę i poziom ustala wyłącznie oceniający."
        )
    return PrzygotowanieRozmowy(
        pytania=tuple(pytania), kierunki_iprz=tuple(kierunki), z_kierunkami=z_kierunkami, ostrzezenia=tuple(ostrzezenia)
    )
