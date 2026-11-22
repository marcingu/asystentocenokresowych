"""Uzgodnienie danych przy imporcie kart i po aktualizacji aplikacji: brakujące cykle i terminy ocen."""
from django.core.management.base import BaseCommand
from django.db import transaction

from oceny import uslugi
from oceny.cykle import uzgodnij
from oceny.models import Pracownik


class Command(BaseCommand):
    help = ("Otwiera brakujące oceny okresowe na podstawie kompletnych kart (nie zakłada pierwszych umów) i przedłuża "
            "terminy trwających ocen o usprawiedliwione nieobecności dłuższe niż miesiąc (art. 81 ust. 7 u.s.c.). "
            "Można uruchamiać wielokrotnie.")

    def handle(self, *args, **options):
        osoby = list(Pracownik.objects.values_list("pk", flat=True))
        cykle = sum(uzgodnij(pk) is not None for pk in osoby)
        przedluzone = 0
        for osoba in Pracownik.objects.filter(nieobecnosci__isnull=False).distinct():
            with transaction.atomic():
                przedluzone += len(uslugi.przedluz_terminy_o_nieobecnosci(osoba, None))
        self.stdout.write(f"Nowe cykle: {cykle}. Terminy przedłużone o nieobecności: {przedluzone}.")
