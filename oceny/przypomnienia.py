"""Przypomnienia e-mail o terminach i osobisty kalendarz użytkownika.

Wiadomość i kalendarz pokazują to samo co lista „Moje zadania”: zadania osoby z terminem dziennym w ocenie
okresowej i w pierwszej ocenie. Nie zawierają ocen ani treści arkuszy; nazwisko ocenianego pojawia się dopiero,
gdy administrator włączy to w ustawieniach skrzynki (poczta wychodzi poza system, więc domyślnie mniej danych).

Wiadomość planowa wychodzi w dniach z `przypomnienia_dni_przed` (przepisy.toml), w dniu terminu i co 7 dni po
terminie - najwyżej raz dziennie na osobę. Uruchamia ją harmonogram serwera: `manage.py wyslij_przypomnienia`.
"""

from __future__ import annotations

import hashlib
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone as strefa

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_not_required
from django.core.mail import EmailMessage
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from asystent_ocen.ics import DOMENA_UID, PRODID, Wydarzenie, kalendarz_ics
from asystent_ocen.konfiguracja import stosuj_przepisy, wczytaj_przepisy

from . import dziennik, karta_pierwszej, poczta, uprawnienia
from .czas import dzis
from .models import KalendarzOsobisty, KonfiguracjaProcesu, OznaczenieUrzedu, SkrzynkaNadawcza, WyslanePrzypomnienie
from .zadania import opis_dni_do_terminu, zadania_uzytkownika

CO_ILE_DNI_PO_TERMINIE = 7
PUSTY_KALENDARZ = f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:{PRODID}\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\nEND:VCALENDAR\r\n"


@dataclass(frozen=True)
class Termin:
    klucz: str      # stały identyfikator zadania - kalendarz aktualizuje wpis zamiast go dublować
    tytul: str
    termin: date
    dni: int        # ile dni zostało; ujemne - po terminie
    rola: str
    podstawa: str
    adres: str      # ścieżka karty w systemie
    oceniany: str   # imię i nazwisko ocenianego; puste, gdy zadanie dotyczy własnej oceny adresata


@dataclass
class Wynik:
    wyslane: int = 0
    bez_adresu: int = 0
    bledy: int = 0
    wstrzymane: bool = False
    powod: str = ""
    opisy_bledow: list[str] = field(default_factory=list)

    @property
    def opis(self) -> str:
        if self.wstrzymane:
            return f"Przypomnienia nie wyszły: {self.powod}"
        czesci = [f"Wysłano przypomnień: {self.wyslane}."]
        if self.bez_adresu:
            czesci.append(f"Osoby z terminami bez adresu e-mail na koncie: {self.bez_adresu}.")
        if self.bledy:
            czesci.append(f"Nieudane wysyłki: {self.bledy} ({self.opisy_bledow[0]}).")
        return " ".join(czesci)


@contextmanager
def _przepisy_urzedu():
    """Poza żądaniem zalogowanej osoby (harmonogram, program kalendarza) przepisy urzędu trzeba włączyć samemu."""
    with stosuj_przepisy(KonfiguracjaProcesu.aktualna().tresc):
        yield


def terminy(uzytkownik, dzien: date) -> list[Termin]:
    """Zadania osoby z terminem dziennym w obu procesach, od najwcześniejszego terminu."""
    ja = uprawnienia.pracownik_uzytkownika(uzytkownik)

    def kto(oceniany) -> str:
        return "" if oceniany == ja else oceniany.imie_i_nazwisko

    pozycje = [
        Termin(f"zadanie-{zadanie.ocena.pk}-{zadanie.kod}", zadanie.tytul, zadanie.termin, (zadanie.termin - dzien).days, zadanie.rola.value,
               zadanie.podstawa, reverse("ocena", args=[zadanie.ocena.pk]), kto(zadanie.ocena.oceniany))
        for zadanie in zadania_uzytkownika(uzytkownik, dzien) if zadanie.termin is not None
    ]
    for wiersz in karta_pierwszej.zadania_uzytkownika(uzytkownik, dzien):
        if wiersz["termin"] is None:
            continue
        skrot = hashlib.sha256(wiersz["tytul"].encode("utf-8")).hexdigest()[:10]
        pozycje.append(Termin(
            f"pierwsza-{wiersz['adres'].strip('/').rsplit('/', 1)[-1]}-{skrot}", wiersz["tytul"], wiersz["termin"],
            (wiersz["termin"] - dzien).days, wiersz["rola"].removeprefix("pierwsza ocena, w roli: "), wiersz["podstawa"],
            wiersz["adres"], kto(wiersz["oceniany"])))
    return sorted(pozycje, key=lambda pozycja: (pozycja.termin, pozycja.klucz))


def dzien_przypomnienia(dni: int, progi) -> bool:
    return dni in progi or dni == 0 or (dni < 0 and -dni % CO_ILE_DNI_PO_TERMINIE == 0)


def _terminow(liczba: int) -> str:
    if liczba == 1:
        return "1 termin wymaga uwagi"
    if liczba % 10 in (2, 3, 4) and liczba % 100 not in (12, 13, 14):
        return f"{liczba} terminy wymagają uwagi"
    return f"{liczba} terminów wymaga uwagi"


def _tytul(pozycja: Termin, nazwiska: bool) -> str:
    return f"{pozycja.tytul} - {pozycja.oceniany}" if nazwiska and pozycja.oceniany else pozycja.tytul


def _kalendarz(pozycje: list[Termin], dzien: date, baza: str, nazwiska: bool) -> str:
    if not pozycje:
        return PUSTY_KALENDARZ
    wydarzenia = [
        Wydarzenie(uid=f"{pozycja.klucz}@{DOMENA_UID}", data=pozycja.termin, tytul=_tytul(pozycja, nazwiska),
                   opis=f"Podstawa: {pozycja.podstawa.rstrip('.')}." + (f" Szczegóły po zalogowaniu: {baza}{pozycja.adres}" if baza else ""))
        for pozycja in pozycje
    ]
    return kalendarz_ics(wydarzenia, wytworzono=datetime.combine(dzien, timezone.now().time(), tzinfo=strefa.utc))


def tresc(pozycje: list[Termin], dzien: date, baza: str, nazwiska: bool) -> tuple[str, str]:
    """Temat i treść wiadomości - zwykły tekst, czytelny w każdym programie pocztowym i czytniku ekranu."""
    zalegle = [pozycja for pozycja in pozycje if pozycja.dni < 0]
    w_nawiasie = (f"po terminie od {zalegle[0].termin:%d.%m.%Y}" if zalegle else f"najbliższy {pozycje[0].termin:%d.%m.%Y}")
    wiersze = ["Dzień dobry,", "",
               f"przypominamy o terminach w ocenach, w których Pani/Pan uczestniczy. Stan na {dzien:%d.%m.%Y}.", ""]
    for naglowek, grupa in (("Po terminie:", zalegle), ("Najbliższe terminy:", [p for p in pozycje if p.dni >= 0])):
        if not grupa:
            continue
        wiersze.append(naglowek)
        for pozycja in grupa:
            wiersze.append(f"- {pozycja.termin:%d.%m.%Y} ({opis_dni_do_terminu(pozycja.dni)}) - {_tytul(pozycja, nazwiska)}")
            wiersze.append(f"  w roli: {pozycja.rola}; podstawa: {pozycja.podstawa}")
            if baza:
                wiersze.append(f"  {baza}{pozycja.adres}")
        wiersze.append("")
    if baza:
        wiersze += [f"Wszystkie zadania: {baza}/", ""]
    wiersze += [
        "W załączniku terminy.ics są te same terminy - można je dodać do kalendarza. Kalendarz, który odświeża się sam,",
        "włącza się w systemie: Moje konto, część „Przypomnienia i kalendarz”.", "",
        f"Wiadomość wysłał automatycznie Cyfrowy asystent ocen okresowych ({OznaczenieUrzedu.aktualne().nazwa}).",
        "Wiadomość nie zawiera ocen ani treści arkuszy. Prosimy na nią nie odpowiadać.", "",
    ]
    return f"Asystent ocen: {_terminow(len(pozycje))} ({w_nawiasie})", "\n".join(wiersze)


def wiadomosc(uzytkownik, dzien: date, *, adres_bazowy: str = "") -> EmailMessage | None:
    """Wiadomość z terminami osoby albo None, gdy nie ma ona zadań z terminem."""
    with _przepisy_urzedu():
        pozycje = terminy(uzytkownik, dzien)
        if not pozycje:
            return None
        skrzynka = SkrzynkaNadawcza.aktualna()
        baza = (skrzynka.adres_systemu or adres_bazowy).rstrip("/")
        temat, tekst = tresc(pozycje, dzien, baza, skrzynka.nazwiska)
        list_ = EmailMessage(temat, tekst, poczta.nadawca(), [uzytkownik.email] if uzytkownik.email else [])
        list_.attach("terminy.ics", _kalendarz(pozycje, dzien, baza, skrzynka.nazwiska), "text/calendar")
        return list_


def _konta():
    return get_user_model().objects.filter(is_active=True, pracownik__isnull=False).order_by("username")


def adresaci(dzien: date) -> list[dict]:
    """Zestawienie dla administratora: kto ma dziś terminy i czy ma adres. Bez tytułów zadań i nazwisk ocenianych."""
    wynik = []
    with _przepisy_urzedu():
        for konto in _konta():
            pozycje = terminy(konto, dzien)
            if pozycje:
                wynik.append({"login": konto.get_username(), "email": konto.email, "liczba": len(pozycje),
                              "po_terminie": sum(pozycja.dni < 0 for pozycja in pozycje)})
    return wynik


def wyslij(dzien: date, *, wymus: bool = False, adres_bazowy: str = "") -> Wynik:
    """Wysyła przypomnienia. Planowo: osobom, którym dziś wypada dzień przypomnienia, raz dziennie.
    `wymus` (przycisk administratora): wszystkim, którzy mają zadania z terminem."""
    if not poczta.gotowa():
        return Wynik(wstrzymane=True, powod="skrzynka nadawcza nie jest ustawiona.")
    if not wymus and not SkrzynkaNadawcza.aktualna().wlaczona:
        return Wynik(wstrzymane=True, powod="przypomnienia planowe są wyłączone w ustawieniach skrzynki.")
    wynik = Wynik()
    with _przepisy_urzedu():
        progi = wczytaj_przepisy().przypomnienia_dni_przed
        for konto in _konta():
            pozycje = terminy(konto, dzien)
            if not pozycje:
                continue
            if not wymus and (not any(dzien_przypomnienia(pozycja.dni, progi) for pozycja in pozycje)
                              or WyslanePrzypomnienie.objects.filter(uzytkownik=konto, dzien=dzien).exists()):
                continue
            if not konto.email:
                wynik.bez_adresu += 1
                continue
            list_ = wiadomosc(konto, dzien, adres_bazowy=adres_bazowy)
            if list_ is None:
                continue
            try:
                list_.connection = poczta.polaczenie()
                list_.send()
            except poczta.BLEDY_WYSYLKI as blad:
                wynik.bledy += 1
                wynik.opisy_bledow.append(f"{type(blad).__name__}: {blad}".strip(": ")[:200])
                continue
            WyslanePrzypomnienie.objects.update_or_create(uzytkownik=konto, dzien=dzien, defaults={"liczba": len(pozycje)})
            wynik.wyslane += 1
    return wynik


# === Moje konto: podgląd wiadomości i osobisty kalendarz ===

def kontekst_konta(request) -> dict:
    kalendarz = KalendarzOsobisty.objects.filter(uzytkownik=request.user).first()
    return {
        "kalendarz": kalendarz,
        "adres_kalendarza": request.build_absolute_uri(reverse("kalendarz_osobisty", args=[kalendarz.token])) if kalendarz else "",
        "progi": sorted(wczytaj_przepisy().przypomnienia_dni_przed, reverse=True),
        "poczta_gotowa": poczta.gotowa() and SkrzynkaNadawcza.aktualna().wlaczona,
    }


@require_GET
def podglad(request):
    """Wiadomość, którą osoba dostałaby dzisiaj - także wtedy, gdy urząd nie ustawił jeszcze skrzynki."""
    dzien = dzis()
    pozycje = terminy(request.user, dzien)
    skrzynka = SkrzynkaNadawcza.aktualna()
    baza = (skrzynka.adres_systemu or request.build_absolute_uri("/")).rstrip("/")
    temat, tekst = tresc(pozycje, dzien, baza, skrzynka.nazwiska) if pozycje else ("", "")
    return render(request, "oceny/przypomnienie.html", {"temat": temat, "tekst": tekst, "adres": request.user.email})


@require_POST
def kalendarz_konta(request):
    akcja = request.POST.get("akcja")
    if akcja not in {"wlacz", "nowy", "wylacz"}:
        messages.error(request, "Nieznana czynność.")
        return redirect("konto")
    KalendarzOsobisty.objects.filter(uzytkownik=request.user).delete()
    if akcja == "wylacz":
        opis, komunikat = "wyłączony", "Kalendarz osobisty jest wyłączony. Dotychczasowy adres przestał działać."
    else:
        KalendarzOsobisty.objects.create(uzytkownik=request.user, token=secrets.token_urlsafe(32))
        opis = "włączony" if akcja == "wlacz" else "nowy adres"
        komunikat = ("Kalendarz osobisty jest włączony. Skopiuj adres do swojego programu kalendarza." if akcja == "wlacz"
                     else "Kalendarz ma nowy adres. Poprzedni przestał działać - podmień go w programie kalendarza.")
    dziennik.zapisz(dziennik.KONTO_ZMIENIONE, request=request, dotyczy=request.user.get_username(), opis=f"Kalendarz osobisty: {opis}.")
    messages.success(request, komunikat)
    return redirect("konto")


@login_not_required
@require_GET
def kalendarz_osobisty(request, token: str):
    """Kalendarz dla programu, który nie potrafi się zalogować: dostęp daje losowy klucz w adresie."""
    kalendarz = KalendarzOsobisty.objects.select_related("uzytkownik").filter(token=token).first()
    if kalendarz is None or not kalendarz.uzytkownik.is_active:
        raise Http404("Nie ma takiego kalendarza.")
    dzien = dzis()
    skrzynka = SkrzynkaNadawcza.aktualna()
    with _przepisy_urzedu():
        plik = _kalendarz(terminy(kalendarz.uzytkownik, dzien), dzien,
                          (skrzynka.adres_systemu or request.build_absolute_uri("/")).rstrip("/"), skrzynka.nazwiska)
    odpowiedz = HttpResponse(plik, content_type="text/calendar; charset=utf-8")
    odpowiedz["Content-Disposition"] = 'inline; filename="terminy.ics"'
    odpowiedz["Cache-Control"] = "private, no-store"
    return odpowiedz
