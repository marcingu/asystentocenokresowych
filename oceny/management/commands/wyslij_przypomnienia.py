"""Planowa wysyłka przypomnień o terminach - do uruchamiania raz dziennie z harmonogramu serwera (cron, systemd)."""
from django.core.management.base import BaseCommand

from oceny import przypomnienia
from oceny.czas import dzis


class Command(BaseCommand):
    help = ("Wysyła przypomnienia e-mail osobom, którym dziś wypada dzień przypomnienia o terminie "
            "(dni z przepisy.toml, dzień terminu i co 7 dni po terminie). Najwyżej jedna wiadomość na osobę dziennie.")

    def add_arguments(self, parser):
        parser.add_argument("--wszystkim", action="store_true",
                            help="wyślij wszystkim, którzy mają zadania z terminem, bez czekania na dzień przypomnienia")

    def handle(self, *args, **options):
        self.stdout.write(przypomnienia.wyslij(dzis(), wymus=options["wszystkim"]).opis)
