"""Symulacja oceny dla pracownika: własne przewidywanie ocen cząstkowych i wskazania z faktów z EZD RP.

Symulacja dotyczy wyłącznie zalogowanej osoby, niczego nie zapisuje i nie jest dostępna dla przełożonego ani
kadr. To przypuszczenie: ocenę wystawia przełożony na podstawie wszystkich informacji, także spoza EZD RP.
Dane z EZD RP przechodzą przez tę samą bramkę co karta kontekstu (warunki Kodeksu pracy), a wynik liczy rdzeń
według § 11 rozp. - tak samo jak przy prawdziwej ocenie.
"""

from __future__ import annotations

from datetime import date

from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.kryteria import kryteria_obowiazkowe
from asystent_ocen.symulacja import wczytaj_ustawienia, wskazania_z_ezd
from asystent_ocen.wynik import NEGATYWNA, formatuj_srednia, oblicz_wynik

from .formularze import nazwy_kryteriow
from .karta import skala_ocen
from .kontekst_ezd import GOTOWA, karta_kontekstu
from .models import Pracownik


def _poziom_oczekiwan() -> int:
    """Ocena cząstkowa „na poziomie oczekiwań” - najniższa z poziomów pozytywnych; od niej startują kryteria,
    o których system nic nie wie."""
    przepisy = wczytaj_przepisy()
    return next(punkty for punkty, poziom in zip(przepisy.skala, przepisy.poziomy) if poziom.pozytywny)


def _dane_z_ezd(ocena, kryteria: list[str], dzien: date) -> dict:
    """Wskazania z faktów EZD RP dla kryteriów ocenianego albo powód, dla którego symulacja z nich nie korzysta."""
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


def dane_symulacji(pracownik: Pracownik, wybrane, dzien: date) -> dict:
    """Dane strony symulacji. `wybrane` to formularz z polami `ocena_<numer wiersza>` albo None przy wejściu."""
    kontekst: dict = {"pracownik": pracownik, "podlega": pracownik.podlega_ocenie, "kryteria": [], "wynik": None}
    kontekst["ezd"] = {"wskazania": [], "powod": "", "przeszkody": ()}
    if not pracownik.podlega_ocenie:
        return kontekst

    przepisy = wczytaj_przepisy()
    ocena = pracownik.biezaca_ocena()
    proces = ocena.proces() if ocena is not None else None
    w_toku = proces is not None and proces.wynik is None
    obowiazkowe = kryteria_obowiazkowe(pracownik.arkusz)
    kryteria = nazwy_kryteriow(proces) if w_toku else list(obowiazkowe)
    if w_toku:
        kontekst["ezd"] = _dane_z_ezd(ocena, kryteria, dzien)
    elif proces is None:
        kontekst["ezd"]["powod"] = "Twój cykl oceny jeszcze się nie rozpoczął, więc nie ma okresu, za który można zestawić fakty."
    else:
        kontekst["ezd"]["powod"] = "Fakty za kolejny okres oceny dopiero się zbiorą."
    z_ezd = {wskazanie["kryterium"]: wskazanie["ocena"] for wskazanie in kontekst["ezd"]["wskazania"]}

    domyslna = _poziom_oczekiwan()
    wiersze = []
    for numer, nazwa in enumerate(kryteria):
        podana = (wybrane.get(f"ocena_{numer}") or "") if wybrane is not None else ""
        wartosc = int(podana) if podana.isdigit() and int(podana) in przepisy.skala else z_ezd.get(nazwa, domyslna)
        wiersze.append({
            "numer": numer, "nazwa": nazwa, "obowiazkowe": nazwa in obowiazkowe, "wartosc": wartosc,
            "z_ezd": z_ezd.get(nazwa),
        })
    wynik = oblicz_wynik({wiersz["nazwa"]: wiersz["wartosc"] for wiersz in wiersze})
    wykluczajaca = przepisy.ocena_czastkowa_wykluczajaca_pozytywna
    kontekst.update({
        "kryteria": wiersze,
        "skala": skala_ocen(),
        "wynik": {
            "srednia": formatuj_srednia(wynik.srednia),
            "poziom": wynik.poziom,
            "ocena": wynik.ocena,
            "negatywna": wynik.ocena == NEGATYWNA,
            "wyklucza": wykluczajaca if any(wiersz["wartosc"] == wykluczajaca for wiersz in wiersze) else None,
        },
        "ocena": ocena if w_toku else None,
        "ocena_sporzadzona": proces is not None and not w_toku,
        "przeliczono": wybrane is not None,
        "progi": [{"ocena": punkty, "prog": prog} for punkty, prog in wczytaj_ustawienia().progi],
        "najnizsza": min(przepisy.skala),
        "liczba_z_danymi": len(z_ezd),
    })
    return kontekst
