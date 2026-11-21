"""Logowanie, weryfikacja dwuetapowa i konto użytkownika.

Kolejność przy logowaniu: blokada po nieudanych próbach -> hasło -> kod jednorazowy (gdy konto ma aplikację
uwierzytelniającą) -> sesja. Sesja powstaje dopiero po ostatnim kroku. Gdy urząd wymaga weryfikacji dwuetapowej,
konto bez aplikacji uwierzytelniającej po zalogowaniu trafia na jej konfigurację i nie wejdzie nigdzie indziej
(pilnuje tego `middleware.BezpieczenstwoKont`).
"""

from __future__ import annotations

import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetConfirmView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import bezpieczenstwo, dziennik, totp
from .kontekst import konta_demo
from .models import OznaczenieUrzedu, UrzadzenieTotp, ZdarzenieBezpieczenstwa

BACKEND = "django.contrib.auth.backends.ModelBackend"
OCZEKUJE_NA_KOD = "oczekuje_na_kod"          # klucz sesji: hasło poprawne, brakuje kodu jednorazowego
WYMAGA_KONFIGURACJI = "wymaga_dwuetapowego"  # klucz sesji: konto musi skonfigurować aplikację uwierzytelniającą
CZAS_NA_KOD = 5 * 60                         # sekund od podania hasła
BLEDNY_KOD = "Kod jest nieprawidłowy albo został już użyty. Poczekaj na nowy kod w aplikacji i wpisz go ponownie."
BLOKADA = (
    "Zbyt wiele nieudanych prób logowania na to konto. Spróbuj ponownie za {minuty} min albo zgłoś się "
    "do administratora."
)


def _komunikat_blokady() -> str:
    return BLOKADA.format(minuty=settings.ASYSTENT_BLOKADA_MINUT)


def _rozpocznij_sesje(request, uzytkownik, dalej: str, sposob: str):
    """Po poprawnym pierwszym składniku: konto z aplikacją uwierzytelniającą podaje jeszcze kod, pozostałe wchodzą.
    Przy polityce „wymagane” konto bez aplikacji dostaje w sesji znacznik i trafia na jej konfigurację."""
    if bezpieczenstwo.urzadzenie(uzytkownik) is not None:
        request.session[OCZEKUJE_NA_KOD] = {"uzytkownik": uzytkownik.pk, "dalej": dalej, "sposob": sposob, "od": time.time()}
        return redirect("logowanie_kod")
    request.sposob_logowania = sposob
    login(request, uzytkownik, backend=BACKEND)
    if bezpieczenstwo.dwuetapowe_wymagane():
        request.session[WYMAGA_KONFIGURACJI] = True
        return redirect("konto_dwuetapowe")
    return redirect(dalej)


class Logowanie(LoginView):
    template_name = "oceny/logowanie.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        podany = request.POST.get("username", "")
        if bezpieczenstwo.logowanie_zablokowane(podany):
            # Hasła nie sprawdzamy: w czasie blokady nie da się go zgadywać.
            dziennik.zapisz(dziennik.LOGOWANIE_ZABLOKOWANE, request=request, uzytkownik=None, login=podany)
            kontekst = self.get_context_data(form=self.form_class(request), blokada=_komunikat_blokady())
            return self.render_to_response(kontekst, status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        return _rozpocznij_sesje(self.request, form.get_user(), self.get_success_url(), "hasło")


@login_not_required
@require_POST
def demo_zaloguj(request):
    """Wejście na konto demonstracyjne bez hasła - działa wyłącznie w trybie demo i tylko dla kont demo.
    Konto pokazowe z aplikacją uwierzytelniającą też podaje kod."""
    konto_ = konta_demo().filter(username=request.POST.get("login", "")).first()
    if konto_ is None:
        raise Http404
    return _rozpocznij_sesje(request, konto_, reverse("zadania"), "tryb demonstracyjny - bez hasła")


@login_not_required
@require_http_methods(["GET", "POST"])
def logowanie_kod(request):
    """Drugi krok logowania: kod jednorazowy z aplikacji uwierzytelniającej."""
    oczekuje = request.session.get(OCZEKUJE_NA_KOD)
    if not oczekuje:
        return redirect("logowanie")
    uzytkownik = get_user_model().objects.filter(pk=oczekuje["uzytkownik"], is_active=True).first()
    if uzytkownik is None or time.time() - oczekuje["od"] > CZAS_NA_KOD:
        del request.session[OCZEKUJE_NA_KOD]
        messages.info(request, "Czas na podanie kodu minął albo konto jest nieczynne. Zaloguj się ponownie.")
        return redirect("logowanie")
    blad = ""
    if request.method == "POST":
        if bezpieczenstwo.logowanie_zablokowane(uzytkownik.get_username()):
            del request.session[OCZEKUJE_NA_KOD]
            dziennik.zapisz(dziennik.LOGOWANIE_ZABLOKOWANE, request=request, uzytkownik=None, login=uzytkownik.get_username())
            messages.error(request, _komunikat_blokady())
            return redirect("logowanie")
        if _przyjmij_kod(uzytkownik, request.POST.get("kod")):
            dziennik.zapisz(dziennik.KOD_POPRAWNY, request=request, uzytkownik=None, login=uzytkownik.get_username())
            del request.session[OCZEKUJE_NA_KOD]
            request.sposob_logowania = f"{oczekuje['sposob']} i kod jednorazowy"
            login(request, uzytkownik, backend=BACKEND)
            return redirect(str(oczekuje["dalej"]))
        dziennik.zapisz(dziennik.KOD_BLEDNY, request=request, uzytkownik=None, login=uzytkownik.get_username())
        blad = BLEDNY_KOD
    return render(request, "oceny/logowanie_kod.html", {"blad": blad}, status=200)


def _przyjmij_kod(uzytkownik, kod: str | None, *, tylko_potwierdzone: bool = True) -> bool:
    """Sprawdza kod i zapamiętuje jego krok czasu - ten sam kod nie zadziała drugi raz."""
    with transaction.atomic():
        urzadzenia = UrzadzenieTotp.objects.select_for_update().filter(uzytkownik=uzytkownik)
        if tylko_potwierdzone:
            urzadzenia = urzadzenia.filter(potwierdzone=True)
        aplikacja = urzadzenia.first()
        if aplikacja is None:
            return False
        krok = totp.sprawdz(aplikacja.sekret, kod, po_kroku=aplikacja.ostatni_krok)
        if krok is None:
            return False
        aplikacja.ostatni_krok = krok
        aplikacja.save(update_fields=["ostatni_krok"])
    return True


# --- moje konto ---

@require_GET
def konto(request):
    logowania = ZdarzenieBezpieczenstwa.objects.filter(
        login__iexact=request.user.get_username(),
        rodzaj__in=(dziennik.LOGOWANIE_UDANE, dziennik.LOGOWANIE_NIEUDANE, dziennik.LOGOWANIE_ZABLOKOWANE, dziennik.KOD_BLEDNY),
    ).order_by("-pk")[:10]
    return render(request, "oceny/konto.html", {
        "aplikacja": bezpieczenstwo.urzadzenie(request.user),
        "dwuetapowe_wymagane": bezpieczenstwo.dwuetapowe_wymagane(),
        "logowania": logowania,
        "ma_haslo": request.user.has_usable_password(),
        "termin_zawieszenia": bezpieczenstwo.termin_zawieszenia(request.user),
    })


@require_http_methods(["GET", "POST"])
def konto_dwuetapowe(request):
    """Konfiguracja aplikacji uwierzytelniającej: klucz, pierwszy kod na potwierdzenie, wyłączenie."""
    uzytkownik = request.user
    aplikacja = bezpieczenstwo.urzadzenie(uzytkownik)
    wymagane = bezpieczenstwo.dwuetapowe_wymagane()
    blad = ""
    if request.method == "POST":
        akcja = request.POST.get("akcja")
        if akcja == "potwierdz" and aplikacja is None:
            if _przyjmij_kod(uzytkownik, request.POST.get("kod"), tylko_potwierdzone=False):
                UrzadzenieTotp.objects.filter(uzytkownik=uzytkownik).update(potwierdzone=True, potwierdzono=timezone.now())
                request.session.pop(WYMAGA_KONFIGURACJI, None)
                dziennik.zapisz(dziennik.DWUETAPOWE_WLACZONE, request=request)
                messages.success(request, "Weryfikacja dwuetapowa jest włączona. Przy następnym logowaniu podasz kod z aplikacji.")
                return redirect("konto")
            blad = BLEDNY_KOD
        elif akcja == "wylacz" and aplikacja is not None:
            if wymagane:
                raise PermissionDenied("Urząd wymaga weryfikacji dwuetapowej - nie można jej wyłączyć.")
            if bezpieczenstwo.logowanie_zablokowane(uzytkownik.get_username()):
                raise PermissionDenied(_komunikat_blokady())
            if _przyjmij_kod(uzytkownik, request.POST.get("kod")):
                aplikacja.delete()
                dziennik.zapisz(dziennik.DWUETAPOWE_WYLACZONE, request=request)
                messages.success(request, "Weryfikacja dwuetapowa została wyłączona.")
                return redirect("konto")
            # Błędny kod przy wyłączaniu liczy się do blokady tak samo jak przy logowaniu - kodu nie da się zgadywać.
            dziennik.zapisz(dziennik.KOD_BLEDNY, request=request, opis="próba wyłączenia weryfikacji dwuetapowej")
            blad = BLEDNY_KOD
        else:
            raise PermissionDenied("Nieznana czynność.")
    kontekst = {"aplikacja": aplikacja, "dwuetapowe_wymagane": wymagane, "blad": blad,
                "wymuszona": bool(request.session.get(WYMAGA_KONFIGURACJI))}
    if aplikacja is None:
        nowa, _ = UrzadzenieTotp.objects.get_or_create(
            uzytkownik=uzytkownik, defaults={"sekret": totp.nowy_sekret()}
        )
        kontekst["klucz"] = totp.sekret_w_grupach(nowa.sekret)
        kontekst["adres"] = totp.adres_otpauth(nowa.sekret, uzytkownik.get_username(), f"Asystent ocen - {OznaczenieUrzedu.aktualne().nazwa}")
    return render(request, "oceny/konto_dwuetapowe.html", kontekst)


class ZmianaHasla(PasswordChangeView):
    template_name = "oceny/haslo.html"
    success_url = reverse_lazy("konto")
    extra_context = {"tytul": "Zmiana hasła", "przycisk": "Zmień hasło"}

    def form_valid(self, form):
        odpowiedz = super().form_valid(form)
        dziennik.zapisz(dziennik.HASLO_ZMIENIONE, request=self.request, opis="zmiana przez użytkownika")
        messages.success(self.request, "Hasło zostało zmienione.")
        return odpowiedz


class UstawienieHasla(PasswordResetConfirmView):
    """Ustawienie hasła z jednorazowego linku wydanego przez administratora (ważny dobę, działa raz)."""

    template_name = "oceny/haslo.html"
    success_url = reverse_lazy("logowanie")
    extra_context = {"tytul": "Ustawienie hasła", "przycisk": "Ustaw hasło"}

    def form_valid(self, form):
        odpowiedz = super().form_valid(form)
        dziennik.zapisz(
            dziennik.HASLO_ZMIENIONE, request=self.request, uzytkownik=None, login=self.user.get_username(),
            opis="ustawienie z linku wydanego przez administratora",
        )
        messages.success(self.request, "Hasło zostało ustawione. Możesz się zalogować.")
        return odpowiedz
