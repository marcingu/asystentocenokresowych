"""HR Copilot - spięcie modułu AI rdzenia (`asystent_ocen.asystent_ai`) z lokalnym modelem językowym.

Model działa lokalnie (Ollama). Każde wywołanie przechodzi w rdzeniu przez rejestr funkcji AI i anonimizację.
AI nie ocenia pracownika: odpowiada na pytania o procedurę i poprawia język tekstu napisanego przez człowieka.
"""

from __future__ import annotations

from django.conf import settings

from asystent_ocen.asystent_ai import BladModelu, KlientOllama, odpowiedz_na_pytanie, popraw_jezyk

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


def model() -> KlientOllama:
    return KlientOllama(
        adres=settings.ASYSTENT_OLLAMA_ADRES,
        model=settings.ASYSTENT_MODEL,
        limit_czasu=settings.ASYSTENT_MODEL_LIMIT_CZASU,
    )


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
