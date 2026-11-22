"""Oznaczenie urzędu w zapleczu administratora i ikona strony z logo urzędu."""
import base64
import binascii
from io import BytesIO
from pathlib import Path

from PIL import Image
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

GODLO = Path(__file__).resolve().parent / "static" / "oceny" / "godlo.svg"
BOK_IKONY = 64

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


def ikona_z_logo(logo_png: str) -> bytes | None:
    """Kwadratowa ikona PNG z logo urzędu: logo zmniejszone z zachowaniem proporcji, dopełnione przezroczystym
    tłem. None, gdy zapisanego logo nie da się odczytać - wtedy ikoną zostaje domyślne godło."""
    try:
        with Image.open(BytesIO(base64.b64decode(logo_png, validate=True)), formats=("PNG",)) as obraz:
            logo = obraz.convert("RGBA")
        logo.thumbnail((BOK_IKONY, BOK_IKONY))
        kwadrat = Image.new("RGBA", (BOK_IKONY, BOK_IKONY), (0, 0, 0, 0))
        kwadrat.paste(logo, ((BOK_IKONY - logo.width) // 2, (BOK_IKONY - logo.height) // 2))
        bufor = BytesIO()
        kwadrat.save(bufor, format="PNG")
        return bufor.getvalue()
    except (OSError, ValueError, SyntaxError, binascii.Error, Image.DecompressionBombError):
        return None


@login_not_required   # ikonę pobiera także strona logowania; logo i tak widać w jej nagłówku
@require_GET
def ikona(request):
    """Ikona strony (favicon) - z logo urzędu ustawionego w zapleczu, a bez niego z domyślnego godła."""
    logo_png = OznaczenieUrzedu.aktualne().logo_png
    obraz = ikona_z_logo(logo_png) if logo_png else None
    if obraz is not None:
        odpowiedz = HttpResponse(obraz, content_type="image/png")
    else:
        odpowiedz = HttpResponse(GODLO.read_bytes(), content_type="image/svg+xml")
    # Adres ikony zawiera skrót logo, więc po zmianie logo przeglądarka pobiera nową ikonę mimo pamięci podręcznej.
    odpowiedz["Cache-Control"] = "public, max-age=86400"
    return odpowiedz
