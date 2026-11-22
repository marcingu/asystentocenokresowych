"""Dobre praktyki zarządcze: podpowiedzi dla przełożonego w formularzach oceny i na przeglądzie współpracy.

Wymaganie (opis wyzwania KPRM, pkt 1): asystent wspiera przełożonych w części rozwojowej oceny - podpowiada, jak
formułować konstruktywną informację zwrotną, jak opisywać mocne strony i obszary do rozwoju oraz jak przekładać
wyniki oceny na codzienne zarządzanie zespołem. Treść opiera się na Poradniku KPRM „Oceny okresowe w służbie
cywilnej” (pkt 6.2.3, 6.2.4, 6.2.5.3 i 6.2.5.4). Decyzja projektowa: to stałe teksty, nie odpowiedzi modelu;
widzi je tylko osoba, która wypełnia formularz - oceniający albo bezpośredni przełożony.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from oceny import dobre_praktyki

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import Zespol
from .test_widoki import klient

ZWROTNA = "Dobre praktyki: jak formułować konstruktywną informację zwrotną"
MOCNE = "Dobre praktyki: jak opisywać mocne strony i obszary do rozwoju"
ZARZADZANIE = "Dobre praktyki: jak przełożyć wynik oceny na codzienne zarządzanie zespołem"
ROZMOWA = "Dobre praktyki: jak prowadzić rozmowę z pracownikiem"
NOTATKA = "Dobre praktyki: jak pisać notatkę"


class TrescTest(TestCase):
    def test_kazda_praktyka_ma_wskazowki_i_przyklad(self):
        self.assertEqual(set(dobre_praktyki.PRAKTYKI), {"informacja_zwrotna", "mocne_strony", "zarzadzanie", "rozmowa", "notatka"})
        for kod, praktyka in dobre_praktyki.PRAKTYKI.items():
            with self.subTest(kod=kod):
                self.assertGreaterEqual(len(praktyka.wskazowki), 3)
                self.assertTrue(praktyka.zamiast and praktyka.napisz)
                for tekst in (*praktyka.wskazowki, praktyka.zamiast, praktyka.napisz):
                    self.assertNotIn(" – ", tekst)  # w interfejsie zwykły dywiz

    def test_trzy_tematy_z_opisu_wyzwania_powoluja_poradnik(self):
        zrodla = {kod: dobre_praktyki.PRAKTYKI[kod].zrodlo for kod in ("informacja_zwrotna", "mocne_strony", "zarzadzanie")}
        self.assertIn("pkt 6.2.5.3", zrodla["informacja_zwrotna"])
        self.assertIn("pkt 6.2.5.4", zrodla["mocne_strony"])
        self.assertIn("pkt 6.2.3", zrodla["zarzadzanie"])


@override_settings(ASYSTENT_DZIS="2026-11-02")
class KartaOcenyTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()  # etap: rozmowa oceniająca i dokonanie oceny
        self.karta = reverse("ocena", args=[self.ocena.pk])

    def test_oceniajacy_ma_podpowiedzi_przy_polach_formularza_oceny(self):
        html = klient(self.z.szef).get(self.karta).content.decode()

        for tytul in (ZWROTNA, MOCNE, ZARZADZANIE, ROZMOWA, NOTATKA):
            self.assertIn(f"<summary>{tytul}</summary>", html)
        # podpowiedź stoi przy polu, którego dotyczy
        self.assertLess(html.index('id="uzasadnienie"'), html.index(ZWROTNA))
        self.assertLess(html.index(ZWROTNA), html.index('id="wnioski_iprz"'))
        self.assertLess(html.index('id="wnioski_iprz"'), html.index(ZARZADZANIE))
        self.assertIn("Podpowiedź dla przełożonego, nie przepis.", html)
        self.assertEqual(bledy_dostepnosci(html), [])

    def test_oceniany_i_kadry_nie_widza_podpowiedzi_dla_przelozonego(self):
        for osoba in (self.z.ola, self.z.kadry):
            with self.subTest(osoba=osoba.uzytkownik.username):
                self.assertNotContains(klient(osoba).get(self.karta), "Dobre praktyki")

    def test_przeglad_wspolpracy_zbiera_wszystkie_praktyki(self):
        html = klient(self.z.szef).get(reverse("przeglad_wspolpracy", args=[self.z.ola.pk])).content.decode()

        self.assertIn('<h2 id="n-praktyki">Dobre praktyki zarządcze</h2>', html)
        for tytul in (ZWROTNA, MOCNE, ZARZADZANIE, ROZMOWA, NOTATKA):
            self.assertIn(f"<summary>{tytul}</summary>", html)
        self.assertEqual(bledy_dostepnosci(html), [])

    def test_szybka_notatka_ma_podpowiedz_o_notatce(self):
        html = klient(self.z.szef).get(reverse("nowa_notatka", args=[self.ocena.pk])).content.decode()

        self.assertIn(f"<summary>{NOTATKA}</summary>", html)
        self.assertNotIn(ZWROTNA, html)


class PierwszyEtapTest(TestCase):
    def test_przy_wyznaczaniu_kryteriow_jest_podpowiedz_o_rozmowie(self):
        z = Zespol()
        ocena = z.nowa_ocena()

        html = klient(z.szef).get(reverse("ocena", args=[ocena.pk])).content.decode()

        self.assertIn(f"<summary>{ROZMOWA}</summary>", html)
        self.assertNotContains(klient(z.ola).get(reverse("ocena", args=[ocena.pk])), "Dobre praktyki")
