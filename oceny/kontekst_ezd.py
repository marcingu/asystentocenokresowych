"""Karta kontekstu z EZD RP: fakty o sprawach ocenianego za okres podlegający ocenie.

Karta pokazuje liczby i terminowość - bez punktów, oceny zbiorczej i rankingów. Widzą ją obie strony oceny.
Zanim cokolwiek pokaże, sprawdza warunki Kodeksu pracy (art. 22[2] § 6-8 w zw. z art. 22[3] § 3-4):
ustalenia pracodawcy, poinformowanie pracowników z wyprzedzeniem i informację dla ocenianego.
Wskaźniki liczy rdzeń (`asystent_ocen.wskazniki_pracy`) jawnymi regułami; model językowy nie ma do nich dostępu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.conf import settings

from asystent_ocen.bledy import Blad
from asystent_ocen.wskazniki_pracy import formatuj_wskaznik, wskazniki_pracy
from asystent_ocen.zgodnosc import UstaleniaMonitoringu as UstaleniaRdzenia
from asystent_ocen.zgodnosc import bledy_uruchomienia_monitoringu

from . import ezd_przyklad
from .models import Ocena, UstaleniaMonitoringu

WYLACZONA = "WYLACZONA"
ZABLOKOWANA = "ZABLOKOWANA"
PRZED_OKRESEM = "PRZED_OKRESEM"
BRAK_ZRODLA = "BRAK_ZRODLA"
GOTOWA = "GOTOWA"

PODSTAWA_INFORMACJI_DLA_PRACOWNIKA = "art. 22[2] § 8 w zw. z art. 22[3] § 3 i 4 KP"


@dataclass(frozen=True)
class KartaKontekstu:
    stan: str
    komunikat: str = ""
    przeszkody: tuple[Blad, ...] = ()
    od: date | None = None
    do: date | None = None
    wskazniki: tuple[dict, ...] = ()
    dane_przykladowe: bool = False
    podstawa: str = ""
    poinformowano: date | None = None


def ustalenia_rdzenia(zapis: UstaleniaMonitoringu) -> UstaleniaRdzenia:
    return UstaleniaRdzenia(
        podstawa=zapis.podstawa, cele=zapis.cele, zakres=zapis.zakres, sposob=zapis.sposob,
        data_poinformowania=zapis.data_poinformowania,
    )


def _dane_zrodlowe(identyfikator: str, od: date, do: date):
    """Sprawy, akceptacje i odwołania stanowiska oraz znacznik „dane przykładowe”; None - brak źródła."""
    if settings.ASYSTENT_EZD_ADRES:
        # Klient Integrator API (asystent_ocen.ezdrp) jest gotowy i przetestowany na atrapie; podłączenie do
        # instancji urzędu wymaga jej adresu, tokenu i mapowania rejestru odwołań - poza zakresem prototypu.
        return None
    if settings.ASYSTENT_TRYB_DEMO:
        return (*ezd_przyklad.dane_przykladowe(identyfikator, od, do), True)
    return None


def integracja_wlaczona() -> bool:
    """Czy komórka kadr włączyła integrację z EZD RP (po ustaleniach wymaganych przez Kodeks pracy)."""
    return UstaleniaMonitoringu.pobierz().integracja_wlaczona


def przeszkody_monitoringu(ocena: Ocena, dzien: date) -> tuple[UstaleniaMonitoringu, list[Blad]]:
    """Ustalenia pracodawcy i przeszkody z Kodeksu pracy, które nie pozwalają pokazać danych o pracy tej osoby.
    Z tej samej bramki korzystają karta kontekstu z EZD RP i Radar Dobrostanu i Doceniania."""
    zapis = UstaleniaMonitoringu.pobierz()
    przeszkody = bledy_uruchomienia_monitoringu(ustalenia_rdzenia(zapis), dzien)
    if not przeszkody and not ocena.oceniany.klauzula_ezd_potwierdzona:
        przeszkody = [Blad(
            "BRAK_INFORMACJI_DLA_PRACOWNIKA",
            "Ocenianemu nie przekazano informacji o celach, zakresie i sposobie korzystania z danych z EZD RP.",
            PODSTAWA_INFORMACJI_DLA_PRACOWNIKA,
        )]
    return zapis, przeszkody


def karta_kontekstu(ocena: Ocena, dzien: date) -> KartaKontekstu:
    zapis, przeszkody = przeszkody_monitoringu(ocena, dzien)
    if not zapis.integracja_wlaczona:
        return KartaKontekstu(
            WYLACZONA,
            "Integracja z EZD RP jest wyłączona. Włącza ją komórka kadr po dokonaniu ustaleń wymaganych przez "
            "Kodeks pracy.",
        )
    if przeszkody:
        return KartaKontekstu(
            ZABLOKOWANA, "Dane z EZD RP nie są pokazywane, dopóki nie zostaną spełnione warunki Kodeksu pracy.",
            przeszkody=tuple(przeszkody),
        )
    proces = ocena.proces()
    if proces.data_zapoznania_z_kryteriami is None:
        return KartaKontekstu(
            PRZED_OKRESEM,
            "Karta obejmuje okres podlegający ocenie - pojawi się po zapoznaniu ocenianego z kryteriami oceny.",
        )
    od = proces.data_zapoznania_z_kryteriami
    do = proces.data_sporzadzenia or dzien
    if do < od:
        do = od
    zrodlo = _dane_zrodlowe(ocena.oceniany.identyfikator_ezd, od, do)
    if zrodlo is None:
        if settings.ASYSTENT_EZD_ADRES:
            komunikat = (
                "Adres EZD RP jest ustawiony, ale ta wersja prototypu nie pobiera jeszcze danych z instancji urzędu. "
                "Klient Integrator API jest gotowy - podłączenie wymaga tokenu i mapowania rejestru odwołań."
            )
        else:
            komunikat = "Połączenie z EZD RP nie jest skonfigurowane - karta nie ma skąd pobrać danych."
        return KartaKontekstu(BRAK_ZRODLA, komunikat, od=od, do=do)
    sprawy, akceptacje, odwolania, przykladowe = zrodlo
    wskazniki = tuple(
        {
            "kod": wskaznik.kod,
            "nazwa": wskaznik.nazwa,
            "wartosc": formatuj_wskaznik(wskaznik),
            "liczba": wskaznik.wartosc,
            "jednostka": wskaznik.jednostka,
            "licznosc": wskaznik.licznosc,
            "uwaga": wskaznik.uwaga or "",
            "szczegoly": tuple(wskaznik.szczegoly),
        }
        for wskaznik in wskazniki_pracy(sprawy=sprawy, akceptacje=akceptacje, odwolania=odwolania, od=od, do=do)
    )
    return KartaKontekstu(
        GOTOWA, od=od, do=do, wskazniki=wskazniki, dane_przykladowe=przykladowe, podstawa=zapis.podstawa,
        poinformowano=zapis.data_poinformowania,
    )
