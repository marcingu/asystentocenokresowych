"""Wygląd wzorowany na serwisie gov.pl/web/premier i pokaz pod nazwą KPRM.

Decyzje prowadzącego projekt z 21.11.2026 (wieczorem): urzędem w pokazie jest Kancelaria Prezesa Rady Ministrów,
a układ i kolory stron mają przypominać strony Prezesa Rady Ministrów w portalu gov.pl.

Wartości odczytane 21.11.2026 ze strony https://www.gov.pl/web/premier (style obliczone przez przeglądarkę):
tekst rgb(27, 27, 27) na białym tle, odnośniki i przyciski rgb(0, 82, 165), górna krawędź stopki rgb(213, 35, 63),
krój „Open Sans”, jasny nagłówek, bieżąca pozycja menu pogrubiona i podkreślona.
Prototyp z godłem nie jest serwisem urzędowym. Czcionek nie pobiera z sieci.
"""

import re
from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from oceny.tests.pomocnicze import Zespol
from oceny.tests.test_dostepnosc import STYL, ArkuszStylow

KATALOG = Path(__file__).resolve().parents[2]
KPRM = "Kancelaria Prezesa Rady Ministrów"


def klient(osoba) -> Client:
    przegladarka = Client()
    przegladarka.force_login(osoba.uzytkownik)
    return przegladarka


def naglowek(odpowiedz) -> str:
    strona = odpowiedz.content.decode()
    return strona[strona.index("<header"):strona.index("</header>")]


class PokazKprmTest(SimpleTestCase):
    def test_skrypt_pokazu_ustawia_kprm_i_warszawe(self):
        skrypt = (KATALOG / "uruchom-demo.sh").read_text(encoding="utf-8")

        self.assertIn("ASYSTENT_URZAD:-" + KPRM + "}", skrypt)
        self.assertIn("ASYSTENT_MIEJSCOWOSC:-Warszawa}", skrypt)
        self.assertNotIn("Przykład", skrypt)


class PaletaGovPlTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tresc = STYL.read_text(encoding="utf-8")
        cls.styl = ArkuszStylow(cls.tresc)

    def test_kolory_przewodnie_sa_kolorami_gov_pl(self):
        oczekiwane = {"granat": "#0052a5", "akcent": "#d5233f", "tekst": "#1b1b1b", "tlo": "#ffffff"}
        self.assertEqual({nazwa: self.styl.zmienne.get(nazwa, "").lower() for nazwa in oczekiwane}, oczekiwane)

    def test_naglowek_jest_jasny_a_stopke_otwiera_czerwona_linia(self):
        self.assertEqual((self.styl.tlo(self.styl.deklaracje(".naglowek")) or "").lower(), "#ffffff")
        self.assertIn("var(--akcent)", self.styl.deklaracje(".stopka").get("border-top", ""))

    def test_kroj_pisma_jak_w_gov_pl_bez_pobierania_czcionek(self):
        self.assertTrue(self.styl.deklaracje("body").get("font-family", "").startswith('"Open Sans"'))
        for zakazane in ("@font-face", "@import", "url("):
            self.assertNotIn(zakazane, self.tresc)

    def test_biezaca_pozycja_menu_jest_pogrubiona_i_podkreslona_kolorem_przewodnim(self):
        deklaracje = self.styl.deklaracje('.menu a[aria-current="page"]')
        self.assertEqual(deklaracje.get("font-weight"), "700")
        self.assertEqual(deklaracje.get("border-bottom-color"), "var(--granat)")


@override_settings(ASYSTENT_URZAD=KPRM)
class NaglowekTest(TestCase):
    def setUp(self):
        self.z = Zespol()

    def test_naglowek_pokazuje_nazwe_urzedu(self):
        self.assertIn(KPRM, naglowek(klient(self.z.kadry).get(reverse("zadania"))))

    def test_menu_oznacza_tylko_biezaca_strone(self):
        """4.1.2 i 2.4.8: bieżąca pozycja menu jest oznaczona także dla czytnika ekranu, nie samym wyglądem."""
        przegladarka = klient(self.z.kadry)
        for nazwa in ("zadania", "kadry", "statystyki", "przepisy", "asystent"):
            with self.subTest(strona=nazwa):
                oznaczone = re.findall(r'<a href="([^"]+)" aria-current="page"', naglowek(przegladarka.get(reverse(nazwa))))
                self.assertEqual(oznaczone, [reverse(nazwa)])

    def test_stopka_mowi_ze_to_prototyp_a_nie_serwis_urzedowy(self):
        strona = klient(self.z.ola).get(reverse("zadania")).content.decode()
        stopka = strona[strona.index("<footer"):strona.index("</footer>")]
        self.assertIn("Prototyp", stopka)
        self.assertIn("nie jest serwisem urzędowym", stopka)
