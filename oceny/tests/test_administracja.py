"""Zaplecze administratora: konta użytkowników, zawieszanie kont bez aktywności i wgląd w dzienniki.

Wymagania:
- § 19 ust. 2 pkt 4 i 5 KRI: stosowne uprawnienia osób i bezzwłoczna zmiana uprawnień;
- § 20 ust. 2 pkt 1 i 2 KRI: działania z uprawnieniami administracyjnymi i zmiany konfiguracji zabezpieczeń
  odnotowuje się w dzienniku obowiązkowo;
- zał. nr 4 część I pkt 4-7 ustawy o KSC: dostęp tylko dla uprawnionych, minimalne uprawnienia, cofanie
  i zawieszanie uprawnień, modyfikacja ich zakresu.

Decyzje projektowe: administrator zarządza kontami i czyta dzienniki, a zaplecze nie pokazuje mu notatek ani szkiców; hasła nie
ustala ani nie poznaje - wydaje użytkownikowi jednorazowy link; nie może zablokować samego siebie ani odebrać
uprawnień ostatniemu czynnemu administratorowi.
"""

import csv
import io
import re
from datetime import datetime, timezone as strefa

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from oceny import bezpieczenstwo, dziennik, middleware, totp
from oceny.models import UrzadzenieTotp, ZdarzenieBezpieczenstwa

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import Zespol
from .test_widoki import klient

KONTA = reverse("administracja")
DZIENNIK = reverse("administracja_dziennik")
HASLO = "Zielony-Tramwaj-2026!"


def zdarzenia(rodzaj: str):
    return ZdarzenieBezpieczenstwa.objects.filter(rodzaj=rodzaj)


def akcja(uzytkownik, nazwa: str) -> str:
    return reverse("administracja_akcja", args=[uzytkownik.pk, nazwa])


@override_settings(ASYSTENT_2FA="dobrowolne", PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class Podstawa(TestCase):
    def setUp(self):
        middleware._dzien_przegladu = timezone.localdate()  # przegląd kont na dziś uznajemy za wykonany
        self.z = Zespol()
        self.admin = get_user_model().objects.create_user(username="admin", is_superuser=True)
        self.przegladarka = Client(REMOTE_ADDR="10.9.9.9")
        self.przegladarka.force_login(self.admin)


class DostepTest(Podstawa):
    ADRESY = [KONTA, DZIENNIK, reverse("administracja_nowe_konto"), reverse("administracja_dziennik_csv")]

    def test_tylko_administrator_wchodzi_na_zaplecze(self):
        for adres in self.ADRESY:
            with self.subTest(adres=adres):
                self.assertEqual(self.przegladarka.get(adres).status_code, 200)
                self.assertEqual(klient(self.z.kadry).get(adres).status_code, 403)
                self.assertEqual(klient(self.z.szef).get(adres).status_code, 403)
                self.assertEqual(Client().get(adres).status_code, 302)

    def test_proba_wejscia_bez_uprawnien_zostaje_w_dzienniku(self):
        klient(self.z.kadry).get(DZIENNIK)

        wpis = zdarzenia(dziennik.ODMOWA_DOSTEPU).get()
        self.assertEqual((wpis.login, wpis.dotyczy), ("kadry", DZIENNIK))

    def test_link_do_zaplecza_widzi_tylko_administrator(self):
        self.assertContains(self.przegladarka.get(reverse("przepisy")), f'href="{KONTA}"')
        self.assertNotContains(klient(self.z.kadry).get(reverse("przepisy")), f'href="{KONTA}"')

    def test_zaplecze_nie_pokazuje_notatek_oceniajacego(self):
        """Zarządzanie kontami nie daje wglądu w notatki ani szkice - zaplecze ich nie pokazuje."""
        ocena = self.z.ocena_z_kryteriami()
        from oceny import uslugi

        uslugi.dodaj_notatke(ocena, self.z.szef.uzytkownik, tresc="Poufna obserwacja naczelnika.")

        for adres in (KONTA, DZIENNIK, f"{DZIENNIK}?dziennik=proces"):
            self.assertNotContains(self.przegladarka.get(adres), "Poufna obserwacja")


class ListaKontTest(Podstawa):
    def test_lista_pokazuje_konta_stan_logowanie_i_weryfikacje_dwuetapowa(self):
        UrzadzenieTotp.objects.create(uzytkownik=self.z.szef.uzytkownik, sekret=totp.nowy_sekret(), potwierdzone=True)
        bezpieczenstwo.zablokuj_konto(self.z.obcy.uzytkownik, wykonawca=self.admin, powod="test")

        odpowiedz = self.przegladarka.get(KONTA)

        for login in ("admin", "kadry", "szef", "ola", "obcy"):
            self.assertContains(odpowiedz, f">{login}<")
        self.assertContains(odpowiedz, "zablokowane przez administratora")
        self.assertContains(odpowiedz, "włączona", count=1)
        self.assertContains(odpowiedz, "Szef Testowy")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_lista_mowi_kiedy_konto_zostanie_zawieszone(self):
        odpowiedz = self.przegladarka.get(KONTA)

        termin = bezpieczenstwo.termin_zawieszenia(self.z.ola.uzytkownik)
        self.assertContains(odpowiedz, f"{termin:%d.%m.%Y}")
        self.assertContains(odpowiedz, "zał. nr 4")

    def test_przycisk_zawiesza_konta_bez_aktywnosci(self):
        get_user_model().objects.filter(pk=self.z.obcy.uzytkownik.pk).update(
            last_login=datetime(2026, 1, 10, 8, 0, tzinfo=strefa.utc), date_joined=datetime(2026, 1, 5, 8, 0, tzinfo=strefa.utc)
        )

        odpowiedz = self.przegladarka.post(reverse("administracja_zawies"), follow=True)

        self.z.obcy.uzytkownik.refresh_from_db()
        self.assertFalse(self.z.obcy.uzytkownik.is_active)
        self.assertContains(odpowiedz, "Zawieszone konta: 1")
        self.assertContains(odpowiedz, "zawieszone - brak aktywności")

    def test_przeglad_kont_dziala_sam_przy_pierwszym_zadaniu_dnia(self):
        """Zawieszanie jest automatyczne także tam, gdzie nikt nie ustawił zadania cyklicznego."""
        get_user_model().objects.filter(pk=self.z.obcy.uzytkownik.pk).update(
            last_login=datetime(2026, 1, 10, 8, 0, tzinfo=strefa.utc), date_joined=datetime(2026, 1, 5, 8, 0, tzinfo=strefa.utc)
        )
        middleware._dzien_przegladu = None

        Client().get(reverse("logowanie"))

        self.z.obcy.uzytkownik.refresh_from_db()
        self.assertFalse(self.z.obcy.uzytkownik.is_active)
        self.assertEqual(zdarzenia(dziennik.KONTO_ZAWIESZONE).get().dotyczy, "obcy")


class NoweKontoTest(Podstawa):
    ADRES = reverse("administracja_nowe_konto")

    def dane(self, **zmiany):
        dane = {"username": "jnowak", "first_name": "Jan", "last_name": "Nowak", "email": "jan.nowak@example.org"}
        dane.update(zmiany)
        return dane

    def test_formularz_jest_dostepny_cyfrowo(self):
        self.assertEqual(bledy_dostepnosci(self.przegladarka.get(self.ADRES).content.decode()), [])

    def test_nowe_konto_nie_ma_hasla_a_administrator_dostaje_jednorazowy_link(self):
        odpowiedz = self.przegladarka.post(self.ADRES, self.dane(), follow=True)

        nowy = get_user_model().objects.get(username="jnowak")
        self.assertFalse(nowy.has_usable_password())
        self.assertEqual((nowy.first_name, nowy.last_name, nowy.email, nowy.is_superuser), ("Jan", "Nowak", "jan.nowak@example.org", False))
        self.assertContains(odpowiedz, "/haslo/")
        self.assertContains(odpowiedz, "Link działa jedną dobę")
        wpis = zdarzenia(dziennik.KONTO_UTWORZONE).get()
        self.assertEqual((wpis.uzytkownik, wpis.dotyczy, wpis.adres_ip), (self.admin, "jnowak", "10.9.9.9"))
        self.assertEqual(zdarzenia(dziennik.HASLO_LINK).get().dotyczy, "jnowak")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_link_nie_trafia_do_dziennika_i_znika_po_odswiezeniu_strony(self):
        odpowiedz = self.przegladarka.post(self.ADRES, self.dane(), follow=True)
        link = re.search(r"/haslo/[^\s\"<]+", odpowiedz.content.decode()).group(0)

        self.assertFalse(ZdarzenieBezpieczenstwa.objects.filter(opis__contains=link.split("/")[-2]).exists())
        nowy = get_user_model().objects.get(username="jnowak")
        self.assertNotContains(self.przegladarka.get(reverse("administracja_konto", args=[nowy.pk])), "/haslo/")

    def test_z_linku_uzytkownik_ustawia_haslo_i_loguje_sie_a_link_dziala_raz(self):
        odpowiedz = self.przegladarka.post(self.ADRES, self.dane(), follow=True)
        link = re.search(r"/haslo/[^\s\"<]+", odpowiedz.content.decode()).group(0)
        nowa = Client()

        formularz = nowa.get(link, follow=True)
        self.assertEqual(bledy_dostepnosci(formularz.content.decode()), [])
        ustawienie = nowa.post(formularz.redirect_chain[-1][0], {"new_password1": HASLO, "new_password2": HASLO})

        self.assertRedirects(ustawienie, reverse("logowanie"))
        self.assertEqual(zdarzenia(dziennik.HASLO_ZMIENIONE).get().login, "jnowak")
        nowa.post(reverse("logowanie"), {"username": "jnowak", "password": HASLO})
        self.assertIn("_auth_user_id", nowa.session)
        self.assertNotContains(Client().get(link, follow=True), 'name="new_password1"')

    def test_konto_mozna_powiazac_z_pracownikiem_bez_konta(self):
        from oceny.models import Pracownik

        nowy_pracownik = Pracownik.objects.create(
            imie="Jan", nazwisko="Nowak", stanowisko="referent", rodzaj_zatrudnienia="umowa_na_czas_nieokreslony",
            data_zatrudnienia=datetime(2026, 9, 1).date(),
        )

        self.przegladarka.post(self.ADRES, self.dane(pracownik=str(nowy_pracownik.pk)))

        nowy_pracownik.refresh_from_db()
        self.assertEqual(nowy_pracownik.uzytkownik.username, "jnowak")

    def test_zajety_login_i_bledny_adres_sa_odrzucane_z_komunikatem(self):
        odpowiedz = self.przegladarka.post(self.ADRES, self.dane(username="ola", email="to-nie-adres"))

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertContains(odpowiedz, "już istnieje")
        self.assertEqual(get_user_model().objects.filter(username="ola").count(), 1)
        self.assertEqual(zdarzenia(dziennik.KONTO_UTWORZONE).count(), 0)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])


class ZmianyKontaTest(Podstawa):
    def test_strona_konta_pokazuje_dane_stan_i_historie_zdarzen(self):
        bezpieczenstwo.zablokuj_konto(self.z.ola.uzytkownik, wykonawca=self.admin, powod="długa nieobecność")

        odpowiedz = self.przegladarka.get(reverse("administracja_konto", args=[self.z.ola.uzytkownik.pk]))

        self.assertContains(odpowiedz, "zablokowane przez administratora")
        self.assertContains(odpowiedz, "długa nieobecność")
        self.assertContains(odpowiedz, "Ola Testowy")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_zmiana_danych_zostaje_w_dzienniku_z_lista_zmienionych_pol(self):
        ola = self.z.ola.uzytkownik

        self.przegladarka.post(reverse("administracja_konto", args=[ola.pk]), {
            "first_name": "Ola", "last_name": "Testowy", "email": "ola@example.org", "administrator": "on",
        })

        ola.refresh_from_db()
        self.assertEqual((ola.email, ola.is_superuser), ("ola@example.org", True))
        wpis = zdarzenia(dziennik.KONTO_ZMIENIONE).get()
        self.assertEqual((wpis.uzytkownik, wpis.dotyczy), (self.admin, "ola"))
        self.assertIn("nadano uprawnienia administratora", wpis.opis)
        self.assertIn("e-mail", wpis.opis)

    def test_blokada_dziala_od_razu_takze_na_trwajaca_sesje(self):
        sesja_oli = klient(self.z.ola)
        self.assertEqual(sesja_oli.get(reverse("zadania")).status_code, 200)

        self.przegladarka.post(akcja(self.z.ola.uzytkownik, "zablokuj"), {"powod": "zakończenie zatrudnienia"})

        self.assertEqual(sesja_oli.get(reverse("zadania")).status_code, 302)
        wpis = zdarzenia(dziennik.KONTO_ZABLOKOWANE).get()
        self.assertEqual((wpis.uzytkownik, wpis.dotyczy, wpis.opis), (self.admin, "ola", "zakończenie zatrudnienia"))

    def test_odblokowanie_przywraca_dostep_i_zostaje_w_dzienniku(self):
        ola = self.z.ola.uzytkownik
        bezpieczenstwo.zablokuj_konto(ola, wykonawca=self.admin)

        self.przegladarka.post(akcja(ola, "odblokuj"))

        ola.refresh_from_db()
        self.assertTrue(ola.is_active)
        self.assertEqual(zdarzenia(dziennik.KONTO_ODBLOKOWANE).get().dotyczy, "ola")

    def test_administrator_nie_zablokuje_siebie_ani_nie_odbierze_sobie_uprawnien(self):
        odpowiedz = self.przegladarka.post(akcja(self.admin, "zablokuj"), follow=True)
        self.przegladarka.post(reverse("administracja_konto", args=[self.admin.pk]), {"first_name": "A", "last_name": "B"})

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active and self.admin.is_superuser)
        self.assertContains(odpowiedz, "własnego konta")

    def test_reset_weryfikacji_dwuetapowej_usuwa_aplikacje_i_zostaje_w_dzienniku(self):
        szef = self.z.szef.uzytkownik
        UrzadzenieTotp.objects.create(uzytkownik=szef, sekret=totp.nowy_sekret(), potwierdzone=True)

        self.przegladarka.post(akcja(szef, "reset-dwuetapowego"))

        self.assertIsNone(bezpieczenstwo.urzadzenie(szef))
        wpis = zdarzenia(dziennik.DWUETAPOWE_ZRESETOWANE).get()
        self.assertEqual((wpis.uzytkownik, wpis.dotyczy), (self.admin, "szef"))

    def test_nowy_link_do_hasla_dla_istniejacego_konta(self):
        odpowiedz = self.przegladarka.post(akcja(self.z.ola.uzytkownik, "link-hasla"), follow=True)

        self.assertContains(odpowiedz, "/haslo/")
        self.assertEqual(zdarzenia(dziennik.HASLO_LINK).get().dotyczy, "ola")

    def test_nieznana_czynnosc_i_metoda_get_sa_odrzucane(self):
        self.assertEqual(self.przegladarka.post(akcja(self.z.ola.uzytkownik, "usun")).status_code, 404)
        self.assertEqual(self.przegladarka.get(akcja(self.z.ola.uzytkownik, "zablokuj")).status_code, 405)


class DziennikTest(Podstawa):
    def setUp(self):
        super().setUp()
        dziennik.zapisz(dziennik.LOGOWANIE_NIEUDANE, login="ola", adres_ip="10.0.0.5")
        dziennik.zapisz(dziennik.LOGOWANIE_NIEUDANE, login="=1+1", adres_ip="10.0.0.6")
        dziennik.zapisz(dziennik.KONTO_ZABLOKOWANE, uzytkownik=self.admin, dotyczy="obcy", opis="test")

    def test_dziennik_pokazuje_zdarzenia_i_stan_lancucha(self):
        odpowiedz = self.przegladarka.get(DZIENNIK)

        self.assertContains(odpowiedz, "nieudane logowanie")
        self.assertContains(odpowiedz, "10.0.0.5")
        self.assertContains(odpowiedz, "konto - zablokowane przez administratora")
        self.assertContains(odpowiedz, "Dziennik jest nienaruszony")
        self.assertContains(odpowiedz, "2 lata")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_wglad_w_dziennik_sam_jest_zdarzeniem(self):
        self.przegladarka.get(DZIENNIK)

        wpis = zdarzenia(dziennik.WGLAD_W_DZIENNIK).get()
        self.assertEqual((wpis.uzytkownik, wpis.adres_ip), (self.admin, "10.9.9.9"))

    def test_filtr_po_rodzaju_i_loginie(self):
        odpowiedz = self.przegladarka.get(DZIENNIK, {"rodzaj": dziennik.LOGOWANIE_NIEUDANE, "login": "ola"})

        self.assertContains(odpowiedz, "10.0.0.5")
        self.assertNotContains(odpowiedz, "10.0.0.6")
        self.assertNotContains(odpowiedz, "<td>konto - zablokowane przez administratora</td>")

    def test_filtr_po_dacie(self):
        odpowiedz = self.przegladarka.get(DZIENNIK, {"od": "2099-01-01"})

        self.assertContains(odpowiedz, "Brak zdarzeń")
        self.assertEqual(self.przegladarka.get(DZIENNIK, {"od": "to-nie-data"}).status_code, 200)

    def test_naruszony_dziennik_jest_zglaszany_na_stronie(self):
        from django.db import connection

        with connection.cursor() as kursor:
            kursor.execute("UPDATE oceny_zdarzeniebezpieczenstwa SET opis = 'x' WHERE login = 'ola'")

        odpowiedz = self.przegladarka.get(DZIENNIK)

        self.assertContains(odpowiedz, "Dziennik jest naruszony")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_dziennik_procesu_pokazuje_czynnosci_bez_opisow(self):
        ocena = self.z.ocena_z_kryteriami()

        odpowiedz = self.przegladarka.get(DZIENNIK, {"dziennik": "proces"})

        self.assertContains(odpowiedz, "Czynności w procesie oceny")
        self.assertContains(odpowiedz, f"ocena {ocena.pk}")
        self.assertContains(odpowiedz, "szef")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_eksport_csv_zostaje_w_dzienniku_i_nie_przenosi_formul(self):
        odpowiedz = self.przegladarka.get(reverse("administracja_dziennik_csv"), {"rodzaj": dziennik.LOGOWANIE_NIEUDANE})

        self.assertEqual(odpowiedz["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", odpowiedz["Content-Disposition"])
        wiersze = list(csv.reader(io.StringIO(odpowiedz.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(wiersze[0][:4], ["czas", "rodzaj", "login", "dotyczy"])
        self.assertEqual(len(wiersze), 3)
        loginy = [wiersz[2] for wiersz in wiersze[1:]]
        self.assertIn("'=1+1", loginy)  # login wpisany przez atakującego nie wykona się w arkuszu jako formuła
        self.assertEqual(zdarzenia(dziennik.EKSPORT_DZIENNIKA).get().uzytkownik, self.admin)

    def test_dluga_lista_jest_dzielona_na_strony(self):
        for numer in range(60):
            dziennik.zapisz(dziennik.LOGOWANIE_NIEUDANE, login=f"osoba{numer}")

        pierwsza = self.przegladarka.get(DZIENNIK)
        druga = self.przegladarka.get(DZIENNIK, {"strona": "2"})

        self.assertContains(pierwsza, "osoba59")
        self.assertNotContains(pierwsza, ">osoba1<")
        self.assertContains(druga, ">osoba1<")
        self.assertContains(pierwsza, "strona 1 z 2")


class PanelDjangoTest(Podstawa):
    """Panel administratora Django (dane kadrowe) nie może być furtką obok logowania z kodem i obok dziennika."""

    def test_panel_nie_ma_wlasnego_logowania(self):
        odpowiedz = Client().get("/admin/login/?next=/admin/")

        self.assertRedirects(odpowiedz, f"{reverse('logowanie')}?next=/admin/", fetch_redirect_response=False)
        self.assertEqual(Client().post("/admin/login/", {"username": "admin", "password": "x"}).status_code, 302)

    def test_zalogowany_bez_uprawnien_do_panelu_dostaje_odmowe_a_nie_petle_przekierowan(self):
        self.assertEqual(klient(self.z.kadry).get("/admin/login/?next=/admin/").status_code, 403)

    def test_zmiana_w_panelu_django_trafia_do_dziennika_zdarzen(self):
        from django.contrib.admin.models import CHANGE, LogEntry
        from django.contrib.contenttypes.models import ContentType

        from oceny.models import Pracownik

        LogEntry.objects.create(
            user=self.admin, content_type=ContentType.objects.get_for_model(Pracownik), object_id=str(self.z.ola.pk),
            object_repr="Ola Testowy", action_flag=CHANGE, change_message="",
        )

        wpis = zdarzenia(dziennik.PANEL_ADMINISTRATORA).get()
        self.assertEqual((wpis.uzytkownik, wpis.dotyczy), (self.admin, "Ola Testowy"))
        self.assertIn("pracownik", wpis.opis)


class KontaPokazuTest(TestCase):
    """Pokaz ma administratora i konto zawieszone za brak aktywności - żeby zaplecze było co oglądać."""

    @override_settings(ASYSTENT_TRYB_DEMO=True)
    def test_pokaz_ma_administratora_bez_hasla_i_bez_dostepu_do_panelu_django(self):
        from datetime import date

        from oceny import dane_demo
        from oceny.kontekst import konta_demo

        dane_demo.zaladuj(date(2026, 11, 21))

        admin = get_user_model().objects.get(username="administrator")
        self.assertTrue(admin.is_superuser)
        self.assertFalse(admin.is_staff or admin.has_usable_password())
        self.assertIn(admin, konta_demo())
        przegladarka = Client()
        przegladarka.post(reverse("demo_zaloguj"), {"login": "administrator"})
        self.assertEqual(przegladarka.get(KONTA).status_code, 200)

    def test_poza_pokazem_na_konto_administratora_pokazu_nie_da_sie_wejsc(self):
        from datetime import date

        from oceny import dane_demo

        dane_demo.zaladuj(date(2026, 11, 21))

        self.assertEqual(Client().post(reverse("demo_zaloguj"), {"login": "administrator"}).status_code, 404)

    def test_pokaz_ma_konto_zawieszone_za_brak_aktywnosci(self):
        from datetime import date

        from oceny import dane_demo

        dane_demo.zaladuj(date(2026, 11, 21))

        ewa = get_user_model().objects.get(username="ewa")
        self.assertFalse(ewa.is_active)
        self.assertEqual(bezpieczenstwo.stan_konta(ewa)["kod"], bezpieczenstwo.ZAWIESZONE)
        self.assertEqual(zdarzenia(dziennik.KONTO_ZAWIESZONE).get().dotyczy, "ewa")
