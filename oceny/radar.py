"""Radar Dobrostanu i Doceniania na karcie oceny: karty obserwacji dla pracownika i jego przełożonego.

Karty liczy rdzeń (`asystent_ocen.radar`) jawnymi regułami z liczb z systemu kadrowego i EZD RP - bez punktów,
rankingu i wniosków o zdrowiu albo emocjach. Zanim radar cokolwiek pokaże, sprawdza te same warunki Kodeksu
pracy co karta kontekstu z EZD RP (art. 22[2] § 6-8 w zw. z art. 22[3] § 3-4): ustalenia pracodawcy,
poinformowanie pracowników z wyprzedzeniem i informację dla ocenianego. Karty widzą obie strony oceny.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.conf import settings

from asystent_ocen.bledy import Blad
from asystent_ocen.partner_hr import CEL, STANDARDY, ZASADY, Sygnal, sygnaly
from asystent_ocen.radar import DOBROSTAN, DOCENIENIE, DaneRadaru, KartaObserwacji, karty_obserwacji

from . import radar_przyklad
from .kontekst_ezd import przeszkody_monitoringu
from .models import Ocena

WYLACZONY = "WYLACZONY"
ZABLOKOWANY = "ZABLOKOWANY"
BRAK_ZRODLA = "BRAK_ZRODLA"
GOTOWY = "GOTOWY"


@dataclass(frozen=True)
class Radar:
    stan: str
    komunikat: str = ""
    przeszkody: tuple[Blad, ...] = ()
    stan_na: date | None = None
    karty: tuple[KartaObserwacji, ...] = ()
    dane_przykladowe: bool = False
    podstawa: str = ""
    poinformowano: date | None = None

    @property
    def dobrostan(self) -> tuple[KartaObserwacji, ...]:
        return tuple(karta for karta in self.karty if karta.rodzaj == DOBROSTAN)

    @property
    def docenienie(self) -> tuple[KartaObserwacji, ...]:
        return tuple(karta for karta in self.karty if karta.rodzaj == DOCENIENIE)

    # Jawne zasady partnera HR i pełna nazwa Standardów - pokazywane obu stronom obok sygnałów.
    cel_partnera = CEL
    zasady_partnera = ZASADY
    standardy_zzl = STANDARDY

    @property
    def partner(self) -> tuple[Sygnal, ...]:
        """Partner HR: obraz sytuacji i działania do rozmowy - zwykły kod na kartach, tylko gdy radar ma dane."""
        return sygnaly(self.karty) if self.stan == GOTOWY else ()


def _dane_zrodlowe(identyfikator: str, dzien: date) -> DaneRadaru | None:
    """Liczby z systemu kadrowego i EZD RP; None - brak źródła. Prototyp nie ma połączenia z systemem kadrowym,
    więc poza trybem demonstracyjnym radar nie pokazuje niczego - nie zmyśla danych."""
    if settings.ASYSTENT_TRYB_DEMO and not settings.ASYSTENT_EZD_ADRES:
        return radar_przyklad.dane_przykladowe(identyfikator, dzien)
    return None


def radar_oceny(ocena: Ocena, dzien: date) -> Radar:
    zapis, przeszkody = przeszkody_monitoringu(ocena, dzien)
    if not zapis.integracja_wlaczona:
        return Radar(
            WYLACZONY,
            "Radar jest wyłączony. Włącza go komórka kadr razem z integracją z EZD RP, po dokonaniu ustaleń "
            "wymaganych przez Kodeks pracy.",
        )
    if przeszkody:
        return Radar(
            ZABLOKOWANY, "Radar nie pokazuje danych, dopóki nie zostaną spełnione warunki Kodeksu pracy.",
            przeszkody=tuple(przeszkody),
        )
    dane = _dane_zrodlowe(ocena.oceniany.identyfikator_ezd, dzien)
    if dane is None:
        return Radar(
            BRAK_ZRODLA,
            "Połączenie z systemem kadrowym i EZD RP nie jest skonfigurowane - radar nie ma skąd pobrać danych.",
            stan_na=dzien,
        )
    return Radar(
        GOTOWY, stan_na=dzien, karty=karty_obserwacji(dane), dane_przykladowe=True, podstawa=zapis.podstawa,
        poinformowano=zapis.data_poinformowania,
    )
