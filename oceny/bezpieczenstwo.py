"""Bezpieczeństwo kont: blokada po nieudanych próbach logowania, zawieszanie kont bez aktywności, blokowanie
i odblokowywanie kont przez administratora.

Podstawy:
- zał. nr 4 część I pkt 6 ustawy o krajowym systemie cyberbezpieczeństwa - zawieszanie uprawnień w przypadku
  niewykonywania obowiązków co najmniej przez jeden miesiąc (okres jest w `zgodnosc.toml`);
- § 19 ust. 2 pkt 5 i 7 rozporządzenia KRI - bezzwłoczna zmiana uprawnień, środki uniemożliwiające
  nieautoryzowany dostęp na poziomie aplikacji.

Brak aktywności to brak udanego logowania (decyzja projektowa): system nie wie, czy pracownik wykonuje obowiązki
poza nim. Miesiąc liczy się według art. 112 KC od ostatniego logowania, a gdy konta nie użyto - od jego
założenia; po odblokowaniu przez administratora biegnie od nowa. Stan konta wynika z dziennika zdarzeń.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from asystent_ocen.kalendarz import dodaj_miesiace, uplynelo_wiecej_niz_miesiecy
from asystent_ocen.zgodnosc import wczytaj_wymogi

from . import dziennik
from .models import UrzadzenieTotp, ZdarzenieBezpieczenstwa

AKTYWNE = "AKTYWNE"
ZABLOKOWANE = "ZABLOKOWANE"
ZAWIESZONE = "ZAWIESZONE"
NAZWY_STANOW = {
    AKTYWNE: "aktywne",
    ZABLOKOWANE: "zablokowane przez administratora",
    ZAWIESZONE: "zawieszone - brak aktywności",
}
_ZMIANY_STANU = (dziennik.KONTO_ZABLOKOWANE, dziennik.KONTO_ZAWIESZONE, dziennik.KONTO_ODBLOKOWANE)


# --- blokada po nieudanych próbach ---

def logowanie_zablokowane(login: str, teraz: datetime | None = None) -> bool:
    """Czy logowanie na ten login jest chwilowo zablokowane: w ostatnich `ASYSTENT_BLOKADA_MINUT` minutach było
    co najmniej `ASYSTENT_PROBY_LOGOWANIA` nieudanych prób (błędne hasło albo błędny kod jednorazowy) i żadna
    udana po nich. Wielkość liter loginu nie ma znaczenia."""
    login = str(login or "").strip()
    if not login:
        return False
    teraz = teraz or timezone.now()
    od = teraz - timedelta(minutes=settings.ASYSTENT_BLOKADA_MINUT)
    proby = ZdarzenieBezpieczenstwa.objects.filter(login__iexact=login, czas__gte=od, czas__lte=teraz)
    ostatnie_udane = proby.filter(rodzaj=dziennik.LOGOWANIE_UDANE).order_by("-pk").first()
    nieudane = proby.filter(rodzaj__in=dziennik.NIEUDANE_PROBY)
    if ostatnie_udane is not None:
        nieudane = nieudane.filter(pk__gt=ostatnie_udane.pk)
    return nieudane.count() >= settings.ASYSTENT_PROBY_LOGOWANIA


# --- aktywność i stan konta ---

def _ostatnia_zmiana_stanu(uzytkownik) -> ZdarzenieBezpieczenstwa | None:
    return (
        ZdarzenieBezpieczenstwa.objects.filter(dotyczy=uzytkownik.get_username(), rodzaj__in=_ZMIANY_STANU)
        .order_by("-pk").first()
    )


def ostatnia_aktywnosc(uzytkownik) -> date:
    """Dzień, od którego liczy się miesiąc bez aktywności: ostatnie logowanie, a gdy konta nie użyto - jego
    założenie; odblokowanie przez administratora też otwiera nowy okres."""
    chwile = [uzytkownik.last_login or uzytkownik.date_joined]
    zmiana = _ostatnia_zmiana_stanu(uzytkownik)
    if zmiana is not None and zmiana.rodzaj == dziennik.KONTO_ODBLOKOWANE:
        chwile.append(zmiana.czas)
    return timezone.localtime(max(chwile)).date()


def termin_zawieszenia(uzytkownik) -> date:
    """Ostatni dzień, w którym konto bez nowego logowania pozostaje czynne."""
    return dodaj_miesiace(ostatnia_aktywnosc(uzytkownik), wczytaj_wymogi().zawieszenie_konta_po_miesiacach)


def stan_konta(uzytkownik) -> dict:
    """Stan konta do wyświetlenia: kod, nazwa, a dla konta nieczynnego - kiedy i dlaczego je wyłączono."""
    if uzytkownik.is_active:
        return {"kod": AKTYWNE, "nazwa": NAZWY_STANOW[AKTYWNE], "termin_zawieszenia": termin_zawieszenia(uzytkownik)}
    zmiana = _ostatnia_zmiana_stanu(uzytkownik)
    kod = ZAWIESZONE if zmiana is not None and zmiana.rodzaj == dziennik.KONTO_ZAWIESZONE else ZABLOKOWANE
    return {"kod": kod, "nazwa": NAZWY_STANOW[kod], "od": zmiana.czas if zmiana else None, "opis": zmiana.opis if zmiana else ""}


def zawies_nieaktywne(dzien: date | None = None) -> list:
    """Zawiesza czynne konta, na których od ostatniej aktywności upłynął ponad miesiąc (okres z `zgodnosc.toml`).
    Zwraca zawieszone konta. Każde zawieszenie trafia do dziennika zdarzeń jako czynność systemu."""
    dzien = dzien or timezone.localdate()
    miesiace = wczytaj_wymogi().zawieszenie_konta_po_miesiacach
    zawieszone = []
    for uzytkownik in get_user_model().objects.filter(is_active=True).order_by("username"):
        ostatnia = ostatnia_aktywnosc(uzytkownik)
        if not uplynelo_wiecej_niz_miesiecy(ostatnia, dzien, miesiace):
            continue
        with transaction.atomic():
            uzytkownik.is_active = False
            uzytkownik.save(update_fields=["is_active"])
            dziennik.zapisz(
                dziennik.KONTO_ZAWIESZONE, dotyczy=uzytkownik.get_username(),
                opis=(
                    f"Brak aktywności od {ostatnia:%d.%m.%Y} - ponad {miesiace} mies. Zawieszenie automatyczne "
                    "(zał. nr 4 część I pkt 6 ustawy o KSC). Konto odblokowuje administrator."
                ),
            )
        zawieszone.append(uzytkownik)
    return zawieszone


def zablokuj_konto(uzytkownik, *, wykonawca, powod: str = "", request=None) -> None:
    """Blokada konta przez administratora. Działa od razu: zablokowany użytkownik traci też trwającą sesję."""
    with transaction.atomic():
        uzytkownik.is_active = False
        uzytkownik.save(update_fields=["is_active"])
        dziennik.zapisz(
            dziennik.KONTO_ZABLOKOWANE, request=request, uzytkownik=wykonawca, dotyczy=uzytkownik.get_username(),
            opis=powod.strip(),
        )


def odblokuj_konto(uzytkownik, *, wykonawca=None, opis: str = "", request=None) -> None:
    """Odblokowanie konta zablokowanego albo zawieszonego. Od tej chwili miesiąc bez aktywności biegnie od nowa."""
    with transaction.atomic():
        uzytkownik.is_active = True
        uzytkownik.save(update_fields=["is_active"])
        dziennik.zapisz(
            dziennik.KONTO_ODBLOKOWANE, request=request, uzytkownik=wykonawca, dotyczy=uzytkownik.get_username(),
            opis=opis.strip(),
        )


# --- weryfikacja dwuetapowa ---

def urzadzenie(uzytkownik) -> UrzadzenieTotp | None:
    """Potwierdzona aplikacja uwierzytelniająca użytkownika albo None."""
    return UrzadzenieTotp.objects.filter(uzytkownik=uzytkownik, potwierdzone=True).first()


def dwuetapowe_wymagane() -> bool:
    """Czy urząd wymaga weryfikacji dwuetapowej od każdego konta. Decyduje ustawienie ASYSTENT_2FA; bez niego
    weryfikacja jest wymagana, a w trybie demonstracyjnym dobrowolna - żeby pokaz dało się obejrzeć bez telefonu."""
    polityka = settings.ASYSTENT_2FA or ("dobrowolne" if settings.ASYSTENT_TRYB_DEMO else "wymagane")
    return polityka == "wymagane"
