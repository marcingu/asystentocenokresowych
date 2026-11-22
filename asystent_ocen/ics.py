"""Eksport terminów procesu oceny do kalendarza w formacie iCalendar (RFC 5545) - plik `.ics`.

- `kalendarz_ics(wydarzenia, wytworzono=...)` składa obiekt VCALENDAR z całodniowych wydarzeń VEVENT
  z przypomnieniami VALARM. Wyprzedzenia przypomnień pochodzą z `przepisy.toml` (`przypomnienia_dni_przed`).
  Wynik zależy tylko od argumentów (znacznik czasu DTSTAMP podaje wywołujący), więc jest powtarzalny.
- `wydarzenia_procesu(proces, kto=..., identyfikator=...)` wylicza funkcjami rdzenia terminy, które jeszcze
  biegną na danym etapie procesu, i opisuje je z podstawą prawną.

Minimalizacja danych: tytuły i opisy zawierają wyłącznie oznaczenie osoby przekazane w `kto` (może to być
oznaczenie niejawne, np. numer). Kalendarz nie zawiera ocen, uzasadnień, notatek ani informacji o wyniku oceny;
wydarzenie „Ponowna ocena okresowa” wskazuje tylko podstawę prawną.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .konfiguracja import Przepisy, _ustal_przepisy
from .nieobecnosci import Nieobecnosc
from .przebieg import ProcesOceny
from .terminy import (
    data_ponownej_oceny_po_negatywnej,
    termin_oceny,
    termin_sprzeciwu,
    termin_wyznaczenia_kryteriow,
)
from .wynik import NEGATYWNA

PRODID = "-//Cyfrowy Asystent Ocen Okresowych//HackNation 2026 KPRM//PL"
DOMENA_UID = "asystent-ocen"

_LIMIT_OKTETOW = 75  # RFC 5545 pkt 3.1
_ROZPORZADZENIE = "rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. (Dz. U. poz. 470)"
_USTAWA = "ustawy z dnia 21 listopada 2008 r. o służbie cywilnej"
_KODEKS = "termin liczony według art. 111 i 115 Kodeksu cywilnego"


@dataclass(frozen=True)
class Wydarzenie:
    """Całodniowe wydarzenie kalendarza."""

    uid: str  # stały identyfikator - ponowny eksport aktualizuje wpis zamiast go dublować
    data: date
    tytul: str
    opis: str = ""


# === Składnia iCalendar ===

def _tekst(wartosc: str) -> str:
    """Wartość typu TEXT (RFC 5545 pkt 3.3.11): ucieczka znaków `\\`, `;`, `,` i nowej linii."""
    wartosc = str(wartosc).replace("\r\n", "\n").replace("\r", "\n")
    return wartosc.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _zlam(wiersz: str) -> list[str]:
    """Łamie wiersz dłuższy niż 75 oktetów UTF-8; dalszy ciąg zaczyna się od spacji (RFC 5545 pkt 3.1).
    Podział wypada zawsze między znakami, nigdy w środku wielobajtowego znaku."""
    if len(wiersz.encode("utf-8")) <= _LIMIT_OKTETOW:
        return [wiersz]
    fizyczne: list[str] = []
    biezacy, oktety = "", 0
    for znak in wiersz:
        rozmiar = len(znak.encode("utf-8"))
        if oktety + rozmiar > _LIMIT_OKTETOW:
            fizyczne.append(biezacy)
            biezacy, oktety = " ", 1  # spacja otwierająca dalszy ciąg wlicza się do limitu
        biezacy += znak
        oktety += rozmiar
    fizyczne.append(biezacy)
    return fizyczne


def _dzien(dzien: date) -> str:
    return f"{dzien:%Y%m%d}"


def _znacznik_czasu(chwila: datetime) -> str:
    """DTSTAMP w czasie UTC (RFC 5545 pkt 3.8.7.2); chwila bez strefy jest traktowana jako UTC."""
    if chwila.tzinfo is not None:
        chwila = chwila.astimezone(timezone.utc)
    return f"{chwila:%Y%m%dT%H%M%S}Z"


def _wyzwalacz(dni_przed: int) -> str:
    """TRIGGER względem początku wydarzenia: `-P30D` = 30 dni wcześniej, `PT0S` = w dniu terminu."""
    return f"-P{dni_przed}D" if dni_przed > 0 else "PT0S"


def kalendarz_ics(
    wydarzenia: Iterable[Wydarzenie], *, wytworzono: datetime, przepisy: Przepisy | None = None
) -> str:
    """Kalendarz iCalendar (RFC 5545) z wydarzeniami całodniowymi, w kolejności podanej przez wywołującego.

    - `wytworzono` trafia do DTSTAMP (w UTC) - ten sam zestaw argumentów daje ten sam wynik;
    - każde wydarzenie dostaje przypomnienia VALARM z wyprzedzeniami `przypomnienia_dni_przed` z przepisów;
      przypomnienie, którego dzień minął przed dniem `wytworzono`, jest pomijane;
    - brak wydarzeń, pusty albo powtórzony identyfikator -> ValueError (obiekt iCalendar musi mieć co najmniej
      jeden składnik, a UID ma być unikalny).

    Wynik to tekst z wierszami zakończonymi CRLF; do pliku należy go zapisać w UTF-8 bez zmiany końców wierszy.
    """
    przepisy = _ustal_przepisy(przepisy)
    wydarzenia = list(wydarzenia)
    if not wydarzenia:
        raise ValueError("Kalendarz iCalendar musi zawierać co najmniej jedno wydarzenie")
    identyfikatory = [str(wydarzenie.uid).strip() for wydarzenie in wydarzenia]
    if not all(identyfikatory):
        raise ValueError("Każde wydarzenie musi mieć niepusty identyfikator (UID)")
    if len(set(identyfikatory)) != len(identyfikatory):
        raise ValueError("Identyfikatory wydarzeń (UID) muszą być różne")

    znacznik = _znacznik_czasu(wytworzono)
    dzien_wytworzenia = wytworzono.date()
    wyprzedzenia = sorted(set(przepisy.przypomnienia_dni_przed), reverse=True)

    wiersze = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{_tekst(PRODID)}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for wydarzenie, uid in zip(wydarzenia, identyfikatory):
        tytul = _tekst(wydarzenie.tytul)
        wiersze += [
            "BEGIN:VEVENT",
            f"UID:{_tekst(uid)}",
            f"DTSTAMP:{znacznik}",
            f"DTSTART;VALUE=DATE:{_dzien(wydarzenie.data)}",
            f"DTEND;VALUE=DATE:{_dzien(wydarzenie.data + timedelta(days=1))}",
            f"SUMMARY:{tytul}",
        ]
        if str(wydarzenie.opis).strip():
            wiersze.append(f"DESCRIPTION:{_tekst(wydarzenie.opis)}")
        wiersze.append("TRANSP:TRANSPARENT")  # termin nie blokuje czasu w kalendarzu
        for dni_przed in wyprzedzenia:
            if wydarzenie.data - timedelta(days=dni_przed) < dzien_wytworzenia:
                continue
            wiersze += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{tytul}",
                f"TRIGGER:{_wyzwalacz(dni_przed)}",
                "END:VALARM",
            ]
        wiersze.append("END:VEVENT")
    wiersze.append("END:VCALENDAR")
    return "".join(f"{fizyczny}\r\n" for wiersz in wiersze for fizyczny in _zlam(wiersz))


# === Terminy procesu ===

def wydarzenia_procesu(
    proces: ProcesOceny,
    *,
    kto: str,
    identyfikator: str,
    po_negatywnej: bool = False,
    nieobecnosci: Iterable[Nieobecnosc] = (),
    przepisy: Przepisy | None = None,
) -> list[Wydarzenie]:
    """Terminy, które biegną na obecnym etapie procesu, chronologicznie.

    - kryteria niepotwierdzone przez ocenianego: termin rozmowy i zapoznania z kryteriami (§ 7 rozp.;
      `po_negatywnej` wybiera termin po ocenie negatywnej);
    - ocena niesporządzona: termin sporządzenia oceny - wpisany w części I arkusza (`proces.termin`), a gdy go
      jeszcze nie ma, ustawowy (art. 81 ust. 4 i 7 u.s.c., z `nieobecnosci`); opis podaje zawsze termin ustawowy;
    - po zapoznaniu z oceną: koniec terminu na sprzeciw (art. 83 ust. 1 u.s.c.), a po ocenie negatywnej także
      dzień ponownej oceny (art. 81 ust. 9 u.s.c.).

    `kto` - oznaczenie ocenianego w tytułach (jedyne dane osobowe w wydarzeniach); `identyfikator` - stały
    identyfikator oceny, z którego powstają UID (pusty -> ValueError). Przepisy: podane, potem procesu, potem
    domyślne. Między sporządzeniem oceny a zapoznaniem lista jest pusta (zapoznanie następuje „niezwłocznie”).
    """
    identyfikator = str(identyfikator).strip()
    if not identyfikator:
        raise ValueError("Podaj identyfikator oceny - powstają z niego identyfikatory wydarzeń (UID)")
    przepisy = przepisy if przepisy is not None else _ustal_przepisy(proces.przepisy)
    kto = str(kto).strip()

    def wydarzenie(kod: str, dzien: date, tytul: str, opis: str, podstawa: str) -> Wydarzenie:
        return Wydarzenie(
            uid=f"{identyfikator}-{kod}@{DOMENA_UID}",
            data=dzien,
            tytul=f"{tytul} - {kto}" if kto else tytul,
            opis=f"{opis}\nPodstawa prawna: {podstawa}.",
        )

    wydarzenia: list[Wydarzenie] = []
    if proces.data_zapoznania_z_kryteriami is None and proces.ponowne_kryteria_do is not None:
        wydarzenia.append(wydarzenie(
            "kryteria",
            proces.ponowne_kryteria_do,
            "Kryteria oceny okresowej po zmianie stanowiska",
            "Ostatni dzień na ponowną rozmowę z ocenianym i zapoznanie go z kryteriami po zmianie stanowiska pracy "
            f"({_dzien_slownie(proces.zmiana_stanowiska)}). Termin sporządzenia oceny nie ulega zmianie.",
            f"§ 9 ust. 1 {_ROZPORZADZENIE}; {_KODEKS}",
        ))
    elif proces.data_zapoznania_z_kryteriami is None:
        dni = przepisy.termin_kryteriow_po_negatywnej_dni if po_negatywnej else przepisy.termin_kryteriow_dni
        wydarzenia.append(wydarzenie(
            "kryteria",
            termin_wyznaczenia_kryteriow(proces.poczatek_cyklu, po_negatywnej, przepisy),
            "Kryteria oceny okresowej",
            "Ostatni dzień na rozmowę z ocenianym, wpisanie kryteriów dodatkowych i terminu oceny do części I "
            f"arkusza oraz potwierdzenie zapoznania przez ocenianego ({dni} dni od {_dzien_slownie(proces.poczatek_cyklu)}).",
            f"§ 7 pkt {2 if po_negatywnej else 1} w zw. z § 5 i § 6 {_ROZPORZADZENIE}; {_KODEKS}",
        ))
    if proces.data_sporzadzenia is None:
        ustawowy = termin_oceny(proces.poczatek_cyklu, nieobecnosci, przepisy)
        opis_ustawowego = (
            f"Termin ustawowy: {_dzien_slownie(ustawowy)} ({przepisy.cykl_oceny_miesiace} mies. od "
            f"{_dzien_slownie(proces.poczatek_cyklu)}, z przedłużeniem o usprawiedliwione nieobecności dłuższe niż "
            f"{przepisy.prog_nieobecnosci_miesiace} mies.)."
        )
        if proces.ocena_najwczesniej is not None and proces.termin is not None:
            opis = (
                "Ostatni dzień na sporządzenie oceny w związku ze zmianą stanowiska pracy "
                f"({_dzien_slownie(proces.zmiana_stanowiska)}); nie wcześniej niż {_dzien_slownie(proces.ocena_najwczesniej)}. "
                "Przed sporządzeniem oceny przeprowadza się rozmowę oceniającą."
            )
            podstawa = f"art. 81 ust. 6 {_USTAWA}; § 9 ust. 2 i § 10 {_ROZPORZADZENIE}"
        elif proces.termin is not None:
            opis = (
                "Termin sporządzenia oceny na piśmie wpisany w części I arkusza. Przed sporządzeniem oceny "
                f"przeprowadza się rozmowę oceniającą. {opis_ustawowego}"
            )
            podstawa = f"§ 5 ust. 3, § 8 i § 10 {_ROZPORZADZENIE}; art. 81 ust. 4, 7 i 8 {_USTAWA}"
        else:
            opis = (
                "Termin sporządzenia oceny okresowej na piśmie. Przed sporządzeniem oceny przeprowadza się "
                f"rozmowę oceniającą. {opis_ustawowego}"
            )
            podstawa = f"art. 81 ust. 4 i 7 {_USTAWA}; § 10 {_ROZPORZADZENIE}"
        wydarzenia.append(wydarzenie(
            "termin-oceny", proces.termin or ustawowy, "Termin sporządzenia oceny okresowej", opis, podstawa
        ))
    if proces.data_zapoznania_z_ocena is not None:
        zapoznanie = proces.data_zapoznania_z_ocena
        wydarzenia.append(wydarzenie(
            "sprzeciw",
            termin_sprzeciwu(zapoznanie, przepisy),
            "Koniec terminu na sprzeciw od oceny okresowej",
            f"Ostatni dzień na wniesienie sprzeciwu od oceny okresowej ({przepisy.sprzeciw_dni} dni od dnia "
            f"zapoznania się z oceną: {_dzien_slownie(zapoznanie)}).",
            f"art. 83 ust. 1 {_USTAWA}; {_KODEKS}",
        ))
        if proces.wynik is not None and proces.wynik.ocena == NEGATYWNA:
            wydarzenia.append(wydarzenie(
                "ponowna-ocena",
                data_ponownej_oceny_po_negatywnej(zapoznanie, przepisy=przepisy),
                "Ponowna ocena okresowa",
                f"Pierwszy dzień, w którym przypada ponowna ocena okresowa - po upływie "
                f"{przepisy.ponowna_ocena_po_negatywnej_miesiace} mies. od dnia zapoznania się z oceną "
                f"({_dzien_slownie(zapoznanie)}).",
                f"art. 81 ust. 9 {_USTAWA}",
            ))
    return sorted(wydarzenia, key=lambda w: (w.data, w.uid))


def _dzien_slownie(dzien: date) -> str:
    return f"{dzien:%d.%m.%Y}"
