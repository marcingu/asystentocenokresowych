"""Oznaczenie urzędu w zapleczu administratora."""
import base64
from io import BytesIO

from PIL import Image
from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from . import dziennik
from .models import OznaczenieUrzedu
from .widoki_administracji import _wymagaj_administratora


class FormularzUrzedu(forms.Form):
    nazwa = forms.CharField(label="Nazwa urzędu", max_length=160)
    logo = forms.FileField(label="Nowe logo (PNG lub JPEG, do 1 MB)", required=False,
                           widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg"}))
    domyslne = forms.BooleanField(label="Przywróć domyślne godło", required=False)

    def clean_logo(self):
        plik = self.cleaned_data.get("logo")
        if not plik:
            return None
        if plik.size > 1024 * 1024:
            raise forms.ValidationError("Wybierz plik nie większy niż 1 MB.")
        try:
            with Image.open(plik, formats=("PNG", "JPEG")) as obraz:
                if obraz.width * obraz.height > 4_000_000:
                    raise forms.ValidationError("Logo może mieć najwyżej 4 miliony pikseli.")
                obraz.thumbnail((256, 256))
                # Nowy obraz zawiera tylko piksele, bez metadanych i oryginalnych bajtów uploadu.
                czysty = Image.new("RGBA", obraz.size)
                czysty.paste(obraz.convert("RGBA"))
                bufor = BytesIO()
                czysty.save(bufor, format="PNG")
                return base64.b64encode(bufor.getvalue()).decode("ascii")
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise forms.ValidationError("Wybierz poprawny obraz PNG albo JPEG.") from None

    def clean(self):
        dane = super().clean()
        if dane.get("logo") and dane.get("domyslne"):
            raise forms.ValidationError("Wybierz nowe logo albo przywróć domyślne godło.")
        return dane


@require_http_methods(["GET", "POST"])
def ustawienia(request):
    _wymagaj_administratora(request)
    urzad = OznaczenieUrzedu.aktualne()
    formularz = FormularzUrzedu(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None, initial={"nazwa": urzad.nazwa})
    if request.method == "POST" and formularz.is_valid():
        dane = formularz.cleaned_data
        with transaction.atomic():
            urzad, _ = OznaczenieUrzedu.objects.select_for_update().get_or_create(pk=1, defaults={"nazwa": urzad.nazwa})
            przed = urzad.nazwa
            urzad.nazwa = dane["nazwa"]
            operacja = "bez zmian"
            if dane["domyslne"] or dane["logo"]:
                urzad.logo_png = dane["logo"] or ""
                operacja = "nowe" if urzad.logo_png else "domyślne"
            urzad.save()
            dziennik.zapisz(dziennik.PANEL_ADMINISTRATORA, request=request, dotyczy="oznaczenie urzędu",
                           opis=f"Nazwa: {przed} -> {urzad.nazwa}; logo: {operacja}.")
        messages.success(request, "Zapisano oznaczenie urzędu.")
        return redirect("administracja_urzad")
    return render(request, "oceny/urzad.html", {"formularz": formularz})
