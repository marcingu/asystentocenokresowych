"""Dane pracowników prowadzone przez komórkę kadr: dodanie pracownika i zmiana jego parametrów.

Parametry decydują o przebiegu oceny: rodzaj zatrudnienia - czy osoba podlega ocenie (art. 81 ust. 1 u.s.c.),
arkusz - które kryteria obowiązują (§ 3 i § 4 rozp.), przełożony - kto ocenia. Konto do logowania zakłada
administrator w zapleczu; ten formularz nie nadaje uprawnień kadr ani dyrektora. Dodanie i każda zmiana trafiają
do dziennika zdarzeń bez danych osobowych - z numerem pracownika i nazwami zmienionych pól.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import dziennik, uprawnienia
from .models import Pracownik, rodzaje_zatrudnienia

ARKUSZE = (
    ("C", "C - pozostali członkowie korpusu służby cywilnej"),
    ("B", "B - osoba kierująca bezpośrednio pracownikami"),
    ("A", "A - kierownik urzędu"),
)


class FormularzPracownika(forms.ModelForm):
    rodzaj_zatrudnienia = forms.ChoiceField(
        label="Rodzaj zatrudnienia",
        help_text="Od rodzaju zatrudnienia zależy, czy osoba podlega ocenie okresowej (art. 81 ust. 1 u.s.c.).",
    )
    arkusz = forms.ChoiceField(
        label="Arkusz oceny", choices=ARKUSZE,
        help_text="Arkusz wynika ze stanowiska (§ 3 rozp.) i wyznacza kryteria obowiązkowe (§ 4 rozp.).",
    )

    class Meta:
        model = Pracownik
        fields = (
            "imie", "nazwisko", "stanowisko", "opis_stanowiska", "wydzial", "rodzaj_zatrudnienia", "arkusz",
            "przelozony", "data_zatrudnienia", "data_mianowania", "stopien_sluzbowy", "data_stopnia",
            "identyfikator_ezd", "klauzula_ezd_potwierdzona",
        )
        labels = {
            "imie": "Imię", "nazwisko": "Nazwisko", "stanowisko": "Stanowisko", "opis_stanowiska": "Opis stanowiska pracy",
            "wydzial": "Komórka organizacyjna", "przelozony": "Bezpośredni przełożony",
            "data_zatrudnienia": "Data rozpoczęcia zatrudnienia",
            "data_mianowania": "Data mianowania", "stopien_sluzbowy": "Stopień służbowy",
            "data_stopnia": "Data przyznania stopnia służbowego",
            "identyfikator_ezd": "Identyfikator stanowiska w EZD RP",
            "klauzula_ezd_potwierdzona": "Pracownikowi przekazano informację o danych z EZD RP",
        }
        help_texts = {
            "przelozony": "Bezpośredni przełożony jest oceniającym w kolejnym cyklu oceny.",
            "data_zatrudnienia": "Od tego dnia liczy się pierwszy okres oceny.",
            "data_mianowania": "Data mianowania ustawia rodzaj zatrudnienia na mianowanie. Wypełnij wtedy także stopień służbowy i datę jego przyznania.",
            "stopien_sluzbowy": "Wypełnij dla urzędnika służby cywilnej.",
            "klauzula_ezd_potwierdzona": "Bez tej informacji system nie pokazuje danych z EZD RP (art. 22[2] § 8 w zw. z art. 22[3] § 3 i 4 KP).",
        }
        widgets = {
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
        pozostali = Pracownik.objects.all()
        if self.instance.pk:
            pozostali = pozostali.exclude(pk=self.instance.pk)
            self.initial["arkusz"] = self.instance.arkusz
        self.fields["przelozony"].queryset = pozostali
        self.fields["przelozony"].empty_label = "- brak -"

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
            if osoba is None:
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
        return redirect("kadry")
    return render(request, "oceny/kadry_pracownik.html", {"formularz": formularz, "osoba": osoba})
