"""Dane pracowników prowadzone przez komórkę kadr: dodanie pracownika i zmiana jego parametrów.

Parametry decydują o przebiegu oceny: rodzaj zatrudnienia - czy osoba podlega ocenie (art. 81 ust. 1 u.s.c.),
arkusz - które kryteria obowiązują (§ 3 i § 4 rozp.), przełożony - kto ocenia. Zwykłe konto powstaje wraz z kartą; ten formularz nie nadaje uprawnień kadr ani dyrektora. Dodanie i każda zmiana trafiają
do dziennika zdarzeń bez danych osobowych - z numerem pracownika i nazwami zmienionych pól.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import dziennik, umowy, uprawnienia
from .models import Pracownik, Wydzial, rodzaje_zatrudnienia
from .podleglosc import PodlegloscZKomorki

ARKUSZE = (
    ("C", "C - pozostali członkowie korpusu służby cywilnej"),
    ("B", "B - osoba kierująca bezpośrednio pracownikami"),
    ("A", "A - kierownik urzędu"),
)


class WyborWydzialu(forms.Select):
    osoba_id = None

    def create_option(self, name, value, *args, **kwargs):
        opcja = super().create_option(name, value, *args, **kwargs)
        if hasattr(value, "instance"):
            szef = value.instance.szef_dla(self.osoba_id)
            opcja["attrs"]["data-szef"] = szef.imie_i_nazwisko if szef else "Nie wyznaczono przełożonego w strukturze urzędu."
        return opcja


class FormularzPracownika(PodlegloscZKomorki, forms.ModelForm):
    rodzaj_zatrudnienia = forms.ChoiceField(
        label="Rodzaj zatrudnienia",
        help_text="Od rodzaju zatrudnienia zależy, czy osoba podlega ocenie okresowej (art. 81 ust. 1 u.s.c.).",
    )
    arkusz = forms.ChoiceField(
        label="Arkusz oceny okresowej", choices=ARKUSZE, required=False,
        help_text="Arkusz wynika ze stanowiska (§ 3 rozp.) i wyznacza kryteria obowiązkowe (§ 4 rozp.).",
    )

    kwalifikacja = forms.ChoiceField(label="Podstawa umowy terminowej", choices=umowy.KWALIFIKACJE, required=False,
        help_text="Potwierdź historię w całej służbie cywilnej, nie tylko w tym urzędzie.")
    ustalenie = umowy.data_formularza("Data ustalenia przez strony pierwszej oceny przy zastępstwie", required=False)
    koniec_umowy = umowy.data_formularza("Ostatni dzień umowy innej niż pierwsza 12-miesięczna", required=False)

    def clean(self):
        pola = super().clean()
        if getattr(self.instance, "umowa", None):
            if "rodzaj_zatrudnienia" in self.changed_data or "data_zatrudnienia" in self.changed_data or pola.get("data_mianowania"):
                self.add_error("rodzaj_zatrudnienia", "Zarejestrowaną umowę zmieniaj w sekcji umowy, nie przez nadpisanie karty.")
        elif pola.get("rodzaj_zatrudnienia") == umowy.TERMINOWA and not pola.get("data_mianowania"):
            tryb = pola.get("kwalifikacja")
            if tryb == "zastepstwo_ocena" and (not pola.get("ustalenie") or not pola.get("data_zatrudnienia") or not pola.get("koniec_umowy") or not pola["data_zatrudnienia"] <= pola["ustalenie"] <= pola["koniec_umowy"]):
                self.add_error("ustalenie", "Podaj datę ustalenia przez strony w okresie umowy.")
            if not tryb:
                self.add_error("kwalifikacja", "Wskaż podstawę umowy terminowej.")
            elif tryb not in ("pierwsza", "ksap"):
                if not pola.get("koniec_umowy") or (pola.get("data_zatrudnienia") and pola["koniec_umowy"] < pola["data_zatrudnienia"]):
                    self.add_error("koniec_umowy", "Podaj ostatni dzień wynikający z umowy.")
            elif pola.get("koniec_umowy"):
                self.add_error("koniec_umowy", "Dla tej umowy system wylicza 12 miesięcy.")
        if not pola.get("arkusz"):
            if pola.get("rodzaj_zatrudnienia") == umowy.TERMINOWA:
                pola["arkusz"] = self.instance.arkusz
            elif "arkusz" not in self.errors:
                self.add_error("arkusz", "Wybierz arkusz oceny okresowej.")
        return pola

    class Meta:
        model = Pracownik
        fields = (
            "imie", "nazwisko", "stanowisko", "opis_stanowiska", "wydzial", "rodzaj_zatrudnienia", "arkusz",
            "data_zatrudnienia", "data_mianowania", "stopien_sluzbowy", "data_stopnia",
            "identyfikator_ezd", "klauzula_ezd_potwierdzona",
        )
        labels = {
            "imie": "Imię", "nazwisko": "Nazwisko", "stanowisko": "Stanowisko", "opis_stanowiska": "Opis stanowiska pracy",
            "wydzial": "Komórka organizacyjna",
            "data_zatrudnienia": "Data rozpoczęcia zatrudnienia",
            "data_mianowania": "Data mianowania", "stopien_sluzbowy": "Stopień służbowy",
            "data_stopnia": "Data przyznania stopnia służbowego",
            "identyfikator_ezd": "Identyfikator stanowiska w EZD RP",
            "klauzula_ezd_potwierdzona": "Pracownikowi przekazano informację o danych z EZD RP",
        }
        help_texts = {
            "data_zatrudnienia": "Od tego dnia liczy się pierwszy okres oceny.",
            "data_mianowania": "Data mianowania ustawia rodzaj zatrudnienia na mianowanie. Wypełnij wtedy także stopień służbowy i datę jego przyznania.",
            "stopien_sluzbowy": "Wypełnij dla urzędnika służby cywilnej.",
            "klauzula_ezd_potwierdzona": "Bez tej informacji system nie pokazuje danych z EZD RP (art. 22[2] § 8 w zw. z art. 22[3] § 3 i 4 KP).",
        }
        widgets = {
            "wydzial": WyborWydzialu(),
            "opis_stanowiska": forms.Textarea(attrs={"rows": 3}),
            "data_zatrudnienia": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "data_mianowania": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "data_stopnia": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rodzaj_zatrudnienia"].choices = rodzaje_zatrudnienia()
        self.fields["wydzial"].empty_label = "- wybierz wydział -"
        self.fields["wydzial"].required = True
        if self.instance.rok_mianowania and not self.instance.data_mianowania:
            self.fields["data_mianowania"].help_text += f" Dotychczas zapisano tylko rok: {self.instance.rok_mianowania}."
        self.fields["wydzial"].queryset = Wydzial.objects.select_related("kierownik", "zwierzchnik")
        self.fields["wydzial"].widget.osoba_id = self.instance.pk
        if getattr(self.instance, "umowa", None):
            for nazwa in ("kwalifikacja", "koniec_umowy", "ustalenie"):
                self.fields.pop(nazwa)
        if self.instance.pk:
            self.initial["arkusz"] = self.instance.arkusz

    def save(self, commit: bool = True) -> Pracownik:
        osoba = super().save(commit=False)
        arkusz = self.cleaned_data["arkusz"]
        osoba.kierownik_urzedu = arkusz == "A"  # § 3 ust. 2 rozp.
        osoba.kieruje_pracownikami = arkusz in ("A", "B")  # § 3 ust. 3 rozp.
        if osoba.data_mianowania:
            osoba.rok_mianowania = osoba.data_mianowania.year
        elif not osoba.urzednik:
            osoba.rok_mianowania = None
        if commit:
            osoba.save()
        return osoba


def _opis_zmian(formularz: FormularzPracownika, arkusz_przed: str | None) -> str:
    """Nazwy zmienionych pól - bez wartości, żeby dane osobowe nie trafiały do dziennika. Wyjątek: arkusz."""
    nazwy = []
    for nazwa in formularz.changed_data:
        if nazwa == "arkusz":
            nazwy.append(f"arkusz ({arkusz_przed} -> {formularz.cleaned_data['arkusz']})")
        else:
            nazwy.append(str(formularz.fields[nazwa].label).split(" - ")[0].lower())
    return "zmieniono: " + ", ".join(nazwy)


@require_http_methods(["GET", "POST"])
def pracownik(request, pk: int | None = None):
    if not uprawnienia.czy_kadry(request.user):
        raise PermissionDenied("Dane pracowników prowadzi komórka kadr.")
    osoba = get_object_or_404(Pracownik, pk=pk) if pk is not None else None
    arkusz_przed = osoba.arkusz if osoba is not None else None
    formularz = FormularzPracownika(request.POST or None, instance=osoba)
    if request.method == "POST" and formularz.is_valid():
        with transaction.atomic():
            zapisana = formularz.save()
            if zapisana.rodzaj_zatrudnienia == umowy.TERMINOWA and not hasattr(zapisana, "umowa"):
                umowy.zaloz_umowe(zapisana, formularz.cleaned_data)
            if osoba is None:
                from .widoki_administracji import _utworz_konto
                _utworz_konto(request, zapisana, email="", administrator=False, wydaj_link=False)
                dziennik.zapisz(
                    dziennik.PRACOWNIK_DODANY, request=request, dotyczy=f"pracownik {zapisana.pk}",
                    opis=f"arkusz {zapisana.arkusz}; {zapisana.rodzaj_zatrudnienia_opis}",
                )
            elif formularz.changed_data:
                dziennik.zapisz(
                    dziennik.PRACOWNIK_ZMIENIONY, request=request, dotyczy=f"pracownik {zapisana.pk}",
                    opis=_opis_zmian(formularz, arkusz_przed),
                )
        if osoba is None:
            messages.success(request, f"Dodano pracownika: {zapisana.imie_i_nazwisko}.")
        else:
            messages.success(request, f"Zapisano dane pracownika: {zapisana.imie_i_nazwisko}.")
            if "arkusz" in formularz.changed_data and zapisana.oceny.exclude(etap="ZAKONCZONA").exists():
                messages.info(request, "Cykl oceny, który trwa, zostaje przy dotychczasowym arkuszu - nowy arkusz obowiązuje od kolejnego cyklu oceny.")
        if not zapisana.przelozony_id:
            messages.info(request, "Nie wyznaczono przełożonego. Obsada wydziału jest w administracji urzędu.")
        return redirect("kadry")
    return render(request, "oceny/kadry_pracownik.html", {"formularz": formularz, "osoba": osoba})
