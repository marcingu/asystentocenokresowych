"""Dziennik zdarzeń bezpieczeństwa - zapis i kontrola nienaruszalności.

§ 20 rozporządzenia KRI wymaga, żeby rozliczalność była wiarygodnie dokumentowana w dziennikach systemów,
a obowiązkowo odnotowuje się dostęp z uprawnieniami administracyjnymi, do konfiguracji i do danych prawnie
chronionych. Tutaj trafiają: logowania i wylogowania, kody jednorazowe, zmiany kont, czynności administratora,
odmowy dostępu oraz odczyty kart ocen i pobrania arkuszy.

Czynności w samym procesie oceny (kto co zrobił w której ocenie) zapisuje osobny dziennik - model `Zdarzenie`.

Każdy wpis zawiera skrót SHA-256 liczony z własnej treści i ze skrótu poprzedniego wpisu. Zmiana albo usunięcie
wpisu poza aplikacją przerywa łańcuch. To wykrywa manipulację, ale jej nie uniemożliwia: osoba z prawem zapisu
do bazy może przeliczyć cały łańcuch, dlatego kopię dziennika urząd przekazuje do własnego systemu zbierania logów.
"""

from __future__ import annotations

import hashlib
import ipaddress
from datetime import timezone as strefa

from django.db import transaction
from django.utils import timezone

from .models import GlowaDziennika, ZdarzenieBezpieczenstwa

LOGOWANIE_UDANE = "LOGOWANIE_UDANE"
LOGOWANIE_NIEUDANE = "LOGOWANIE_NIEUDANE"
LOGOWANIE_ZABLOKOWANE = "LOGOWANIE_ZABLOKOWANE"
WYLOGOWANIE = "WYLOGOWANIE"
KOD_POPRAWNY = "KOD_POPRAWNY"
KOD_BLEDNY = "KOD_BLEDNY"
DWUETAPOWE_WLACZONE = "DWUETAPOWE_WLACZONE"
DWUETAPOWE_WYLACZONE = "DWUETAPOWE_WYLACZONE"
DWUETAPOWE_ZRESETOWANE = "DWUETAPOWE_ZRESETOWANE"
HASLO_ZMIENIONE = "HASLO_ZMIENIONE"
HASLO_LINK = "HASLO_LINK"
KONTO_UTWORZONE = "KONTO_UTWORZONE"
KONTO_ZMIENIONE = "KONTO_ZMIENIONE"
KONTO_ZABLOKOWANE = "KONTO_ZABLOKOWANE"
KONTO_ZAWIESZONE = "KONTO_ZAWIESZONE"
KONTO_ODBLOKOWANE = "KONTO_ODBLOKOWANE"
ODMOWA_DOSTEPU = "ODMOWA_DOSTEPU"
ODCZYT_OCENY = "ODCZYT_OCENY"
POBRANIE_ARKUSZA = "POBRANIE_ARKUSZA"
WGLAD_W_DZIENNIK = "WGLAD_W_DZIENNIK"
EKSPORT_DZIENNIKA = "EKSPORT_DZIENNIKA"
PANEL_ADMINISTRATORA = "PANEL_ADMINISTRATORA"
PRACOWNIK_DODANY = "PRACOWNIK_DODANY"
PRACOWNIK_ZMIENIONY = "PRACOWNIK_ZMIENIONY"

ZMIANA_KONFIGURACJI = "ZMIANA_KONFIGURACJI"

PIERWSZA_CZYNNOSC = "PIERWSZA_CZYNNOSC"

RODZAJE = {
    PIERWSZA_CZYNNOSC: "czynność w pierwszej ocenie",
    ZMIANA_KONFIGURACJI: "zmiana konfiguracji procesu",
    LOGOWANIE_UDANE: "logowanie",
    LOGOWANIE_NIEUDANE: "nieudane logowanie",
    LOGOWANIE_ZABLOKOWANE: "logowanie odrzucone - blokada po nieudanych próbach",
    WYLOGOWANIE: "wylogowanie",
    KOD_POPRAWNY: "kod jednorazowy - poprawny",
    KOD_BLEDNY: "kod jednorazowy - błędny",
    DWUETAPOWE_WLACZONE: "weryfikacja dwuetapowa - włączona",
    DWUETAPOWE_WYLACZONE: "weryfikacja dwuetapowa - wyłączona",
    DWUETAPOWE_ZRESETOWANE: "weryfikacja dwuetapowa - zresetowana przez administratora",
    HASLO_ZMIENIONE: "zmiana hasła",
    HASLO_LINK: "link do ustawienia hasła - wydany przez administratora",
    KONTO_UTWORZONE: "konto - utworzone",
    KONTO_ZMIENIONE: "konto - zmienione",
    KONTO_ZABLOKOWANE: "konto - zablokowane przez administratora",
    KONTO_ZAWIESZONE: "konto - zawieszone z powodu braku aktywności",
    KONTO_ODBLOKOWANE: "konto - odblokowane",
    ODMOWA_DOSTEPU: "odmowa dostępu",
    ODCZYT_OCENY: "odczyt karty oceny",
    POBRANIE_ARKUSZA: "pobranie arkusza oceny",
    WGLAD_W_DZIENNIK: "wgląd w dziennik zdarzeń",
    EKSPORT_DZIENNIKA: "eksport dziennika zdarzeń",
    PANEL_ADMINISTRATORA: "czynność w panelu administratora",
    PRACOWNIK_DODANY: "dane pracownika - dodane przez komórkę kadr",
    PRACOWNIK_ZMIENIONY: "dane pracownika - zmienione przez komórkę kadr",
}
NIEUDANE_PROBY = (LOGOWANIE_NIEUDANE, KOD_BLEDNY)


def adres_zadania(request) -> str | None:
    """Adres, z którego przyszło żądanie. Za serwerem pośredniczącym urzędu (ustawienie ASYSTENT_ZA_PROXY)
    brany jest ostatni adres z nagłówka X-Forwarded-For - ten, który dopisał serwer pośredniczący."""
    from django.conf import settings

    if request is None:
        return None
    adres = request.META.get("REMOTE_ADDR") or ""
    if settings.SECURE_PROXY_SSL_HEADER:
        przekazane = [czesc.strip() for czesc in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if czesc.strip()]
        if przekazane:
            adres = przekazane[-1]
    try:
        return str(ipaddress.ip_address(adres))
    except ValueError:
        return None  # nagłówek z wartością, która nie jest adresem - nie zapisujemy jej


def _skrot(poprzedni: str, wpis: ZdarzenieBezpieczenstwa) -> str:
    pola = [
        poprzedni,
        wpis.czas.astimezone(strefa.utc).isoformat(timespec="microseconds"),
        wpis.rodzaj,
        str(wpis.uzytkownik_id or ""),
        wpis.login,
        wpis.dotyczy,
        wpis.adres_ip or "",
        wpis.opis,
    ]
    # Długość każdego pola przed jego treścią: dwa różne wpisy nie złożą się w ten sam ciąg znaków.
    return hashlib.sha256("".join(f"{len(pole)}:{pole}|" for pole in pola).encode("utf-8")).hexdigest()


def zapisz(
    rodzaj: str, *, request=None, uzytkownik=None, login: str = "", dotyczy: str = "", opis: str = "",
    adres_ip: str | None = None,
) -> ZdarzenieBezpieczenstwa:
    """Dopisuje zdarzenie. `uzytkownik` to osoba, która wykonała czynność (None przy czynności systemu albo
    osoby niezalogowanej); `login` - login w chwili zdarzenia, także nieistniejący przy nieudanym logowaniu;
    `dotyczy` - konto albo zasób, którego dotyczy czynność."""
    if rodzaj not in RODZAJE:
        raise ValueError(f"Nieznany rodzaj zdarzenia bezpieczeństwa: {rodzaj}.")
    if uzytkownik is None and request is not None and getattr(request, "user", None) is not None:
        uzytkownik = request.user if request.user.is_authenticated else None
    if uzytkownik is not None and not login:
        login = uzytkownik.get_username()
    with transaction.atomic():
        glowa, _ = GlowaDziennika.objects.select_for_update().get_or_create(pk=1)
        wpis = ZdarzenieBezpieczenstwa(
            czas=timezone.now(),
            rodzaj=rodzaj,
            uzytkownik=uzytkownik,
            login=str(login or "")[:150],
            dotyczy=str(dotyczy or "")[:150],
            adres_ip=adres_ip or adres_zadania(request),
            opis=opis,
            poprzedni_skrot=glowa.skrot,
        )
        wpis.skrot = _skrot(glowa.skrot, wpis)
        wpis.save()
        glowa.liczba += 1
        glowa.skrot = wpis.skrot
        glowa.save(update_fields=["liczba", "skrot"])
    return wpis


def sprawdz_lancuch() -> dict:
    """Kontrola nienaruszalności dziennika: liczba wpisów, czy łańcuch skrótów jest ciągły i zgodny z treścią,
    oraz identyfikator pierwszego wpisu, przy którym kontrola się nie zgadza (None, gdy dziennik jest w porządku
    albo gdy brakuje wpisów na końcu)."""
    poprzedni = ""
    liczba = 0
    for wpis in ZdarzenieBezpieczenstwa.objects.order_by("pk").iterator():
        liczba += 1
        if wpis.poprzedni_skrot != poprzedni or wpis.skrot != _skrot(poprzedni, wpis):
            return {"wpisow": liczba, "poprawny": False, "pierwszy_bledny": wpis.pk}
        poprzedni = wpis.skrot
    glowa = GlowaDziennika.objects.filter(pk=1).first()
    zgodny_koniec = (glowa.liczba, glowa.skrot) == (liczba, poprzedni) if glowa else liczba == 0
    return {"wpisow": liczba, "poprawny": zgodny_koniec, "pierwszy_bledny": None}
