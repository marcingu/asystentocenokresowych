"""Komórki organizacyjne Kancelarii Prezesa Rady Ministrów - lista do słownika struktury urzędu.

Źródło: strona „Sekretariaty, Departamenty, Biura” w portalu gov.pl (adres w `ZRODLO`), odczyt 22.11.2026;
kolejność jak na stronie. Lista zawiera wyłącznie nazwy komórek - bez nazwisk dyrekcji i danych kontaktowych.
Obsadę komórek w pokazie tworzą osoby fikcyjne. Struktura urzędu się zmienia: przed użyciem poza pokazem listę
trzeba porównać ze stroną, a słownik w zapleczu administratora można potem poprawić ręcznie.
"""

from __future__ import annotations

from datetime import date

from .models import Wydzial

ZRODLO = "https://www.gov.pl/web/premier/sekretariaty-departamenty-biura2"
ODCZYT = date(2026, 11, 22)
KOMORKI = (
    "Biuro Prezesa Rady Ministrów",
    "Biuro Szefa Kancelarii Prezesa Rady Ministrów",
    "Biuro Rzecznika Rządu",
    "Centrum Informacyjne Rządu",
    "Departament Bezpieczeństwa Narodowego",
    "Departament Koordynacji Polityk Publicznych",
    "Departament Koordynacji Procesu Legislacyjnego",
    "Departament Koordynacji Służb Specjalnych",
    "Departament Nadzoru i Kontroli",
    "Departament Oceny Skutków Regulacji i Analiz",
    "Departament Polityki Senioralnej",
    "Departament Prawny",
    "Departament Służby Cywilnej",
    "Departament Społeczeństwa Obywatelskiego",
    "Departament Spraw Parlamentarnych",
    "Departament do spraw Równego Traktowania",
    "Departament Spraw Zagranicznych",
    "Departament Wniosków, Petycji i Skarg",
    "Biuro Budżetowo-Finansowe",
    "Biuro Dyrektora Generalnego",
    "Biuro Informatyki",
    "Biuro Kadr i Rozwoju Zawodowego",
    "Biuro Ochrony Informacji i Spraw Obronnych",
)


def wczytaj() -> list[str]:
    """Dodaje do słownika brakujące komórki i zwraca ich nazwy. Istniejących komórek, ich nazw, obsady
    i przypisanych pracowników nie zmienia; niczego nie usuwa. Wielkość liter w nazwie nie tworzy drugiej komórki."""
    obecne = {nazwa.casefold() for nazwa in Wydzial.objects.values_list("nazwa", flat=True)}
    brakujace = [nazwa for nazwa in KOMORKI if nazwa.casefold() not in obecne]
    Wydzial.objects.bulk_create(Wydzial(nazwa=nazwa) for nazwa in brakujace)
    return brakujace
