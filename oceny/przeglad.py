"""Przegląd współpracy: to, co przełożony wie o pracy jednej osoby, na jednej stronie - oraz szybka notatka.

Strona zbiera notatki oceniającego, karty Radaru Dobrostanu i Doceniania, nieobecności i oceny, które prowadzi.
Widzi ją wyłącznie oceniający, bo zawiera jego notatki (decyzja zespołu z 21.11.2026) - komórka kadr, oceniany
i dyrektor generalny dostają 404. Nazwa: nie „teczka” ani „akta” (akta osobowe prowadzi pracodawca w komórce
kadr) i nie „profil” (to nie profilowanie) - strona niczego nie ocenia i niczego nie wylicza.

Zakres dat dotyczy tego, co ma datę: notatek i nieobecności. Domyślnie jest nim bieżący okres oceny, bo po to
przełożony tu zagląda. Karty Radaru pokazują stan na dziś - liczą okna 3 i 12 miesięcy wstecz od dnia odczytu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from asystent_ocen.kalendarz import dodaj_miesiace
from asystent_ocen.przebieg import DOBROSTAN, OBSERWACJA, OSIAGNIECIE

from . import dziennik, uprawnienia
from .czas import dzis
from .models import Ocena
from .notatki import POWROTY, RODZAJ_DLA_KARTY, RODZAJE_NOTATEK
from .radar import WYLACZONY, radar_oceny

OKRES = "okres"
WLASNY = "wlasny"
ZAKRESY = (
    (OKRES, "Bieżący okres oceny"),
    ("3m", "Ostatnie 3 miesiące"),
    ("12m", "Ostatnie 12 miesięcy"),
    ("wszystko", "Cały okres zatrudnienia"),
)


@dataclass(frozen=True)
class Zakres:
    od: date
    do: date
    kod: str   # jeden z ZAKRESY albo WLASNY
    opis: str  # nazwa małą literą - do zdania pod formularzem
    blad: str = ""


def oceny_prowadzone(uzytkownik):
    """Oceny, w których użytkownik jest oceniającym - tylko w nich ma wgląd w notatki."""
    ja = uprawnienia.pracownik_uzytkownika(uzytkownik)
    if ja is None:
        return Ocena.objects.none()
    return Ocena.objects.filter(oceniajacy=ja).select_related("oceniany__wydzial", "oceniajacy", "poprzednia")


def ustal_zakres(parametry, dzien: date, poczatek_okresu: date, pierwszy_dzien: date) -> Zakres:
    """Zakres dat z adresu strony: własny (`od` i `do`) albo gotowy (`zakres`). Błędny zakres nie jest awarią:
    strona pokazuje bieżący okres oceny i mówi, co poprawić."""
    od_tekst, do_tekst = (str(parametry.get(pole, "")).strip() for pole in ("od", "do"))
    blad = ""
    if od_tekst or do_tekst:
        if not (od_tekst and do_tekst):
            blad = "Podaj obie daty zakresu: początek i koniec."
        else:
            try:
                od, do = date.fromisoformat(od_tekst), date.fromisoformat(do_tekst)
            except ValueError:
                blad = "Podaj daty zakresu w postaci RRRR-MM-DD."
            else:
                if od <= do:
                    return Zakres(od, do, WLASNY, "własny zakres")
                blad = f"Początek zakresu ({od:%d.%m.%Y}) nie może być późniejszy niż koniec ({do:%d.%m.%Y})."
    nazwy = dict(ZAKRESY)
    kod = parametry.get("zakres") if not blad and parametry.get("zakres") in nazwy else OKRES
    od = {
        OKRES: poczatek_okresu, "3m": dodaj_miesiace(dzien, -3), "12m": dodaj_miesiace(dzien, -12), "wszystko": pierwszy_dzien,
    }[kod]
    opis = nazwy[kod][0].lower() + nazwy[kod][1:]
    return Zakres(min(od, dzien), dzien, kod, opis, f"{blad} Pokazuję bieżący okres oceny." if blad else "")


def kontekst_przegladu(pracownik, prowadzone: list[Ocena], parametry, dzien: date) -> dict:
    # Bieżąca jest ocena w toku; gdy wszystkie są zakończone - ostatnia z nich.
    biezaca = next((ocena for ocena in prowadzone if not ocena.zakonczona), prowadzone[0])
    pierwszy_dzien = min([pracownik.data_zatrudnienia, *(ocena.poczatek_cyklu for ocena in prowadzone)])
    zakres = ustal_zakres(parametry, dzien, biezaca.poczatek_cyklu, pierwszy_dzien)
    wpisy = sorted(
        (notatka for ocena in prowadzone for notatka in ocena.proces().notatki if zakres.od <= notatka.data <= zakres.do),
        key=lambda notatka: notatka.data, reverse=True,
    )
    radar = radar_oceny(biezaca, dzien)
    return {
        "pracownik": pracownik, "biezaca": biezaca, "oceny": prowadzone, "zakres": zakres,
        "zakresy": [{"kod": kod, "nazwa": nazwa, "wybrany": kod == zakres.kod} for kod, nazwa in ZAKRESY],
        "dzis_iso": dzien.isoformat(),
        # Notatka stoi przy kartach Radaru tego samego rodzaju: dobrostan przy dobrostanie, osiągnięcie przy docenieniu.
        "dobrostan": [notatka for notatka in wpisy if notatka.rodzaj == DOBROSTAN],
        "osiagniecia": [notatka for notatka in wpisy if notatka.rodzaj == OSIAGNIECIE],
        "obserwacje": [notatka for notatka in wpisy if notatka.rodzaj not in (DOBROSTAN, OSIAGNIECIE)],
        "liczba_notatek": len(wpisy),
        "nieobecnosci": list(pracownik.nieobecnosci.filter(od__lte=zakres.do, do__gte=zakres.od)),
        "radar": None if radar.stan == WYLACZONY else radar,
        "mozna_dodac_notatke": not biezaca.zakonczona,
        "rodzaje_notatek": RODZAJE_NOTATEK,
    }


@require_GET
def przeglad(request, pk: int):
    prowadzone = list(oceny_prowadzone(request.user).filter(oceniany_id=pk).order_by("-poczatek_cyklu", "-pk"))
    if not prowadzone:
        raise Http404  # jak przy cudzej ocenie: system nie zdradza, czy taka osoba i jej notatki istnieją
    pracownik = prowadzone[0].oceniany
    # § 19 ust. 2 pkt 7 lit. a KRI: monitorowanie dostępu do informacji - kto i kiedy otworzył przegląd.
    dziennik.zapisz(dziennik.ODCZYT_OCENY, request=request, dotyczy=f"przegląd współpracy {pracownik.pk}")
    return render(request, "oceny/przeglad.html", kontekst_przegladu(pracownik, prowadzone, request.GET, dzis()))


@require_GET
def nowa_notatka(request, pk: int):
    """Szybka notatka z listy zadań, z przeglądu albo do karty Radaru: sam formularz, bez reszty karty oceny."""
    ocena = get_object_or_404(oceny_prowadzone(request.user), pk=pk)
    if ocena.zakonczona:
        messages.info(request, "Ta ocena jest zakończona - notatki dodaje się w trakcie okresu oceny.")
        return redirect("ocena", pk=ocena.pk)
    powrot = request.GET.get("powrot", "")
    rodzaj = request.GET.get("rodzaj", "")
    # Notatka do karty Radaru: rodzaj wynika z rodzaju karty, a treść zaczyna się od jej tytułu.
    kod = request.GET.get("karta", "")
    karta = next((karta for karta in radar_oceny(ocena, dzis()).karty if karta.kod == kod), None) if kod else None
    return render(request, "oceny/nowa_notatka.html", {
        "ocena": ocena, "pracownik": ocena.oceniany, "karta": karta,
        "powrot": powrot if powrot in POWROTY else "",
        "wybrany_rodzaj": RODZAJ_DLA_KARTY[karta.rodzaj] if karta else rodzaj if rodzaj in dict(RODZAJE_NOTATEK) else OBSERWACJA,
        "tresc_notatki": f"{karta.tytul}: " if karta else "",
        "rodzaje_notatek": RODZAJE_NOTATEK,
    })
