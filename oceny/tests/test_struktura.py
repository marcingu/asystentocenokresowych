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


class StrukturaKprmTest(Podstawa):
    """Słownik struktury z listy komórek organizacyjnych KPRM (gov.pl, strona „Sekretariaty, Departamenty, Biura”,
    odczyt 22.11.2026). Lista zawiera same nazwy komórek - bez nazwisk dyrekcji i danych kontaktowych."""

    def test_lista_ma_komorki_ze_strony_kprm_bez_powtorzen(self):
        from oceny import struktura_kprm

        self.assertEqual(len(struktura_kprm.KOMORKI), 23)
        self.assertEqual(len(set(struktura_kprm.KOMORKI)), 23)
        self.assertEqual(struktura_kprm.KOMORKI[0], "Biuro Prezesa Rady Ministrów")
        self.assertEqual(struktura_kprm.KOMORKI[-1], "Biuro Ochrony Informacji i Spraw Obronnych")
        for nazwa in ("Departament Służby Cywilnej", "Biuro Dyrektora Generalnego", "Biuro Kadr i Rozwoju Zawodowego",
                      "Departament do spraw Równego Traktowania", "Centrum Informacyjne Rządu"):
            self.assertIn(nazwa, struktura_kprm.KOMORKI)
        self.assertEqual(struktura_kprm.ZRODLO, "https://www.gov.pl/web/premier/sekretariaty-departamenty-biura2")

    def test_administrator_wczytuje_strukture_a_ponowne_wczytanie_niczego_nie_zmienia(self):
        from oceny import dziennik, struktura_kprm
        from oceny.models import Wydzial, ZdarzenieBezpieczenstwa

        istniejaca = Wydzial.objects.create(nazwa="biuro informatyki", kierownik=self.z.szef)  # ta sama komórka, inna wielkość liter
        przed = set(Wydzial.objects.values_list("nazwa", flat=True))

        odpowiedz = self.przegladarka.post(ADRES, {"akcja": "wczytaj"}, follow=True)

        self.assertContains(odpowiedz, "Dodano 22 komórki organizacyjne z listy KPRM.")
        nazwy = set(Wydzial.objects.values_list("nazwa", flat=True))
        self.assertEqual(nazwy - przed, set(struktura_kprm.KOMORKI) - {"Biuro Informatyki"})
        self.assertLessEqual(przed, nazwy)  # niczego nie usunięto ani nie przemianowano
        istniejaca.refresh_from_db()
        self.assertEqual((istniejaca.nazwa, istniejaca.kierownik), ("biuro informatyki", self.z.szef))
        wpis = ZdarzenieBezpieczenstwa.objects.order_by("pk").last()
        self.assertEqual((wpis.rodzaj, wpis.dotyczy), (dziennik.PANEL_ADMINISTRATORA, "struktura urzędu"))
        self.assertIn("22", wpis.opis)

        ponownie = self.przegladarka.post(ADRES, {"akcja": "wczytaj"}, follow=True)
        self.assertContains(ponownie, "Wszystkie komórki z listy KPRM są już w strukturze.")
        self.assertEqual(set(Wydzial.objects.values_list("nazwa", flat=True)), nazwy)

    def test_strone_struktury_opisuje_zrodlo_a_wczytac_moze_tylko_administrator(self):
        from oceny.models import Wydzial

        strona = self.przegladarka.get(ADRES)
        self.assertContains(strona, "<h1>Struktura urzędu</h1>")
        self.assertContains(strona, 'href="https://www.gov.pl/web/premier/sekretariaty-departamenty-biura2"')
        self.assertContains(strona, "odczyt 22.11.2026")
        self.assertContains(strona, 'name="akcja" value="wczytaj"')
        self.assertEqual(bledy_dostepnosci(strona.content.decode()), [])
        liczba = Wydzial.objects.count()
        for osoba in (self.z.kadry, self.z.szef, self.z.ola):
            self.assertEqual(klient(osoba).post(ADRES, {"akcja": "wczytaj"}).status_code, 403)
        self.assertEqual(Wydzial.objects.count(), liczba)
