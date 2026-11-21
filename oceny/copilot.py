"""HR Copilot - spięcie modułu AI rdzenia (`asystent_ocen.asystent_ai`) z lokalnym modelem językowym.

Model działa lokalnie (Ollama). Każde wywołanie przechodzi w rdzeniu przez rejestr funkcji AI i anonimizację.
AI nie ocenia pracownika: odpowiada na pytania o procedurę, poprawia język tekstu napisanego przez człowieka
i układa notatki oceniającego w projekt uzasadnienia, o którego losie decyduje oceniający.
"""

from __future__ import annotations

from django.conf import settings

from asystent_ocen.asystent_ai import (
    FUNKCJA_REDAKCJI,
    BladModelu,
    KlientOllama,
    odpowiedz_na_pytanie,
    popraw_jezyk,
    zredaguj_notatki,
)
from asystent_ocen.zgodnosc import BladZgodnosci, wymagaj_dozwolonej_funkcji_ai

PRZYKLADOWE_PYTANIA = (
    "Co ile sporządza się ocenę okresową?",
    "Ile mam czasu na sprzeciw od oceny?",
    "Kiedy oceniający musi napisać uzasadnienie oceny?",
    "Ile kryteriów dodatkowych może wybrać oceniający?",
    "Co się dzieje po ocenie negatywnej?",
)

MODEL_NIEDOSTEPNY = (
    "Lokalny model językowy jest teraz niedostępny. Proces oceny działa bez niego - asystent jest dodatkiem."
)
FUNKCJA_WYLACZONA = "Ta funkcja asystenta jest wyłączona w rejestrze funkcji AI urzędu."


def model() -> KlientOllama:
    return KlientOllama(
        adres=settings.ASYSTENT_OLLAMA_ADRES,
        model=settings.ASYSTENT_MODEL,
        limit_czasu=settings.ASYSTENT_MODEL_LIMIT_CZASU,
    )


def funkcja_wlaczona(kod: str) -> bool:
    """Czy rejestr funkcji AI (`zgodnosc.toml`) dopuszcza funkcję o tym kodzie."""
    try:
        wymagaj_dozwolonej_funkcji_ai(kod)
    except BladZgodnosci:
        return False
    return True


def redakcja_notatek_dostepna() -> bool:
    return funkcja_wlaczona(FUNKCJA_REDAKCJI)


def odpowiedz(pytanie: str) -> dict:
    """Odpowiedź na pytanie o procedurę: tekst, przepisy podane modelowi i ostrzeżenia kontroli odpowiedzi."""
    try:
        wynik = odpowiedz_na_pytanie(pytanie, model=model())
    except BladModelu:
        return {"blad": MODEL_NIEDOSTEPNY}
    return {"odpowiedz": wynik}


def korekta(tekst: str, osoby: list[str]) -> dict:
    """Propozycja poprawek językowych tekstu oceniającego. Treść merytoryczna zostaje jego."""
    try:
        wynik = popraw_jezyk(tekst, model=model(), osoby=osoby)
    except BladModelu:
        return {"blad": MODEL_NIEDOSTEPNY}
    return {"korekta": wynik}


def projekt_uzasadnienia(notatki: list[str], osoby: list[str]) -> dict:
    """Projekt uzasadnienia ułożony z notatek oceniającego - bez ocen cząstkowych i bez danych z EZD RP.

    Zwraca słownik z kluczem „projekt” (wynik rdzenia, także odmowa przy braku notatek) albo „blad” (komunikat).
    """
    try:
        wynik = zredaguj_notatki(notatki, model=model(), osoby=osoby)
    except BladZgodnosci:
        return {"blad": FUNKCJA_WYLACZONA}
    except BladModelu:
        return {"blad": MODEL_NIEDOSTEPNY}
    return {"projekt": wynik}
