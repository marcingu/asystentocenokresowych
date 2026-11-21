"""Karta kontekstu z EZD RP: fakty o sprawach ocenianego za okres oceny - bez punktów i rankingów.

Zanim karta cokolwiek pokaże, muszą być spełnione warunki Kodeksu pracy (art. 22[2] § 6-8 w zw. z art. 22[3]
§ 3-4 KP): ustalenia pracodawcy, poinformowanie pracowników z dwutygodniowym wyprzedzeniem i informacja dla
pracownika. Wymagania zespołu (architektura v4): karta jawna dla obu stron, tylko ilość i terminowość.
"""

from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse

from asystent_ocen.bledy import BladWalidacji
from asystent_ocen.przebieg import BladUprawnien
from asystent_ocen.wskazniki_pracy import KODY_WSKAZNIKOW
from oceny import uslugi
from oceny.kontekst_ezd import karta_kontekstu
from oceny.models import UstaleniaMonitoringu

from .pomocnicze import DZIEN_OCENY, DZIEN_POTWIERDZENIA, Zespol, pracownik
from .test_widoki import klient

DZIS = date(2026, 6, 1)
USTALENIA = {
    "podstawa": "Regulamin pracy, § 27a.",
    "cele": "Organizacja pracy umożliwiająca pełne wykorzystanie czasu pracy.",
    "zakres": "Liczba i terminowość spraw w EZD RP.",
    "sposob": "Zestawienie zbiorcze za okres oceny.",
}


def ustalenia(poinformowano: date | None = DZIS - timedelta(days=30), wlaczona: bool = True, **zmiany):
    dane = {**USTALENIA, **zmiany}
    return UstaleniaMonitoringu.objects.create(
        integracja_wlaczona=wlaczona, data_poinformowania=poinformowano, **dane
    )


@override_settings(ASYSTENT_TRYB_DEMO=True)
class BramkaKartyTest(TestCase):
    def setUp(self):
        self.z = Zespol(klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-ola")
        self.ocena = self.z.ocena_z_kryteriami()

    def test_bez_ustalen_integracja_jest_wylaczona(self):
        karta = karta_kontekstu(self.ocena, DZIS)
        self.assertEqual((karta.stan, karta.wskazniki), ("WYLACZONA", ()))

    def test_wylaczona_integracja_nie_pokazuje_danych_mimo_kompletu_ustalen(self):
        ustalenia(wlaczona=False)
        self.assertEqual(karta_kontekstu(self.ocena, DZIS).stan, "WYLACZONA")

    def test_brak_ustalen_pracodawcy_blokuje_karte(self):
        """Art. 22[2] § 6 KP: cele, zakres i sposób ustala się w regulaminie, układzie albo obwieszczeniu."""
        ustalenia(cele="", zakres="  ")

        karta = karta_kontekstu(self.ocena, DZIS)

        self.assertEqual(karta.stan, "ZABLOKOWANA")
        self.assertEqual({blad.kod for blad in karta.przeszkody}, {"BRAK_CELOW_MONITORINGU", "BRAK_ZAKRESU_MONITORINGU"})
        self.assertEqual(karta.wskazniki, ())

    def test_przed_uplywem_dwoch_tygodni_od_poinformowania_karta_jest_zablokowana(self):
        """Art. 22[2] § 7 KP: informacja nie później niż 2 tygodnie przed uruchomieniem."""
        ustalenia(poinformowano=DZIS - timedelta(days=13))

        karta = karta_kontekstu(self.ocena, DZIS)

        self.assertEqual(karta.stan, "ZABLOKOWANA")
        self.assertEqual([blad.kod for blad in karta.przeszkody], ["MONITORING_ZA_WCZESNIE"])
        self.assertIn("§ 7", karta.przeszkody[0].podstawa)

    def test_w_czternastym_dniu_po_poinformowaniu_karta_dziala(self):
        ustalenia(poinformowano=DZIS - timedelta(days=14))
        self.assertEqual(karta_kontekstu(self.ocena, DZIS).stan, "GOTOWA")

    def test_pracownik_bez_przekazanej_informacji_nie_jest_objety_karta(self):
        """Art. 22[2] § 8 KP: pracodawca przekazuje pracownikowi informacje o celach, zakresie i sposobie."""
        ustalenia()
        self.z.ola.klauzula_ezd_potwierdzona = False
        self.z.ola.save()

        karta = karta_kontekstu(self.ocena, DZIS)

        self.assertEqual(karta.stan, "ZABLOKOWANA")
        self.assertEqual([blad.kod for blad in karta.przeszkody], ["BRAK_INFORMACJI_DLA_PRACOWNIKA"])
        self.assertIn("§ 8", karta.przeszkody[0].podstawa)

    def test_karta_obejmuje_okres_od_zapoznania_z_kryteriami(self):
        ustalenia()
        z = Zespol.__new__(Zespol)
        z.kadry, z.szef = self.z.kadry, self.z.szef
        z.ola = pracownik("jan", przelozony=z.szef, klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-jan")
        nowa = z.nowa_ocena()

        self.assertEqual(karta_kontekstu(nowa, DZIS).stan, "PRZED_OKRESEM")

    @override_settings(ASYSTENT_TRYB_DEMO=False, ASYSTENT_EZD_ADRES=None)
    def test_poza_trybem_demo_bez_polaczenia_z_ezd_nie_ma_zmyslonych_danych(self):
        ustalenia()

        karta = karta_kontekstu(self.ocena, DZIS)

        self.assertEqual((karta.stan, karta.wskazniki), ("BRAK_ZRODLA", ()))


@override_settings(ASYSTENT_TRYB_DEMO=True)
class TrescKartyTest(TestCase):
    def setUp(self):
        self.z = Zespol(klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-ola")
        self.ocena = self.z.ocena_z_kryteriami()
        ustalenia()

    def test_karta_zawiera_komplet_wskaznikow_rdzenia_za_okres_oceny(self):
        karta = karta_kontekstu(self.ocena, DZIS)

        self.assertEqual(karta.stan, "GOTOWA")
        self.assertEqual([wskaznik["kod"] for wskaznik in karta.wskazniki], list(KODY_WSKAZNIKOW))
        self.assertEqual((karta.od, karta.do), (DZIEN_POTWIERDZENIA, DZIS))
        self.assertTrue(karta.dane_przykladowe)

    def test_po_sporzadzeniu_oceny_okres_konczy_sie_w_dniu_jej_sporzadzenia(self):
        """Przypis do części II arkusza: data „do” oznacza datę sporządzenia oceny."""
        uslugi.sporzadz_ocene(
            self.ocena, self.z.szef.uzytkownik, data_rozmowy=date(2026, 11, 3), oceny=self.z.oceny(7),
            wnioski_iprz="Szkolenie.", data=DZIEN_OCENY,
        )

        karta = karta_kontekstu(self.ocena, date(2026, 11, 20))

        self.assertEqual((karta.od, karta.do), (DZIEN_POTWIERDZENIA, DZIEN_OCENY))

    def test_dane_przykladowe_sa_powtarzalne(self):
        self.assertEqual(karta_kontekstu(self.ocena, DZIS), karta_kontekstu(self.ocena, DZIS))

    def test_karta_nie_ma_oceny_zbiorczej_ani_punktow(self):
        """Architektura v4 i art. 22 RODO: fakty, bez automatycznej punktacji. `liczba` i `jednostka` to ten sam
        fakt w postaci liczbowej - bez żadnej oceny."""
        karta = karta_kontekstu(self.ocena, DZIS)
        for wskaznik in karta.wskazniki:
            self.assertEqual(
                set(wskaznik), {"kod", "nazwa", "wartosc", "liczba", "jednostka", "licznosc", "uwaga", "szczegoly"}
            )
            self.assertNotIn("pkt", wskaznik["wartosc"])

    def test_karte_widza_obie_strony_a_kadry_nie(self):
        adres = reverse("ocena", args=[self.ocena.pk])
        with override_settings(ASYSTENT_DZIS=DZIS.isoformat()):
            for strona in (self.z.szef, self.z.ola):
                odpowiedz = klient(strona).get(adres)
                self.assertContains(odpowiedz, "Kontekst z EZD RP")
                self.assertContains(odpowiedz, "Sprawy zakończone w okresie")
                self.assertContains(odpowiedz, "dane przykładowe")
            odpowiedz = klient(self.z.kadry).get(adres)
            self.assertNotContains(odpowiedz, "Kontekst z EZD RP")
            self.assertNotContains(odpowiedz, "Sprawy zakończone w okresie")

    def test_zablokowana_karta_pokazuje_powod_z_podstawa_prawna(self):
        UstaleniaMonitoringu.objects.update(data_poinformowania=DZIS - timedelta(days=3))
        with override_settings(ASYSTENT_DZIS=DZIS.isoformat()):
            odpowiedz = klient(self.z.szef).get(reverse("ocena", args=[self.ocena.pk]))

        self.assertContains(odpowiedz, "art. 22[2] § 7")
        self.assertNotContains(odpowiedz, "Sprawy zakończone w okresie")


class UstaleniaKadrTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.dane = {**USTALENIA, "data_poinformowania": (DZIS - timedelta(days=20)).isoformat(), "wlaczona": "on"}

    def test_ustalenia_zapisuja_tylko_kadry(self):
        with self.assertRaises(BladUprawnien):
            uslugi.zapisz_ustalenia_monitoringu(
                self.z.szef.uzytkownik, **USTALENIA, data_poinformowania=DZIS, wlaczona=False, data=DZIS
            )
        self.assertEqual(klient(self.z.szef).get(reverse("kadry_ezd")).status_code, 403)
        self.assertEqual(klient(self.z.kadry).get(reverse("kadry_ezd")).status_code, 200)

    def test_integracji_nie_da_sie_wlaczyc_bez_kompletu_ustalen(self):
        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.zapisz_ustalenia_monitoringu(
                self.z.kadry.uzytkownik, podstawa="", cele="", zakres="", sposob="", data_poinformowania=None,
                wlaczona=True, data=DZIS,
            )

        self.assertIn("BRAK_PODSTAWY_MONITORINGU", kontekst.exception.kody)
        self.assertIn("BRAK_POINFORMOWANIA_PRACOWNIKOW", kontekst.exception.kody)
        self.assertFalse(UstaleniaMonitoringu.pobierz().integracja_wlaczona)

    def test_niepelne_ustalenia_mozna_zapisac_roboczo_przy_wylaczonej_integracji(self):
        uslugi.zapisz_ustalenia_monitoringu(
            self.z.kadry.uzytkownik, podstawa="Regulamin pracy, § 27a.", cele="", zakres="", sposob="",
            data_poinformowania=None, wlaczona=False, data=DZIS,
        )
        zapisane = UstaleniaMonitoringu.pobierz()
        self.assertEqual((zapisane.podstawa, zapisane.integracja_wlaczona), ("Regulamin pracy, § 27a.", False))
        self.assertEqual(UstaleniaMonitoringu.objects.count(), 1)

    @override_settings(ASYSTENT_DZIS=DZIS.isoformat())
    def test_formularz_kadr_wlacza_integracje_po_spelnieniu_warunkow(self):
        odpowiedz = klient(self.z.kadry).post(reverse("kadry_ezd"), self.dane, follow=True)

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertTrue(UstaleniaMonitoringu.pobierz().integracja_wlaczona)

    @override_settings(ASYSTENT_DZIS=DZIS.isoformat())
    def test_formularz_kadr_odmawia_wlaczenia_za_wczesnie_i_podaje_date(self):
        self.dane["data_poinformowania"] = (DZIS - timedelta(days=2)).isoformat()

        odpowiedz = klient(self.z.kadry).post(reverse("kadry_ezd"), self.dane, follow=True)

        self.assertContains(odpowiedz, "art. 22[2] § 7")
        self.assertContains(odpowiedz, f"{DZIS + timedelta(days=12):%d.%m.%Y}")
        self.assertFalse(UstaleniaMonitoringu.pobierz().integracja_wlaczona)
