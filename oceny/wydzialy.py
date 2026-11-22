"""Struktura urzędu: słownik komórek organizacyjnych i ich obsada. Zmiany należą do administratora technicznego."""
from django import forms
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from . import dziennik, struktura_kprm
from .models import Pracownik, Wydzial
from .podleglosc import ustaw_obsade
from .widoki_administracji import _wymagaj_administratora


class FormularzWydzialu(forms.Form):
    nazwa = forms.CharField(label="Nazwa komórki organizacyjnej", max_length=160)


class FormularzObsady(forms.Form):
    kierownik = forms.ModelChoiceField(queryset=Pracownik.objects.all(), required=False)
    zwierzchnik = forms.ModelChoiceField(queryset=Pracownik.objects.all(), required=False)


def _powrot(pk=None, *, blad: bool = False):
    """Powrót na stronę struktury. Po zapisie w komórce jej gałąź zostaje rozwinięta i przewinięta na ekran -
    widać skutek. Po błędzie strona wraca na początek treści, bo kotwica gałęzi schowałaby komunikat."""
    adres = reverse("wydzialy") + (f"?otwarta={pk}" if pk else "")
    return redirect(adres + (f"#wydzial-{pk}" if pk and not blad else "#tresc"))


@require_http_methods(["GET", "POST"])
def struktura(request):
    _wymagaj_administratora(request)
    if request.method == "POST":
        akcja = request.POST.get("akcja")
        numer = request.POST.get("pk", "")
        pk = int(numer) if akcja in {"zmien", "obsada"} and numer.isascii() and numer.isdigit() else None
        if akcja not in {"dodaj", "zmien", "usun", "obsada", "wczytaj"}:
            messages.error(request, "Nieznana czynność.")
            return _powrot(blad=True)
        if akcja == "wczytaj":
            with transaction.atomic():
                dodane = struktura_kprm.wczytaj()
                opis = (f"Dodano {len(dodane)} {_komorki(len(dodane))} z listy KPRM." if dodane
                        else "Wszystkie komórki z listy KPRM są już w strukturze.")
                dziennik.zapisz(dziennik.PANEL_ADMINISTRATORA, request=request, dotyczy="struktura urzędu",
                               opis=f"{opis} Źródło: {struktura_kprm.ZRODLO}, odczyt {struktura_kprm.ODCZYT:%d.%m.%Y}.")
            messages.success(request, opis)
            return _powrot()
        formularz = FormularzWydzialu(request.POST)
        if akcja in {"dodaj", "zmien"} and not formularz.is_valid():
            messages.error(request, "Podaj nazwę komórki organizacyjnej (od 1 do 160 znaków).")
            return _powrot(pk, blad=True)
        try:
            with transaction.atomic():
                wpis = Wydzial()
                if akcja != "dodaj":
                    identyfikator = forms.IntegerField(min_value=1).clean(request.POST.get("pk"))
                    wpis = get_object_or_404(Wydzial.objects.select_for_update(), pk=identyfikator)
                if akcja == "usun":
                    opis = f"Usunięto komórkę: {wpis.nazwa}."
                    wpis.delete()
                elif akcja == "obsada":
                    obsada = FormularzObsady(request.POST)
                    if not obsada.is_valid() or "kierownik" not in request.POST:
                        raise forms.ValidationError("Nie zapisano obsady. Wybierz osobę z ewidencji.")
                    ustaw_obsade(wpis, **obsada.cleaned_data)
                    opis = f"Zapisano obsadę komórki: {wpis.nazwa}."
                else:
                    nazwa = formularz.cleaned_data["nazwa"]
                    if Wydzial.objects.filter(nazwa__iexact=nazwa).exclude(pk=wpis.pk).exists():
                        raise forms.ValidationError("Komórka organizacyjna o tej nazwie już istnieje.")
                    opis = f"Zmieniono nazwę: {wpis.nazwa} -> {nazwa}." if wpis.pk else f"Dodano komórkę: {nazwa}."
                    wpis.nazwa = nazwa
                    wpis.save()
                dziennik.zapisz(dziennik.PANEL_ADMINISTRATORA, request=request, dotyczy="struktura urzędu", opis=opis)
        except ProtectedError:
            messages.error(request, "Nie usunięto komórki. Najpierw przenieś przypisanych do niej pracowników.")
        except forms.ValidationError as blad:
            messages.error(request, " ".join(blad.messages))
        except IntegrityError:
            messages.error(request, "Nie zapisano komórki. Odśwież listę i sprawdź nazwę.")
        else:
            messages.success(request, opis)
            return _powrot(pk)
        return _powrot(pk, blad=True)
    osoby = list(Pracownik.objects.select_related("wydzial").order_by("nazwisko", "imie", "pk"))
    return render(request, "oceny/wydzialy.html", {
        "galezie": drzewo(osoby, otwarta=request.GET.get("otwarta", "")),
        "osoby": osoby,
        "zrodlo_kprm": struktura_kprm.ZRODLO, "odczyt_kprm": struktura_kprm.ODCZYT, "liczba_kprm": len(struktura_kprm.KOMORKI),
    })


def drzewo(osoby: list[Pracownik], otwarta: str = "") -> list[dict]:
    """Gałęzie drzewa struktury (urząd - komórki - stanowiska z osobami), w układzie znanym z EZD.

    Osoba kierująca stoi w gałęzi pierwsza i nie jest wypisana drugi raz wśród pozostałych. `otwarta` to numer
    komórki, której gałąź ma być rozwinięta; pozostałe są zwinięte."""
    w_komorce: dict[int, list[Pracownik]] = {}
    for osoba in osoby:
        if osoba.wydzial_id:
            w_komorce.setdefault(osoba.wydzial_id, []).append(osoba)
    galezie = []
    for wpis in Wydzial.objects.select_related("kierownik__wydzial", "zwierzchnik"):
        przypisani = w_komorce.get(wpis.pk, [])
        kierujacy = wpis.kierownik
        galezie.append({
            "wpis": wpis,
            "kierujacy": kierujacy,
            "kierujacy_z_innej_komorki": kierujacy.komorka if kierujacy and kierujacy.wydzial_id != wpis.pk else "",
            "osoby": [osoba for osoba in przypisani if osoba.pk != wpis.kierownik_id],
            "liczba": len(przypisani),
            "liczba_opis": _osoby(len(przypisani)),
            "otwarta": otwarta == str(wpis.pk),
        })
    return galezie


def _osoby(liczba: int) -> str:
    """Odmiana po liczebniku: brak osób, 1 osoba, 2-4 osoby, 5-21 osób, 22-24 osoby."""
    if liczba == 0:
        return "brak osób"
    if liczba == 1:
        return "1 osoba"
    if liczba % 10 in (2, 3, 4) and liczba % 100 not in (12, 13, 14):
        return f"{liczba} osoby"
    return f"{liczba} osób"


def _komorki(liczba: int) -> str:
    """Odmiana po liczebniku: 1 komórkę, 2-4 komórki, 5-21 komórek, 22-24 komórki."""
    if liczba == 1:
        return "komórkę organizacyjną"
    if liczba % 10 in (2, 3, 4) and liczba % 100 not in (12, 13, 14):
        return "komórki organizacyjne"
    return "komórek organizacyjnych"
