"""Lista pracowników dla komórki kadr: wyszukiwanie, filtry i sortowanie.

Lista urzędu liczy setki albo tysiące osób, więc kadry muszą umieć zawęzić ją do komórki organizacyjnej,
etapu oceny albo nazwiska. Wszystko dzieje się po stronie serwera - adres z filtrami można zapisać w zakładkach.
"""

from __future__ import annotations

import unicodedata
from datetime import date

from asystent_ocen.przebieg import Etap

from .models import Pracownik

PO_TERMINIE = "po_terminie"
BEZ_OCENY = "bez_oceny"
NIE_PODLEGA = "nie_podlega"

STATUSY = (
    *((etap.name, etap.value) for etap in Etap),
    (PO_TERMINIE, "po terminie sporządzenia oceny"),
    (BEZ_OCENY, "cykl oceny nierozpoczęty"),
    (NIE_PODLEGA, "nie podlega ocenie"),
)
SORTOWANIA = (
    ("nazwisko", "nazwisko"),
    ("komorka", "komórka organizacyjna"),
    ("termin", "termin oceny (najbliższe na początku)"),
)

_ALFABET = "aąbcćdeęfghijklłmnńoópqrsśtuvwxyzźż"
_MIEJSCE_W_ALFABECIE = {znak: numer for numer, znak in enumerate(_ALFABET)}


def klucz_alfabetyczny(tekst: str) -> list[tuple[int, int]]:
    """Klucz sortowania według polskiego alfabetu - baza danych ustawia „Ł” i „Ś” za „Z”."""
    return [
        (1, _MIEJSCE_W_ALFABECIE[znak]) if znak in _MIEJSCE_W_ALFABECIE else (2 if znak.isalpha() else 0, ord(znak))
        for znak in tekst.casefold()
    ]


def bez_ogonkow(tekst: str) -> str:
    """Postać do porównań przy wyszukiwaniu: małe litery bez znaków diakrytycznych („Zielińska” = „zielinska”)."""
    rozlozony = unicodedata.normalize("NFKD", tekst.casefold().replace("ł", "l"))
    return "".join(znak for znak in rozlozony if not unicodedata.combining(znak))


def _status(wiersz: dict) -> str:
    if not wiersz["osoba"].podlega_ocenie:
        return NIE_PODLEGA
    if wiersz["ocena"] is None:
        return BEZ_OCENY
    return wiersz["ocena"].etap


def wiersze_pracownikow(dzien: date) -> list[dict]:
    wiersze = []
    osoby = Pracownik.objects.select_related("przelozony", "wydzial", "umowa__pierwsza").prefetch_related("oceny", "nieobecnosci")
    for osoba in osoby:
        biezaca = max(osoba.oceny.all(), key=lambda ocena: (ocena.poczatek_cyklu, ocena.pk), default=None)
        wiersz = {
            "osoba": osoba,
            "ocena": biezaca,
            "po_terminie": bool(biezaca and biezaca.termin and not biezaca.zakonczona and biezaca.termin < dzien),
            "mozna_rozpoczac": osoba.podlega_ocenie and biezaca is None,
            "nieobecnosci": list(osoba.nieobecnosci.all()),
        }
        wiersz["status"] = _status(wiersz)
        wiersze.append(wiersz)
    return wiersze


def _pasuje(wiersz: dict, slowa: list[str], komorka: str, status: str) -> bool:
    osoba = wiersz["osoba"]
    if komorka and osoba.komorka != komorka:
        return False
    if status == PO_TERMINIE:
        if not wiersz["po_terminie"]:
            return False
    elif status and wiersz["status"] != status:
        return False
    opis = bez_ogonkow(f"{osoba.imie} {osoba.nazwisko} {osoba.stanowisko} {osoba.komorka}")
    return all(slowo in opis for slowo in slowa)


def _klucz_sortowania(sortowanie: str):
    def nazwisko(wiersz: dict) -> tuple:
        return klucz_alfabetyczny(wiersz["osoba"].nazwisko), klucz_alfabetyczny(wiersz["osoba"].imie)

    if sortowanie == "komorka":
        return lambda wiersz: (klucz_alfabetyczny(wiersz["osoba"].komorka), *nazwisko(wiersz))
    if sortowanie == "termin":
        # Najpierw oceny w toku z terminem, od najbliższego; osoby bez biegnącego terminu na końcu.
        def termin(wiersz: dict) -> tuple:
            ocena = wiersz["ocena"]
            biegnie = bool(ocena and ocena.termin and not ocena.zakonczona)
            return (0, ocena.termin.toordinal()) if biegnie else (1, 0)

        return lambda wiersz: (*termin(wiersz), *nazwisko(wiersz))
    return nazwisko


def lista_pracownikow(zapytanie, dzien: date) -> dict:
    """Dane strony kadr dla parametrów z adresu: `q`, `komorka`, `status`, `sort`. Nieznane wartości są pomijane."""
    wszystkie = wiersze_pracownikow(dzien)
    komorki = sorted({wiersz["osoba"].komorka for wiersz in wszystkie if wiersz["osoba"].komorka}, key=klucz_alfabetyczny)
    szukane = " ".join(zapytanie.get("q", "").split())[:100]
    komorka = zapytanie.get("komorka", "")
    komorka = komorka if komorka in komorki else ""
    status = zapytanie.get("status", "")
    status = status if status in dict(STATUSY) else ""
    sortowanie = zapytanie.get("sort", "")
    sortowanie = sortowanie if sortowanie in dict(SORTOWANIA) else SORTOWANIA[0][0]

    slowa = bez_ogonkow(szukane).split()
    wybrane = [wiersz for wiersz in wszystkie if _pasuje(wiersz, slowa, komorka, status)]
    wybrane.sort(key=_klucz_sortowania(sortowanie))
    return {
        "wiersze": wybrane,
        "wszystkich": len(wszystkie),
        "filtry": {"q": szukane, "komorka": komorka, "status": status, "sort": sortowanie},
        "filtrowanie_aktywne": bool(szukane or komorka or status),
        "komorki": komorki,
        "statusy": STATUSY,
        "sortowania": SORTOWANIA,
    }
