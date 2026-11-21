"""Symulacja oceny dla pracownika: własne przewidywanie ocen cząstkowych i to, na co wskazują fakty z EZD RP.

Wymagania (decyzja zespołu z 21.11.2026): moduł dla roli pracownika; pokazuje, na jaki wynik wskazują dane
z EZD RP; wyraźnie zaznacza, że to jedynie przypuszczenie, a ocena zależy od informacji posiadanych przez
przełożonego, także spoza EZD RP. Decyzje projektowe: symulacja jest tylko o zalogowanej osobie, niczego nie
zapisuje i nie widzi jej przełożony ani kadry; dane z EZD RP podlegają tym samym warunkom Kodeksu pracy co karta
kontekstu (art. 22[2] § 6-8 w zw. z art. 22[3] § 3-4 KP); wynik liczy rdzeń według § 11 rozp.
"""

from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from asystent_ocen.kryteria import kryteria_obowiazkowe
from asystent_ocen.symulacja import wskazania_z_ezd
from oceny.kontekst_ezd import karta_kontekstu
from oceny.models import Ocena, Zdarzenie

from .pomocnicze import Zespol, pracownik
from .test_ezd import ustalenia
from .test_widoki import klient

DZIEN = date(2026, 11, 2)
RZETELNOSC = "Rzetelność"
ZASTRZEZENIE = "To jedynie przypuszczenie"


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_TRYB_DEMO=True)
class Podstawa(TestCase):
    def setUp(self):
        self.z = Zespol(klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-marek")
        self.ocena = self.z.ocena_z_kryteriami()
        self.adres = reverse("symulacja")
        self.ola = klient(self.z.ola)

    def wiersze(self, odpowiedz) -> dict[str, dict]:
        return {wiersz["nazwa"]: wiersz for wiersz in odpowiedz.context["kryteria"]}

    def wybor(self, punkty: int, **wyjatki: int | str) -> dict[str, str]:
        """Dane formularza: ta sama ocena dla wszystkich kryteriów, z wyjątkami podanymi numerem wiersza."""
        nazwy = kryteria_obowiazkowe("C") + self.z.dodatkowe()
        dane = {f"ocena_{numer}": str(punkty) for numer in range(len(nazwy))}
        dane.update({f"ocena_{klucz.removeprefix('w')}": str(wartosc) for klucz, wartosc in wyjatki.items()})
        return dane


class ZastrzezeniaTest(Podstawa):
    def test_strona_mowi_wprost_ze_to_przypuszczenie(self):
        odpowiedz = self.ola.get(self.adres)

        self.assertContains(odpowiedz, ZASTRZEZENIE)
        self.assertContains(odpowiedz, "także tych, których nie ma w systemie EZD RP")
        self.assertContains(odpowiedz, "Symulacji nie widzi przełożony ani kadry")

    def test_zastrzezenie_jest_tez_przy_wyniku_po_przeliczeniu(self):
        odpowiedz = self.ola.post(self.adres, self.wybor(7))

        self.assertContains(odpowiedz, ZASTRZEZENIE)

    def test_odnosnik_do_symulacji_jest_w_menu_osoby_podlegajacej_ocenie(self):
        self.assertContains(self.ola.get(reverse("zadania")), 'href="/symulacja/"')

    def test_niezalogowany_trafia_na_logowanie(self):
        odpowiedz = self.client.get(self.adres)

        self.assertEqual(odpowiedz.status_code, 302)
        self.assertIn("/logowanie/", odpowiedz["Location"])


class DaneZEzdTest(Podstawa):
    def setUp(self):
        super().setUp()
        ustalenia()

    def test_symulacja_pokazuje_na_co_wskazuja_fakty_z_ezd_rp(self):
        karta = karta_kontekstu(self.ocena, DZIEN)
        udzialy = {wskaznik["kod"]: wskaznik["liczba"] for wskaznik in karta.wskazniki if wskaznik["jednostka"] == "%"}
        (oczekiwane,) = wskazania_z_ezd(kryteria_obowiazkowe("C") + self.z.dodatkowe(), udzialy)

        odpowiedz = self.ola.get(self.adres)

        self.assertContains(odpowiedz, "Na co wskazują dane z EZD RP")
        (wskazanie,) = odpowiedz.context["ezd"]["wskazania"]
        self.assertEqual((wskazanie["kryterium"], wskazanie["ocena"]), (RZETELNOSC, oczekiwane.ocena))
        self.assertEqual(len(wskazanie["fakty"]), len(oczekiwane.skladniki))
        self.assertLess(oczekiwane.ocena, 5)  # profil z zaległościami: fakty wskazują poniżej oczekiwań

    def test_kryterium_z_danymi_startuje_od_wskazania_a_pozostale_od_poziomu_oczekiwan(self):
        odpowiedz = self.ola.get(self.adres)

        wiersze = self.wiersze(odpowiedz)
        wskazanie = odpowiedz.context["ezd"]["wskazania"][0]["ocena"]
        self.assertEqual((wiersze[RZETELNOSC]["wartosc"], wiersze[RZETELNOSC]["z_ezd"]), (wskazanie, wskazanie))
        pozostale = [wiersz for nazwa, wiersz in wiersze.items() if nazwa != RZETELNOSC]
        self.assertEqual({(wiersz["wartosc"], wiersz["z_ezd"]) for wiersz in pozostale}, {(5, None)})

    def test_strona_podaje_ile_kryteriow_obejmuja_dane(self):
        self.assertContains(self.ola.get(self.adres), "o 1 z 7 Twoich kryteriów")

    def test_strona_pokazuje_progi_i_to_ze_ustala_je_urzad(self):
        odpowiedz = self.ola.get(self.adres)

        self.assertContains(odpowiedz, "co najmniej 95%")
        self.assertContains(odpowiedz, "Przepisy takich progów nie przewidują")

    def test_pracownik_moze_zmienic_ocene_wskazana_przez_dane(self):
        odpowiedz = self.ola.post(self.adres, self.wybor(9))

        wiersz = self.wiersze(odpowiedz)[RZETELNOSC]
        self.assertEqual(wiersz["wartosc"], 9)
        self.assertLess(wiersz["z_ezd"], 5)

    def test_bez_informacji_dla_pracownika_symulacja_nie_siega_do_ezd_rp(self):
        """Art. 22[2] § 8 KP - te same warunki co dla karty kontekstu."""
        self.z.ola.klauzula_ezd_potwierdzona = False
        self.z.ola.save()

        odpowiedz = self.ola.get(self.adres)

        self.assertEqual(odpowiedz.context["ezd"]["wskazania"], [])
        self.assertEqual({wiersz["wartosc"] for wiersz in odpowiedz.context["kryteria"]}, {5})
        self.assertContains(odpowiedz, "Symulacja nie korzysta teraz z danych EZD RP")

    def test_przelozony_nie_dostaje_wskazan_na_karcie_oceny_pracownika(self):
        """Wyliczona liczba nie może zastąpić oceny przełożonego - karta kontekstu pokazuje mu same fakty."""
        odpowiedz = klient(self.z.szef).get(f"/oceny/{self.ocena.pk}/")

        self.assertContains(odpowiedz, "Kontekst z EZD RP")
        self.assertNotContains(odpowiedz, "wskazuj")


class BezEzdTest(Podstawa):
    def test_bez_wlaczonej_integracji_symulacja_dziala_na_samych_przewidywaniach(self):
        odpowiedz = self.ola.get(self.adres)

        self.assertEqual(odpowiedz.context["ezd"]["wskazania"], [])
        self.assertContains(odpowiedz, "Symulacja nie korzysta teraz z danych EZD RP")
        self.assertEqual(odpowiedz.context["wynik"]["ocena"], "POZYTYWNA")

    def test_wynik_liczy_rdzen_wedlug_rozporzadzenia(self):
        odpowiedz = self.ola.post(self.adres, self.wybor(7, w0=9))

        wynik = odpowiedz.context["wynik"]
        self.assertEqual((wynik["srednia"], wynik["poziom"], wynik["ocena"]), ("7,3", "powyżej oczekiwań", "POZYTYWNA"))
        self.assertContains(odpowiedz, "średnia 7,3")

    def test_ocena_czastkowa_1_daje_wynik_negatywny_z_wyjasnieniem(self):
        odpowiedz = self.ola.post(self.adres, self.wybor(7, w1=1))

        self.assertEqual(odpowiedz.context["wynik"]["ocena"], "NEGATYWNA")
        self.assertContains(odpowiedz, "wyklucza ocenę pozytywną")

    def test_wartosci_spoza_skali_sa_pomijane(self):
        odpowiedz = self.ola.post(self.adres, self.wybor(7, w0=8, w1="x"))

        wartosci = [wiersz["wartosc"] for wiersz in odpowiedz.context["kryteria"]]
        self.assertEqual(wartosci, [5, 5, 7, 7, 7, 7, 7])

    def test_symulacja_niczego_nie_zapisuje(self):
        przed = (Ocena.objects.get(pk=self.ocena.pk).stan, Zdarzenie.objects.count())

        self.ola.post(self.adres, self.wybor(3))

        ocena = Ocena.objects.get(pk=self.ocena.pk)
        self.assertEqual((ocena.stan, Zdarzenie.objects.count()), przed)
        self.assertIsNone(ocena.szkic)

    def test_kazdy_symuluje_tylko_wlasna_ocene(self):
        """Adres nie przyjmuje wskazania osoby - przełożony widzi kryteria swojego arkusza, nie podwładnej."""
        odpowiedz = klient(self.z.szef).get(self.adres, {"pracownik": self.z.ola.pk, "ocena": self.ocena.pk})

        self.assertEqual(odpowiedz.context["pracownik"], self.z.szef)
        self.assertEqual([wiersz["nazwa"] for wiersz in odpowiedz.context["kryteria"]], kryteria_obowiazkowe("B"))

    def test_osoba_niepodlegajaca_ocenie_dostaje_wyjasnienie_zamiast_formularza(self):
        ewa = pracownik("ewa", rodzaj_zatrudnienia="umowa_na_czas_okreslony")

        odpowiedz = klient(ewa).get(self.adres)

        self.assertContains(odpowiedz, "nie podlegasz ocenie okresowej")
        self.assertNotContains(odpowiedz, 'name="ocena_0"')
        self.assertNotContains(klient(ewa).get(reverse("zadania")), 'href="/symulacja/"')


@override_settings(ASYSTENT_DZIS="2026-11-10", ASYSTENT_TRYB_DEMO=True)
class PoSporzadzeniuOcenyTest(TestCase):
    def test_po_sporzadzeniu_oceny_symulacja_dotyczy_kolejnego_okresu(self):
        """Gdy wynik jest już znany, nie ma czego przewidywać: zostają kryteria obowiązkowe kolejnego okresu,
        a danych z EZD RP za ten okres jeszcze nie ma."""
        z = Zespol(klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-marek")
        z.ocena_do_zapoznania()
        ustalenia()

        odpowiedz = klient(z.ola).get(reverse("symulacja"))

        self.assertContains(odpowiedz, "Twoja ocena za bieżący okres jest już sporządzona")
        self.assertEqual([wiersz["nazwa"] for wiersz in odpowiedz.context["kryteria"]], kryteria_obowiazkowe("C"))
        self.assertEqual(odpowiedz.context["ezd"]["wskazania"], [])
