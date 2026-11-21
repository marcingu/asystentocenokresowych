"""Administracja utrzymuje wydziały, a kadry przypisują pracownika do istniejącego wydziału."""
from .dostepnosc_html import bledy_dostepnosci
from .test_administracja import Podstawa
from .test_kadry_pracownik import NOWY, dane
from .test_widoki import klient
from oceny.models import Pracownik

ADRES = "/administracja/wydzialy/"


class StrukturaTest(Podstawa):
    def test_dostep_i_dodawanie(self):
        self.assertContains(self.przegladarka.get("/administracja/"), 'href="' + ADRES + '"')
        for osoba in (self.z.kadry, self.z.szef, self.z.ola):
            self.assertEqual(klient(osoba).post(ADRES, {"akcja": "dodaj", "nazwa": "Inny"}).status_code, 403)
        self.assertEqual(self.przegladarka.post(ADRES, {"akcja": "dodaj", "nazwa": "Wydział Rozwoju"}).status_code, 302)
        wynik = klient(self.z.kadry).get(NOWY)
        self.assertContains(wynik, '<select name="wydzial"')
        self.assertContains(wynik, 'Wydział Rozwoju</option>')
        self.assertEqual(bledy_dostepnosci(self.przegladarka.get(ADRES).content.decode()), [])

    def test_zmiana_nazwy_nie_zrywa_przypisan_i_usunac_mozna_tylko_pusty(self):
        from oceny.models import Wydzial
        wpis = self.z.ola.wydzial
        self.assertEqual(self.przegladarka.post(ADRES, {"akcja": "zmien", "pk": wpis.pk, "nazwa": "Wydział Spraw"}).status_code, 302)
        self.z.ola.refresh_from_db()
        self.assertEqual(self.z.ola.komorka, "Wydział Spraw")
        self.przegladarka.post(ADRES, {"akcja": "usun", "pk": wpis.pk})
        self.assertTrue(Wydzial.objects.filter(pk=wpis.pk).exists())
        pusty = Wydzial.objects.create(nazwa="Wolny")
        self.assertEqual(self.przegladarka.post(ADRES, {"akcja": "usun", "pk": pusty.pk}).status_code, 302)
        self.assertFalse(Wydzial.objects.filter(pk=pusty.pk).exists())

    def test_kadry_nie_wpisza_dowolnej_nazwy_lub_obcego_id(self):
        for wydzial in ("Nowy wydział", "999999"):
            self.assertContains(klient(self.z.kadry).post(NOWY, dane(wydzial=wydzial)), 'role="alert"')
        self.assertFalse(Pracownik.objects.filter(nazwisko="Nowicki").exists())
