"""Widoki: dostęp, uprawnienia, przebieg oceny przez przeglądarkę, wydruki.

Wymagania: KPRM - kontrola dostępu i ról; architektura v4 - blokady i walidacja pól; decyzja zespołu z 21.11.2026 -
notatek oceniającego nie widzi nikt poza nim.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from asystent_ocen.kryteria import kryteria_obowiazkowe
from oceny import uslugi
from oceny.models import Nieobecnosc, Ocena

from .pomocnicze import DZIEN_OCENY, POCZATEK, TERMIN, Zespol, pracownik


def klient(pracownik_) -> Client:
    c = Client()
    c.force_login(pracownik_.uzytkownik)
    return c


def czynnosc(ocena, nazwa: str) -> str:
    return reverse("czynnosc", args=[ocena.pk, nazwa])


class DostepTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()

    def test_bez_logowania_kazda_strona_odsyla_do_logowania(self):
        adresy = [
            reverse("zadania"), reverse("ocena", args=[self.ocena.pk]), reverse("kadry"), reverse("statystyki"),
            reverse("przepisy"), reverse("asystent"), reverse("arkusz_docx", args=[self.ocena.pk]),
            reverse("kalendarz", args=[self.ocena.pk]),
        ]
        for adres in adresy:
            odpowiedz = Client().get(adres)
            self.assertEqual(odpowiedz.status_code, 302, adres)
            self.assertTrue(odpowiedz["Location"].startswith(reverse("logowanie")), adres)

    def test_strona_logowania_jest_dostepna_bez_logowania(self):
        self.assertEqual(Client().get(reverse("logowanie")).status_code, 200)

    def test_cudzej_oceny_nie_widac(self):
        """Osoba bez roli w ocenie dostaje 404 - system nie zdradza nawet istnienia oceny."""
        obcy = klient(self.z.obcy)
        self.assertEqual(obcy.get(reverse("ocena", args=[self.ocena.pk])).status_code, 404)
        self.assertEqual(obcy.get(reverse("arkusz_docx", args=[self.ocena.pk])).status_code, 404)
        self.assertEqual(obcy.get(reverse("kalendarz", args=[self.ocena.pk])).status_code, 404)
        self.assertEqual(obcy.post(czynnosc(self.ocena, "notatka"), {"tresc": "x"}).status_code, 404)

    def test_notatki_widzi_tylko_oceniajacy(self):
        uslugi.dodaj_notatke(
            self.ocena, self.z.szef.uzytkownik, tresc="Obserwacja-tylko-dla-szefa.", data=date(2025, 6, 10)
        )
        adres = reverse("ocena", args=[self.ocena.pk])

        self.assertContains(klient(self.z.szef).get(adres), "Obserwacja-tylko-dla-szefa.")
        for inny in (self.z.ola, self.z.kadry):
            odpowiedz = klient(inny).get(adres)
            self.assertNotContains(odpowiedz, "Obserwacja-tylko-dla-szefa.")
            # Także historia czynności nie zdradza, że oceniający prowadzi notatki i kiedy je zapisał.
            self.assertNotContains(odpowiedz, "notatk")

    def test_szkicu_oceny_nie_widzi_oceniany(self):
        uslugi.zapisz_szkic(self.ocena, self.z.szef.uzytkownik, {"uzasadnienie": "Szkic-niewidoczny-dla-ocenianej."})
        adres = reverse("ocena", args=[self.ocena.pk])

        self.assertContains(klient(self.z.szef).get(adres), "Szkic-niewidoczny-dla-ocenianej.")
        self.assertNotContains(klient(self.z.ola).get(adres), "Szkic-niewidoczny-dla-ocenianej.")

    def test_czynnosc_w_cudzej_roli_jest_odrzucana(self):
        odpowiedz = klient(self.z.ola).post(czynnosc(self.ocena, "notatka"), {"tresc": "Notatka ocenianej."})

        self.assertEqual(odpowiedz.status_code, 403)
        self.assertEqual(self.ocena.proces().notatki, [])

    def test_czynnosc_wymaga_metody_post_i_znanej_nazwy(self):
        szef = klient(self.z.szef)
        self.assertEqual(szef.get(czynnosc(self.ocena, "notatka")).status_code, 405)
        self.assertEqual(szef.post(czynnosc(self.ocena, "usun-wszystko")).status_code, 404)

    def test_formularz_bez_zetonu_csrf_jest_odrzucany(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.z.szef.uzytkownik)
        self.assertEqual(c.post(czynnosc(self.ocena, "notatka"), {"tresc": "x"}).status_code, 403)

    def test_odpowiedzi_maja_naglowki_bezpieczenstwa(self):
        odpowiedz = klient(self.z.szef).get(reverse("zadania"))

        self.assertIn("default-src 'self'", odpowiedz["Content-Security-Policy"])
        self.assertEqual(odpowiedz["Cache-Control"], "no-store")
        self.assertEqual(odpowiedz["X-Frame-Options"], "DENY")

    def test_strony_nie_odwoluja_sie_do_zasobow_zewnetrznych(self):
        """System ma działać w sieci urzędu bez dostępu do internetu."""
        for adres in (reverse("zadania"), reverse("ocena", args=[self.ocena.pk]), reverse("przepisy")):
            tresc = klient(self.z.kadry).get(adres).content.decode()
            self.assertNotIn("http://", tresc, adres)
            self.assertNotIn("https://", tresc, adres)
            self.assertNotIn("<style", tresc, adres)  # polityka treści nie dopuszcza stylów w kodzie strony


class PrzebiegPrzezPrzegladarkeTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.nowa_ocena()
        self.adres = reverse("ocena", args=[self.ocena.pk])

    def test_pierwsza_okresowa_ma_wlasne_przygotowanie_rozmowy(self):
        strona = klient(self.z.szef).get(self.adres)
        self.assertContains(strona, "Przygotuj rozmowę o kryteriach")
        self.assertContains(strona, "cele zadaniowe")
        self.assertContains(strona, 'name="kryterium_1"')
        self.assertNotContains(strona, 'name="zadania"')

    def test_pelny_przebieg_oceny(self):
        z = self.z
        szef, ola = klient(z.szef), klient(z.ola)
        dodatkowe = z.dodatkowe()

        self.assertContains(szef.get(reverse("zadania")), "Ola Testowy")
        odpowiedz = szef.post(czynnosc(self.ocena, "wyznacz-kryteria"), {
            "kryterium_1": dodatkowe[0], "kryterium_2": dodatkowe[1], "kryterium_3": "",
        })
        self.assertRedirects(odpowiedz, self.adres)
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).etap, "KRYTERIA_DO_POTWIERDZENIA")

        self.assertContains(ola.get(self.adres), dodatkowe[0])
        self.assertRedirects(ola.post(czynnosc(self.ocena, "potwierdz-kryteria")), self.adres)
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).etap, "OCENIANIE")

        nazwy = kryteria_obowiazkowe("C") + dodatkowe
        dane = {f"ocena_{numer}": "7" for numer in range(len(nazwy))}
        dane.update({"data_rozmowy": "2026-11-03", "wnioski_iprz": "Szkolenie z postępowania administracyjnego."})
        with override_settings(ASYSTENT_DZIS="2026-11-04"):
            self.assertRedirects(szef.post(czynnosc(self.ocena, "sporzadz-ocene"), dane), self.adres)
            self.assertContains(ola.get(self.adres), "powyżej oczekiwań")
            self.assertRedirects(ola.post(czynnosc(self.ocena, "potwierdz-zapoznanie")), self.adres)

        z_bazy = Ocena.objects.get(pk=self.ocena.pk)
        self.assertEqual((z_bazy.etap, z_bazy.wynik, z_bazy.data_zapoznania), ("ZAKONCZONA", "POZYTYWNA", DZIEN_OCENY))
        self.assertEqual(z_bazy.zdarzenia.count(), 5)
        kolejna = Ocena.objects.get(poprzednia=z_bazy)
        self.assertEqual(kolejna.oceniany_id, z_bazy.oceniany_id)
        self.assertContains(ola.get(self.adres), "sprzeciw")

    def test_blad_walidacji_pokazuje_komunikat_z_podstawa_prawna(self):
        """§ 5 ust. 2 rozp. - to samo kryterium wybrane dwa razy."""
        dodatkowe = self.z.dodatkowe()
        szef = klient(self.z.szef)

        odpowiedz = szef.post(czynnosc(self.ocena, "wyznacz-kryteria"), {
            "kryterium_1": dodatkowe[0], "kryterium_2": dodatkowe[0], "kryterium_3": "", "termin": "2026-11-20",
        }, follow=True)

        self.assertContains(odpowiedz, "§ 5 ust. 2 rozp.")
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).etap, "KRYTERIA_DO_WYZNACZENIA")

    def test_data_doslana_do_formularza_kryteriow_jest_pomijana_i_nie_wywraca_strony(self):
        """Termin wynika z ustawy i wylicza go system - formularz kryteriów nie ma pola daty."""
        odpowiedz = klient(self.z.szef).post(
            czynnosc(self.ocena, "wyznacz-kryteria"), {"termin": "20.11.2026"}, follow=True
        )

        self.assertEqual(odpowiedz.status_code, 200)
        zapisana = Ocena.objects.get(pk=self.ocena.pk)
        self.assertEqual((zapisana.etap, zapisana.termin), ("KRYTERIA_DO_POTWIERDZENIA", date(2026, 11, 23)))

    def test_formularz_kryteriow_podaje_termin_ustawowy(self):
        """Art. 81 ust. 4 u.s.c.: 24 miesiące; 21.11.2026 to sobota, więc termin przypada 23.11.2026."""
        self.assertContains(
            klient(self.z.szef).get(self.adres), "Termin sporządzenia oceny: <strong>23.11.2026</strong>", html=True
        )

    def test_niekompletna_ocena_zostaje_w_szkicu_i_pokazuje_braki(self):
        """Architektura v4: wnioski IPRZ zawsze obowiązkowe; wpisane dane nie przepadają po błędzie."""
        ocena = self.ocena
        uslugi.wyznacz_kryteria(
            ocena, self.z.szef.uzytkownik, kryteria_dodatkowe=[], termin=TERMIN, data=date(2024, 12, 2)
        )
        uslugi.potwierdz_kryteria(ocena, self.z.ola.uzytkownik, data=date(2024, 12, 3))
        dane = {f"ocena_{numer}": "5" for numer in range(5)}
        dane.update({"data_rozmowy": "2026-11-03", "wnioski_iprz": "", "uzasadnienie": "Tekst-zachowany-po-bledzie."})

        with override_settings(ASYSTENT_DZIS="2026-11-04"):
            odpowiedz = klient(self.z.szef).post(czynnosc(ocena, "sporzadz-ocene"), dane, follow=True)

        self.assertEqual(Ocena.objects.get(pk=ocena.pk).etap, "OCENIANIE")
        self.assertContains(odpowiedz, "Tekst-zachowany-po-bledzie.")
        self.assertContains(odpowiedz, "indywidualnego programu rozwoju zawodowego")

    def test_szkic_pokazuje_wynik_wyliczony_przez_rdzen(self):
        ocena = self.ocena
        uslugi.wyznacz_kryteria(
            ocena, self.z.szef.uzytkownik, kryteria_dodatkowe=[], termin=TERMIN, data=date(2024, 12, 2)
        )
        uslugi.potwierdz_kryteria(ocena, self.z.ola.uzytkownik, data=date(2024, 12, 3))
        dane = {f"ocena_{numer}": "9" for numer in range(5)}
        dane["ocena_0"] = "1"

        odpowiedz = klient(self.z.szef).post(czynnosc(ocena, "szkic"), dane, follow=True)

        # § 11 ust. 1 pkt 3 rozp.: ocena cząstkowa „znacznie poniżej oczekiwań” wyklucza ocenę pozytywną.
        self.assertContains(odpowiedz, "NEGATYWNA")
        self.assertEqual(Ocena.objects.get(pk=ocena.pk).etap, "OCENIANIE")


class WydrukiTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_zakonczona()

    def test_arkusz_docx_pobieraja_strony_oceny(self):
        for osoba in (self.z.szef, self.z.ola, self.z.kadry):
            odpowiedz = klient(osoba).get(reverse("arkusz_docx", args=[self.ocena.pk]))
            self.assertEqual(odpowiedz.status_code, 200)
            self.assertIn("wordprocessingml", odpowiedz["Content-Type"])
            self.assertIn("attachment", odpowiedz["Content-Disposition"])
            self.assertEqual(odpowiedz.content[:2], b"PK")

    def test_kalendarz_zawiera_termin_sprzeciwu(self):
        """Art. 83 ust. 1 u.s.c.: zapoznanie 4.11.2026 -> sprzeciw do 12.11.2026 (11.11 jest świętem)."""
        odpowiedz = klient(self.z.ola).get(reverse("kalendarz", args=[self.ocena.pk]))

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertTrue(odpowiedz["Content-Type"].startswith("text/calendar"))
        tresc = odpowiedz.content.decode()
        self.assertIn("BEGIN:VCALENDAR", tresc)
        self.assertIn("DTSTART;VALUE=DATE:20261112", tresc)

    def test_kalendarz_bez_biegnacych_terminow_odsyla_na_karte_z_wyjasnieniem(self):
        """Między sporządzeniem oceny a zapoznaniem nie biegnie żaden termin dzienny (§ 12 ust. 1: „niezwłocznie”)."""
        z = Zespol.__new__(Zespol)
        z.kadry, z.szef = self.z.kadry, self.z.szef
        z.ola = pracownik("jan", przelozony=z.szef)
        ocena = z.ocena_do_zapoznania()

        odpowiedz = klient(z.szef).get(reverse("kalendarz", args=[ocena.pk]), follow=True)

        self.assertRedirects(odpowiedz, reverse("ocena", args=[ocena.pk]))
        self.assertContains(odpowiedz, "nie biegnie żaden termin")
        self.assertNotContains(odpowiedz, reverse("kalendarz", args=[ocena.pk]))

    def test_pdf_bez_konwertera_daje_czytelny_komunikat(self):
        with override_settings(ASYSTENT_SOFFICE="/nie/ma/takiego/programu"):
            odpowiedz = klient(self.z.szef).get(reverse("arkusz_pdf", args=[self.ocena.pk]), follow=True)

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertContains(odpowiedz, "LibreOffice")


class KadryTest(TestCase):
    def setUp(self):
        self.z = Zespol()

    def test_panel_kadr_jest_tylko_dla_kadr(self):
        self.assertEqual(klient(self.z.kadry).get(reverse("kadry")).status_code, 200)
        self.assertEqual(klient(self.z.szef).get(reverse("kadry")).status_code, 403)
        self.assertEqual(klient(self.z.ola).get(reverse("kadry")).status_code, 403)

    def test_reczny_start_nie_jest_juz_czynnoscia_dostepna_z_panelu(self):
        for rola in (self.z.kadry, self.z.szef):
            self.assertEqual(klient(rola).post(f"/kadry/pracownik/{self.z.ola.pk}/rozpocznij/").status_code, 404)
        self.assertFalse(Ocena.objects.exists())

    def test_panel_pokazuje_kto_nie_podlega_ocenie_i_dlaczego(self):
        pracownik("okresowy", rodzaj_zatrudnienia="umowa_na_czas_okreslony", przelozony=self.z.szef)

        odpowiedz = klient(self.z.kadry).get(reverse("kadry"))

        self.assertContains(odpowiedz, "nie podlega ocenie")
        self.assertContains(odpowiedz, "art. 81 ust. 1 u.s.c.")

    def test_kadry_dodaja_nieobecnosc_ktora_przesuwa_termin_ustawowy(self):
        """Art. 81 ust. 7 u.s.c.: nieobecność dłuższa niż miesiąc przedłuża termin."""
        ocena = self.z.ocena_z_kryteriami()

        odpowiedz = klient(self.z.kadry).post(
            reverse("kadry_nieobecnosc", args=[self.z.ola.pk]), {"od": "2025-03-03", "do": "2025-05-30"}
        )

        self.assertRedirects(odpowiedz, reverse("kadry"))
        self.assertEqual(Nieobecnosc.objects.filter(pracownik=self.z.ola).count(), 1)
        self.assertContains(klient(self.z.szef).get(reverse("ocena", args=[ocena.pk])), "art. 81 ust. 7 u.s.c.")


class StatystykiIPrzepisyTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.z.ocena_zakonczona()

    def test_statystyki_widza_kadry_i_dyrektor(self):
        dyrektor = pracownik("dyrektor", rola_dyrektor=True)
        self.assertEqual(klient(dyrektor).get(reverse("statystyki")).status_code, 200)
        self.assertEqual(klient(self.z.kadry).get(reverse("statystyki")).status_code, 200)
        self.assertEqual(klient(self.z.szef).get(reverse("statystyki")).status_code, 403)

    def test_statystyki_sa_zbiorcze_bez_danych_osob(self):
        dyrektor = pracownik("dyrektor", rola_dyrektor=True, nazwisko="Dyrektorski")

        odpowiedz = klient(dyrektor).get(reverse("statystyki"))

        self.assertNotContains(odpowiedz, "Ola")
        self.assertNotContains(odpowiedz, "Testowy")

    def test_strona_przepisow_pokazuje_parametry_z_konfiguracji(self):
        odpowiedz = klient(self.z.kadry).get(reverse("przepisy"))

        self.assertContains(odpowiedz, "art. 81 ust. 4 u.s.c.")
        self.assertContains(odpowiedz, "przepisy.toml")


class TrybDemoTest(TestCase):
    def setUp(self):
        self.konto = get_user_model().objects.create_user(username="demo-ola")
        self.konto.set_unusable_password()
        self.konto.save()

    def test_bez_trybu_demo_szybkie_logowanie_nie_istnieje(self):
        odpowiedz = Client().post(reverse("demo_zaloguj"), {"login": "demo-ola"})
        self.assertEqual(odpowiedz.status_code, 404)

    @override_settings(ASYSTENT_TRYB_DEMO=True)
    def test_w_trybie_demo_mozna_wejsc_na_konto_demonstracyjne(self):
        c = Client()
        odpowiedz = c.post(reverse("demo_zaloguj"), {"login": "demo-ola"})

        self.assertRedirects(odpowiedz, reverse("zadania"))
        self.assertEqual(c.get(reverse("zadania")).status_code, 200)

    @override_settings(ASYSTENT_TRYB_DEMO=True)
    def test_tryb_demo_nie_otwiera_kont_z_haslem_ani_administratorow(self):
        z_haslem = get_user_model().objects.create_user(username="prawdziwy", password="Bardzo-Dlugie-Haslo-2026")
        admin = get_user_model().objects.create_superuser(username="szef-it")
        admin.set_unusable_password()
        admin.save()

        for login in (z_haslem.username, admin.username, "nie-ma-takiego"):
            self.assertEqual(Client().post(reverse("demo_zaloguj"), {"login": login}).status_code, 404, login)
