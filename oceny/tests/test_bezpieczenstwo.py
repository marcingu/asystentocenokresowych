"""Bezpieczeństwo kont: kody jednorazowe TOTP, dziennik zdarzeń, blokada po nieudanych próbach i zawieszanie
kont bez aktywności.

Wymagania:
- § 19 ust. 2 pkt 4, 5 i 7 rozporządzenia KRI (Dz. U. z 2024 r. poz. 773): stosowne uprawnienia, bezzwłoczna zmiana
  uprawnień, monitorowanie dostępu i środki uniemożliwiające nieautoryzowany dostęp na poziomie aplikacji;
- § 20 KRI: rozliczalność dokumentowana w dziennikach systemów (logach), przechowywanych co najmniej 2 lata;
- art. 8 ust. 1 pkt 2 lit. l i n ustawy o krajowym systemie cyberbezpieczeństwa (w brzmieniu z Dz. U. z 2026 r.
  poz. 252): uwierzytelnianie wieloskładnikowe w stosownych przypadkach, polityki kontroli dostępu;
- załącznik nr 4 część I pkt 6 tej ustawy: zawieszanie uprawnień w przypadku niewykonywania obowiązków co najmniej
  przez jeden miesiąc.

Kody jednorazowe: RFC 6238 (TOTP) i RFC 4226 (HOTP) - wektory testowe z dodatków do tych dokumentów.

Decyzje projektowe: brak aktywności = brak udanego logowania; dziennik ma łańcuch skrótów, który ujawnia zmianę
albo usunięcie wpisu; progi blokady po nieudanych próbach są ustawieniem urzędu.
"""

from datetime import date, datetime, timedelta, timezone as strefa
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from asystent_ocen.zgodnosc import wczytaj_wymogi
from oceny import bezpieczenstwo, dziennik, totp
from oceny.models import ZdarzenieBezpieczenstwa

SEKRET_RFC = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # „12345678901234567890” w Base32 - klucz z RFC 4226 i RFC 6238
TERAZ = datetime(2026, 11, 21, 12, 0, tzinfo=strefa.utc)


def konto(login: str, **pola):
    return get_user_model().objects.create_user(username=login, **pola)


class KodyJednorazoweTest(TestCase):
    def test_hotp_zgadza_sie_z_wektorami_rfc_4226(self):
        oczekiwane = ["755224", "287082", "359152", "969429", "338314", "254676", "287922", "162583", "399871", "520489"]

        self.assertEqual([totp.kod(SEKRET_RFC, licznik=licznik) for licznik in range(10)], oczekiwane)

    def test_totp_zgadza_sie_z_wektorami_rfc_6238(self):
        wektory = {59: "94287082", 1111111109: "07081804", 1111111111: "14050471", 1234567890: "89005924",
                   2000000000: "69279037", 20000000000: "65353130"}

        for czas, oczekiwany in wektory.items():
            with self.subTest(czas=czas):
                self.assertEqual(totp.kod(SEKRET_RFC, czas, cyfry=8), oczekiwany)

    def test_nowy_sekret_ma_160_bitow_i_jest_za_kazdym_razem_inny(self):
        pierwszy, drugi = totp.nowy_sekret(), totp.nowy_sekret()

        self.assertEqual(len(pierwszy), 32)
        self.assertRegex(pierwszy, r"^[A-Z2-7]{32}$")
        self.assertNotEqual(pierwszy, drugi)

    def test_kod_jest_przyjmowany_w_biezacym_i_sasiednim_kroku_czasu(self):
        czas = 1_800_000_000
        for przesuniecie in (-30, 0, 30):
            with self.subTest(przesuniecie=przesuniecie):
                self.assertIsNotNone(totp.sprawdz(SEKRET_RFC, totp.kod(SEKRET_RFC, czas + przesuniecie), czas))
        self.assertIsNone(totp.sprawdz(SEKRET_RFC, totp.kod(SEKRET_RFC, czas + 90), czas))
        self.assertIsNone(totp.sprawdz(SEKRET_RFC, totp.kod(SEKRET_RFC, czas - 90), czas))

    def test_kod_dziala_tylko_raz(self):
        """Wynik sprawdzenia to numer kroku czasu; kod z kroku już użytego albo starszego jest odrzucany."""
        czas = 1_800_000_000
        kod = totp.kod(SEKRET_RFC, czas)

        krok = totp.sprawdz(SEKRET_RFC, kod, czas)

        self.assertEqual(krok, czas // 30)
        self.assertIsNone(totp.sprawdz(SEKRET_RFC, kod, czas, po_kroku=krok))

    def test_kod_ze_spacja_jest_przyjmowany_a_tekst_inny_niz_6_cyfr_nie(self):
        czas = 1_800_000_000
        kod = totp.kod(SEKRET_RFC, czas)

        self.assertIsNotNone(totp.sprawdz(SEKRET_RFC, f"{kod[:3]} {kod[3:]}", czas))
        for zly in ("", "12345", "1234567", "abcdef", None):
            with self.subTest(kod=zly):
                self.assertIsNone(totp.sprawdz(SEKRET_RFC, zly, czas))

    def test_adres_dla_aplikacji_uwierzytelniajacej(self):
        adres = totp.adres_otpauth(SEKRET_RFC, "anna", "Asystent ocen - KPRM")

        self.assertTrue(adres.startswith("otpauth://totp/Asystent%20ocen%20-%20KPRM:anna?"))
        for fragment in (f"secret={SEKRET_RFC}", "issuer=Asystent%20ocen%20-%20KPRM", "algorithm=SHA1", "digits=6", "period=30"):
            self.assertIn(fragment, adres)


class DziennikZdarzenTest(TestCase):
    def test_wpis_ma_rodzaj_konto_czas_i_adres(self):
        anna = konto("anna")

        wpis = dziennik.zapisz(dziennik.LOGOWANIE_UDANE, uzytkownik=anna, adres_ip="10.0.0.7", opis="hasło i kod")

        self.assertEqual((wpis.rodzaj, wpis.login, wpis.adres_ip, wpis.opis), (dziennik.LOGOWANIE_UDANE, "anna", "10.0.0.7", "hasło i kod"))
        self.assertIsNotNone(wpis.czas)
        self.assertEqual(wpis.rodzaj_opis, dziennik.RODZAJE[dziennik.LOGOWANIE_UDANE])

    def test_nieznany_rodzaj_zdarzenia_jest_bledem(self):
        with self.assertRaises(ValueError):
            dziennik.zapisz("COS_INNEGO")

    def test_wpisu_nie_da_sie_zmienic_ani_usunac(self):
        wpis = dziennik.zapisz(dziennik.WYLOGOWANIE, login="anna")

        wpis.opis = "zmiana"
        with self.assertRaises(ValueError):
            wpis.save()
        with self.assertRaises(ValueError):
            wpis.delete()
        with self.assertRaises(ValueError):
            ZdarzenieBezpieczenstwa.objects.all().delete()
        with self.assertRaises(ValueError):
            ZdarzenieBezpieczenstwa.objects.update(opis="zmiana")

    def test_lancuch_skrotow_potwierdza_nienaruszony_dziennik(self):
        for numer in range(3):
            dziennik.zapisz(dziennik.LOGOWANIE_NIEUDANE, login=f"osoba{numer}")

        wynik = dziennik.sprawdz_lancuch()

        self.assertEqual((wynik["wpisow"], wynik["poprawny"], wynik["pierwszy_bledny"]), (3, True, None))

    def test_zmiana_wpisu_poza_aplikacja_wychodzi_przy_sprawdzeniu(self):
        wpisy = [dziennik.zapisz(dziennik.LOGOWANIE_NIEUDANE, login=f"osoba{numer}") for numer in range(3)]
        with connection.cursor() as kursor:
            kursor.execute("UPDATE oceny_zdarzeniebezpieczenstwa SET login = %s WHERE id = %s", ["ktos", wpisy[1].pk])

        wynik = dziennik.sprawdz_lancuch()

        self.assertFalse(wynik["poprawny"])
        self.assertEqual(wynik["pierwszy_bledny"], wpisy[1].pk)

    def test_usuniecie_wpisu_poza_aplikacja_wychodzi_przy_sprawdzeniu(self):
        wpisy = [dziennik.zapisz(dziennik.LOGOWANIE_NIEUDANE, login=f"osoba{numer}") for numer in range(3)]
        with connection.cursor() as kursor:
            kursor.execute("DELETE FROM oceny_zdarzeniebezpieczenstwa WHERE id = %s", [wpisy[1].pk])

        wynik = dziennik.sprawdz_lancuch()

        self.assertFalse(wynik["poprawny"])
        self.assertEqual(wynik["pierwszy_bledny"], wpisy[2].pk)

    def test_usuniecie_ostatniego_wpisu_tez_wychodzi(self):
        wpisy = [dziennik.zapisz(dziennik.LOGOWANIE_NIEUDANE, login=f"osoba{numer}") for numer in range(2)]
        with connection.cursor() as kursor:
            kursor.execute("DELETE FROM oceny_zdarzeniebezpieczenstwa WHERE id = %s", [wpisy[1].pk])

        self.assertFalse(dziennik.sprawdz_lancuch()["poprawny"])

    def test_okres_przechowywania_dziennika_pochodzi_z_konfiguracji_zgodnosci(self):
        """§ 20 ust. 4 KRI: dwa lata, gdy przepisy odrębne nie mówią inaczej."""
        self.assertEqual(wczytaj_wymogi().dziennik_przechowywanie_lat, 2)

    def test_polecenie_sprawdza_dziennik(self):
        dziennik.zapisz(dziennik.WYLOGOWANIE, login="anna")
        wyjscie = StringIO()

        call_command("sprawdz_dziennik", stdout=wyjscie)

        self.assertIn("nienaruszony", wyjscie.getvalue())


@override_settings(ASYSTENT_PROBY_LOGOWANIA=5, ASYSTENT_BLOKADA_MINUT=15)
class BlokadaPoNieudanychProbachTest(TestCase):
    def nieudane(self, ile: int, login: str = "anna", rodzaj: str = dziennik.LOGOWANIE_NIEUDANE):
        for _ in range(ile):
            dziennik.zapisz(rodzaj, login=login)

    def test_cztery_nieudane_proby_nie_blokuja_a_piata_blokuje(self):
        self.nieudane(4)
        self.assertFalse(bezpieczenstwo.logowanie_zablokowane("anna"))

        self.nieudane(1)

        self.assertTrue(bezpieczenstwo.logowanie_zablokowane("anna"))
        self.assertFalse(bezpieczenstwo.logowanie_zablokowane("piotr"))

    def test_wielkosc_liter_loginu_nie_omija_blokady(self):
        self.nieudane(5, login="Anna")

        self.assertTrue(bezpieczenstwo.logowanie_zablokowane("ANNA"))

    def test_bledne_kody_jednorazowe_licza_sie_do_blokady(self):
        self.nieudane(3)
        self.nieudane(2, rodzaj=dziennik.KOD_BLEDNY)

        self.assertTrue(bezpieczenstwo.logowanie_zablokowane("anna"))

    def test_blokada_mija_po_ustalonym_czasie(self):
        self.nieudane(5)

        za_16_minut = timezone.now() + timedelta(minutes=16)

        self.assertFalse(bezpieczenstwo.logowanie_zablokowane("anna", teraz=za_16_minut))

    def test_udane_logowanie_zeruje_licznik(self):
        self.nieudane(4)
        dziennik.zapisz(dziennik.LOGOWANIE_UDANE, login="anna")
        self.nieudane(1)

        self.assertFalse(bezpieczenstwo.logowanie_zablokowane("anna"))


class ZawieszanieNieaktywnychKontTest(TestCase):
    """Zał. nr 4 część I pkt 6 ustawy o KSC: zawieszanie uprawnień po co najmniej miesiącu niewykonywania obowiązków."""

    def konto_z_logowaniem(self, login: str, ostatnie: datetime | None, zalozone: datetime | None = None):
        uzytkownik = konto(login)
        get_user_model().objects.filter(pk=uzytkownik.pk).update(
            last_login=ostatnie, date_joined=zalozone or datetime(2026, 1, 5, 9, 0, tzinfo=strefa.utc)
        )
        uzytkownik.refresh_from_db()
        return uzytkownik

    def test_okres_pochodzi_z_konfiguracji_zgodnosci(self):
        self.assertEqual(wczytaj_wymogi().zawieszenie_konta_po_miesiacach, 1)

    def test_konto_jest_zawieszane_gdy_od_ostatniego_logowania_uplynal_ponad_miesiac(self):
        stare = self.konto_z_logowaniem("stare", datetime(2026, 10, 20, 8, 0, tzinfo=strefa.utc))
        graniczne = self.konto_z_logowaniem("graniczne", datetime(2026, 10, 21, 8, 0, tzinfo=strefa.utc))
        swieze = self.konto_z_logowaniem("swieze", datetime(2026, 11, 10, 8, 0, tzinfo=strefa.utc))

        zawieszone = bezpieczenstwo.zawies_nieaktywne(date(2026, 11, 21))

        self.assertEqual([uzytkownik.username for uzytkownik in zawieszone], ["stare"])
        for uzytkownik in (stare, graniczne, swieze):
            uzytkownik.refresh_from_db()
        self.assertEqual((stare.is_active, graniczne.is_active, swieze.is_active), (False, True, True))

    def test_miesiac_liczy_sie_kalendarzowo(self):
        """Ostatnie logowanie 31 stycznia: miesiąc upływa z końcem lutego (art. 112 KC)."""
        uzytkownik = self.konto_z_logowaniem("luty", datetime(2026, 1, 31, 8, 0, tzinfo=strefa.utc))

        self.assertEqual(bezpieczenstwo.zawies_nieaktywne(date(2026, 2, 28)), [])
        self.assertEqual(bezpieczenstwo.zawies_nieaktywne(date(2026, 3, 1)), [uzytkownik])

    def test_konto_nigdy_nieuzyte_liczy_sie_od_zalozenia(self):
        self.konto_z_logowaniem("nowe", None, zalozone=datetime(2026, 11, 2, 9, 0, tzinfo=strefa.utc))
        nieuzywane = self.konto_z_logowaniem("nieuzywane", None, zalozone=datetime(2026, 9, 1, 9, 0, tzinfo=strefa.utc))

        self.assertEqual(bezpieczenstwo.zawies_nieaktywne(date(2026, 11, 21)), [nieuzywane])

    def test_zawieszenie_zostaje_w_dzienniku_z_data_ostatniej_aktywnosci(self):
        self.konto_z_logowaniem("stare", datetime(2026, 10, 1, 8, 0, tzinfo=strefa.utc))

        bezpieczenstwo.zawies_nieaktywne(date(2026, 11, 21))

        wpis = ZdarzenieBezpieczenstwa.objects.get(rodzaj=dziennik.KONTO_ZAWIESZONE)
        self.assertEqual(wpis.dotyczy, "stare")
        self.assertIn("01.10.2026", wpis.opis)
        self.assertIsNone(wpis.uzytkownik)  # czynność systemu, nie osoby

    def test_drugie_uruchomienie_niczego_nie_zmienia(self):
        self.konto_z_logowaniem("stare", datetime(2026, 10, 1, 8, 0, tzinfo=strefa.utc))
        bezpieczenstwo.zawies_nieaktywne(date(2026, 11, 21))

        self.assertEqual(bezpieczenstwo.zawies_nieaktywne(date(2026, 11, 22)), [])
        self.assertEqual(ZdarzenieBezpieczenstwa.objects.filter(rodzaj=dziennik.KONTO_ZAWIESZONE).count(), 1)

    def test_po_odblokowaniu_miesiac_biegnie_od_nowa(self):
        """Bez tego konto odblokowane przez administratora byłoby zawieszane przy najbliższym przeglądzie."""
        stare = self.konto_z_logowaniem("stare", datetime(2026, 10, 1, 8, 0, tzinfo=strefa.utc))
        admin = konto("admin", is_superuser=True)
        bezpieczenstwo.zawies_nieaktywne(date(2026, 11, 21))

        bezpieczenstwo.odblokuj_konto(stare, wykonawca=admin)

        stare.refresh_from_db()
        self.assertTrue(stare.is_active)
        dzis_ = timezone.now().date()
        self.assertEqual(bezpieczenstwo.zawies_nieaktywne(dzis_ + timedelta(days=5)), [])
        self.assertIn(stare, bezpieczenstwo.zawies_nieaktywne(dzis_ + timedelta(days=40)))

    def test_stan_konta_rozroznia_blokade_administratora_i_zawieszenie(self):
        stare = self.konto_z_logowaniem("stare", datetime(2026, 10, 1, 8, 0, tzinfo=strefa.utc))
        blokowane = self.konto_z_logowaniem("blokowane", datetime(2026, 11, 20, 8, 0, tzinfo=strefa.utc))
        czynne = self.konto_z_logowaniem("czynne", datetime(2026, 11, 20, 8, 0, tzinfo=strefa.utc))
        admin = konto("admin", is_superuser=True)
        bezpieczenstwo.zawies_nieaktywne(date(2026, 11, 21))
        bezpieczenstwo.zablokuj_konto(blokowane, wykonawca=admin, powod="zakończenie zatrudnienia")
        stare.refresh_from_db()

        stany = {login: bezpieczenstwo.stan_konta(uzytkownik) for login, uzytkownik in
                 (("stare", stare), ("blokowane", blokowane), ("czynne", czynne))}

        self.assertEqual(stany["stare"]["kod"], bezpieczenstwo.ZAWIESZONE)
        self.assertEqual(stany["blokowane"]["kod"], bezpieczenstwo.ZABLOKOWANE)
        self.assertEqual(stany["czynne"]["kod"], bezpieczenstwo.AKTYWNE)
        wpis = ZdarzenieBezpieczenstwa.objects.get(rodzaj=dziennik.KONTO_ZABLOKOWANE)
        self.assertEqual((wpis.uzytkownik, wpis.dotyczy), (admin, "blokowane"))
        self.assertIn("zakończenie zatrudnienia", wpis.opis)

    def test_polecenie_zawiesza_konta_i_podaje_liczbe(self):
        self.konto_z_logowaniem("stare", datetime(2026, 10, 1, 8, 0, tzinfo=strefa.utc))
        wyjscie = StringIO()

        call_command("zawies_nieaktywne", "--dzien", "2026-11-21", stdout=wyjscie)

        self.assertIn("1", wyjscie.getvalue())
        self.assertIn("stare", wyjscie.getvalue())

    def test_polecenie_odblokowuje_konto_gdy_nie_ma_czynnego_administratora(self):
        admin = self.konto_z_logowaniem("admin", datetime(2026, 10, 1, 8, 0, tzinfo=strefa.utc))
        bezpieczenstwo.zawies_nieaktywne(date(2026, 11, 21))

        call_command("odblokuj_konto", "admin", stdout=StringIO())

        admin.refresh_from_db()
        self.assertTrue(admin.is_active)
        wpis = ZdarzenieBezpieczenstwa.objects.get(rodzaj=dziennik.KONTO_ODBLOKOWANE)
        self.assertIn("serwera", wpis.opis)
