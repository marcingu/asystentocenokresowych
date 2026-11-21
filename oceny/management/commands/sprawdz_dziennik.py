"""Kontrola nienaruszalności dziennika zdarzeń bezpieczeństwa (łańcuch skrótów)."""

from django.core.management.base import BaseCommand, CommandError

from oceny import dziennik


class Command(BaseCommand):
    help = "Sprawdza, czy dziennik zdarzeń bezpieczeństwa nie został zmieniony poza aplikacją."

    def handle(self, *args, **opcje):
        wynik = dziennik.sprawdz_lancuch()
        if not wynik["poprawny"]:
            gdzie = f"pierwszy niezgodny wpis: {wynik['pierwszy_bledny']}" if wynik["pierwszy_bledny"] else "brakuje wpisów na końcu"
            raise CommandError(f"Dziennik zdarzeń jest naruszony ({gdzie}).")
        self.stdout.write(f"Dziennik zdarzeń jest nienaruszony. Liczba wpisów: {wynik['wpisow']}.")
