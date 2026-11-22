"""Pierwsza ocena w służbie cywilnej - art. 38 u.s.c., Dz. U. 2015 poz. 1144."""
from datetime import date

from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from asystent_ocen.kalendarz import dodaj_miesiace, koniec_terminu_dni
from . import dziennik, uprawnienia
from .czas import dzis
from .models import PierwszaOcena
from .umowy import DZIEN, data_formularza, koniec_okresu

ELEMENTY = ("Rzetelność", "Wykorzystywanie wiedzy i doskonalenie zawodowe", "Organizacja pracy i orientacja na osiąganie celów", "Komunikacja", "Współpraca")
WNIOSKI = {"stala": "Zawarcie umowy na czas nieokreślony", "brak": "Niezawieranie umowy na czas nieokreślony", "rozwiazanie": "Rozwiązanie umowy na czas określony"}


def widoczne(user):
    osoba = uprawnienia.pracownik_uzytkownika(user)
    qs = PierwszaOcena.objects.select_related("umowa__osoba__wydzial", "szef", "kierujacy")
    if not osoba:
        return qs.none()
    warunki = Q(umowa__osoba=osoba) | Q(szef=osoba) | Q(kierujacy=osoba)
    if osoba.rola_dyrektor:
        warunki |= Q(dane__has_key="wniosek")
    return qs.filter(warunki)


class Wstepna(forms.Form):
    rozmowa = data_formularza("Data rozmowy wstępnej")
    od = data_formularza("Termin złożenia sprawozdania - od")
    do = data_formularza("Termin złożenia sprawozdania - do")


class NowyTermin(forms.Form):
    od = data_formularza("Nowy początek terminu sprawozdania")
    do = data_formularza("Nowy koniec terminu sprawozdania")
    pismo = forms.BooleanField(label="Potwierdzam podstawę z § 6 rozporządzenia oraz pisemne zawiadomienie pracownika. Kopię należy dołączyć do arkusza.")


def wynik_pozytywny(punkty, egzamin, na_czas):
    return na_czas and egzamin != "nie" and punkty.count(3) <= 1 and sum(punkty) >= 5 * len(punkty)


class Raport(forms.Form):
    tresc = forms.CharField(label="Sprawozdanie: wykonane zadania, problemy i rozwiązania, zdobyta wiedza i umiejętności, propozycje usprawnień", widget=forms.Textarea, max_length=20000)
    okres = forms.BooleanField(label="Sprawozdanie obejmuje co najmniej 7 przepracowanych miesięcy.")


class Ocena(forms.Form):
    rozmowa = data_formularza("Data rozmowy oceniającej")
    egzamin = forms.ChoiceField(label="Wynik egzaminu", choices=(("", "- wybierz -"), ("tak", "Zaliczony"), ("nie", "Niezaliczony"), ("ksap", "Nie dotyczy - absolwent KSAP bez wniosku o mianowanie"), ("wyzsze", "Nie dotyczy - wyższe stanowisko")))
    porozumienie = forms.BooleanField(label="Potwierdzam dokonanie oceny w porozumieniu z kierującym komórką.")
    uzasadnienie = forms.CharField(label="Uzasadnienie (obowiązkowe przy ocenie negatywnej)", widget=forms.Textarea, max_length=8000, required=False)
    rozwoj = forms.CharField(label="Wnioski rozwojowe (tylko przy ocenie pozytywnej, nieobowiązkowe)", widget=forms.Textarea, max_length=4000, required=False)

    def __init__(self, *args, zastepstwo=False, **kwargs):
        super().__init__(*args, **kwargs)
        if zastepstwo:
            self.fields["egzamin"].choices = [("zastepstwo", "Nie dotyczy - zastępstwo")]
        for i, nazwa in enumerate(ELEMENTY):
            self.fields[f"pkt{i}"] = forms.TypedChoiceField(label=nazwa, coerce=int, choices=[("", "- wybierz -"), (3, "3 - poniżej oczekiwań"), (5, "5 - na poziomie oczekiwań"), (7, "7 - powyżej oczekiwań")])
        self.order_fields(["rozmowa", *(f"pkt{i}" for i in range(5)), "egzamin", "uzasadnienie", "rozwoj", "porozumienie"])


class Wniosek(forms.Form):
    wybor = forms.ChoiceField(label="Wniosek do dyrektora generalnego")

    def __init__(self, *args, pozytywna, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wybor"].choices = [(k, v) for k, v in WNIOSKI.items() if (k == "stala") == pozytywna]


def zapisz_etap(akcja, formularz, ocena, dzien, od, do):
    dane, pola = ocena.dane, formularz.cleaned_data
    zapis = {k: v.isoformat() if isinstance(v, date) else v for k, v in pola.items()}
    zapis["data"] = dzien.isoformat()
    if akcja == "wstepna":
        if not date.fromisoformat(dane.get("ustalenie", ocena.umowa.poczatek.isoformat())) <= pola["rozmowa"] <= min(dzien, ocena.umowa.koniec):
            formularz.add_error("rozmowa", "Podaj faktyczną datę rozmowy w okresie zatrudnienia.")
        if not od <= pola["od"] <= pola["do"] <= do or pola["rozmowa"] > pola["od"]:
            formularz.add_error("do", "Termin sprawozdania musi mieścić się w okresie pierwszej oceny i nie poprzedzać rozmowy.")
    elif akcja == "termin":
        if not od <= pola["od"] <= pola["do"] <= do or pola["do"].isoformat() <= dane["wstepna"]["do"] or pola["do"] < dzien:
            formularz.add_error("do", "Wskaż późniejszy termin w okresie oceny.")
        else:
            dane.setdefault("historia_terminow", []).append(dict(dane["wstepna"]))
            dane["wstepna"].update(od=zapis["od"], do=zapis["do"])
    elif akcja == "raport":
        if dzien < od or dzien > do:
            formularz.add_error(None, "Sprawozdanie poza okresem pierwszej oceny.")
    elif akcja == "ocena":
        raport = dane.get("raport", {}).get("data", "")
        koniec = dane["wstepna"]["do"]
        rozmowa = pola["rozmowa"]
        po_sprawozdaniu = raport and rozmowa.isoformat() >= raport
        po_terminie = rozmowa.isoformat() > koniec
        if not od <= rozmowa <= dzien <= do or not (po_sprawozdaniu or po_terminie):
            formularz.add_error("rozmowa", "Rozmowa i ocena muszą przypadać w okresie oceny, po złożeniu sprawozdania albo upływie jego terminu.")
        na_czas = dane["wstepna"]["od"] <= raport <= koniec
        punkty = [pola[f"pkt{i}"] for i in range(len(ELEMENTY))]
        srednia = sum(punkty) / len(punkty)
        pozytywna = wynik_pozytywny(punkty, pola["egzamin"], na_czas)
        if not pozytywna and not pola["uzasadnienie"]:
            formularz.add_error("uzasadnienie", "Uzasadnij ocenę negatywną.")
        if not pozytywna and pola["rozwoj"]:
            formularz.add_error("rozwoj", "Wnioski rozwojowe można wpisać tylko przy ocenie pozytywnej.")
        zapis.update(wynik="Pozytywna" if pozytywna else "Negatywna", srednia=srednia, na_czas=na_czas)
    if formularz.errors:
        return False
    dane[akcja] = zapis
    ocena.save(update_fields=["dane"])
    return True


@require_http_methods(["GET", "POST"])
@transaction.atomic
def karta(request, pk):
    ocena = get_object_or_404(PierwszaOcena.objects.select_for_update().select_related("umowa__osoba__wydzial", "szef", "kierujacy"), pk=pk)
    if not widoczne(request.user).filter(pk=pk).exists():
        raise PermissionDenied
    osoba = uprawnienia.pracownik_uzytkownika(request.user)
    dane, umowa, dzien = ocena.dane, ocena.umowa, dzis()
    od, do = koniec_okresu(umowa.poczatek, 8) + DZIEN, dodaj_miesiace(umowa.koniec, -1)
    akcja = request.POST.get("akcja") if request.method == "POST" else None
    formularze = {}

    def dodaj(kod, klasa, **opcje):
        formularze[kod] = klasa(request.POST if akcja == kod else None, auto_id=f"id_{kod}_%s", **opcje)

    if "wstepna" not in dane:
        if osoba == ocena.szef:
            dodaj("wstepna", Wstepna, initial={"rozmowa": dzien, "od": od, "do": do})
    elif "ocena" not in dane:
        if osoba == umowa.osoba and "raport" not in dane:
            dodaj("raport", Raport)
        if osoba == ocena.szef and "raport" not in dane:
            dodaj("termin", NowyTermin)
        if osoba == ocena.szef and ocena.kierujacy_id and osoba != umowa.osoba:
            dodaj("ocena", Ocena, zastepstwo=umowa.kwalifikacja == "zastepstwo_ocena", initial={"rozmowa": dzien})
    elif "wniosek" not in dane and osoba == ocena.kierujacy:
        dodaj("wniosek", Wniosek, pozytywna=dane["ocena"]["wynik"] == "Pozytywna")
    if request.method == "POST":
        if akcja not in formularze:
            raise PermissionDenied
        formularz = formularze[akcja]
        if formularz.is_valid() and zapisz_etap(akcja, formularz, ocena, dzien, od, do):
            dziennik.zapisz(dziennik.PIERWSZA_CZYNNOSC, request=request, dotyczy=f"pierwsza ocena {pk}", opis=akcja)
            return redirect("pierwsza_ocena", pk=pk)
    else:
        dziennik.zapisz(dziennik.ODCZYT_OCENY, request=request, dotyczy=f"pierwsza ocena {pk}")
    return render(request, "oceny/pierwsza.html", {"ocena": ocena, "dane": dane, "od": od, "do": do, "formularze": formularze,
        "punkty": [(n, dane.get("ocena", {}).get(f"pkt{i}")) for i,n in enumerate(ELEMENTY)],
        "wniosek": WNIOSKI.get(dane.get("wniosek", {}).get("wybor")),
        "termin_wstepnej": koniec_terminu_dni(date.fromisoformat(dane.get("ustalenie", umowa.poczatek.isoformat())), 21)})


@require_http_methods(["GET"])
def wydruk(request, pk, rodzaj, format):
    from django.contrib import messages
    from django.http import Http404
    from . import drukowanie
    from .pierwsza_druk import dokument
    from .views import _plik

    if rodzaj not in ("arkusz", "sprawozdanie") or format not in ("docx", "pdf"):
        raise Http404
    ocena = get_object_or_404(widoczne(request.user), pk=pk)
    tresc = dokument(ocena, rodzaj)
    typ = drukowanie.TYP_DOCX
    if format == "pdf":
        try:
            tresc = drukowanie.docx_do_pdf(tresc)
        except drukowanie.BladKonwersji as blad:
            messages.error(request, str(blad))
            return redirect("pierwsza_ocena", pk=pk)
        typ = "application/pdf"
    dziennik.zapisz(dziennik.POBRANIE_ARKUSZA, request=request, dotyczy=f"pierwsza ocena {pk}", opis=f"{rodzaj} {format}")
    odpowiedz = _plik(tresc, typ, f"pierwsza-ocena-{pk}-{rodzaj}.{format}")
    odpowiedz["Cache-Control"] = "private, no-store"
    return odpowiedz
