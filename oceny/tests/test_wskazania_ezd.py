"""Moje dane z EZD RP: strona pracownika z tym, na co wskazują fakty z EZD RP w jego kryteriach.

Wymagania (decyzje zespołu z 21.11.2026): strona dla roli pracownika; pokazuje, na jaki poziom wskazują dane
z EZD RP; wyraźnie zaznacza, że to jedynie przypuszczenie, a ocena zależy od informacji posiadanych przez
przełożonego, także spoza EZD RP. Późniejsza decyzja prowadzącego projekt (21.11.2026): strona nie zbiera
własnych przewidywań pracownika, a przy wyłączonej integracji z EZD RP nie pokazuje sekcji z danymi.

Decyzje projektowe: strona jest tylko o zalogowanej osobie, niczego nie zapisuje i nie widzi jej przełożony
ani kadry; dane z EZD RP podlegają tym samym warunkom Kodeksu pracy co karta kontekstu (art. 22[2] § 6-8 w zw.
z art. 22[3] § 3-4 KP).
"""

from datetime import date
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from asystent_ocen.kryteria import kryteria_obowiazkowe
from asystent_ocen.symulacja import wskazania_z_ezd
from oceny.kontekst_ezd import karta_kontekstu
from oceny.models import Ocena, Pracownik, Zdarzenie

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import Zespol
from .test_ezd import ustalenia
from .test_widoki import klient

DZIEN = date(2026, 11, 2)
RZETELNOSC = "Rzetelność"
ZASTRZEZENIE = "To jedynie przypuszczenie"
NAGLOWEK = "Na co wskazują dane z EZD RP"
ODNOSNIK = 'href="/moje-dane-ezd/"'


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_TRYB_DEMO=True)
class Podstawa(TestCase):
    def setUp(self):
        self.z = Zespol(klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-marek")
        self.ocena = self.z.ocena_z_kryteriami()
        self.adres = reverse("moje_dane_ezd")
        self.ola = klient(self.z.ola)


class PrzyWlaczonejIntegracjiTest(Podstawa):
    def setUp(self):
        super().setUp()
        ustalenia()

    def test_strona_pokazuje_na_co_wskazuja_fakty_z_ezd_rp(self):
        karta = karta_kontekstu(self.ocena, DZIEN)
        udzialy = {wskaznik["kod"]: wskaznik["liczba"] for wskaznik in karta.wskazniki if wskaznik["jednostka"] == "%"}
        (oczekiwane,) = wskazania_z_ezd(kryteria_obowiazkowe("C") + self.z.dodatkowe(), udzialy)

        odpowiedz = self.ola.get(self.adres)

        self.assertContains(odpowiedz, "<h1>Moje dane z EZD RP</h1>", html=True)
        self.assertContains(odpowiedz, NAGLOWEK, count=1)
        (wskazanie,) = odpowiedz.context["ezd"]["wskazania"]
        self.assertEqual((wskazanie["kryterium"], wskazanie["ocena"]), (RZETELNOSC, oczekiwane.ocena))
        self.assertEqual(len(wskazanie["fakty"]), len(oczekiwane.skladniki))
        self.assertLess(oczekiwane.ocena, 5)  # profil z zaległościami: fakty wskazują poniżej oczekiwań
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_strona_mowi_wprost_ze_to_przypuszczenie(self):
        odpowiedz = self.ola.get(self.adres)

        self.assertContains(odpowiedz, ZASTRZEZENIE)
        self.assertContains(odpowiedz, "także tych, których nie ma w systemie EZD RP")
        self.assertContains(odpowiedz, "nie widzi przełożony ani kadry")

    def test_strona_podaje_ile_kryteriow_obejmuja_dane_i_progi_urzedu(self):
        odpowiedz = self.ola.get(self.adres)

        self.assertContains(odpowiedz, "o 1 z 7 Twoich kryteriów")
        self.assertContains(odpowiedz, "co najmniej 95%")
        self.assertContains(odpowiedz, "Przepisy takich progów nie przewidują")

    def test_strona_nie_zbiera_wlasnych_przewidywan_pracownika(self):
        odpowiedz = self.ola.get(self.adres)

        tresc = odpowiedz.content.decode().lower()
        for slad in ("przewidywa", "symulacj", 'name="ocena_', "przelicz"):
            self.assertNotIn(slad, tresc)
        self.assertEqual(self.ola.post(self.adres, {"ocena_0": "9"}).status_code, 405)

    def test_odnosnik_jest_w_menu_osoby_podlegajacej_ocenie(self):
        odpowiedz = self.ola.get(reverse("zadania"))

        self.assertContains(odpowiedz, ODNOSNIK, count=1)
        self.assertContains(odpowiedz, "Moje dane z EZD RP")
        self.assertNotContains(odpowiedz, "Symulacja")

    def test_bez_informacji_dla_pracownika_strona_nie_siega_do_ezd_rp(self):
        """Art. 22[2] § 8 KP - te same warunki co dla karty kontekstu."""
        self.z.ola.klauzula_ezd_potwierdzona = False
        self.z.ola.save()

        odpowiedz = self.ola.get(self.adres)

        self.assertEqual(odpowiedz.context["ezd"]["wskazania"], [])
        self.assertContains(odpowiedz, "Dane z EZD RP nie są teraz pokazywane")
        self.assertContains(odpowiedz, "Ocenianemu nie przekazano informacji")

    def test_przelozony_nie_dostaje_wskazan_na_karcie_oceny_pracownika(self):
        """Wyliczona liczba nie może zastąpić oceny przełożonego - karta kontekstu pokazuje mu same fakty."""
        odpowiedz = klient(self.z.szef).get(f"/oceny/{self.ocena.pk}/")

        self.assertContains(odpowiedz, "Kontekst z EZD RP")
        self.assertNotContains(odpowiedz, "wskazuj")

    def test_strona_niczego_nie_zapisuje(self):
        stan, zdarzenia = Ocena.objects.get(pk=self.ocena.pk).stan, Zdarzenie.objects.count()

        self.ola.get(self.adres)

        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).stan, stan)
        self.assertEqual(Zdarzenie.objects.count(), zdarzenia)

    def test_kazdy_widzi_tylko_wlasne_dane(self):
        odpowiedz = klient(self.z.szef).get(f"{self.adres}?pracownik={self.z.ola.pk}")

        self.assertEqual(odpowiedz.context["pracownik"], self.z.szef)
        self.assertEqual(odpowiedz.context["ezd"]["wskazania"], [])

    def test_osoba_niepodlegajaca_ocenie_dostaje_wyjasnienie(self):
        with mock.patch.object(Pracownik, "podlega_ocenie", new_callable=mock.PropertyMock, return_value=False):
            odpowiedz = self.ola.get(self.adres)

        self.assertContains(odpowiedz, "nie podlegasz ocenie okresowej")
        self.assertNotContains(odpowiedz, NAGLOWEK)


class PrzyWylaczonejIntegracjiTest(Podstawa):
    def test_bez_ustalen_nie_ma_sekcji_z_danymi_ani_odnosnika_w_menu(self):
        odpowiedz = self.ola.get(self.adres)

        self.assertNotContains(odpowiedz, NAGLOWEK)
        self.assertContains(odpowiedz, "Integracja z EZD RP jest wyłączona")
        self.assertNotContains(self.ola.get(reverse("zadania")), ODNOSNIK)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_wylaczona_integracja_ukrywa_sekcje_mimo_kompletu_ustalen(self):
        ustalenia(wlaczona=False)

        self.assertNotContains(self.ola.get(self.adres), NAGLOWEK)
        self.assertNotContains(self.ola.get(reverse("zadania")), ODNOSNIK)

    def test_niezalogowany_trafia_na_logowanie(self):
        odpowiedz = self.client.get(self.adres)

        self.assertEqual(odpowiedz.status_code, 302)
        self.assertIn("/logowanie/", odpowiedz["Location"])


@override_settings(ASYSTENT_DZIS=date(2026, 11, 5).isoformat(), ASYSTENT_TRYB_DEMO=True)
class PoSporzadzeniuOcenyTest(TestCase):
    def test_po_sporzadzeniu_oceny_nie_ma_wskazan_za_miniony_okres(self):
        z = Zespol(klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-marek")
        z.ocena_do_zapoznania()
        ustalenia()

        odpowiedz = klient(z.ola).get(reverse("moje_dane_ezd"))

        self.assertEqual(odpowiedz.context["ezd"]["wskazania"], [])
        self.assertContains(odpowiedz, "jest już sporządzona")
