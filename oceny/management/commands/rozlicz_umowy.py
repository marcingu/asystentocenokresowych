"""Rozliczenie dni granicznych bez oczekiwania na ruch HTTP."""
from django.core.management.base import BaseCommand
from oceny.umowy import rozlicz_umowy


class Command(BaseCommand):
    help = "Blokuje konta po zakończeniu zatrudnienia i uwzględnia zawarte umowy bezterminowe."

    def handle(self, *args, **options):
        self.stdout.write(f"Rozliczone umowy: {rozlicz_umowy()}")
