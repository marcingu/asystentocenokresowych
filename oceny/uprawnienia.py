"""Role i uprawnienia.

Role rdzenia (`przebieg.Rola`) odpowiadają torom modelu BPMN i wynikają z relacji użytkownika do konkretnej oceny:
oceniany, oceniający, zarządzający (komórka kadr), dyrektor generalny, administrator. Oceny, w której użytkownik
nie ma żadnej roli, nie widać. Dyrektor generalny rozstrzyga sprzeciwy (art. 83 ust. 1 u.s.c.), więc widzi
oceny, od których wniesiono sprzeciw - i tylko te. Notatki oceniającego widzi wyłącznie oceniający (decyzja zespołu z 21.11.2026).
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from asystent_ocen.przebieg import Rola

from .models import Ocena, Pracownik


def pracownik_uzytkownika(uzytkownik) -> Pracownik | None:
    if uzytkownik is None or not uzytkownik.is_authenticated:
        return None
    try:
        return uzytkownik.pracownik
    except Pracownik.DoesNotExist:
        return None


def czy_kadry(uzytkownik) -> bool:
    pracownik = pracownik_uzytkownika(uzytkownik)
    return bool(pracownik and pracownik.rola_kadry)


def czy_administrator(uzytkownik) -> bool:
    return bool(uzytkownik is not None and uzytkownik.is_authenticated and uzytkownik.is_superuser)


def konto_funkcyjne(uzytkownik) -> bool:
    """Konto administratora bez karty pracownika - służy wyłącznie do obsługi zaplecza."""
    return czy_administrator(uzytkownik) and pracownik_uzytkownika(uzytkownik) is None


def czy_dyrektor(uzytkownik) -> bool:
    """Dyrektor generalny urzędu (w urzędzie bez dyrektora generalnego - kierownik urzędu)."""
    pracownik = pracownik_uzytkownika(uzytkownik)
    return bool(pracownik and pracownik.rola_dyrektor)


def widzi_statystyki(uzytkownik) -> bool:
    """Statystyki zbiorcze (bez danych osób): dyrektor i komórka kadr."""
    pracownik = pracownik_uzytkownika(uzytkownik)
    return bool(pracownik and (pracownik.rola_dyrektor or pracownik.rola_kadry))


def role_uzytkownika(uzytkownik, ocena: Ocena) -> set[Rola]:
    role: set[Rola] = set()
    if czy_administrator(uzytkownik):
        role.add(Rola.ADMIN)
    pracownik = pracownik_uzytkownika(uzytkownik)
    if pracownik is None:
        return role
    if ocena.oceniany_id == pracownik.pk:
        role.add(Rola.OCENIANY)
    if ocena.oceniajacy_id == pracownik.pk:
        role.add(Rola.OCENIAJACY)
    if pracownik.rola_kadry:
        role.add(Rola.ZARZADZAJACY)
    if pracownik.rola_dyrektor:
        role.add(Rola.DYREKTOR_GENERALNY)
    return role


def widzi_notatki(uzytkownik, ocena: Ocena) -> bool:
    return Rola.OCENIAJACY in role_uzytkownika(uzytkownik, ocena)


def oceny_widoczne(uzytkownik) -> QuerySet[Ocena]:
    """Oceny, w których użytkownik ma rolę wynikającą z procesu oceny.

    Uprawnienia administratora nie dają wglądu w oceny: konto administratora jest kontem funkcyjnym zaplecza,
    a pracownik z takimi uprawnieniami widzi tylko to, co wynika z jego własnej roli w ocenie.
    """
    wszystkie = Ocena.objects.select_related("oceniany", "oceniajacy", "poprzednia")
    if czy_kadry(uzytkownik):
        return wszystkie
    pracownik = pracownik_uzytkownika(uzytkownik)
    if pracownik is None:
        return wszystkie.none()
    strona = Q(oceniany=pracownik) | Q(oceniajacy=pracownik)
    if pracownik.rola_dyrektor:
        return wszystkie.filter(strona | Q(sprzeciwy__isnull=False)).distinct()
    return wszystkie.filter(strona)
