"""Widoki aplikacji. Każdy wymaga zalogowania (LoginRequiredMiddleware), poza logowaniem.

Widoki niczego nie liczą i niczego nie rozstrzygają: odczytują formularz, wywołują usługę i pokazują wynik
albo komunikat rdzenia razem z podstawą prawną.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from asystent_ocen.bledy import Blad, BladWalidacji
from asystent_ocen.konfiguracja import DOMYSLNY_PLIK, wczytaj_przepisy
from asystent_ocen.przebieg import BladEtapu, BladUprawnien, Etap, Rola
from asystent_ocen.wynik import NEGATYWNA, POZYTYWNA
from asystent_ocen.zgodnosc import bledy_uruchomienia_monitoringu, rejestr_funkcji_ai, wczytaj_wymogi

from . import drukowanie, formularze, uprawnienia, uslugi
from .czas import dzis
from .karta import kontekst_karty
from .kontekst import konta_demo
from .kontekst_ezd import ustalenia_rdzenia
from .models import Ocena, Pracownik, Sprzeciw, UstaleniaMonitoringu
from .zadania import zadania_uzytkownika


# --- narzędzia wspólne ---

def _zglos_bledy(request, wyjatek: BladWalidacji) -> None:
    for blad in wyjatek.bledy:
        komunikat = blad.komunikat or blad.kod
        messages.error(request, f"{komunikat} Podstawa: {blad.podstawa}" if blad.podstawa else komunikat)


def _ocena_uzytkownika(request, pk: int) -> Ocena:
    """Ocena, w której zalogowany ma rolę. Cudza ocena daje 404 - system nie zdradza, że istnieje."""
    return get_object_or_404(uprawnienia.oceny_widoczne(request.user), pk=pk)


# --- logowanie ---

class Logowanie(LoginView):
    template_name = "oceny/logowanie.html"
    redirect_authenticated_user = True


@login_not_required
@require_POST
def demo_zaloguj(request):
    """Wejście na konto demonstracyjne bez hasła - działa wyłącznie w trybie demo i tylko dla kont demo."""
    konto = konta_demo().filter(username=request.POST.get("login", "")).first()
    if konto is None:
        raise Http404
    login(request, konto, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("zadania")


# --- moje zadania ---

@require_GET
def zadania(request):
    dzien = dzis()
    widoczne = uprawnienia.oceny_widoczne(request.user)
    return render(request, "oceny/zadania.html", {
        "zadania": zadania_uzytkownika(request.user, dzien),
        "moje_oceny": [ocena for ocena in widoczne if ocena.oceniany == uprawnienia.pracownik_uzytkownika(request.user)],
        "oceny_podwladnych": [
            ocena for ocena in widoczne
            if ocena.oceniajacy == uprawnienia.pracownik_uzytkownika(request.user) and not ocena.zakonczona
        ],
    })


# --- karta oceny ---

@require_GET
def ocena(request, pk: int):
    wybrana = _ocena_uzytkownika(request, pk)
    return render(request, "oceny/ocena.html", kontekst_karty(wybrana, request.user, dzis()))


def _wyznacz_kryteria(request, wybrana: Ocena):
    termin = formularze.wymagana_data(request.POST, "termin", "termin sporządzenia oceny")
    uslugi.wyznacz_kryteria(
        wybrana, request.user, kryteria_dodatkowe=formularze.kryteria_dodatkowe(request.POST), termin=termin
    )
    messages.success(request, "Kryteria i termin oceny zostały przekazane ocenianemu do potwierdzenia.")


def _potwierdz_kryteria(request, wybrana: Ocena):
    uslugi.potwierdz_kryteria(wybrana, request.user)
    messages.success(request, "Potwierdzono rozmowę oraz zapoznanie z kryteriami i terminem oceny.")


def _notatka(request, wybrana: Ocena):
    uslugi.dodaj_notatke(wybrana, request.user, tresc=formularze.tekst(request.POST, "tresc"))
    messages.success(request, "Notatka została zapisana. Widzi ją tylko oceniający.")


def _zmien_termin(request, wybrana: Ocena):
    nowy = formularze.wymagana_data(request.POST, "nowy_termin", "nowy termin sporządzenia oceny")
    uslugi.zmien_termin(wybrana, request.user, nowy_termin=nowy, przyczyna=formularze.tekst(request.POST, "przyczyna"))
    messages.success(request, "Termin oceny został zmieniony. Zawiadomienie dla ocenianego jest w dokumentach sprawy.")


def _wniosek_o_termin(request, wybrana: Ocena):
    uslugi.zloz_wniosek_o_zmiane_terminu(
        wybrana, request.user, uzasadnienie=formularze.tekst(request.POST, "uzasadnienie")
    )
    messages.success(request, "Wniosek o zmianę terminu oceny został przekazany oceniającemu.")


def _rozpatrz_wniosek(request, wybrana: Ocena):
    uwzglednic = request.POST.get("decyzja") == "uwzglednij"
    nowy = formularze.wymagana_data(request.POST, "nowy_termin", "nowy termin sporządzenia oceny") if uwzglednic else None
    uslugi.rozpatrz_wniosek_o_zmiane_terminu(wybrana, request.user, uwzglednic=uwzglednic, nowy_termin=nowy)
    messages.success(request, "Wniosek o zmianę terminu został rozpatrzony.")


def _szkic(request, wybrana: Ocena):
    uslugi.zapisz_szkic(wybrana, request.user, formularze.czesc_II(request.POST, wybrana.proces()))
    messages.success(request, "Szkic oceny został zapisany. Widzi go tylko oceniający.")


def _sporzadz_ocene(request, wybrana: Ocena):
    szkic = formularze.czesc_II(request.POST, wybrana.proces())
    # Najpierw szkic: po błędzie walidacji wpisane dane zostają w formularzu.
    uslugi.zapisz_szkic(wybrana, request.user, szkic)
    data_rozmowy = formularze.wymagana_data(request.POST, "data_rozmowy", "dzień rozmowy oceniającej")
    uslugi.sporzadz_ocene(
        wybrana,
        request.user,
        data_rozmowy=data_rozmowy,
        oceny=szkic["oceny"],
        wnioski_iprz=szkic["wnioski_iprz"],
        uzasadnienie=szkic["uzasadnienie"],
        wniosek_o_stopien=szkic["wniosek_o_stopien"],
        umotywowanie_wniosku=szkic["umotywowanie_wniosku"],
        poprzednia_reczna=szkic["poprzednia"],
    )
    messages.success(request, "Ocena została sporządzona i przekazana ocenianemu do zapoznania.")


def _potwierdz_zapoznanie(request, wybrana: Ocena):
    uslugi.potwierdz_zapoznanie(wybrana, request.user)
    messages.success(request, "Potwierdzono zapoznanie z oceną. Od dziś biegnie termin na sprzeciw.")


def _fikcja_zapoznania(request, wybrana: Ocena):
    role = uprawnienia.role_uzytkownika(request.user, wybrana)
    rola = next((r for r in (Rola.OCENIAJACY, Rola.ZARZADZAJACY, Rola.OCENIANY) if r in role), None)
    if rola is None:
        raise BladUprawnien("Fikcję zapoznania z oceną stwierdza strona procesu oceny.")
    uslugi.stwierdz_fikcje_zapoznania(wybrana, request.user, rola=rola)
    messages.success(request, "Stwierdzono fikcję zapoznania z oceną. Od dziś biegnie termin na sprzeciw.")


def _sprzeciw(request, wybrana: Ocena):
    sprzeciw = uslugi.wnies_sprzeciw(wybrana, request.user, tresc=formularze.tekst(request.POST, "tresc"))
    if sprzeciw.po_terminie:
        messages.warning(request, "Sprzeciw został zarejestrowany po upływie terminu (art. 83 ust. 1 u.s.c.).")
    else:
        messages.success(request, "Sprzeciw został wniesiony. Termin rozpatrzenia: 14 dni (art. 83 ust. 3 u.s.c.).")


def _rozpatrz_sprzeciw(request, wybrana: Ocena):
    rozstrzygniecie = request.POST.get("rozstrzygniecie", "")
    if rozstrzygniecie not in Sprzeciw.NAZWY_ROZSTRZYGNIEC:
        raise BladWalidacji([Blad("BRAK_ROZSTRZYGNIECIA", "Wybierz rozstrzygnięcie sprzeciwu.", "art. 83 ust. 4 u.s.c.")])
    nowe_oceny = formularze.oceny_czastkowe(request.POST, wybrana.proces()) if rozstrzygniecie == Sprzeciw.ZMIANA else None
    uslugi.rozpatrz_sprzeciw(
        wybrana, request.user, rozstrzygniecie=rozstrzygniecie,
        uzasadnienie=formularze.tekst(request.POST, "uzasadnienie"), nowe_oceny=nowe_oceny,
    )
    messages.success(request, "Rozstrzygnięcie sprzeciwu zostało wprowadzone.")


def _kolejny_cykl(request, wybrana: Ocena):
    nowa = uslugi.rozpocznij_kolejny_cykl(wybrana, request.user)
    messages.success(request, "Rozpoczęto kolejny cykl oceny.")
    return redirect("ocena", pk=nowa.pk)


CZYNNOSCI = {
    "wyznacz-kryteria": _wyznacz_kryteria,
    "potwierdz-kryteria": _potwierdz_kryteria,
    "notatka": _notatka,
    "zmien-termin": _zmien_termin,
    "wniosek-o-termin": _wniosek_o_termin,
    "rozpatrz-wniosek": _rozpatrz_wniosek,
    "szkic": _szkic,
    "sporzadz-ocene": _sporzadz_ocene,
    "potwierdz-zapoznanie": _potwierdz_zapoznanie,
    "fikcja-zapoznania": _fikcja_zapoznania,
    "sprzeciw": _sprzeciw,
    "rozpatrz-sprzeciw": _rozpatrz_sprzeciw,
    "kolejny-cykl": _kolejny_cykl,
}


@require_POST
def czynnosc(request, pk: int, nazwa: str):
    """Jedna czynność procesu. Kto może ją wykonać, rozstrzygają usługi i rdzeń - nie ten widok."""
    obsluga = CZYNNOSCI.get(nazwa)
    if obsluga is None:
        raise Http404
    wybrana = _ocena_uzytkownika(request, pk)
    try:
        odpowiedz = obsluga(request, wybrana)
    except BladWalidacji as wyjatek:
        _zglos_bledy(request, wyjatek)
        odpowiedz = None
    except BladEtapu as wyjatek:
        messages.error(request, f"{wyjatek}.")
        odpowiedz = None
    except BladUprawnien as wyjatek:
        raise PermissionDenied(str(wyjatek)) from wyjatek
    return odpowiedz or redirect("ocena", pk=wybrana.pk)


# --- wydruki ---

def _plik(tresc: bytes | str, typ: str, nazwa: str) -> HttpResponse:
    odpowiedz = HttpResponse(tresc, content_type=typ)
    odpowiedz["Content-Disposition"] = f'attachment; filename="{nazwa}"'
    odpowiedz["X-Content-Type-Options"] = "nosniff"
    return odpowiedz


@require_GET
def arkusz_docx(request, pk: int):
    wybrana = _ocena_uzytkownika(request, pk)
    return _plik(drukowanie.arkusz_docx(wybrana), drukowanie.TYP_DOCX, drukowanie.nazwa_pliku(wybrana, "docx"))


@require_GET
def arkusz_pdf(request, pk: int):
    wybrana = _ocena_uzytkownika(request, pk)
    try:
        pdf = drukowanie.docx_do_pdf(drukowanie.arkusz_docx(wybrana))
    except drukowanie.BladKonwersji as wyjatek:
        messages.error(request, str(wyjatek))
        return redirect("ocena", pk=wybrana.pk)
    return _plik(pdf, "application/pdf", drukowanie.nazwa_pliku(wybrana, "pdf"))


@require_GET
def kalendarz(request, pk: int):
    wybrana = _ocena_uzytkownika(request, pk)
    role = uprawnienia.role_uzytkownika(request.user, wybrana)
    tresc = drukowanie.kalendarz(wybrana, role)
    if tresc is None:
        messages.info(request, "Na tym etapie oceny nie biegnie żaden termin, który można dodać do kalendarza.")
        return redirect("ocena", pk=wybrana.pk)
    return _plik(tresc, "text/calendar; charset=utf-8", f"terminy-oceny-{wybrana.pk}.ics")


# --- kadry ---

def _wymagaj_kadr(request) -> None:
    if not uprawnienia.czy_kadry(request.user):
        raise PermissionDenied("Ta część systemu jest przeznaczona dla komórki kadr.")


@require_GET
def kadry(request):
    _wymagaj_kadr(request)
    dzien = dzis()
    wiersze = []
    osoby = Pracownik.objects.select_related("przelozony").prefetch_related("oceny", "nieobecnosci")
    for osoba in osoby:
        biezaca = max(osoba.oceny.all(), key=lambda o: (o.poczatek_cyklu, o.pk), default=None)
        wiersze.append({
            "osoba": osoba,
            "ocena": biezaca,
            "po_terminie": bool(biezaca and biezaca.termin and not biezaca.zakonczona and biezaca.termin < dzien),
            "mozna_rozpoczac": osoba.podlega_ocenie and biezaca is None,
            "nieobecnosci": list(osoba.nieobecnosci.all()),
        })
    return render(request, "oceny/kadry.html", {"wiersze": wiersze})


@require_POST
def kadry_rozpocznij(request, pk: int):
    _wymagaj_kadr(request)
    osoba = get_object_or_404(Pracownik, pk=pk)
    try:
        nowa = uslugi.rozpocznij_cykl(osoba, request.user)
    except BladWalidacji as wyjatek:
        _zglos_bledy(request, wyjatek)
        return redirect("kadry")
    messages.success(request, f"Rozpoczęto cykl oceny: {osoba.imie_i_nazwisko}.")
    return redirect("ocena", pk=nowa.pk)


@require_POST
def kadry_nieobecnosc(request, pk: int):
    _wymagaj_kadr(request)
    osoba = get_object_or_404(Pracownik, pk=pk)
    try:
        uslugi.dodaj_nieobecnosc(
            osoba, request.user,
            od=formularze.wymagana_data(request.POST, "od", "pierwszy dzień nieobecności"),
            do=formularze.wymagana_data(request.POST, "do", "ostatni dzień nieobecności"),
        )
    except BladWalidacji as wyjatek:
        _zglos_bledy(request, wyjatek)
    else:
        messages.success(request, f"Dodano nieobecność: {osoba.imie_i_nazwisko}. Terminy ocen zostały przeliczone.")
    return redirect("kadry")


@require_http_methods(["GET", "POST"])
def kadry_ezd(request):
    """Ustalenia wymagane przez Kodeks pracy przed pokazaniem danych z EZD RP - i włącznik integracji."""
    _wymagaj_kadr(request)
    dzien = dzis()
    if request.method == "POST":
        dane = {
            "podstawa": formularze.tekst(request.POST, "podstawa"),
            "cele": formularze.tekst(request.POST, "cele"),
            "zakres": formularze.tekst(request.POST, "zakres"),
            "sposob": formularze.tekst(request.POST, "sposob"),
            "data_poinformowania": formularze.data_lub_none(request.POST, "data_poinformowania"),
        }
        wlaczona = request.POST.get("wlaczona") == "on"
        try:
            uslugi.zapisz_ustalenia_monitoringu(request.user, **dane, wlaczona=wlaczona)
        except BladWalidacji as wyjatek:
            # Wpisana treść zostaje zapisana roboczo - integracja pozostaje wyłączona.
            uslugi.zapisz_ustalenia_monitoringu(request.user, **dane, wlaczona=False)
            messages.error(request, "Integracji z EZD RP nie można jeszcze włączyć. Ustalenia zapisano roboczo.")
            _zglos_bledy(request, wyjatek)
        else:
            messages.success(
                request, "Ustalenia zapisano. Integracja z EZD RP jest " + ("włączona." if wlaczona else "wyłączona.")
            )
        return redirect("kadry_ezd")
    zapis = UstaleniaMonitoringu.pobierz()
    return render(request, "oceny/kadry_ezd.html", {
        "ustalenia": zapis,
        "przeszkody": bledy_uruchomienia_monitoringu(ustalenia_rdzenia(zapis), dzien),
        "bez_informacji": Pracownik.objects.filter(klauzula_ezd_potwierdzona=False).count(),
        "wyprzedzenie": wczytaj_wymogi().monitoring_wyprzedzenie_informacji_dni,
    })


# --- statystyki zbiorcze ---

@require_GET
def statystyki(request):
    """Liczby dla całego urzędu, bez danych osób. Komórek poniżej progu liczności nie pokazuje się osobno."""
    if not uprawnienia.widzi_statystyki(request.user):
        raise PermissionDenied("Statystyki zbiorcze są dostępne dla dyrektora i komórki kadr.")
    dzien = dzis()
    prog = wczytaj_wymogi().min_licznosc_wskaznika
    oceny = list(Ocena.objects.select_related("oceniany"))
    w_toku = [o for o in oceny if not o.zakonczona]
    zakonczone = [o for o in oceny if o.zakonczona]
    etapy = [
        {"nazwa": etap.value, "liczba": sum(1 for o in oceny if o.etap == etap.name)} for etap in Etap
    ]
    poziomy = [
        {"nazwa": poziom.nazwa, "liczba": sum(1 for o in zakonczone if o.poziom == poziom.nazwa)}
        for poziom in wczytaj_przepisy().poziomy
    ]
    najwiecej = max([p["liczba"] for p in poziomy] + [1])
    for poziom in poziomy:
        poziom["procent"] = round(100 * poziom["liczba"] / najwiecej)
    komorki: dict[str, list[Ocena]] = {}
    for o in oceny:
        komorki.setdefault(o.oceniany.komorka or "bez komórki", []).append(o)
    wiersze_komorek = [
        {
            "nazwa": nazwa,
            "liczba": len(lista),
            "w_toku": sum(1 for o in lista if not o.zakonczona),
            "po_terminie": sum(1 for o in lista if not o.zakonczona and o.termin and o.termin < dzien),
        }
        for nazwa, lista in sorted(komorki.items()) if len(lista) >= prog
    ]
    return render(request, "oceny/statystyki.html", {
        "liczba_ocen": len(oceny),
        "liczba_w_toku": len(w_toku),
        "liczba_zakonczonych": len(zakonczone),
        "po_terminie": sum(1 for o in w_toku if o.termin and o.termin < dzien),
        "pozytywne": sum(1 for o in zakonczone if o.wynik == POZYTYWNA),
        "negatywne": sum(1 for o in zakonczone if o.wynik == NEGATYWNA),
        "sprzeciwy": Sprzeciw.objects.count(),
        "sprzeciwy_w_toku": Sprzeciw.objects.filter(rozstrzygniecie="").count(),
        "nie_podlega": sum(1 for osoba in Pracownik.objects.all() if not osoba.podlega_ocenie),
        "etapy": etapy,
        "poziomy": poziomy,
        "komorki": wiersze_komorek,
        "pominiete_komorki": len(komorki) - len(wiersze_komorek),
        "prog": prog,
    })


# --- przepisy w konfiguracji ---

@require_GET
def przepisy(request):
    """Parametry prawne systemu - dokładnie ten plik, z którego korzysta rdzeń."""
    return render(request, "oceny/przepisy.html", {
        "plik": DOMYSLNY_PLIK.name,
        "tresc": DOMYSLNY_PLIK.read_text(encoding="utf-8"),
        "funkcje_ai": rejestr_funkcji_ai(),
    })


# --- HR Copilot: pytania o procedurę ---

@require_http_methods(["GET", "POST"])
def asystent(request):
    from . import copilot  # import przy użyciu - moduł AI nie jest potrzebny do pracy reszty systemu

    kontekst = {"model": settings.ASYSTENT_MODEL, "przyklady": copilot.PRZYKLADOWE_PYTANIA}
    if request.method == "POST":
        pytanie = formularze.tekst(request.POST, "pytanie")[:1000]
        kontekst["pytanie"] = pytanie
        if pytanie:
            kontekst.update(copilot.odpowiedz(pytanie))
    return render(request, "oceny/asystent.html", kontekst)
