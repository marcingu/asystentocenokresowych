"""Uzupełnienie brakujących cykli przy imporcie kart i po aktualizacji aplikacji."""
from django.core.management.base import BaseCommand
from oceny.cykle import uzgodnij
from oceny.models import Pracownik


class Command(BaseCommand):
    help = "Otwiera brakujące oceny okresowe na podstawie kompletnych kart. Nie zakłada pierwszych umów."

    def handle(self, *args, **options):
        liczba = sum(uzgodnij(pk) is not None for pk in list(Pracownik.objects.values_list("pk", flat=True)))
        self.stdout.write(f"Nowe cykle: {liczba}")
