"""Odblokowanie konta z serwera - na wypadek, gdy żaden administrator nie ma czynnego konta."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from oceny import bezpieczenstwo


class Command(BaseCommand):
    help = "Odblokowuje konto o podanym loginie. Czynność trafia do dziennika zdarzeń."

    def add_arguments(self, parser):
        parser.add_argument("login")

    def handle(self, *args, **opcje):
        uzytkownik = get_user_model().objects.filter(username=opcje["login"]).first()
        if uzytkownik is None:
            raise CommandError("Nie ma konta o takim loginie.")
        bezpieczenstwo.odblokuj_konto(uzytkownik, opis="Odblokowanie poleceniem z serwera (bez konta administratora).")
        self.stdout.write(f"Konto {uzytkownik.get_username()} jest odblokowane.")
