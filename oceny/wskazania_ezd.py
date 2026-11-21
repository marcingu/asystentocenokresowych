"""Moje dane z EZD RP: na jaki poziom w kryteriach pracownika wskazują fakty z EZD RP.

Strona dotyczy wyłącznie zalogowanej osoby, niczego nie zapisuje i nie jest dostępna dla przełożonego ani kadr.
To przypuszczenie: ocenę wystawia przełożony na podstawie wszystkich informacji, także spoza EZD RP. Dane z EZD RP
przechodzą przez tę samą bramkę co karta kontekstu (warunki Kodeksu pracy). Przy wyłączonej integracji z EZD RP
strona nie ma czego pokazać - nie zbiera własnych przewidywań pracownika.
"""

from __future__ import annotations

from datetime import date

from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.symulacja import wczytaj_ustawienia, wskazania_z_ezd

from .formularze import nazwy_kryteriow
from .karta import skala_ocen
from .kontekst_ezd import GOTOWA, integracja_wlaczona, karta_kontekstu
from .models import Pracownik


def _dane_z_ezd(ocena, kryteria: list[str], dzien: date) -> dict:
    """Wskazania z faktów EZD RP dla kryteriów ocenianego albo powód, dla którego strona ich nie pokazuje."""
    karta = karta_kontekstu(ocena, dzien)
    if karta.stan != GOTOWA:
        return {"wskazania": [], "powod": karta.komunikat, "przeszkody": karta.przeszkody}
    fakty = {wskaznik["kod"]: wskaznik for wskaznik in karta.wskazniki if wskaznik["jednostka"] == "%"}
    udzialy = {kod: wskaznik["liczba"] for kod, wskaznik in fakty.items()}
    nazwy_skali = {pozycja["punkty"]: pozycja["nazwa"] for pozycja in skala_ocen()}
    wskazania = [
        {
            "kryterium": wskazanie.kryterium,
            "ocena": wskazanie.ocena,
            "poziom": nazwy_skali[wskazanie.ocena],
            "uzasadnienie": wskazanie.uzasadnienie,
            "fakty": [
                {
                    "nazwa": fakty[skladnik.kod]["nazwa"],
                    "wartosc": fakty[skladnik.kod]["wartosc"],
                    "licznosc": fakty[skladnik.kod]["licznosc"],
                    "ocena": skladnik.ocena,
                    "poziom": nazwy_skali[skladnik.ocena],
                }
                for skladnik in wskazanie.skladniki
            ],
        }
        for wskazanie in wskazania_z_ezd(kryteria, udzialy)
    ]
    return {
        "wskazania": wskazania, "powod": "", "przeszkody": (), "od": karta.od, "do": karta.do,
        "dane_przykladowe": karta.dane_przykladowe,
    }


def dane_wskazan(pracownik: Pracownik, dzien: date) -> dict:
    """Dane strony „Moje dane z EZD RP” dla jednej osoby."""
    kontekst: dict = {
        "pracownik": pracownik, "podlega": pracownik.podlega_ocenie, "integracja": integracja_wlaczona(),
        "ezd": {"wskazania": [], "powod": "", "przeszkody": ()}, "kryteria": [], "liczba_z_danymi": 0,
    }
    if not kontekst["podlega"] or not kontekst["integracja"]:
        return kontekst

    przepisy = wczytaj_przepisy()
    ocena = pracownik.biezaca_ocena()
    proces = ocena.proces() if ocena is not None else None
    if proces is None:
        kontekst["ezd"]["powod"] = "Twój cykl oceny jeszcze się nie rozpoczął, więc nie ma okresu, za który można zestawić fakty."
    elif proces.wynik is not None:
        kontekst["ezd"]["powod"] = "Ocena za bieżący okres jest już sporządzona. Fakty za kolejny okres dopiero się zbiorą."
    else:
        kontekst["kryteria"] = nazwy_kryteriow(proces)
        kontekst["ezd"] = _dane_z_ezd(ocena, kontekst["kryteria"], dzien)
    kontekst.update({
        "liczba_z_danymi": len(kontekst["ezd"]["wskazania"]),
        "progi": [{"ocena": punkty, "prog": prog} for punkty, prog in wczytaj_ustawienia().progi],
        "najnizsza": min(przepisy.skala),
    })
    return kontekst
