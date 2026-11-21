"""Rejestr funkcji AI urzędu: rejestr z pakietu i decyzje urzędu o funkcjach wysokiego ryzyka.

Rejestr z pakietu (`asystent_ocen/zgodnosc.toml`) ma funkcje wysokiego ryzyka wyłączone. Urząd włącza taką funkcję
własną decyzją zapisaną w pliku wskazanym ustawieniem `ASYSTENT_DECYZJE_AI`. Plik jest czytany przy każdym użyciu,
więc usunięcie wpisu wyłącza funkcję od razu. Błędny albo brakujący plik niczego nie włącza: system pracuje dalej
na rejestrze z pakietu, a opis błędu pokazuje strona „Przepisy”.
"""

from __future__ import annotations

from django.conf import settings

from asystent_ocen.zgodnosc import BladZgodnosci, Wymogi, wczytaj_wymogi


def stan() -> tuple[Wymogi, str]:
    """Wymogi z naniesionymi decyzjami urzędu oraz opis błędu pliku decyzji (pusty, gdy błędu nie ma)."""
    plik = settings.ASYSTENT_DECYZJE_AI
    if not plik:
        return wczytaj_wymogi(), ""
    try:
        return wczytaj_wymogi(decyzje=plik), ""
    except BladZgodnosci as blad:
        return wczytaj_wymogi(), str(blad)


def wymogi() -> Wymogi:
    return stan()[0]
