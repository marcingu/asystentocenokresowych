"""Polecenie `manage.py demo` - ładuje dane demonstracyjne do pustej bazy.

Polecenie niczego nie usuwa. Konta pokazowe nie mają haseł - wejść na nie można tylko w trybie
demonstracyjnym (ASYSTENT_TRYB_DEMO=1).
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from asystent_ocen.bledy import BladWalidacji
from asystent_ocen.przebieg import BladEtapu, BladUprawnien
from oceny import dane_demo
from oceny.czas import dzis
from oceny.models import Ocena, Pracownik


class Command(BaseCommand):
    help = "Ładuje dane demonstracyjne (fikcyjny urząd z ocenami na każdym etapie) do pustej bazy."

    def add_arguments(self, parser):
        parser.add_argument("--dzis", help="Data odniesienia RRRR-MM-DD (domyślnie dzisiejsza).")

    def handle(self, *args, **opcje):
        try:
            dzien = date.fromisoformat(opcje["dzis"]) if opcje.get("dzis") else dzis()
        except ValueError:
            raise CommandError("Opcja --dzis wymaga daty w postaci RRRR-MM-DD.") from None
        if get_user_model().objects.exists() or Pracownik.objects.exists():
            raise CommandError(
                "Baza zawiera już dane. Dane demonstracyjne ładuje się wyłącznie do pustej bazy - "
                "to polecenie niczego nie usuwa. Wskaż inną bazę zmienną ASYSTENT_BAZA."
            )
        try:
            osoby = dane_demo.zaladuj(dzien)
        except (BladWalidacji, BladEtapu, BladUprawnien) as blad:
            raise CommandError(f"Dane demonstracyjne nie przeszły reguł systemu: {blad}") from blad
        if opcje.get("verbosity", 1):
            self.stdout.write(self.style.SUCCESS(
                f"Załadowano dane demonstracyjne na dzień {dzien:%d.%m.%Y}: "
                f"{len(osoby)} osób, {Ocena.objects.count()} ocen."
            ))
            self.stdout.write("Konta pokazowe: " + ", ".join(sorted(osoby)))
