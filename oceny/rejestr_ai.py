"""Rejestr funkcji AI urzędu: rejestr z pakietu i decyzje urzędu o funkcjach wysokiego ryzyka.

Rejestr z pakietu (`asystent_ocen/zgodnosc.toml`) ma funkcje wysokiego ryzyka wyłączone. O włączeniu decyduje urząd:
po wykonaniu analiz z rejestru zapisuje decyzję (organ, data, dokument każdej analizy) w pliku wskazanym ustawieniem
`ASYSTENT_DECYZJE_AI`. Plik jest czytany przy każdym użyciu, więc usunięcie wpisu wyłącza funkcję od razu. Błędny,
niepełny albo brakujący plik niczego nie włącza: system pracuje dalej na rejestrze z pakietu, a opis błędu
pokazuje strona „Przepisy”.

Decyzja pokazowa (bez analiz) działa tylko w trybie demonstracyjnym, czyli na danych fikcyjnych.
"""

from __future__ import annotations

from dataclasses import replace

from django.conf import settings

from .models import KonfiguracjaProcesu

from asystent_ocen.zgodnosc import BladZgodnosci, Wymogi, wczytaj_wymogi


def bazowy() -> tuple[Wymogi, str]:
    """Wymogi z naniesionymi decyzjami urzędu oraz opis błędu pliku decyzji (pusty, gdy błędu nie ma)."""
    plik = settings.ASYSTENT_DECYZJE_AI
    if not plik:
        return wczytaj_wymogi(), ""
    try:
        return wczytaj_wymogi(decyzje=plik, tryb_pokazu=settings.ASYSTENT_TRYB_DEMO), ""
    except BladZgodnosci as blad:
        return wczytaj_wymogi(), str(blad)


def stan(konfiguracja=None) -> tuple[Wymogi, str]:
    baza, blad = bazowy()
    blokady = set((konfiguracja or KonfiguracjaProcesu.aktualna()).wylaczone)
    funkcje = tuple(replace(f, wlaczona=False) if f.kod in blokady else f for f in baza.funkcje_ai)
    return replace(baza, funkcje_ai=funkcje), blad


def wymogi() -> Wymogi:
    return stan()[0]
