"""Sprzeciw od oceny: rozstrzyga dyrektor generalny urzędu, a stan sprzeciwu widać na liście zadań.

Art. 83 u.s.c.: sprzeciw służy do dyrektora generalnego urzędu (ust. 1) i jest rozpatrywany w terminie 14 dni
od wniesienia (ust. 3). Decyzje prowadzącego projekt z 21.11.2026: rozstrzygnięcie wprowadza w systemie dyrektor
generalny, a nie komórka kadr; strona „Moje zadania” pokazuje stan sprzeciwu.

Decyzje projektowe: dyrektor generalny widzi oceny, od których wniesiono sprzeciw, i tylko te; nie widzi
notatek oceniającego ani danych z EZD RP; sprzeciwu od własnej oceny nie rozstrzyga.
"""

from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from asystent_ocen import terminy
from asystent_ocen.przebieg import BladUprawnien, Rola
from oceny import uslugi
from oceny.models import Zdarzenie
from oceny.zadania import sprzeciwy_uzytkownika, zadania_uzytkownika

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import POCZATEK, Zespol, dyrektor_generalny, pracownik
from .test_widoki import czynnosc, klient

WNIESIONY = date(2026, 11, 10)
DZIEN = date(2026, 11, 11)
TRESC = "Ocena nie uwzględnia zadań wykonanych w zastępstwie."
FORMULARZ = "rozpatrz-sprzeciw"


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat())
class Podstawa(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.dyrektor = dyrektor_generalny()
        self.ocena = self.z.ocena_zakonczona(punkty=1)
        self.sprzeciw = uslugi.wnies_sprzeciw(self.ocena, self.z.ola.uzytkownik, tresc=TRESC, data=WNIESIONY)
        self.karta = f"/oceny/{self.ocena.pk}/"
        self.termin = terminy.termin_rozpatrzenia_sprzeciwu(WNIESIONY)


class RozstrzyganieTest(Podstawa):
    def test_dyrektor_generalny_ma_zadanie_z_terminem_14_dni_a_komorka_kadr_nie(self):
        zadania = zadania_uzytkownika(self.dyrektor.uzytkownik, DZIEN)

        self.assertEqual(
            [(zadanie.kod, zadanie.rola, zadanie.termin) for zadanie in zadania],
            [("ROZPATRZ_SPRZECIW", Rola.DYREKTOR_GENERALNY, self.termin)],
        )
        self.assertEqual(zadania_uzytkownika(self.z.kadry.uzytkownik, DZIEN), [])

    def test_dyrektor_widzi_ocene_ze_sprzeciwem_i_formularz_rozstrzygniecia(self):
        odpowiedz = klient(self.dyrektor).get(self.karta)

        self.assertContains(odpowiedz, TRESC)
        self.assertContains(odpowiedz, "Rozstrzygnięcie dyrektora generalnego", count=1)
        self.assertContains(odpowiedz, czynnosc(self.ocena, FORMULARZ))
        self.assertEqual(odpowiedz.context["role_opis"], "dyrektor generalny")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_dyrektor_nie_dostaje_notatek_oceniajacego_ani_danych_z_ezd_rp(self):
        odpowiedz = klient(self.dyrektor).get(self.karta)

        self.assertContains(klient(self.z.szef).get(self.karta), 'id="n-notatki"')  # oceniający ma panel notatek
        self.assertNotContains(odpowiedz, 'id="n-notatki"')
        for klucz in ("notatki", "karta_ezd", "radar"):
            self.assertNotIn(klucz, odpowiedz.context)

    def test_dyrektor_nie_widzi_ocen_bez_sprzeciwu(self):
        inny = pracownik("jan", przelozony=self.z.szef)
        bez_sprzeciwu = uslugi.rozpocznij_cykl(inny, self.z.kadry.uzytkownik, poczatek_cyklu=POCZATEK, data=POCZATEK)

        self.assertEqual(klient(self.dyrektor).get(f"/oceny/{bez_sprzeciwu.pk}/").status_code, 404)

    def test_komorka_kadr_nie_ma_formularza_i_nie_moze_rozstrzygnac(self):
        kadry = klient(self.z.kadry)

        self.assertNotContains(kadry.get(self.karta), FORMULARZ)
        odpowiedz = kadry.post(czynnosc(self.ocena, FORMULARZ), {"rozstrzygniecie": "nieuwzgledniony"})

        self.assertEqual(odpowiedz.status_code, 403)
        self.sprzeciw.refresh_from_db()
        self.assertFalse(self.sprzeciw.rozpatrzony)

    def test_dyrektor_rozstrzyga_sprzeciw_w_formularzu(self):
        odpowiedz = klient(self.dyrektor).post(
            czynnosc(self.ocena, FORMULARZ),
            {"rozstrzygniecie": "nieuwzgledniony", "uzasadnienie": "Ocena odnosi się do kryteriów."}, follow=True,
        )

        self.sprzeciw.refresh_from_db()
        self.assertEqual((self.sprzeciw.rozstrzygniecie, self.sprzeciw.data_rozstrzygniecia), ("nieuwzgledniony", DZIEN))
        wpis = Zdarzenie.objects.get(ocena=self.ocena, czynnosc="rozpatrzenie sprzeciwu")
        self.assertIn("dyrektor generalny urzędu", wpis.podpis)
        self.assertContains(odpowiedz, "Rozstrzygnięcie sprzeciwu zostało wprowadzone.")
        self.assertNotContains(odpowiedz, czynnosc(self.ocena, FORMULARZ))

    def test_dyrektor_nie_rozstrzyga_sprzeciwu_od_wlasnej_oceny(self):
        z = Zespol.__new__(Zespol)
        z.kadry, z.szef = self.z.kadry, self.z.szef
        self.dyrektor.przelozony = self.z.szef
        self.dyrektor.save()
        z.ola = self.dyrektor
        wlasna = z.ocena_zakonczona(punkty=1)
        uslugi.wnies_sprzeciw(wlasna, self.dyrektor.uzytkownik, tresc=TRESC, data=WNIESIONY)

        with self.assertRaises(BladUprawnien):
            uslugi.rozpatrz_sprzeciw(wlasna, self.dyrektor.uzytkownik, rozstrzygniecie="nieuwzgledniony", data=DZIEN)
        zadania = [zadanie.ocena for zadanie in zadania_uzytkownika(self.dyrektor.uzytkownik, DZIEN) if zadanie.kod == "ROZPATRZ_SPRZECIW"]
        self.assertEqual(zadania, [self.ocena])
        self.assertNotContains(klient(self.dyrektor).get(f"/oceny/{wlasna.pk}/"), czynnosc(wlasna, FORMULARZ))


class StanNaLiscieZadanTest(Podstawa):
    def test_oceniany_przelozony_kadry_i_dyrektor_widza_stan_sprzeciwu(self):
        for osoba in (self.z.ola, self.z.szef, self.z.kadry, self.dyrektor):
            odpowiedz = klient(osoba).get(reverse("zadania"))

            self.assertContains(odpowiedz, "<h2>Sprzeciwy od ocen</h2>", count=1, html=True, msg_prefix=osoba.imie)
            self.assertContains(odpowiedz, f"{WNIESIONY:%d.%m.%Y}", msg_prefix=osoba.imie)
            self.assertContains(odpowiedz, f"{self.termin:%d.%m.%Y}", msg_prefix=osoba.imie)
            self.assertContains(odpowiedz, "w toku - ", msg_prefix=osoba.imie)
            self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [], osoba.imie)

    def test_osoba_spoza_sprawy_nie_widzi_sprzeciwu(self):
        self.assertEqual(sprzeciwy_uzytkownika(self.z.obcy.uzytkownik, DZIEN), [])
        self.assertNotContains(klient(self.z.obcy).get(reverse("zadania")), "Sprzeciwy od ocen okresowych")

    def test_po_terminie_stan_mowi_o_ile_dni(self):
        po = date(2026, 12, 1)

        (wiersz,) = sprzeciwy_uzytkownika(self.z.ola.uzytkownik, po)

        self.assertEqual(wiersz["stan"], "po_terminie")
        self.assertIn(f"{(po - self.termin).days} dni po terminie", wiersz["stan_opis"])

    def test_po_rozstrzygnieciu_widac_wynik_i_date(self):
        uslugi.rozpatrz_sprzeciw(self.ocena, self.dyrektor.uzytkownik, rozstrzygniecie="nieuwzgledniony", data=DZIEN)

        (wiersz,) = sprzeciwy_uzytkownika(self.z.ola.uzytkownik, DZIEN)
        odpowiedz = klient(self.z.ola).get(reverse("zadania"))

        self.assertEqual((wiersz["stan"], wiersz["stan_opis"]), ("wykonane", "nieuwzględniony"))
        self.assertContains(odpowiedz, "nieuwzględniony")
        self.assertContains(odpowiedz, f"{DZIEN:%d.%m.%Y}")
