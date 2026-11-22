"""Zaplecze administratora: jeden układ wszystkich stron, struktura urzędu jako drzewo i ikona strony z logo.

Wymagania prowadzącego projekt (22.11.2026): poukładać panel administracyjny, strukturę pokazać w sposób zbliżony do
EZD (drzewo: urząd - komórki organizacyjne - stanowiska z osobami), zrobić ikonę strony z logo urzędu.
"""

import base64
import re
from io import BytesIO

from django.test import Client
from django.urls import reverse
from PIL import Image

from oceny.models import OznaczenieUrzedu, Wydzial

from .dostepnosc_html import bledy_dostepnosci
from .test_administracja import Podstawa
from .test_widoki import klient

STRUKTURA = "/administracja/wydzialy/"
MENU = '<nav class="zaplecze-menu" aria-label="Zaplecze administratora">'


def fragment(html: str, poczatek: str, koniec: str) -> str:
    start = html.index(poczatek)
    return html[start:html.index(koniec, start)]


def logo(szerokosc: int = 120, wysokosc: int = 60) -> str:
    bufor = BytesIO()
    Image.new("RGBA", (szerokosc, wysokosc), (0, 82, 165, 255)).save(bufor, format="PNG")
    return base64.b64encode(bufor.getvalue()).decode("ascii")


class UkladZapleczaTest(Podstawa):
    def strony(self):
        konto = reverse("administracja_konto", args=[self.z.ola.uzytkownik.pk])
        return (
            # adres, pozycja zaznaczona w menu zaplecza, nagłówek strony
            (reverse("administracja"), reverse("administracja"), "Konta użytkowników"),
            (konto, reverse("administracja"), "Konto ola"),
            (reverse("administracja_nowe_konto"), reverse("administracja"), "Nowe konto"),
            (STRUKTURA, STRUKTURA, "Struktura urzędu"),
            (reverse("administracja_urzad"), reverse("administracja_urzad"), "Oznaczenie urzędu"),
            (reverse("administracja_poczta"), reverse("administracja_poczta"), "Poczta i przypomnienia"),
            (reverse("przepisy"), reverse("przepisy"), "Konfiguracja procesu"),
            (reverse("administracja_dziennik"), reverse("administracja_dziennik"), "Dziennik zdarzeń bezpieczeństwa"),
            (reverse("administracja_dziennik") + "?dziennik=proces", reverse("administracja_dziennik") + "?dziennik=proces",
             "Czynności w procesie oceny"),
        )

    def test_kazda_strona_zaplecza_ma_to_samo_menu_okruszki_i_naglowek(self):
        for adres, zaznaczona, naglowek in self.strony():
            with self.subTest(adres=adres):
                html = self.przegladarka.get(adres).content.decode()

                menu = fragment(html, MENU, "</nav>")
                self.assertEqual(re.findall(r'<a href="([^"]+)" aria-current="page"', menu), [zaznaczona])
                for grupa in ("Ludzie i struktura", "Urząd i konfiguracja", "Dzienniki"):
                    self.assertIn(grupa, menu)
                self.assertEqual(len(re.findall(r"<a ", menu)), 7)
                self.assertEqual(re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S), [naglowek])
                self.assertIn(f'<p class="okruszki"><a href="{reverse("administracja")}">Administracja</a> / ', html)
                self.assertIn("<title>Administracja - ", html)
                glowne = fragment(html, 'aria-label="Menu główne"', "</nav>")
                self.assertEqual(re.findall(r'<a href="([^"]+)" aria-current="page"', glowne), [reverse("administracja")])
                self.assertEqual(bledy_dostepnosci(html), [])

    def test_menu_zaplecza_stoi_przed_naglowkiem_w_jednym_ukladzie(self):
        for adres, _, _ in self.strony():
            html = self.przegladarka.get(adres).content.decode()
            self.assertLess(html.index('<div class="zaplecze">'), html.index(MENU), adres)
            self.assertLess(html.index(MENU), html.index('<div class="zaplecze-tresc">'), adres)
            self.assertLess(html.index('<div class="zaplecze-tresc">'), html.index("<h1"), adres)

    def test_przepisy_do_odczytu_nie_pokazuja_zaplecza(self):
        html = klient(self.z.kadry).get(reverse("przepisy")).content.decode()

        self.assertNotIn("zaplecze-menu", html)
        self.assertIn("<h1>Przepisy, na których działa system</h1>", html)
        glowne = fragment(html, 'aria-label="Menu główne"', "</nav>")
        self.assertEqual(re.findall(r'<a href="([^"]+)" aria-current="page"', glowne), [reverse("przepisy")])

    def test_administrator_ma_przepisy_w_zapleczu_a_nie_drugi_raz_w_menu_glownym(self):
        glowne = fragment(self.przegladarka.get(reverse("zadania")).content.decode(), 'aria-label="Menu główne"', "</nav>")

        self.assertNotIn(reverse("przepisy"), glowne)
        self.assertIn(reverse("administracja"), glowne)


class DrzewoStrukturyTest(Podstawa):
    """Struktura jak w EZD: urząd - komórki organizacyjne - stanowiska z osobami; gałęzie zwinięte do rozwinięcia."""

    def setUp(self):
        super().setUp()
        self.wydzial = self.z.ola.wydzial
        self.wydzial.kierownik, self.wydzial.zwierzchnik = self.z.szef, self.z.kadry
        self.wydzial.save()
        self.pusta = Wydzial.objects.create(nazwa="Biuro Informatyki")

    def html(self, adres=STRUKTURA):
        return self.przegladarka.get(adres).content.decode()

    def drzewo(self, html):
        return fragment(html, '<ul class="drzewo"', 'id="nowy-wydzial"')

    def galaz(self, html, wydzial):
        drzewo = self.drzewo(html)
        start = drzewo.index(f'<details class="galaz" id="wydzial-{wydzial.pk}"')
        koniec = drzewo.find('<details class="galaz"', start + 1)
        return drzewo[start:koniec if koniec != -1 else len(drzewo)]

    def test_korzeniem_drzewa_jest_urzad_a_galeziami_komorki(self):
        html = self.html()

        drzewo = self.drzewo(html)
        self.assertIn('<span class="korzen">', drzewo)
        self.assertIn(OznaczenieUrzedu.aktualne().nazwa, fragment(drzewo, '<span class="korzen">', "</span>"))
        self.assertEqual(drzewo.count('<details class="galaz"'), Wydzial.objects.count())
        self.assertNotIn("<details class=\"galaz\" open", drzewo)   # jak w EZD: gałęzie są zwinięte
        self.assertEqual(bledy_dostepnosci(html), [])

    def test_galaz_pokazuje_kierujacego_i_stanowiska_z_osobami(self):
        galaz = self.galaz(self.html(), self.wydzial)

        naglowek = fragment(galaz, "<summary>", "</summary>")
        self.assertIn(self.wydzial.nazwa, naglowek)
        self.assertIn("4 osoby", naglowek)                      # kadry, szef, ola, obcy
        kierujacy = fragment(galaz, '<li class="stanowisko stanowisko-kierujacy">', "</li>")
        self.assertIn("naczelnik wydziału", kierujacy)
        self.assertIn("Testowy Szef", kierujacy)               # nazwisko przed imieniem, jak w EZD
        self.assertIn("kieruje komórką", kierujacy)
        pozostale = re.findall(r'<li class="stanowisko">(.*?)</li>', galaz, re.S)
        self.assertEqual(len(pozostale), 3)
        self.assertTrue(any("Testowy Ola" in wiersz and "specjalista" in wiersz for wiersz in pozostale))
        self.assertNotIn("Testowy Szef", "".join(pozostale))   # kierujący nie jest wypisany drugi raz

    def test_komorka_bez_obsady_mowi_to_wprost(self):
        galaz = self.galaz(self.html(), self.pusta)

        self.assertIn("brak osób", fragment(galaz, "<summary>", "</summary>"))
        self.assertIn("Nie wyznaczono osoby kierującej", galaz)
        self.assertIn("Usuń pustą komórkę", galaz)
        self.assertNotIn("Usuń pustą komórkę", self.galaz(self.html(), self.wydzial))

    def test_formularze_komorki_sa_w_jej_galezi_i_po_zapisie_galaz_zostaje_otwarta(self):
        galaz = self.galaz(self.html(), self.wydzial)
        for pole in ('name="nazwa"', 'name="kierownik"', 'name="zwierzchnik"', 'value="obsada"', 'value="zmien"'):
            self.assertIn(pole, galaz)

        odpowiedz = self.przegladarka.post(STRUKTURA, {
            "akcja": "obsada", "pk": self.pusta.pk, "kierownik": self.z.szef.pk, "zwierzchnik": "",
        })

        self.assertRedirects(odpowiedz, f"{STRUKTURA}?otwarta={self.pusta.pk}#wydzial-{self.pusta.pk}", fetch_redirect_response=False)
        html = self.html(f"{STRUKTURA}?otwarta={self.pusta.pk}")
        self.assertIn(f'<details class="galaz" id="wydzial-{self.pusta.pk}" open>', html)
        self.assertEqual(len(re.findall(r'<details class="galaz" id="wydzial-\d+" open>', html)), 1)
        self.assertIn("Testowy Szef", self.galaz(html, self.pusta))

    def test_po_bledzie_galaz_zostaje_otwarta_a_strona_wraca_do_komunikatu(self):
        """Kotwica gałęzi przewinęłaby stronę poniżej komunikatu o błędzie - błąd prowadzi więc na początek treści."""
        zajeta = self.wydzial.nazwa
        for dane in ({"akcja": "zmien", "nazwa": zajeta}, {"akcja": "zmien", "nazwa": "  "}, {"akcja": "obsada", "kierownik": "999999"}):
            odpowiedz = self.przegladarka.post(STRUKTURA, {"pk": self.pusta.pk, **dane})

            self.assertRedirects(odpowiedz, f"{STRUKTURA}?otwarta={self.pusta.pk}#tresc", fetch_redirect_response=False, msg_prefix=str(dane))
        self.pusta.refresh_from_db()
        self.assertEqual((self.pusta.nazwa, self.pusta.kierownik_id), ("Biuro Informatyki", None))
        for dane in ({"akcja": "dodaj", "nazwa": ""}, {"akcja": "nieznana"}, {"akcja": "zmien", "pk": "abc", "nazwa": "X"}):
            self.assertRedirects(self.przegladarka.post(STRUKTURA, dane), f"{STRUKTURA}#tresc", fetch_redirect_response=False, msg_prefix=str(dane))

    def test_bledny_parametr_otwarcia_nie_wywraca_strony(self):
        for wartosc in ("abc", "999999", "", "1 OR 1=1"):
            self.assertEqual(self.przegladarka.get(STRUKTURA, {"otwarta": wartosc}).status_code, 200, wartosc)

    def test_dodawanie_i_lista_kprm_sa_pod_drzewem(self):
        html = self.html()

        self.assertLess(html.index('<ul class="drzewo"'), html.index("Dodaj komórkę organizacyjną"))
        self.assertLess(html.index("Dodaj komórkę organizacyjną"), html.index("Wczytaj brakujące komórki KPRM"))


class IkonaStronyTest(Podstawa):
    ADRES = "/favicon.png"

    def test_kazda_strona_wskazuje_ikone_takze_przed_zalogowaniem(self):
        for odpowiedz in (Client().get(reverse("logowanie")), self.przegladarka.get(reverse("zadania"))):
            self.assertRegex(odpowiedz.content.decode(), r'<link rel="icon" href="/favicon\.png\?v=[0-9a-f]{8}">')

    def test_ikona_powstaje_z_logo_urzedu_jako_kwadrat(self):
        OznaczenieUrzedu.objects.create(pk=1, nazwa="Urząd", logo_png=logo(120, 60))

        odpowiedz = Client().get(self.ADRES)      # bez logowania - ikonę pobiera też strona logowania

        self.assertEqual((odpowiedz.status_code, odpowiedz["Content-Type"]), (200, "image/png"))
        obraz = Image.open(BytesIO(odpowiedz.content))
        self.assertEqual((obraz.size, obraz.mode), ((64, 64), "RGBA"))
        self.assertEqual(obraz.getpixel((32, 32)), (0, 82, 165, 255))   # logo w środku
        self.assertEqual(obraz.getpixel((32, 2))[3], 0)                 # dopełnienie do kwadratu jest przezroczyste
        self.assertIn("max-age", odpowiedz["Cache-Control"])

    def test_bez_logo_ikona_jest_godlem_domyslnym(self):
        odpowiedz = Client().get(self.ADRES)

        self.assertEqual((odpowiedz.status_code, odpowiedz["Content-Type"]), (200, "image/svg+xml"))
        self.assertIn(b"<svg", odpowiedz.content)

    def test_zmiana_logo_zmienia_adres_ikony(self):
        przed = re.search(r"favicon\.png\?v=([0-9a-f]{8})", Client().get(reverse("logowanie")).content.decode()).group(1)
        OznaczenieUrzedu.objects.create(pk=1, nazwa="Urząd", logo_png=logo())

        po = re.search(r"favicon\.png\?v=([0-9a-f]{8})", Client().get(reverse("logowanie")).content.decode()).group(1)

        self.assertNotEqual(przed, po)

    def test_uszkodzone_logo_nie_wywraca_ikony(self):
        OznaczenieUrzedu.objects.create(pk=1, nazwa="Urząd", logo_png="to-nie-jest-obraz")

        odpowiedz = Client().get(self.ADRES)

        self.assertEqual((odpowiedz.status_code, odpowiedz["Content-Type"]), (200, "image/svg+xml"))
