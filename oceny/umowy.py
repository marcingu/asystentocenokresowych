"""Kwalifikacja kadrowa i terminy pierwszej umowy - art. 35, 37 i 38 u.s.c."""
from datetime import timedelta

from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import dziennik, uprawnienia
from .czas import dzis

from asystent_ocen.kalendarz import dodaj_miesiace
from .models import PierwszaOcena, UmowaTerminowa

TERMINOWA = "umowa_na_czas_okreslony"
STALA = "umowa_na_czas_nieokreslony"
DZIEN = timedelta(days=1)
WYJATKI_TERMINOWE = (
    ("ksap", "Pierwsza umowa - absolwent KSAP z wnioskiem o mianowanie"),
    ("zastepstwo", "Zastępstwo - bez pierwszej oceny"),
    ("zastepstwo_ocena", "Zastępstwo - strony ustaliły pierwszą ocenę"),
    ("inna", "Inna umowa terminowa - np. uprzednie zatrudnienie bezterminowe lub art. 34"),
)


def koniec_okresu(od, miesiace):
    rocznica = dodaj_miesiace(od, miesiace)
    return rocznica if rocznica.day < od.day else rocznica - DZIEN


def data_formularza(etykieta, required=True):
    return forms.DateField(label=etykieta, required=required, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


def zaloz_umowe(osoba, pola):
    tryb = pola["kwalifikacja"]
    koniec = koniec_okresu(osoba.data_zatrudnienia, 12) if tryb in ("pierwsza", "ksap") else pola["koniec_umowy"]
    umowa = UmowaTerminowa.objects.create(osoba=osoba, poczatek=osoba.data_zatrudnienia, kwalifikacja=tryb, koniec=koniec)
    if tryb in ("pierwsza", "zastepstwo_ocena"):
        PierwszaOcena.objects.create(umowa=umowa, szef=osoba.przelozony, kierujacy=osoba.wydzial.kierownik,
            dane={"ustalenie": pola["ustalenie"].isoformat()} if tryb == "zastepstwo_ocena" else {})


def do_rozliczenia(dzien):
    return UmowaTerminowa.objects.filter(
        Q(koniec__lt=dzien, stala_od=None, osoba__uzytkownik__is_active=True)
        | Q(stala_od__lte=dzien, osoba__rodzaj_zatrudnienia=TERMINOWA)
    )


def rozlicz_umowy():
    """Idempotentnie, przed uwierzytelnieniem lub z harmonogramu, bez odblokowywania cudzych blokad."""
    from .bezpieczenstwo import zablokuj_konto

    dzien = dzis()
    zmiany = 0
    for pk in do_rozliczenia(dzien).values_list("pk", flat=True):
        with transaction.atomic():
            umowa = do_rozliczenia(dzien).select_for_update().select_related("osoba__uzytkownik").filter(pk=pk).first()
            if not umowa:
                continue
            if umowa.stala_od:
                osoba = umowa.osoba
                osoba.rodzaj_zatrudnienia = STALA
                osoba.save(update_fields=["rodzaj_zatrudnienia"])
                from .cykle import uzgodnij
                uzgodnij(osoba.pk)
            else:
                zablokuj_konto(umowa.osoba.uzytkownik, wykonawca=None, powod="Upłynął okres zatrudnienia.")
            zmiany += 1
    return zmiany


class RozliczenieUmow:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rozlicz_umowy()
        return self.get_response(request)


class ZmianaUmowy(forms.Form):
    akcja = forms.ChoiceField(label="Czynność", choices=(("stala", "Wpisz zawartą umowę na czas nieokreślony"),
        ("przedluzenie", "Wpisz przedłużenie pierwszej umowy przez dyrektora (art. 35 ust. 4)"),
        ("koniec", "Wpisz wcześniejsze zakończenie zatrudnienia")))
    data = data_formularza("Data rozpoczęcia nowej umowy lub zmieniony ostatni dzień zatrudnienia")
    potwierdzenie = forms.BooleanField(label="Potwierdzam datę na podstawie podpisanej umowy lub dokumentu kadrowego; dla przedłużenia - decyzję dyrektora na wniosek pracownika i nieobecność dłuższą niż 3 miesiące.")


@require_http_methods(["GET", "POST"])
@transaction.atomic
def karta_umowy(request, pk):
    if not uprawnienia.czy_kadry(request.user):
        raise PermissionDenied
    umowa = get_object_or_404(UmowaTerminowa.objects.select_for_update(), pk=pk)
    formularz = ZmianaUmowy(request.POST if request.method == "POST" else None)
    if formularz.is_valid():
        akcja, data = formularz.cleaned_data["akcja"], formularz.cleaned_data["data"]
        if umowa.stala_od:
            formularz.add_error(None, "Bezpośrednia kontynuacja została już zarejestrowana.")
        elif akcja == "stala" and data != umowa.koniec + DZIEN:
            formularz.add_error("data", "Kontynuacja bez przerwy zaczyna się dzień po końcu umowy terminowej.")
        elif akcja == "przedluzenie" and (umowa.kwalifikacja not in ("pierwsza", "ksap") or data <= umowa.koniec):
            formularz.add_error("data", "Przedłużenie dotyczy pierwszej umowy i wymaga późniejszej daty.")
        elif akcja == "koniec" and not umowa.poczatek <= data < umowa.koniec:
            formularz.add_error("data", "Wskaż dzień trwania umowy wcześniejszy niż jej planowany koniec.")
        else:
            pole = "stala_od" if akcja == "stala" else "koniec"
            setattr(umowa, pole, data)
            umowa.save(update_fields=[pole])
            dziennik.zapisz(dziennik.PRACOWNIK_ZMIENIONY, request=request, dotyczy=f"umowa {pk}", opis=f"{akcja}: {data}")
            rozlicz_umowy()
            return redirect("karta_umowy", pk=pk)
    return render(request, "oceny/umowa.html", {"umowa": umowa, "formularz": formularz})
