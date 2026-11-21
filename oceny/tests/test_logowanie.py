"""Logowanie: hasło, blokada po nieudanych próbach, weryfikacja dwuetapowa kodem TOTP, konto użytkownika.

Wymagania: art. 8 ust. 1 pkt 2 lit. l i n ustawy o KSC (uwierzytelnianie wieloskładnikowe w stosownych przypadkach,
polityki kontroli dostępu); § 19 ust. 2 pkt 7 lit. a-c KRI (monitorowanie dostępu, wykrywanie nieautoryzowanych
działań, środki uniemożliwiające nieautoryzowany dostęp na poziomie aplikacji); § 20 KRI (dziennik zdarzeń).

Decyzje projektowe: sesja powstaje dopiero po drugim składniku; kod działa raz; komunikat po nieudanym logowaniu
nie zdradza, czy konto istnieje; hasło i kod nigdy nie trafiają do dziennika; przy polityce „wymagane” konto bez
aplikacji uwierzytelniającej nie wejdzie nigdzie poza jej konfigurację.
"""

import time

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from oceny import bezpieczenstwo, dziennik, totp
from oceny.models import UrzadzenieTotp, ZdarzenieBezpieczenstwa

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import Zespol
from .test_widoki import czynnosc, klient

HASLO = "Zielony-Tramwaj-2026!"
# W testach skrót hasła liczy się szybkim algorytmem - produkcyjny celowo trwa długo.
SZYBKIE_HASLA = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LOGOWANIE = reverse("logowanie")
KOD = reverse("logowanie_kod")
DWUETAPOWE = reverse("konto_dwuetapowe")


def konto(login="anna", **pola):
    return get_user_model().objects.create_user(username=login, password=HASLO, **pola)


def z_aplikacja(uzytkownik) -> UrzadzenieTotp:
    return UrzadzenieTotp.objects.create(uzytkownik=uzytkownik, sekret=totp.nowy_sekret(), potwierdzone=True)


def zdarzenia(rodzaj: str):
    return ZdarzenieBezpieczenstwa.objects.filter(rodzaj=rodzaj)


def zalogowany(przegladarka: Client) -> bool:
    return "_auth_user_id" in przegladarka.session


@override_settings(ASYSTENT_2FA="dobrowolne", PASSWORD_HASHERS=SZYBKIE_HASLA)
class LogowanieHaslemTest(TestCase):
    def setUp(self):
        self.anna = konto()
        self.przegladarka = Client(REMOTE_ADDR="10.1.2.3")

    def zaloguj(self, haslo=HASLO, login="anna"):
        return self.przegladarka.post(LOGOWANIE, {"username": login, "password": haslo})

    def test_udane_logowanie_zostaje_w_dzienniku_z_adresem(self):
        odpowiedz = self.zaloguj()

        self.assertRedirects(odpowiedz, reverse("zadania"))
        wpis = zdarzenia(dziennik.LOGOWANIE_UDANE).get()
        self.assertEqual((wpis.login, wpis.uzytkownik, wpis.adres_ip), ("anna", self.anna, "10.1.2.3"))
        self.assertIn("hasło", wpis.opis)

    def test_logowanie_administratora_jest_oznaczone_w_dzienniku(self):
        """§ 20 ust. 2 pkt 1 KRI: dostęp do systemu z uprawnieniami administracyjnymi odnotowuje się obowiązkowo."""
        konto("admin", is_superuser=True)

        self.zaloguj(login="admin")

        self.assertIn("uprawnienia administracyjne", zdarzenia(dziennik.LOGOWANIE_UDANE).get().opis)

    def test_nieudane_logowanie_zostaje_w_dzienniku_bez_hasla(self):
        odpowiedz = self.zaloguj("zle-haslo-123")

        self.assertContains(odpowiedz, "Nieprawidłowy login lub hasło")
        self.assertFalse(zalogowany(self.przegladarka))
        wpis = zdarzenia(dziennik.LOGOWANIE_NIEUDANE).get()
        self.assertEqual((wpis.login, wpis.adres_ip, wpis.uzytkownik), ("anna", "10.1.2.3", None))
        self.assertNotIn("zle-haslo-123", f"{wpis.opis} {wpis.dotyczy} {wpis.login}")

    def test_komunikat_jest_taki_sam_dla_konta_ktorego_nie_ma_i_dla_zablokowanego(self):
        zablokowana = konto("ewa", is_active=False)
        komunikaty = set()
        for login in ("anna", "nie-ma-takiego", zablokowana.username):
            odpowiedz = self.zaloguj("zle-haslo-123" if login == "anna" else HASLO, login=login)
            komunikaty.add("Nieprawidłowy login lub hasło albo konto jest nieczynne." in odpowiedz.content.decode())

        self.assertEqual(komunikaty, {True})
        self.assertEqual(zdarzenia(dziennik.LOGOWANIE_NIEUDANE).count(), 3)

    def test_po_pieciu_nieudanych_probach_nawet_dobre_haslo_nie_wchodzi(self):
        for _ in range(5):
            self.zaloguj("zle-haslo-123")

        odpowiedz = self.zaloguj()

        self.assertEqual(odpowiedz.status_code, 429)
        self.assertContains(odpowiedz, "Zbyt wiele nieudanych prób", status_code=429)
        self.assertFalse(zalogowany(self.przegladarka))
        self.assertEqual(zdarzenia(dziennik.LOGOWANIE_ZABLOKOWANE).count(), 1)
        self.assertEqual(zdarzenia(dziennik.LOGOWANIE_NIEUDANE).count(), 5)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    @override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_za_serwerem_posredniczacym_zapisywany_jest_adres_ktory_on_dopisal(self):
        """Początek nagłówka X-Forwarded-For wpisuje klient, więc do dziennika idzie ostatni adres - od serwera urzędu."""
        self.przegladarka.post(
            LOGOWANIE, {"username": "anna", "password": "zle-haslo-123"}, HTTP_X_FORWARDED_FOR="1.2.3.4, 192.0.2.77"
        )
        self.przegladarka.post(
            LOGOWANIE, {"username": "anna", "password": "zle-haslo-123"}, HTTP_X_FORWARDED_FOR="<script>alert(1)</script>"
        )

        adresy = list(zdarzenia(dziennik.LOGOWANIE_NIEUDANE).values_list("adres_ip", flat=True))
        self.assertEqual(adresy, ["192.0.2.77", None])

    def test_wylogowanie_zostaje_w_dzienniku(self):
        self.zaloguj()

        self.przegladarka.post(reverse("wylogowanie"))

        self.assertEqual(zdarzenia(dziennik.WYLOGOWANIE).get().login, "anna")

    def test_strona_logowania_jest_dostepna_cyfrowo(self):
        self.assertEqual(bledy_dostepnosci(self.przegladarka.get(LOGOWANIE).content.decode()), [])


@override_settings(ASYSTENT_2FA="dobrowolne", PASSWORD_HASHERS=SZYBKIE_HASLA)
class WeryfikacjaDwuetapowaTest(TestCase):
    def setUp(self):
        self.anna = konto()
        self.aplikacja = z_aplikacja(self.anna)
        self.przegladarka = Client(REMOTE_ADDR="10.1.2.3")

    def haslo(self):
        return self.przegladarka.post(LOGOWANIE, {"username": "anna", "password": HASLO})

    def kod(self, wartosc=None):
        return self.przegladarka.post(KOD, {"kod": wartosc or totp.kod(self.aplikacja.sekret)})

    def test_po_hasle_nie_ma_jeszcze_sesji_tylko_pytanie_o_kod(self):
        odpowiedz = self.haslo()

        self.assertRedirects(odpowiedz, KOD)
        self.assertFalse(zalogowany(self.przegladarka))
        self.assertEqual(zdarzenia(dziennik.LOGOWANIE_UDANE).count(), 0)
        self.assertRedirects(self.przegladarka.get(reverse("zadania")), f"{LOGOWANIE}?next=/")

    def test_strona_kodu_jest_dostepna_cyfrowo_i_ma_pole_na_kod_jednorazowy(self):
        self.haslo()

        odpowiedz = self.przegladarka.get(KOD)

        self.assertContains(odpowiedz, 'autocomplete="one-time-code"')
        self.assertContains(odpowiedz, 'inputmode="numeric"')
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_poprawny_kod_loguje_i_zostaje_w_dzienniku(self):
        self.haslo()

        odpowiedz = self.kod()

        self.assertRedirects(odpowiedz, reverse("zadania"))
        self.assertTrue(zalogowany(self.przegladarka))
        self.assertEqual(zdarzenia(dziennik.KOD_POPRAWNY).get().login, "anna")
        self.assertIn("kod jednorazowy", zdarzenia(dziennik.LOGOWANIE_UDANE).get().opis)

    def test_bledny_kod_nie_loguje_i_zostaje_w_dzienniku_bez_kodu(self):
        self.haslo()

        odpowiedz = self.kod("000000" if totp.kod(self.aplikacja.sekret) != "000000" else "111111")

        self.assertContains(odpowiedz, "Kod jest nieprawidłowy")
        self.assertFalse(zalogowany(self.przegladarka))
        wpis = zdarzenia(dziennik.KOD_BLEDNY).get()
        self.assertEqual(wpis.login, "anna")
        self.assertNotIn("000000", wpis.opis)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_ten_sam_kod_nie_dziala_drugi_raz(self):
        self.haslo()
        kod = totp.kod(self.aplikacja.sekret)
        self.kod(kod)
        self.przegladarka.post(reverse("wylogowanie"))

        self.haslo()
        odpowiedz = self.kod(kod)

        self.assertContains(odpowiedz, "Kod jest nieprawidłowy albo został już użyty")
        self.assertFalse(zalogowany(self.przegladarka))

    def test_piec_blednych_kodow_blokuje_logowanie(self):
        self.haslo()
        for _ in range(5):
            self.kod("12345x")

        odpowiedz = self.kod()

        self.assertRedirects(odpowiedz, LOGOWANIE)
        self.assertFalse(zalogowany(self.przegladarka))
        self.assertEqual(zdarzenia(dziennik.LOGOWANIE_ZABLOKOWANE).count(), 1)
        self.assertEqual(self.haslo().status_code, 429)

    def test_strona_kodu_bez_hasla_odsyla_do_logowania(self):
        self.assertRedirects(self.przegladarka.get(KOD), LOGOWANIE)
        self.assertRedirects(self.przegladarka.post(KOD, {"kod": totp.kod(self.aplikacja.sekret)}), LOGOWANIE)
        self.assertFalse(zalogowany(self.przegladarka))

    def test_na_kod_jest_piec_minut(self):
        self.haslo()
        sesja = self.przegladarka.session
        oczekuje = sesja["oczekuje_na_kod"]
        oczekuje["od"] = time.time() - 301
        sesja["oczekuje_na_kod"] = oczekuje
        sesja.save()

        odpowiedz = self.kod()

        self.assertRedirects(odpowiedz, LOGOWANIE)
        self.assertFalse(zalogowany(self.przegladarka))

    def test_konto_zablokowane_po_podaniu_hasla_nie_wejdzie_kodem(self):
        self.haslo()
        get_user_model().objects.filter(pk=self.anna.pk).update(is_active=False)

        self.kod()

        self.assertFalse(zalogowany(self.przegladarka))

    @override_settings(ASYSTENT_TRYB_DEMO=True)
    def test_konto_pokazowe_z_aplikacja_tez_podaje_kod(self):
        self.anna.set_unusable_password()
        self.anna.save()

        odpowiedz = self.przegladarka.post(reverse("demo_zaloguj"), {"login": "anna"})

        self.assertRedirects(odpowiedz, KOD)
        self.assertFalse(zalogowany(self.przegladarka))
        self.kod()
        self.assertTrue(zalogowany(self.przegladarka))


@override_settings(PASSWORD_HASHERS=SZYBKIE_HASLA)
class KonfiguracjaAplikacjiUwierzytelniajacejTest(TestCase):
    def setUp(self):
        self.anna = konto(first_name="Anna", last_name="Testowa")
        self.przegladarka = Client()

    def zaloguj(self):
        return self.przegladarka.post(LOGOWANIE, {"username": "anna", "password": HASLO})

    @override_settings(ASYSTENT_2FA="wymagane")
    def test_przy_polityce_wymagane_konto_bez_aplikacji_trafia_na_konfiguracje_i_nigdzie_indziej(self):
        odpowiedz = self.zaloguj()

        self.assertRedirects(odpowiedz, DWUETAPOWE)
        for adres in (reverse("zadania"), reverse("przepisy"), reverse("asystent"), reverse("konto")):
            with self.subTest(adres=adres):
                self.assertRedirects(self.przegladarka.get(adres), DWUETAPOWE)
        self.assertEqual(self.przegladarka.get(DWUETAPOWE).status_code, 200)
        self.assertEqual(self.przegladarka.post(reverse("wylogowanie")).status_code, 302)

    @override_settings(ASYSTENT_2FA="wymagane")
    def test_po_potwierdzeniu_pierwszego_kodu_system_sie_otwiera(self):
        self.zaloguj()
        self.przegladarka.get(DWUETAPOWE)
        sekret = UrzadzenieTotp.objects.get(uzytkownik=self.anna).sekret

        odpowiedz = self.przegladarka.post(DWUETAPOWE, {"akcja": "potwierdz", "kod": totp.kod(sekret)})

        self.assertRedirects(odpowiedz, reverse("konto"))
        self.assertIsNotNone(bezpieczenstwo.urzadzenie(self.anna))
        self.assertEqual(zdarzenia(dziennik.DWUETAPOWE_WLACZONE).get().login, "anna")
        self.assertEqual(self.przegladarka.get(reverse("zadania")).status_code, 200)

    @override_settings(ASYSTENT_2FA="dobrowolne")
    def test_strona_konfiguracji_pokazuje_klucz_adres_i_instrukcje(self):
        self.zaloguj()

        odpowiedz = self.przegladarka.get(DWUETAPOWE)

        sekret = UrzadzenieTotp.objects.get(uzytkownik=self.anna).sekret
        self.assertContains(odpowiedz, totp.sekret_w_grupach(sekret))
        self.assertContains(odpowiedz, "otpauth://totp/")
        self.assertContains(odpowiedz, "aplikacji uwierzytelniającej")
        self.assertIsNone(bezpieczenstwo.urzadzenie(self.anna))  # samo wejście na stronę niczego nie włącza
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    @override_settings(ASYSTENT_2FA="dobrowolne")
    def test_bledny_kod_nie_wlacza_weryfikacji(self):
        self.zaloguj()
        self.przegladarka.get(DWUETAPOWE)

        odpowiedz = self.przegladarka.post(DWUETAPOWE, {"akcja": "potwierdz", "kod": "12345x"})

        self.assertContains(odpowiedz, "Kod jest nieprawidłowy")
        self.assertIsNone(bezpieczenstwo.urzadzenie(self.anna))
        self.assertEqual(zdarzenia(dziennik.DWUETAPOWE_WLACZONE).count(), 0)

    @override_settings(ASYSTENT_2FA="dobrowolne")
    def test_wylaczenie_wymaga_biezacego_kodu(self):
        aplikacja = z_aplikacja(self.anna)
        self.zaloguj()
        self.przegladarka.post(KOD, {"kod": totp.kod(aplikacja.sekret)})

        zly = self.przegladarka.post(DWUETAPOWE, {"akcja": "wylacz", "kod": "12345x"})
        self.assertIsNotNone(bezpieczenstwo.urzadzenie(self.anna))
        self.assertContains(zly, "Kod jest nieprawidłowy")

        # kod użyty przy logowaniu nie zadziała drugi raz, więc do testu cofamy zapamiętany krok
        UrzadzenieTotp.objects.filter(pk=aplikacja.pk).update(ostatni_krok=0)
        self.przegladarka.post(DWUETAPOWE, {"akcja": "wylacz", "kod": totp.kod(aplikacja.sekret)})

        self.assertIsNone(bezpieczenstwo.urzadzenie(self.anna))
        self.assertEqual(zdarzenia(dziennik.DWUETAPOWE_WYLACZONE).get().login, "anna")

    @override_settings(ASYSTENT_2FA="dobrowolne")
    def test_kodu_przy_wylaczaniu_nie_da_sie_zgadywac(self):
        """Błędne kody przy wyłączaniu liczą się do blokady tak samo jak przy logowaniu."""
        aplikacja = z_aplikacja(self.anna)
        self.zaloguj()
        self.przegladarka.post(KOD, {"kod": totp.kod(aplikacja.sekret)})
        UrzadzenieTotp.objects.filter(pk=aplikacja.pk).update(ostatni_krok=0)
        for _ in range(5):
            self.przegladarka.post(DWUETAPOWE, {"akcja": "wylacz", "kod": "12345x"})

        odpowiedz = self.przegladarka.post(DWUETAPOWE, {"akcja": "wylacz", "kod": totp.kod(aplikacja.sekret)})

        self.assertEqual(odpowiedz.status_code, 403)
        self.assertIsNotNone(bezpieczenstwo.urzadzenie(self.anna))
        self.assertEqual(zdarzenia(dziennik.KOD_BLEDNY).count(), 5)

    @override_settings(ASYSTENT_2FA="wymagane")
    def test_przy_polityce_wymagane_weryfikacji_nie_da_sie_wylaczyc(self):
        aplikacja = z_aplikacja(self.anna)
        self.zaloguj()
        self.przegladarka.post(KOD, {"kod": totp.kod(aplikacja.sekret)})
        UrzadzenieTotp.objects.filter(pk=aplikacja.pk).update(ostatni_krok=0)

        strona = self.przegladarka.get(DWUETAPOWE)
        odpowiedz = self.przegladarka.post(DWUETAPOWE, {"akcja": "wylacz", "kod": totp.kod(aplikacja.sekret)})

        self.assertNotContains(strona, 'value="wylacz"')
        self.assertEqual(odpowiedz.status_code, 403)
        self.assertIsNotNone(bezpieczenstwo.urzadzenie(self.anna))


@override_settings(ASYSTENT_2FA="dobrowolne", PASSWORD_HASHERS=SZYBKIE_HASLA)
class MojeKontoTest(TestCase):
    def setUp(self):
        self.anna = konto(first_name="Anna", last_name="Testowa", email="anna@example.org")
        self.przegladarka = Client(REMOTE_ADDR="10.1.2.3")
        self.przegladarka.post(LOGOWANIE, {"username": "anna", "password": HASLO})

    def test_strona_konta_pokazuje_stan_zabezpieczen_i_ostatnie_logowania(self):
        odpowiedz = self.przegladarka.get(reverse("konto"))

        self.assertContains(odpowiedz, "Weryfikacja dwuetapowa")
        self.assertContains(odpowiedz, "wyłączona")
        self.assertContains(odpowiedz, "10.1.2.3")
        self.assertContains(odpowiedz, "Ostatnie logowania")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_menu_ma_link_do_konta(self):
        self.assertContains(self.przegladarka.get(reverse("zadania")), f'href="{reverse("konto")}"')

    def test_zmiana_hasla_zostaje_w_dzienniku_bez_hasla(self):
        nowe = "Fioletowy-Autobus-2027!"

        strona = self.przegladarka.get(reverse("konto_haslo"))
        odpowiedz = self.przegladarka.post(
            reverse("konto_haslo"), {"old_password": HASLO, "new_password1": nowe, "new_password2": nowe}
        )

        self.assertEqual(bledy_dostepnosci(strona.content.decode()), [])
        self.assertRedirects(odpowiedz, reverse("konto"))
        self.anna.refresh_from_db()
        self.assertTrue(self.anna.check_password(nowe))
        wpis = zdarzenia(dziennik.HASLO_ZMIENIONE).get()
        self.assertEqual(wpis.login, "anna")
        self.assertNotIn(nowe, wpis.opis)

    def test_za_krotkie_haslo_jest_odrzucane(self):
        odpowiedz = self.przegladarka.post(
            reverse("konto_haslo"), {"old_password": HASLO, "new_password1": "Krotkie1!", "new_password2": "Krotkie1!"}
        )

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertContains(odpowiedz, "12")
        self.assertEqual(zdarzenia(dziennik.HASLO_ZMIENIONE).count(), 0)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])


@override_settings(ASYSTENT_2FA="dobrowolne", PASSWORD_HASHERS=SZYBKIE_HASLA)
class DziennikDostepuTest(TestCase):
    """§ 19 ust. 2 pkt 7 lit. a KRI: monitorowanie dostępu do informacji."""

    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()

    def test_odczyt_karty_oceny_zostaje_w_dzienniku(self):
        klient(self.z.szef).get(reverse("ocena", args=[self.ocena.pk]))

        wpis = zdarzenia(dziennik.ODCZYT_OCENY).get()
        self.assertEqual((wpis.login, wpis.dotyczy), ("szef", f"ocena {self.ocena.pk}"))

    def test_pobranie_arkusza_zostaje_w_dzienniku(self):
        klient(self.z.szef).get(reverse("arkusz_docx", args=[self.ocena.pk]))

        wpis = zdarzenia(dziennik.POBRANIE_ARKUSZA).get()
        self.assertEqual((wpis.login, wpis.dotyczy), ("szef", f"ocena {self.ocena.pk}"))
        self.assertIn("DOCX", wpis.opis)

    def test_odmowa_dostepu_zostaje_w_dzienniku(self):
        odpowiedz = klient(self.z.ola).post(czynnosc(self.ocena, "notatka"), {"tresc": "x"})

        self.assertEqual(odpowiedz.status_code, 403)
        wpis = zdarzenia(dziennik.ODMOWA_DOSTEPU).get()
        self.assertEqual(wpis.login, "ola")
        self.assertIn("notatka", wpis.dotyczy)

    def test_proba_wejscia_na_cudza_ocene_nie_zostawia_wpisu_o_odczycie(self):
        odpowiedz = klient(self.z.obcy).get(reverse("ocena", args=[self.ocena.pk]))

        self.assertEqual(odpowiedz.status_code, 404)
        self.assertEqual(zdarzenia(dziennik.ODCZYT_OCENY).count(), 0)
