"""Podległość w ewidencji pochodzi z obsady wydziału. Oceny mają odrębne pole oceniającego."""
from django import forms
from django.db import transaction

from .models import Pracownik


def sprawdz_lancuch(osoba_id, szef_id, powiazania):
    odwiedzone = {osoba_id}
    while szef_id is not None:
        if szef_id in odwiedzone:
            raise forms.ValidationError("Takie przypisanie tworzy pętlę w podległości służbowej.")
        odwiedzone.add(szef_id)
        szef_id = powiazania.get(szef_id)


@transaction.atomic
def ustaw_obsade(wydzial, kierownik, zwierzchnik):
    if zwierzchnik and (not kierownik or kierownik == zwierzchnik):
        raise forms.ValidationError("Przełożony kierownika wymaga wskazania innej osoby jako kierownika.")
    wydzial.kierownik, wydzial.zwierzchnik = kierownik, zwierzchnik
    podleglosc = dict(Pracownik.objects.values_list("pk", "przelozony_id"))
    osoby = list(wydzial.pracownicy.values_list("pk", flat=True))
    for pk in osoby:
        podleglosc[pk] = wydzial.zwierzchnik_id if pk == wydzial.kierownik_id else wydzial.kierownik_id
    for pk in osoby:
        sprawdz_lancuch(pk, podleglosc[pk], podleglosc)
    wydzial.save(update_fields=["kierownik", "zwierzchnik"])
    wydzial.pracownicy.exclude(pk=wydzial.kierownik_id).update(przelozony_id=wydzial.kierownik_id)
    if kierownik:
        wydzial.pracownicy.filter(pk=kierownik.pk).update(przelozony_id=wydzial.zwierzchnik_id)


class PodlegloscZKomorki:
    """Wspólne dla kadr i formularza Django admin. Przeglądarka nie podaje przełożonego."""
    def clean(self):
        dane = super().clean()
        wydzial = dane.get("wydzial")
        if wydzial:
            szef = wydzial.szef_dla(self.instance.pk)
            # Przy nierozstrzygniętych dawnych przypisaniach nie kasujemy przełożonego samą edycją nazwiska.
            zachowaj = not wydzial.kierownik_id and self.instance.pk and self.instance.wydzial_id == wydzial.pk
            if not zachowaj:
                if szef and self.instance.pk:
                    try:
                        sprawdz_lancuch(self.instance.pk, szef.pk, dict(Pracownik.objects.values_list("pk", "przelozony_id")))
                    except forms.ValidationError as blad:
                        self.add_error("wydzial", blad)
                self.instance.przelozony = szef
        elif "wydzial" in dane:
            self.instance.przelozony = None
        return dane
