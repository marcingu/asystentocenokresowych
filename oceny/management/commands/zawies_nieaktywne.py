"""Zawieszanie kont bez aktywności - do codziennego uruchamiania (cron albo timer systemd).

Aplikacja wykonuje ten przegląd także sama, przy pierwszym żądaniu każdego dnia.
"""

from datetime import date

from django.core.management.base import BaseCommand

from oceny import bezpieczenstwo


class Command(BaseCommand):
    help = "Zawiesza konta, na których od ostatniego logowania upłynął ponad miesiąc (zał. nr 4 część I pkt 6 ustawy o KSC)."

    def add_arguments(self, parser):
        parser.add_argument("--dzien", help="dzień przeglądu w postaci RRRR-MM-DD; domyślnie dziś")

    def handle(self, *args, **opcje):
        dzien = date.fromisoformat(opcje["dzien"]) if opcje["dzien"] else None
        zawieszone = bezpieczenstwo.zawies_nieaktywne(dzien)
        loginy = ", ".join(uzytkownik.get_username() for uzytkownik in zawieszone)
        self.stdout.write(f"Zawieszone konta: {len(zawieszone)}{' (' + loginy + ')' if loginy else ''}.")
