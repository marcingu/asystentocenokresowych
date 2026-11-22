"""Partner HR na karcie oceny i w przeglądzie współpracy: obraz sytuacji, działania do rozmowy, docenianie.

Wymaganie (prowadzący projekt, 22.11.2026): moduł wspiera przełożonego w zarządzaniu ludźmi - nie ocenia pracownika,
prowadzi do rozmowy, podpowiada działania realne w służbie cywilnej i konkretną formę docenienia.
Reguły sygnałów i ich podstawy - `tests/test_partner_hr.py`.

Decyzje projektowe: sygnały i działania wynikają z danych pracownika, więc widzą je obie strony - tak jak karty
Radaru (bez ukrytego profilowania; rozmowa ma być partnerska). Tylko przełożony ma odnośniki do notatek i podpowiedzi
o prowadzeniu rozmowy. Notatka z działania ma gotowy początek i właściwy rodzaj. Sygnałów nie układa model językowy.
"""

from django.test import override_settings
from django.urls import reverse

from asystent_ocen import partner_hr
from oceny.models import UstaleniaMonitoringu
from oceny.radar import radar_oceny

from .dostepnosc_html import bledy_dostepnosci
from .test_radar import DZIEN, Podstawa
from .test_widoki import klient

NAGLOWEK = '<h3 id="n-partner">Partner HR - obraz sytuacji i możliwe działania</h3>'


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_TRYB_DEMO=True)
class PartnerNaKarcieOcenyTest(Podstawa):
    def sygnaly(self):
        return radar_oceny(self.ocena, DZIEN).partner

    def test_obie_strony_widza_ten_sam_obraz_sytuacji_i_te_same_dzialania(self):
        sygnaly = self.sygnaly()
        self.assertEqual([sygnal.kod for sygnal in sygnaly],
                         ["ODKLADANY_WYPOCZYNEK", "SZERSZY_ZAKRES_ZADAN", "DOBRE_WYNIKI_PRZY_OBCIAZENIU", "MOMENT_NA_DOCENIENIE"])
        for osoba in (self.z.szef, self.z.ola):
            with self.subTest(osoba=osoba.uzytkownik.username):
                html = klient(osoba).get(self.karta).content.decode()
                self.assertIn(NAGLOWEK, html)
                for sygnal in sygnaly:
                    self.assertIn(f"<h4>{sygnal.tytul}</h4>", html)
                    self.assertIn(sygnal.obserwacja, html)
                    self.assertIn(sygnal.rozmowa, html)
                    for dzialanie in sygnal.dzialania:
                        self.assertIn(dzialanie.tekst, html)
                        self.assertIn(dzialanie.podstawa, html)
                self.assertIn("to nie jest system AI", html)
                self.assertIn("nie ocenia pracownika", html)
                self.assertIn(partner_hr.STANDARDY, html)
                self.assertEqual(bledy_dostepnosci(html), [])

    def test_zasady_partnera_sa_jawne_dla_obu_stron(self):
        for osoba in (self.z.szef, self.z.ola):
            html = klient(osoba).get(self.karta).content.decode()
            self.assertIn("<summary>Zasady, którymi kieruje się partner HR</summary>", html)
            self.assertIn(partner_hr.CEL, html)
            for zasada in partner_hr.ZASADY:
                self.assertIn(zasada, html)

    def test_tylko_przelozony_ma_odnosniki_do_notatek_i_podpowiedzi_o_rozmowie(self):
        nowa = reverse("nowa_notatka", args=[self.ocena.pk])
        szef = klient(self.z.szef).get(self.karta).content.decode()
        ola = klient(self.z.ola).get(self.karta).content.decode()

        for sygnal in self.sygnaly():
            for numer, _ in enumerate(sygnal.dzialania):
                self.assertIn(f'href="{nowa}?sygnal={sygnal.kod}&amp;dzialanie={numer}"', szef)
        self.assertIn('aria-label="Zanotuj ustalenie - Odkładany wypoczynek, działanie 1"', szef)
        self.assertNotIn("?sygnal=", ola)
        for tytul in ("jak rozmawiać o obciążeniu i organizacji pracy", "jak doceniać, żeby to działało"):
            self.assertIn(f"<summary>Dobre praktyki: {tytul}</summary>", szef)
        self.assertNotIn("Dobre praktyki", ola)

    def test_notatka_z_dzialania_ma_gotowy_poczatek_i_wlasciwy_rodzaj(self):
        nowa = reverse("nowa_notatka", args=[self.ocena.pk])
        szef = klient(self.z.szef)
        wypoczynek, *_, docenienie = self.sygnaly()

        dobrostan = szef.get(f"{nowa}?sygnal=ODKLADANY_WYPOCZYNEK&dzialanie=0")
        self.assertEqual(dobrostan.context["wybrany_rodzaj"], "dobrostan")
        self.assertEqual(dobrostan.context["tresc_notatki"], f"Odkładany wypoczynek: {wypoczynek.dzialania[0].tekst} ")
        self.assertContains(dobrostan, wypoczynek.dzialania[0].tekst)
        self.assertEqual(bledy_dostepnosci(dobrostan.content.decode()), [])

        uznanie = szef.get(f"{nowa}?sygnal=MOMENT_NA_DOCENIENIE&dzialanie=1")
        self.assertEqual(uznanie.context["wybrany_rodzaj"], "osiagniecie")
        self.assertIn(docenienie.dzialania[1].tekst, uznanie.context["tresc_notatki"])

    def test_nieznany_sygnal_albo_dzialanie_daje_pusty_formularz_a_nie_blad(self):
        nowa = reverse("nowa_notatka", args=[self.ocena.pk])
        szef = klient(self.z.szef)
        for parametry in ("sygnal=NIE_MA&dzialanie=0", "sygnal=ODKLADANY_WYPOCZYNEK&dzialanie=99",
                          "sygnal=ODKLADANY_WYPOCZYNEK&dzialanie=x", "sygnal=ODKLADANY_WYPOCZYNEK&dzialanie=-1", "sygnal=ODKLADANY_WYPOCZYNEK"):
            with self.subTest(parametry=parametry):
                odpowiedz = szef.get(f"{nowa}?{parametry}")
                self.assertEqual(odpowiedz.status_code, 200)
                self.assertEqual(odpowiedz.context["tresc_notatki"], "")

    def test_bez_danych_radaru_partner_niczego_nie_pokazuje(self):
        UstaleniaMonitoringu.objects.update(integracja_wlaczona=False)

        self.assertEqual(self.sygnaly(), ())
        self.assertNotContains(klient(self.z.szef).get(self.karta), "Partner HR")

    def test_przeglad_wspolpracy_pokazuje_partnera_i_wraca_po_notatce_na_przeglad(self):
        html = klient(self.z.szef).get(reverse("przeglad_wspolpracy", args=[self.z.ola.pk])).content.decode()
        nowa = reverse("nowa_notatka", args=[self.ocena.pk])

        self.assertIn(NAGLOWEK.replace("<h3", "<h2").replace("</h3>", "</h2>"), html)
        for sygnal in self.sygnaly():
            self.assertIn(sygnal.obserwacja, html)
        self.assertIn(f'href="{nowa}?sygnal=MOMENT_NA_DOCENIENIE&amp;dzialanie=0&amp;powrot=przeglad"', html)
        self.assertEqual(bledy_dostepnosci(html), [])
