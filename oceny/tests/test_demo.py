"""Dane demonstracyjne: fikcyjny urząd z ocenami na każdym etapie, budowany względem dzisiejszej daty.

Dane powstają tymi samymi usługami, z których korzysta aplikacja - pokaz nie omija żadnej reguły rdzenia.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from asystent_ocen.przebieg import Etap
from oceny.kontekst_ezd import karta_kontekstu
from oceny.models import Ocena, Pracownik, UstaleniaMonitoringu
from oceny.zadania import skutki_oceny_zakonczonej, zadania_uzytkownika


def zaladuj(dzien: str = "2026-11-21") -> None:
    call_command("demo", dzis=dzien, verbosity=0)


class DaneDemoTest(TestCase):
    def test_jan_ma_arkusz_pierwszej_oceny(self):
        zaladuj()
        jan = Pracownik.objects.get(uzytkownik__username="jan")
        self.assertTrue(hasattr(jan, "umowa"))
        self.assertEqual(jan.umowa.pierwsza.szef, jan.przelozony)

    def test_powstaja_oceny_na_kazdym_etapie(self):
        zaladuj()
        etapy = set(Ocena.objects.values_list("etap", flat=True))
        self.assertEqual(etapy, {etap.name for etap in Etap})

    def test_konta_demo_nie_maja_hasel_ani_dostepu_do_panelu_django(self):
        """Jedynym kontem z uprawnieniami administratora jest administrator pokazu - do obejrzenia zaplecza."""
        zaladuj()
        konta = get_user_model().objects.all()
        self.assertGreaterEqual(konta.count(), 8)
        for konto in konta:
            self.assertFalse(konto.has_usable_password(), konto.username)
            self.assertFalse(konto.is_staff, konto.username)
        self.assertEqual([konto.username for konto in konta.filter(is_superuser=True)], ["administrator"])

    def test_polecenie_odmawia_pracy_na_bazie_z_danymi(self):
        """Polecenie niczego nie usuwa - na niepustej bazie nie robi nic."""
        zaladuj()
        liczba = Pracownik.objects.count()
        with self.assertRaises(CommandError):
            zaladuj()
        self.assertEqual(Pracownik.objects.count(), liczba)

    def test_sa_osoby_ktore_nie_podlegaja_ocenie_i_osoba_bez_rozpoczetego_cyklu(self):
        zaladuj()
        osoby = list(Pracownik.objects.all())
        self.assertTrue(any(not osoba.podlega_ocenie for osoba in osoby))
        self.assertTrue(any(osoba.podlega_ocenie and not osoba.oceny.exists() for osoba in osoby))

    def test_przelozony_ma_zadanie_pilne_i_zadanie_po_terminie(self):
        zaladuj()
        naczelnik = get_user_model().objects.get(username="naczelnik")
        stany = {zadanie.stan for zadanie in zadania_uzytkownika(naczelnik, date(2026, 11, 21))}
        self.assertLessEqual({"pilne", "po_terminie"}, stany)

    def test_bohaterka_pokazu_ma_poprzednia_ocene_na_najwyzszym_poziomie(self):
        """Druga taka ocena z rzędu da stopień służbowy z mocy prawa (art. 89 ust. 2 u.s.c.)."""
        zaladuj()
        biezaca = Pracownik.objects.get(uzytkownik__username="anna").biezaca_ocena()
        self.assertEqual(biezaca.etap, "OCENIANIE")
        self.assertEqual((biezaca.poprzednia.wynik, biezaca.poprzednia.poziom), ("POZYTYWNA", "powyżej oczekiwań"))
        self.assertGreaterEqual(len(biezaca.proces().notatki), 3)
        self.assertNotIn("STOPIEN_OBLIGATORYJNY", {s.kod for s in skutki_oceny_zakonczonej(biezaca.poprzednia)})

    def test_notatki_pokazowe_obejmuja_osiagniecia_i_wyniki_egzaminu(self):
        """Pokaz ma dodatkowe osiągnięcie u bohaterki oraz egzamin ze służby przygotowawczej u dwóch nowych osób:
        zdany w pierwszym terminie i po egzaminie poprawkowym."""
        zaladuj()

        def notatki(login: str, rodzaj: str) -> list[str]:
            proces = Pracownik.objects.get(uzytkownik__username=login).biezaca_ocena().proces()
            return [notatka.tresc for notatka in proces.notatki if notatka.rodzaj == rodzaj]

        self.assertEqual(len(notatki("anna", "osiagniecie")), 1)
        self.assertIn("w pierwszym terminie", notatki("katarzyna", "egzamin")[0])
        self.assertIn("po egzaminie poprawkowym", notatki("piotr", "egzamin")[0])

    def test_strona_danych_z_ezd_rp_bohaterki_wskazuje_ocene_z_faktow(self):
        """Anna: 100% spraw w terminie (9) i 92% projektów przyjętych za pierwszym razem (7) - remis rozstrzyga się
        w dół, więc fakty wskazują na 7 w kryterium „Rzetelność”; o pozostałych sześciu kryteriach EZD RP milczy."""
        zaladuj()
        anna = Client()
        anna.force_login(get_user_model().objects.get(username="anna"))

        with override_settings(ASYSTENT_TRYB_DEMO=True, ASYSTENT_DZIS="2026-11-21"):
            odpowiedz = anna.get(reverse("moje_dane_ezd"))

        (wskazanie,) = odpowiedz.context["ezd"]["wskazania"]
        self.assertEqual((wskazanie["kryterium"], wskazanie["ocena"]), ("Rzetelność", 7))
        self.assertEqual([(fakt["wartosc"], fakt["ocena"]) for fakt in wskazanie["fakty"]], [("100%", 9), ("92%", 7)])
        self.assertEqual(len(odpowiedz.context["kryteria"]), 7)

    def test_ustalenia_dotyczace_danych_z_ezd_rp_sa_wpisane(self):
        zaladuj()
        ustalenia = UstaleniaMonitoringu.pobierz()
        self.assertTrue(ustalenia.integracja_wlaczona)
        self.assertIsNotNone(ustalenia.data_poinformowania)

    def test_karta_z_ezd_rp_zgadza_sie_z_uzasadnieniem_oceny_w_danych_pokazowych(self):
        """Uzasadnienie mówi o 11 z 34 spraw załatwionych po terminie - karta faktów pokazuje to samo."""
        zaladuj()
        ocena = Pracownik.objects.get(uzytkownik__username="marek").biezaca_ocena()

        with override_settings(ASYSTENT_TRYB_DEMO=True):
            karta = karta_kontekstu(ocena, date(2026, 11, 21))

        wartosci = {wskaznik["kod"]: wskaznik["wartosc"] for wskaznik in karta.wskazniki}
        self.assertEqual((wartosci["SPRAWY_ZAKONCZONE"], wartosci["TERMINOWOSC"]), ("34", "68%"))
        self.assertIn("11 z 34 spraw", ocena.proces().formularz.uzasadnienie)

    def _sprawdz_date(self, dzien: str) -> None:
        zaladuj(dzien)
        self.assertEqual(set(Ocena.objects.values_list("etap", flat=True)), {etap.name for etap in Etap})

    # Daty są względne - pokaz działa także w dzień wolny, przy świętach i w lutym roku przestępnego.
    def test_dane_dla_niedzieli(self):
        self._sprawdz_date("2026-11-22")

    def test_dane_dla_konca_roku(self):
        self._sprawdz_date("2026-12-28")

    def test_dane_dla_poczatku_roku(self):
        self._sprawdz_date("2027-01-04")

    def test_dane_dla_29_lutego(self):
        self._sprawdz_date("2028-02-29")

    def test_dane_dla_swieta(self):
        self._sprawdz_date("2027-05-03")


@override_settings(ASYSTENT_TRYB_DEMO=True, ASYSTENT_DZIS="2026-11-21")
class PrzegladStronDemoTest(TestCase):
    """Każda strona otwiera się dla każdego konta pokazowego - na danych z każdego etapu procesu."""

    @classmethod
    def setUpTestData(cls):
        zaladuj()

    def test_kazde_czynne_konto_otwiera_swoje_strony_a_zawieszone_nie_wchodzi(self):
        for konto in get_user_model().objects.all():
            klient = Client()
            odpowiedz = klient.post(reverse("demo_zaloguj"), {"login": konto.username})
            if not konto.is_active:  # konto zawieszone za brak aktywności - odblokowuje je administrator
                self.assertEqual(odpowiedz.status_code, 404, konto.username)
                continue
            self.assertEqual(odpowiedz.status_code, 302, konto.username)
            ma_podglad = konto.username in ("administrator", "kadry", "dyrektor")
            self.assertEqual(klient.get(reverse("przepisy")).status_code, 200 if ma_podglad else 403)
            for nazwa in ("zadania", "asystent"):
                self.assertEqual(klient.get(reverse(nazwa)).status_code, 200, f"{konto.username}: {nazwa}")

    def test_kazda_karta_oceny_otwiera_sie_dla_kazdej_strony_procesu(self):
        kadry = get_user_model().objects.get(username="kadry")
        for ocena in Ocena.objects.select_related("oceniany__uzytkownik", "oceniajacy__uzytkownik"):
            for konto in (ocena.oceniany.uzytkownik, ocena.oceniajacy.uzytkownik, kadry):
                if not konto.is_active:
                    continue
                klient = Client()
                klient.force_login(konto)
                odpowiedz = klient.get(reverse("ocena", args=[ocena.pk]))
                self.assertEqual(odpowiedz.status_code, 200, f"{konto.username}: ocena {ocena.pk} ({ocena.etap})")

    def test_arkusz_kazdej_oceny_daje_sie_wydrukowac(self):
        kadry = get_user_model().objects.get(username="kadry")
        klient = Client()
        klient.force_login(kadry)
        for ocena in Ocena.objects.all():
            odpowiedz = klient.get(reverse("arkusz_docx", args=[ocena.pk]))
            self.assertEqual(odpowiedz.status_code, 200, f"ocena {ocena.pk} ({ocena.etap})")
            # Kalendarz: plik albo - gdy na danym etapie nie biegnie żaden termin - powrót na kartę oceny.
            self.assertIn(klient.get(reverse("kalendarz", args=[ocena.pk])).status_code, (200, 302))

    def test_panel_kadr_i_statystyki_dzialaja_na_danych_demo(self):
        klient = Client()
        klient.force_login(get_user_model().objects.get(username="kadry"))
        self.assertContains(klient.get(reverse("kadry")), "Rozpocznij cykl oceny")
        self.assertContains(klient.get(reverse("statystyki")), "Wydział Organizacyjny")

    def test_pasek_demo_pozwala_przelaczac_konta(self):
        klient = Client()
        klient.force_login(get_user_model().objects.get(username="anna"))
        self.assertContains(klient.get(reverse("zadania")), "Tryb demonstracyjny")
