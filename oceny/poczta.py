"""Skrzynka nadawcza SMTP: połączenie z serwerem pocztowym i ustawienia w zapleczu administratora.

Kolejność źródeł: skrzynka zapisana w zapleczu, a gdy jej nie ma - zmienne środowiskowe ASYSTENT_EMAIL_*.
Hasło ze zmiennej ASYSTENT_EMAIL_PASSWORD ma pierwszeństwo przed hasłem zapisanym w bazie. Połączenie szyfrowane
sprawdza certyfikat serwera (domyślne ustawienia Pythona).
"""

from __future__ import annotations

from email.utils import formataddr
from smtplib import SMTPException

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from . import dziennik
from .czas import dzis
from .models import OznaczenieUrzedu, SkrzynkaNadawcza, WyslanePrzypomnienie
from .widoki_administracji import _wymagaj_administratora

LIMIT_CZASU = 20  # sekund na połączenie z serwerem pocztowym
BLEDY_WYSYLKI = (SMTPException, OSError)  # OSError obejmuje brak połączenia, błąd TLS i przekroczenie czasu


def polaczenie():
    skrzynka = SkrzynkaNadawcza.aktualna()
    if not skrzynka.host:
        return get_connection()
    return get_connection(
        "django.core.mail.backends.smtp.EmailBackend", host=skrzynka.host, port=skrzynka.port,
        username=skrzynka.uzytkownik, password=settings.EMAIL_HOST_PASSWORD or skrzynka.haslo,
        use_tls=skrzynka.zabezpieczenie == SkrzynkaNadawcza.STARTTLS,
        use_ssl=skrzynka.zabezpieczenie == SkrzynkaNadawcza.SSL, timeout=LIMIT_CZASU)


def gotowa() -> bool:
    """Czy jest dokąd wysyłać: skrzynka z zaplecza albo serwer ze zmiennych środowiskowych. Sam wydruk wiadomości
    na konsolę serwera (ustawienie domyślne) nie jest wysyłką."""
    return bool(SkrzynkaNadawcza.aktualna().host) or not settings.EMAIL_BACKEND.endswith("console.EmailBackend")


def nadawca() -> str:
    skrzynka = SkrzynkaNadawcza.aktualna()
    adres = skrzynka.nadawca or settings.DEFAULT_FROM_EMAIL
    return formataddr((skrzynka.nazwa_nadawcy, adres)) if skrzynka.nazwa_nadawcy else adres


class FormularzSkrzynki(forms.Form):
    wlaczona = forms.BooleanField(label="Wysyłaj przypomnienia planowe", required=False)
    host = forms.CharField(label="Serwer SMTP", max_length=255)
    port = forms.IntegerField(label="Port", min_value=1, max_value=65535)
    zabezpieczenie = forms.ChoiceField(label="Szyfrowanie połączenia", choices=SkrzynkaNadawcza.ZABEZPIECZENIA)
    uzytkownik = forms.CharField(label="Nazwa użytkownika skrzynki", max_length=255, required=False)
    haslo = forms.CharField(label="Hasło skrzynki", max_length=255, required=False, strip=False,
                            widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "aria-describedby": "haslo-opis"}))
    usun_haslo = forms.BooleanField(label="Usuń zapisane hasło", required=False)
    nadawca = forms.EmailField(label="Adres nadawcy")
    nazwa_nadawcy = forms.CharField(label="Nazwa nadawcy", max_length=120, required=False)
    adres_systemu = forms.URLField(label="Adres systemu w wiadomościach", required=False, assume_scheme="https")
    nazwiska = forms.BooleanField(label="Podawaj w wiadomości i w kalendarzu imię i nazwisko ocenianego", required=False)

    def clean_adres_systemu(self):
        adres = self.cleaned_data.get("adres_systemu") or ""
        if adres and not adres.startswith(("https://", "http://")):
            raise forms.ValidationError("Podaj pełny adres zaczynający się od https://.")
        return adres.rstrip("/")


_POLA = ("wlaczona", "host", "port", "zabezpieczenie", "uzytkownik", "nadawca", "nazwa_nadawcy", "adres_systemu", "nazwiska")


def _zapisz(request, dane: dict) -> None:
    with transaction.atomic():
        skrzynka, _ = SkrzynkaNadawcza.objects.select_for_update().get_or_create(pk=1)
        for pole in _POLA:
            setattr(skrzynka, pole, dane[pole])
        haslo = "bez zmian"
        if dane["usun_haslo"]:
            skrzynka.haslo, haslo = "", "usunięte"
        elif dane["haslo"]:
            skrzynka.haslo, haslo = dane["haslo"], "zmienione"
        skrzynka.save()
        dziennik.zapisz(
            dziennik.PANEL_ADMINISTRATORA, request=request, dotyczy="skrzynka nadawcza",
            opis=(f"Serwer: {skrzynka.host}:{skrzynka.port} ({skrzynka.zabezpieczenie}); użytkownik: {skrzynka.uzytkownik or '-'}; "
                  f"nadawca: {skrzynka.nadawca}; hasło: {haslo}; przypomnienia planowe: {'tak' if skrzynka.wlaczona else 'nie'}; "
                  f"nazwiska w wiadomościach: {'tak' if skrzynka.nazwiska else 'nie'}."))


def _probna(request) -> None:
    adres = request.user.email
    if not adres:
        messages.error(request, "Twoje konto nie ma adresu e-mail. Uzupełnij go w „Konta użytkowników” i wyślij wiadomość próbną ponownie.")
        return
    if not gotowa():
        messages.error(request, "Najpierw zapisz ustawienia skrzynki nadawczej.")
        return
    urzad = OznaczenieUrzedu.aktualne().nazwa
    wiadomosc = EmailMessage(
        "Asystent ocen: wiadomość próbna",
        f"Dzień dobry,\n\nto wiadomość próbna ze skrzynki nadawczej Cyfrowego asystenta ocen okresowych ({urzad}).\n"
        "Jeżeli ją widzisz, przypomnienia o terminach będą dochodziły do użytkowników.\n",
        nadawca(), [adres])
    try:
        wiadomosc.connection = polaczenie()
        wiadomosc.send()
    except BLEDY_WYSYLKI as blad:
        opis = f"{type(blad).__name__}: {blad}".strip(": ")[:300]
        dziennik.zapisz(dziennik.PANEL_ADMINISTRATORA, request=request, dotyczy="skrzynka nadawcza", opis=f"Wiadomość próbna nie wyszła. {opis}")
        messages.error(request, f"Nie udało się wysłać wiadomości próbnej. Odpowiedź serwera: {opis}")
        return
    dziennik.zapisz(dziennik.PANEL_ADMINISTRATORA, request=request, dotyczy="skrzynka nadawcza", opis=f"Wysłano wiadomość próbną na adres {adres}.")
    messages.success(request, f"Wysłano wiadomość próbną na adres {adres}.")


def _przypomnienia(request) -> None:
    from . import przypomnienia

    wynik = przypomnienia.wyslij(dzis(), wymus=True, adres_bazowy=request.build_absolute_uri("/"))
    dziennik.zapisz(dziennik.PANEL_ADMINISTRATORA, request=request, dotyczy="przypomnienia e-mail", opis=f"Wysyłka od ręki. {wynik.opis}")
    (messages.success if wynik.wyslane and not wynik.bledy else messages.warning)(request, wynik.opis)


@require_http_methods(["GET", "POST"])
def ustawienia(request):
    from . import przypomnienia

    _wymagaj_administratora(request)
    skrzynka = SkrzynkaNadawcza.aktualna()
    poczatkowe = {pole: getattr(skrzynka, pole) for pole in _POLA}
    formularz = FormularzSkrzynki(initial=poczatkowe)
    if request.method == "POST":
        akcja = request.POST.get("akcja")
        if akcja == "probna":
            _probna(request)
            return redirect("administracja_poczta")
        if akcja == "przypomnienia":
            _przypomnienia(request)
            return redirect("administracja_poczta")
        formularz = FormularzSkrzynki(request.POST, initial=poczatkowe)
        if akcja == "zapisz" and formularz.is_valid():
            _zapisz(request, dict(formularz.cleaned_data))
            messages.success(request, "Zapisano ustawienia skrzynki nadawczej.")
            return redirect("administracja_poczta")
        if akcja != "zapisz":
            messages.error(request, "Nieznana czynność.")
            return redirect("administracja_poczta")
    return render(request, "oceny/poczta.html", {
        "formularz": formularz, "skrzynka": skrzynka, "gotowa": gotowa(),
        "haslo_ze_srodowiska": bool(settings.EMAIL_HOST_PASSWORD),
        "adresaci": przypomnienia.adresaci(dzis()),
        "ostatnie": WyslanePrzypomnienie.objects.select_related("uzytkownik").order_by("-wyslano")[:10],
    })
