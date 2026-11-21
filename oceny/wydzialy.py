"""Słownik wydziałów urzędu. Zmiany należą do administratora technicznego."""
from django import forms
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import dziennik
from .models import Wydzial
from .widoki_administracji import _wymagaj_administratora


class FormularzWydzialu(forms.Form):
    nazwa = forms.CharField(label="Nazwa wydziału", max_length=160)


@require_http_methods(["GET", "POST"])
def struktura(request):
    _wymagaj_administratora(request)
    if request.method == "POST":
        akcja = request.POST.get("akcja")
        if akcja not in {"dodaj", "zmien", "usun"}:
            messages.error(request, "Nieznana czynność.")
            return redirect("wydzialy")
        formularz = FormularzWydzialu(request.POST)
        if akcja != "usun" and not formularz.is_valid():
            messages.error(request, "Podaj nazwę wydziału (od 1 do 160 znaków).")
            return redirect("wydzialy")
        try:
            with transaction.atomic():
                wpis = Wydzial()
                if akcja != "dodaj":
                    identyfikator = forms.IntegerField(min_value=1).clean(request.POST.get("pk"))
                    wpis = get_object_or_404(Wydzial.objects.select_for_update(), pk=identyfikator)
                if akcja == "usun":
                    opis = f"Usunięto wydział: {wpis.nazwa}."
                    wpis.delete()
                else:
                    nazwa = formularz.cleaned_data["nazwa"]
                    if Wydzial.objects.filter(nazwa__iexact=nazwa).exclude(pk=wpis.pk).exists():
                        raise forms.ValidationError("Wydział o tej nazwie już istnieje.")
                    opis = f"Zmieniono nazwę: {wpis.nazwa} -> {nazwa}." if wpis.pk else f"Dodano wydział: {nazwa}."
                    wpis.nazwa = nazwa
                    wpis.save()
                dziennik.zapisz(dziennik.PANEL_ADMINISTRATORA, request=request, dotyczy="struktura wydziałów", opis=opis)
        except ProtectedError:
            messages.error(request, "Nie usunięto wydziału. Najpierw przenieś przypisanych do niego pracowników.")
        except forms.ValidationError as blad:
            messages.error(request, " ".join(blad.messages))
        except IntegrityError:
            messages.error(request, "Nie zapisano wydziału. Odśwież listę i sprawdź nazwę.")
        else:
            messages.success(request, opis)
        return redirect("wydzialy")
    return render(request, "oceny/wydzialy.html", {"wydzialy": Wydzial.objects.annotate(liczba=Count("pracownicy"))})
