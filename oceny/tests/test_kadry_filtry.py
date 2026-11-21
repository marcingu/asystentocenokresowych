"""Lista pracowników w panelu kadr: wyszukiwanie, filtry i sortowanie.

Wymaganie: przypadki użycia KPRM („use cases - opis”) - „przeglądanie listy pracowników (w tym wyszukiwanie
i sortowanie)”; decyzja zespołu z 21.11.2026 - filtry po komórce organizacyjnej i statusie oceny, żeby dało się
pracować z listą dużego urzędu.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from .pomocnicze import Zespol, pracownik
from .test_widoki import klient

FINANSE = "Wydział Finansowy"


@override_settings(ASYSTENT_DZIS="2026-06-01")
class FiltryKadrTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()  # Ola: etap oceniania, termin 20.11.2026
        pracownik("jan", nazwisko="Kowalski", komorka=FINANSE, przelozony=self.z.szef)
        pracownik(
            "ewa", nazwisko="Zielińska", komorka=FINANSE, stanowisko="inspektor",
            rodzaj_zatrudnienia="umowa_na_czas_okreslony",
        )
        self.kadry = klient(self.z.kadry)

    def loginy(self, **zapytanie) -> list[str]:
        odpowiedz = self.kadry.get(reverse("kadry"), zapytanie)
        self.assertEqual(odpowiedz.status_code, 200)
        return [wiersz["osoba"].uzytkownik.username for wiersz in odpowiedz.context["wiersze"]]

    def test_bez_filtrow_lista_pokazuje_wszystkich_wedlug_nazwisk(self):
        self.assertEqual(self.loginy(), ["jan", "kadry", "obcy", "ola", "szef", "ewa"])

    def test_wyszukiwanie_po_fragmencie_nazwiska_bez_wielkosci_liter_i_ogonkow(self):
        self.assertEqual(self.loginy(q="kowal"), ["jan"])
        self.assertEqual(self.loginy(q="ZIELINSKA"), ["ewa"])

    def test_wyszukiwanie_obejmuje_imie_i_stanowisko(self):
        self.assertEqual(self.loginy(q="ola"), ["ola"])
        self.assertEqual(self.loginy(q="naczelnik"), ["szef"])

    def test_filtr_komorki_organizacyjnej(self):
        self.assertEqual(self.loginy(komorka=FINANSE), ["jan", "ewa"])

    def test_filtr_statusu_oceny(self):
        self.assertEqual(self.loginy(status="OCENIANIE"), ["ola"])
        self.assertEqual(self.loginy(status="nie_podlega"), ["ewa"])
        self.assertEqual(self.loginy(status="bez_oceny"), ["jan", "kadry", "obcy", "szef"])
        self.assertEqual(self.loginy(status="ZAKONCZONA"), [])

    def test_filtr_po_terminie_liczy_termin_wzgledem_dzisiejszej_daty(self):
        self.assertEqual(self.loginy(status="po_terminie"), [])
        with override_settings(ASYSTENT_DZIS="2026-11-21"):
            self.assertEqual(self.loginy(status="po_terminie"), ["ola"])

    def test_filtry_lacza_sie(self):
        self.assertEqual(self.loginy(q="testowy", komorka="Wydział Organizacyjny", status="OCENIANIE"), ["ola"])
        self.assertEqual(self.loginy(q="kowal", status="OCENIANIE"), [])

    def test_sortowanie_wedlug_terminu_stawia_najblizsze_oceny_na_poczatku(self):
        self.assertEqual(self.loginy(sort="termin")[0], "ola")

    def test_sortowanie_wedlug_komorki(self):
        self.assertEqual(self.loginy(sort="komorka")[:2], ["jan", "ewa"])

    def test_sortowanie_uwzglednia_polski_alfabet(self):
        """„Ł” stoi po „L”, a nie za „Z”, jak w porządku kodów znaków bazy danych."""
        pracownik("lucja", nazwisko="Łukasik")
        pracownik("stefan", nazwisko="Śliwa")

        self.assertEqual(self.loginy(), ["jan", "lucja", "stefan", "kadry", "obcy", "ola", "szef", "ewa"])

    def test_nieznane_wartosci_filtrow_sa_pomijane(self):
        self.assertEqual(len(self.loginy(status="cokolwiek", sort="<script>")), 6)

    def test_formularz_pamieta_wybor_i_pokazuje_licznik(self):
        odpowiedz = self.kadry.get(reverse("kadry"), {"q": "kowal", "komorka": FINANSE, "status": "bez_oceny"})

        self.assertContains(odpowiedz, 'value="kowal"')
        self.assertContains(odpowiedz, f'<option value="{FINANSE}" selected>')
        self.assertContains(odpowiedz, '<option value="bez_oceny" selected>')
        self.assertContains(odpowiedz, "Pokazano 1 z 6")
        self.assertContains(odpowiedz, "Wyczyść filtry")

    def test_brak_wynikow_ma_komunikat_zamiast_pustej_tabeli(self):
        odpowiedz = self.kadry.get(reverse("kadry"), {"q": "nie-ma-takiej-osoby"})

        self.assertContains(odpowiedz, "Żaden pracownik nie spełnia podanych warunków")
        self.assertNotContains(odpowiedz, "<table")

    def test_filtry_nie_otwieraja_listy_osobom_spoza_kadr(self):
        self.assertEqual(klient(self.z.szef).get(reverse("kadry"), {"q": "kowal"}).status_code, 403)
