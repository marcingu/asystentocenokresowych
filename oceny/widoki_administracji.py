"""Zaplecze administratora: konta użytkowników, zawieszanie kont bez aktywności i wgląd w dzienniki.

Każda czynność administratora trafia do dziennika zdarzeń bezpieczeństwa (§ 20 ust. 2 pkt 1 i 2 rozporządzenia
KRI). Administrator zarządza kontami i czyta dzienniki, ale zaplecze nie pokazuje mu treści ocen, notatek ani
szkiców. Hasła nie ustala i nie poznaje: wydaje użytkownikowi jednorazowy link do jego ustawienia.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from asystent_ocen.zgodnosc import wczytaj_wymogi

from . import bezpieczenstwo, dziennik, uprawnienia
from .models import Pracownik, UrzadzenieTotp, Zdarzenie, ZdarzenieBezpieczenstwa

NA_STRONIE = 50
LINK_HASLA = "link_hasla"  # klucz sesji: link pokazywany administratorowi jeden raz
# Początek komórki, który arkusz kalkulacyjny potraktowałby jak formułę - login przy nieudanym logowaniu
# wpisuje dowolna osoba, więc eksport musi takie wartości unieszkodliwić.
_ZNAKI_FORMULY = ("=", "+", "-", "@", "\t", "\r")


def _wymagaj_administratora(request) -> None:
    if not uprawnienia.czy_administrator(request.user):
        raise PermissionDenied("Zaplecze jest dostępne tylko dla administratora.")


def _lata(liczba: int) -> str:
    if liczba == 1:
        return "1 rok"
    return f"{liczba} lata" if 2 <= liczba % 10 <= 4 and not 12 <= liczba % 100 <= 14 else f"{liczba} lat"


def _pracownik(uzytkownik) -> Pracownik | None:
    return Pracownik.objects.filter(uzytkownik=uzytkownik).first()


def _czynni_administratorzy():
    return get_user_model().objects.filter(is_superuser=True, is_active=True)


# --- konta ---

@require_GET
def konta(request):
    _wymagaj_administratora(request)
    z_aplikacja = set(UrzadzenieTotp.objects.filter(potwierdzone=True).values_list("uzytkownik_id", flat=True))
    pracownicy = {osoba.uzytkownik_id: osoba for osoba in Pracownik.objects.exclude(uzytkownik=None)}
    wiersze = [
        {
            "konto": uzytkownik,
            "pracownik": pracownicy.get(uzytkownik.pk),
            "stan": bezpieczenstwo.stan_konta(uzytkownik),
            "dwuetapowe": uzytkownik.pk in z_aplikacja,
        }
        for uzytkownik in get_user_model().objects.order_by("username")
    ]
    return render(request, "oceny/administracja.html", {
        "wiersze": wiersze,
        "miesiace": wczytaj_wymogi().zawieszenie_konta_po_miesiacach,
        "dwuetapowe_wymagane": bezpieczenstwo.dwuetapowe_wymagane(),
    })


class FormularzKonta(forms.Form):
    username = forms.CharField(label="Login", max_length=150, validators=[UnicodeUsernameValidator()])
    first_name = forms.CharField(label="Imię", max_length=150)
    last_name = forms.CharField(label="Nazwisko", max_length=150)
    email = forms.EmailField(label="Adres e-mail", required=False)
    pracownik = forms.ModelChoiceField(
        label="Pracownik", queryset=Pracownik.objects.none(), required=False, empty_label="- bez powiązania -",
    )
    administrator = forms.BooleanField(label="Administrator systemu", required=False)

    def __init__(self, *args, konto=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.konto = konto
        wolni = Q(uzytkownik=None)
        if konto is not None:
            wolni |= Q(uzytkownik=konto)
            del self.fields["username"]  # login jest stały - występuje w dziennikach
        self.fields["pracownik"].queryset = Pracownik.objects.filter(wolni)

    def clean_username(self):
        login = self.cleaned_data["username"].strip()
        if get_user_model().objects.filter(username__iexact=login).exists():
            raise forms.ValidationError("Konto o takim loginie już istnieje.")
        return login


def _powiaz_z_pracownikiem(uzytkownik, pracownik: Pracownik | None) -> bool:
    """Ustawia powiązanie konta z pracownikiem. Zwraca, czy coś się zmieniło."""
    dotychczas = _pracownik(uzytkownik)
    if dotychczas == pracownik:
        return False
    if dotychczas is not None:
        dotychczas.uzytkownik = None
        dotychczas.save(update_fields=["uzytkownik"])
    if pracownik is not None:
        pracownik.uzytkownik = uzytkownik
        pracownik.save(update_fields=["uzytkownik"])
    return True


def _wydaj_link(request, uzytkownik) -> None:
    """Jednorazowy link do ustawienia hasła: działa dobę i przestaje działać po ustawieniu hasła albo zalogowaniu.
    Administrator widzi go raz, na stronie konta. Do dziennika trafia sam fakt wydania, bez linku."""
    adres = request.build_absolute_uri(reverse("haslo_ustaw", kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(uzytkownik.pk)),
        "token": default_token_generator.make_token(uzytkownik),
    }))
    request.session[LINK_HASLA] = {"konto": uzytkownik.pk, "adres": adres}
    dziennik.zapisz(dziennik.HASLO_LINK, request=request, dotyczy=uzytkownik.get_username())


@require_http_methods(["GET", "POST"])
def nowe_konto(request):
    _wymagaj_administratora(request)
    formularz = FormularzKonta(request.POST or None)
    if request.method == "POST" and formularz.is_valid():
        dane = formularz.cleaned_data
        with transaction.atomic():
            nowe = get_user_model().objects.create_user(
                username=dane["username"], email=dane["email"], first_name=dane["first_name"],
                last_name=dane["last_name"], is_superuser=dane["administrator"],
            )
            _powiaz_z_pracownikiem(nowe, dane["pracownik"])
            dziennik.zapisz(
                dziennik.KONTO_UTWORZONE, request=request, dotyczy=nowe.get_username(),
                opis="z uprawnieniami administratora" if nowe.is_superuser else "",
            )
            _wydaj_link(request, nowe)
        messages.success(request, f"Konto {nowe.get_username()} zostało utworzone. Przekaż użytkownikowi link do ustawienia hasła.")
        return redirect("administracja_konto", pk=nowe.pk)
    return render(request, "oceny/administracja_konto.html", {"formularz": formularz, "nowe": True})


@require_http_methods(["GET", "POST"])
def konto(request, pk: int):
    _wymagaj_administratora(request)
    wybrane = get_object_or_404(get_user_model(), pk=pk)
    pracownik = _pracownik(wybrane)
    poczatkowe = {
        "first_name": wybrane.first_name, "last_name": wybrane.last_name, "email": wybrane.email,
        "pracownik": pracownik, "administrator": wybrane.is_superuser,
    }
    formularz = FormularzKonta(request.POST or None, initial=poczatkowe, konto=wybrane)
    if request.method == "POST" and formularz.is_valid():
        dane = formularz.cleaned_data
        zmiany = []
        if (wybrane.first_name, wybrane.last_name) != (dane["first_name"], dane["last_name"]):
            zmiany.append("imię i nazwisko")
        if wybrane.email != dane["email"]:
            zmiany.append("e-mail")
        administrator = dane["administrator"]
        if wybrane.is_superuser and not administrator:
            if wybrane == request.user:
                messages.error(request, "Nie można odebrać uprawnień administratora z własnego konta.")
                administrator = True
            elif wybrane.is_active and _czynni_administratorzy().count() <= 1:
                messages.error(request, "To jedyny czynny administrator - uprawnień nie można odebrać.")
                administrator = True
            else:
                zmiany.append("odebrano uprawnienia administratora")
        elif administrator and not wybrane.is_superuser:
            zmiany.append("nadano uprawnienia administratora")
        with transaction.atomic():
            wybrane.first_name, wybrane.last_name, wybrane.email = dane["first_name"], dane["last_name"], dane["email"]
            wybrane.is_superuser = administrator
            wybrane.save(update_fields=["first_name", "last_name", "email", "is_superuser"])
            if _powiaz_z_pracownikiem(wybrane, dane["pracownik"]):
                zmiany.append("powiązanie z pracownikiem")
            if zmiany:
                dziennik.zapisz(dziennik.KONTO_ZMIENIONE, request=request, dotyczy=wybrane.get_username(), opis=", ".join(zmiany))
        if zmiany:
            messages.success(request, "Zmiany zostały zapisane.")
        return redirect("administracja_konto", pk=wybrane.pk)
    link = request.session.get(LINK_HASLA)
    if link and link["konto"] == wybrane.pk and request.method == "GET":
        del request.session[LINK_HASLA]
    else:
        link = None
    login = wybrane.get_username()
    return render(request, "oceny/administracja_konto.html", {
        "formularz": formularz,
        "wybrane": wybrane,
        "pracownik": pracownik,
        "stan": bezpieczenstwo.stan_konta(wybrane),
        "aplikacja": bezpieczenstwo.urzadzenie(wybrane),
        "link_hasla": link["adres"] if link else "",
        "to_ja": wybrane == request.user,
        "zdarzenia": ZdarzenieBezpieczenstwa.objects.filter(Q(dotyczy=login) | Q(login__iexact=login)).order_by("-pk")[:20],
    })


@require_POST
def akcja(request, pk: int, akcja: str):
    _wymagaj_administratora(request)
    wybrane = get_object_or_404(get_user_model(), pk=pk)
    if akcja == "zablokuj":
        if wybrane == request.user:
            messages.error(request, "Nie można zablokować własnego konta.")
        elif wybrane.is_superuser and wybrane.is_active and _czynni_administratorzy().count() <= 1:
            messages.error(request, "To jedyny czynny administrator - konta nie można zablokować.")
        elif wybrane.is_active:
            bezpieczenstwo.zablokuj_konto(wybrane, wykonawca=request.user, powod=request.POST.get("powod", ""), request=request)
            messages.success(request, f"Konto {wybrane.get_username()} zostało zablokowane. Trwające sesje tego konta przestały działać.")
    elif akcja == "odblokuj":
        if not wybrane.is_active:
            bezpieczenstwo.odblokuj_konto(wybrane, wykonawca=request.user, request=request)
            messages.success(request, f"Konto {wybrane.get_username()} zostało odblokowane.")
    elif akcja == "reset-dwuetapowego":
        usuniete, _ = UrzadzenieTotp.objects.filter(uzytkownik=wybrane).delete()
        if usuniete:
            dziennik.zapisz(dziennik.DWUETAPOWE_ZRESETOWANE, request=request, dotyczy=wybrane.get_username())
            messages.success(request, "Aplikacja uwierzytelniająca została odłączona. Użytkownik skonfiguruje ją ponownie.")
    elif akcja == "link-hasla":
        _wydaj_link(request, wybrane)
        messages.success(request, "Wydano nowy link do ustawienia hasła.")
    else:
        raise Http404
    return redirect("administracja_konto", pk=wybrane.pk)


@require_POST
def zawies_nieaktywne(request):
    _wymagaj_administratora(request)
    zawieszone = bezpieczenstwo.zawies_nieaktywne()
    loginy = ", ".join(uzytkownik.get_username() for uzytkownik in zawieszone)
    messages.success(request, f"Zawieszone konta: {len(zawieszone)}{' (' + loginy + ')' if loginy else ''}.")
    return redirect("administracja")


# --- dzienniki ---

def _data(request, nazwa: str) -> date | None:
    wartosc = request.GET.get(nazwa, "").strip()
    if not wartosc:
        return None
    try:
        return date.fromisoformat(wartosc)
    except ValueError:
        messages.error(request, "Datę podaj w postaci RRRR-MM-DD - filtr daty został pominięty.")
        return None


def _zakres(od: date | None, do: date | None) -> dict:
    """Warunki na pole `czas` dla dni od-do włącznie, w strefie czasowej urzędu."""
    warunki = {}
    strefa = timezone.get_current_timezone()
    if od:
        warunki["czas__gte"] = datetime.combine(od, time.min, tzinfo=strefa)
    if do:
        warunki["czas__lt"] = datetime.combine(do + timedelta(days=1), time.min, tzinfo=strefa)
    return warunki


def _filtry(request) -> dict:
    return {
        "rodzaj": request.GET.get("rodzaj", "") if request.GET.get("rodzaj", "") in dziennik.RODZAJE else "",
        "login": request.GET.get("login", "").strip()[:150],
        "od": _data(request, "od"),
        "do": _data(request, "do"),
    }


def _zdarzenia_bezpieczenstwa(filtry: dict):
    wpisy = ZdarzenieBezpieczenstwa.objects.filter(**_zakres(filtry["od"], filtry["do"])).order_by("-pk")
    if filtry["rodzaj"]:
        wpisy = wpisy.filter(rodzaj=filtry["rodzaj"])
    if filtry["login"]:
        wpisy = wpisy.filter(Q(login__icontains=filtry["login"]) | Q(dotyczy__icontains=filtry["login"]))
    return wpisy


def _opis_filtrow(filtry: dict) -> str:
    czesci = [f"{nazwa}: {wartosc}" for nazwa, wartosc in filtry.items() if wartosc]
    return "; ".join(czesci) or "bez filtrów"


@require_GET
def dziennik_zdarzen(request):
    _wymagaj_administratora(request)
    filtry = _filtry(request)
    proces = request.GET.get("dziennik") == "proces"
    dziennik.zapisz(
        dziennik.WGLAD_W_DZIENNIK, request=request,
        dotyczy="czynności w procesie oceny" if proces else "zdarzenia bezpieczeństwa", opis=_opis_filtrow(filtry),
    )
    if proces:
        # Czynności w procesie oceny: kto, kiedy i co zrobił - bez opisów, które mogą nieść treść sprawy.
        wpisy = Zdarzenie.objects.select_related("uzytkownik").filter(**_zakres(filtry["od"], filtry["do"])).order_by("-pk")
        if filtry["login"]:
            wpisy = wpisy.filter(Q(uzytkownik__username__icontains=filtry["login"]) | Q(podpis__icontains=filtry["login"]))
    else:
        wpisy = _zdarzenia_bezpieczenstwa(filtry)
    strona = Paginator(wpisy, NA_STRONIE).get_page(request.GET.get("strona"))
    parametry = request.GET.copy()
    parametry.pop("strona", None)
    return render(request, "oceny/administracja_dziennik.html", {
        "strona": strona,
        "proces": proces,
        "filtry": filtry,
        "rodzaje": dziennik.RODZAJE,
        "parametry": parametry.urlencode(),
        "lancuch": dziennik.sprawdz_lancuch(),
        "przechowywanie": _lata(wczytaj_wymogi().dziennik_przechowywanie_lat),
    })


def _komorka(wartosc) -> str:
    tekst = "" if wartosc is None else str(wartosc)
    return f"'{tekst}" if tekst.startswith(_ZNAKI_FORMULY) else tekst


@require_GET
def dziennik_csv(request):
    """Eksport zdarzeń bezpieczeństwa (z bieżącymi filtrami) do pliku CSV - np. do systemu zbierania logów urzędu."""
    _wymagaj_administratora(request)
    filtry = _filtry(request)
    wpisy = _zdarzenia_bezpieczenstwa(filtry).select_related("uzytkownik").order_by("pk")
    odpowiedz = HttpResponse(content_type="text/csv; charset=utf-8")
    odpowiedz["Content-Disposition"] = f'attachment; filename="dziennik-zdarzen-{timezone.localdate():%Y-%m-%d}.csv"'
    odpowiedz["X-Content-Type-Options"] = "nosniff"
    odpowiedz.write("\ufeff")  # znacznik kodowania - arkusz kalkulacyjny odczyta polskie znaki
    arkusz = csv.writer(odpowiedz, delimiter=";")
    arkusz.writerow(["czas", "rodzaj", "login", "dotyczy", "adres IP", "opis", "skrót wpisu"])
    liczba = 0
    for wpis in wpisy.iterator():
        liczba += 1
        arkusz.writerow([_komorka(pole) for pole in (
            timezone.localtime(wpis.czas).isoformat(timespec="seconds"), wpis.rodzaj_opis, wpis.login, wpis.dotyczy,
            wpis.adres_ip, wpis.opis, wpis.skrot,
        )])
    dziennik.zapisz(dziennik.EKSPORT_DZIENNIKA, request=request, opis=f"{_opis_filtrow(filtry)}; wpisów: {liczba}")
    return odpowiedz
