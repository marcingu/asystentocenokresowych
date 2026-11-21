"""Konfiguracja procesu: podgląd dla kadr i dyrektora, edycja przez administratora technicznego."""
from difflib import unified_diff

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from asystent_ocen.konfiguracja import przepisy_z_tekstu

from . import dziennik, rejestr_ai, uprawnienia
from .models import KonfiguracjaProcesu

LIMIT = 64 * 1024


class Konflikt(Exception):
    pass


def _zapisz(request, stan, baza):
    if request.POST.get("wersja") != str(stan.wersja):
        raise Konflikt
    akcja = request.POST.get("akcja")
    if akcja == "toml":
        przed = stan.toml
        po = request.POST.get("tresc", "").replace("\r\n", "\n").replace("\r", "\n")
        if len(po.encode()) > LIMIT:
            raise ValueError("Konfiguracja może mieć najwyżej 64 KB.")
        przepisy = przepisy_z_tekstu(po)
        if not {"A", "B", "C"}.issubset(przepisy.arkusze):
            raise ValueError("W konfiguracji muszą pozostać arkusze A, B i C.")
        if przed == po:
            return False
        pola = {"tresc": po}
        zasob = "przepisy.toml"
        opis = "\n".join(unified_diff(przed.splitlines(), po.splitlines(), "przed", "po", n=0, lineterm=""))
    elif akcja == "opcja":
        kod = request.POST.get("kod", "")
        docelowy = request.POST.get("stan")
        if docelowy not in ("wlacz", "wylacz") or not any(f.kod == kod and f.wlaczona for f in baza.funkcje_ai):
            raise ValueError("Rejestr i decyzje urzędu nie dopuszczają tej zmiany.")
        blokady = set(stan.wylaczone)
        if (kod not in blokady) == (docelowy == "wlacz"):
            return False
        if docelowy == "wlacz":
            blokady.discard(kod)
            opis = f"{kod}: wyłączona -> włączona"
        else:
            blokady.add(kod)
            opis = f"{kod}: włączona -> wyłączona"
        pola = {"wylaczone": sorted(blokady)}
        zasob = "rejestr funkcji AI"
    else:
        raise ValueError("Nieznana czynność.")
    KonfiguracjaProcesu.objects.get_or_create(pk=1)
    with transaction.atomic():
        if not KonfiguracjaProcesu.objects.filter(pk=1, wersja=stan.wersja).update(wersja=stan.wersja + 1, **pola):
            raise Konflikt
        dziennik.zapisz(dziennik.ZMIANA_KONFIGURACJI, request=request, dotyczy=zasob,
                       opis=f"Wersja {stan.wersja} -> {stan.wersja + 1}\n{opis}")
    return True


@require_http_methods(["GET", "POST"])
def przepisy(request):
    edycja = uprawnienia.czy_administrator(request.user)
    if not edycja and (request.method == "POST" or not uprawnienia.widzi_statystyki(request.user)):
        raise PermissionDenied
    stan = request.konfiguracja
    baza, blad_decyzji = rejestr_ai.bazowy()
    tekst = stan.toml
    status = 200
    if request.method == "POST":
        try:
            zmiana = _zapisz(request, stan, baza)
        except Konflikt:
            messages.error(request, "Konfiguracja zmieniła się od otwarcia strony. Odśwież ją i porównaj wartości przed zapisem.")
            status = 409
        except (ValueError, RecursionError) as blad:
            messages.error(request, f"Nie zapisano zmian: {blad}")
            status = 400
            if request.POST.get("akcja") == "toml":
                tekst = request.POST.get("tresc", "")[:LIMIT]
        else:
            messages.success(request, "Zapisano zmianę konfiguracji." if zmiana else "Konfiguracja nie zmieniła się.")
            return redirect("przepisy")
    wymogi, _ = rejestr_ai.stan(stan)
    return render(request, "oceny/przepisy.html", {
        "edycja": edycja, "wersja": stan.wersja, "plik": "przepisy.toml", "tresc": tekst,
        "funkcje_ai": wymogi.funkcje_ai, "przelaczalne": {f.kod for f in baza.funkcje_ai if f.wlaczona},
        "blad_decyzji_ai": blad_decyzji, "warunki_wlaczenia": baza.warunki_wlaczenia,
    }, status=status)
