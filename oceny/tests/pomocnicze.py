"""Dane pomocnicze do testów aplikacji - fikcyjne osoby i gotowe etapy procesu."""

from datetime import date

from django.contrib.auth import get_user_model

from asystent_ocen.kryteria import kryteria_dodatkowe_do_wyboru, kryteria_obowiazkowe
from oceny import uslugi
from oceny.models import Pracownik, Wydzial

POCZATEK = date(2024, 11, 21)
DZIEN_KRYTERIOW = date(2024, 12, 2)
DZIEN_POTWIERDZENIA = date(2024, 12, 3)
TERMIN = date(2026, 11, 20)
DZIEN_ROZMOWY = date(2026, 11, 3)
DZIEN_OCENY = date(2026, 11, 4)


def pracownik(login: str, **pola) -> Pracownik:
    """Pracownik z kontem użytkownika o podanym loginie (hasło nieustawione)."""
    uzytkownik = get_user_model().objects.create_user(username=login)
    dane = {
        "imie": login.capitalize(),
        "nazwisko": "Testowy",
        "stanowisko": "specjalista",
        "opis_stanowiska": "Prowadzenie spraw wydziału.",
        "komorka": "Wydział Organizacyjny",
        "rodzaj_zatrudnienia": "umowa_na_czas_nieokreslony",
        "data_zatrudnienia": POCZATEK,
    }
    dane.update(pola)
    nazwa = dane.pop("komorka")
    dane["wydzial"] = Wydzial.objects.get_or_create(nazwa=nazwa)[0] if nazwa else None
    return Pracownik.objects.create(uzytkownik=uzytkownik, **dane)


def dyrektor_generalny() -> Pracownik:
    """Dyrektor generalny urzędu - rozstrzyga sprzeciwy (art. 83 ust. 1 u.s.c.). Powstaje przy pierwszym użyciu."""
    istniejacy = Pracownik.objects.filter(rola_dyrektor=True).first()
    return istniejacy or pracownik("dyrektor", rola_dyrektor=True, stanowisko="dyrektor generalny urzędu")


class Zespol:
    """Kadry, przełożony i oceniany - najmniejszy komplet ról do przejścia procesu."""

    def __init__(self, **pola_ocenianego) -> None:
        self.kadry = pracownik("kadry", rola_kadry=True)
        self.szef = pracownik("szef", kieruje_pracownikami=True, stanowisko="naczelnik wydziału")
        self.ola = pracownik("ola", przelozony=self.szef, **pola_ocenianego)
        self.obcy = pracownik("obcy")

    def nowa_ocena(self):
        return uslugi.rozpocznij_cykl(self.ola, self.kadry.uzytkownik, poczatek_cyklu=POCZATEK, data=POCZATEK)

    def dodatkowe(self, ile: int = 2) -> list[str]:
        return kryteria_dodatkowe_do_wyboru(self.ola.arkusz)[:ile]

    def oceny(self, punkty: int = 7, ile_dodatkowych: int = 2) -> dict[str, int]:
        nazwy = kryteria_obowiazkowe(self.ola.arkusz) + self.dodatkowe(ile_dodatkowych)
        return {nazwa: punkty for nazwa in nazwy}

    def ocena_z_kryteriami(self):
        ocena = self.nowa_ocena()
        uslugi.wyznacz_kryteria(
            ocena, self.szef.uzytkownik, kryteria_dodatkowe=self.dodatkowe(), termin=TERMIN, data=DZIEN_KRYTERIOW
        )
        uslugi.potwierdz_kryteria(ocena, self.ola.uzytkownik, data=DZIEN_POTWIERDZENIA)
        return ocena

    def ocena_do_zapoznania(self, punkty: int = 7, **pola):
        ocena = self.ocena_z_kryteriami()
        dane = {
            "data_rozmowy": DZIEN_ROZMOWY,
            "oceny": self.oceny(punkty),
            "wnioski_iprz": "Szkolenie z postępowania administracyjnego.",
            "uzasadnienie": "Zadania wykonywane po terminie." if punkty == 1 else "",
            "data": DZIEN_OCENY,
        }
        dane.update(pola)
        uslugi.sporzadz_ocene(ocena, self.szef.uzytkownik, **dane)
        return ocena

    def ocena_zakonczona(self, punkty: int = 7, **pola):
        ocena = self.ocena_do_zapoznania(punkty, **pola)
        uslugi.potwierdz_zapoznanie(ocena, self.ola.uzytkownik, data=DZIEN_OCENY)
        return ocena
