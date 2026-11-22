"""Przypomnienia e-mail o terminach, skrzynka nadawcza SMTP w zapleczu administratora i osobisty kalendarz.

Wymaganie (prowadzący projekt, 22.11.2026): system wysyła na skrzynki połączone z kontami użytkowników wiadomości
z przypomnieniem o nadchodzących terminach, łączy się z kalendarzami użytkowników, a administrator ustawia
skrzynkę nadawczą SMTP. Decyzje projektowe:
- wiadomość i kalendarz pokazują to samo co lista „Moje zadania” - zadania z terminem dziennym w obu procesach;
- wiadomość wychodzi w dniach z `przypomnienia_dni_przed` (30, 14 i 3 dni przed terminem), w dniu terminu
  i co 7 dni po terminie - najwyżej raz dziennie na osobę;
- wiadomość i kalendarz nie zawierają ocen ani treści arkuszy, a domyślnie także nazwisk ocenianych;
- hasła skrzynki nie pokazuje żadna strona ani dziennik;
- kalendarz osobisty to adres z losowym kluczem, który program kalendarza odświeża bez logowania.
"""

from datetime import date
from io import StringIO
from smtplib import SMTPException
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse

from oceny import poczta, przypomnienia
from oceny.models import KalendarzOsobisty, SkrzynkaNadawcza, WyslanePrzypomnienie, ZdarzenieBezpieczenstwa

from .dostepnosc_html import bledy_dostepnosci
from .test_administracja import Podstawa
from .test_widoki import klient

POCZTA = "/administracja/poczta/"
TYTUL = "Przeprowadź rozmowę oceniającą i sporządź ocenę"  # zadanie przełożonego z terminem 20.11.2026
FIKCYJNE = "fikcyjne-do-testu-123"
DANE = {
    "akcja": "zapisz", "wlaczona": "on", "host": "poczta.urzad.example", "port": "587", "zabezpieczenie": "starttls",
    "uzytkownik": "asystent", "haslo": FIKCYJNE, "nadawca": "asystent@urzad.example",
    "nazwa_nadawcy": "Asystent ocen", "adres_systemu": "https://oceny.urzad.example",
}


class Sprawa(Podstawa):
    """Przełożony ma jedno zadanie z terminem 20.11.2026; oceniana i kadry nie mają zadań z terminem."""

    def setUp(self):
        super().setUp()
        self.ocena = self.z.ocena_z_kryteriami()
        self.adres(self.z.szef, "szef@urzad.example")
        self.adres(self.z.ola, "ola@urzad.example")

    @staticmethod
    def adres(osoba, email):
        osoba.uzytkownik.email = email
        osoba.uzytkownik.save(update_fields=["email"])


class TrescTest(Sprawa):
    def test_wiadomosc_wymienia_termin_z_podstawa_i_adresem_bez_nazwisk_i_ocen(self):
        SkrzynkaNadawcza.objects.create(pk=1, adres_systemu="https://oceny.urzad.example/")

        wiadomosc = przypomnienia.wiadomosc(self.z.szef.uzytkownik, date(2026, 11, 6))

        self.assertEqual(wiadomosc.to, ["szef@urzad.example"])
        self.assertEqual(wiadomosc.subject, "Asystent ocen: 1 termin wymaga uwagi (najbliższy 20.11.2026)")
        for fragment in ("20.11.2026 (zostało 14 dni)", TYTUL, "art. 81 ust. 4 u.s.c.",
                         f"https://oceny.urzad.example/oceny/{self.ocena.pk}/", "nie zawiera ocen ani treści arkuszy"):
            self.assertIn(fragment, wiadomosc.body)
        self.assertNotIn("Testowy", wiadomosc.body)  # domyślnie bez nazwisk ocenianych
        nazwa, tresc, typ = wiadomosc.attachments[0]
        self.assertEqual((nazwa, typ), ("terminy.ics", "text/calendar"))
        self.assertIn("BEGIN:VEVENT", tresc)
        self.assertIn("DTSTART;VALUE=DATE:20261120", tresc)
        self.assertNotIn("Testowy", tresc)
        self.assertNotIn("rozp..", tresc)  # podstawa kończy się skrótem z kropką - opis nie może jej podwajać

    def test_nazwisko_ocenianego_pojawia_sie_dopiero_po_decyzji_administratora(self):
        SkrzynkaNadawcza.objects.create(pk=1, nazwiska=True)

        wiadomosc = przypomnienia.wiadomosc(self.z.szef.uzytkownik, date(2026, 11, 6))

        self.assertIn(f"{TYTUL} - Ola Testowy", wiadomosc.body)
        self.assertIn("Ola Testowy", wiadomosc.attachments[0][1].replace("\r\n ", ""))  # RFC 5545: długi wiersz jest łamany

    def test_po_terminie_wiadomosc_mowi_o_zaleglosci(self):
        wiadomosc = przypomnienia.wiadomosc(self.z.szef.uzytkownik, date(2026, 11, 27))

        self.assertEqual(wiadomosc.subject, "Asystent ocen: 1 termin wymaga uwagi (po terminie od 20.11.2026)")
        self.assertIn("Po terminie:", wiadomosc.body)
        self.assertIn("20.11.2026 (7 dni po terminie)", wiadomosc.body)

    def test_osoba_bez_zadan_z_terminem_nie_dostaje_wiadomosci(self):
        self.assertIsNone(przypomnienia.wiadomosc(self.z.ola.uzytkownik, date(2026, 11, 6)))


class WysylkaTest(Sprawa):
    def test_planowa_wysylka_trafia_w_dni_progowe_i_najwyzej_raz_dziennie(self):
        przypadki = (("2026-11-05", 0), ("2026-11-06", 1), ("2026-11-06", 0), ("2026-11-07", 0), ("2026-11-17", 1),
                     ("2026-11-20", 1), ("2026-11-21", 0), ("2026-11-27", 1), ("2026-12-04", 1), ("2026-12-05", 0))
        for dzien, oczekiwane in przypadki:
            with self.subTest(dzien=dzien):
                mail.outbox.clear()
                wynik = przypomnienia.wyslij(date.fromisoformat(dzien))
                self.assertEqual((len(mail.outbox), wynik.wyslane), (oczekiwane, oczekiwane))
        self.assertEqual(WyslanePrzypomnienie.objects.count(), 5)

    def test_osoba_bez_adresu_jest_pominieta_i_policzona(self):
        self.adres(self.z.szef, "")

        wynik = przypomnienia.wyslij(date(2026, 11, 6))

        self.assertEqual((wynik.wyslane, wynik.bez_adresu, len(mail.outbox)), (0, 1, 0))

    def test_konto_nieczynne_nie_dostaje_przypomnien(self):
        self.z.szef.uzytkownik.is_active = False
        self.z.szef.uzytkownik.save(update_fields=["is_active"])

        self.assertEqual(przypomnienia.wyslij(date(2026, 11, 6)).wyslane, 0)

    def test_wymuszona_wysylka_nie_czeka_na_dzien_progowy(self):
        wynik = przypomnienia.wyslij(date(2026, 11, 5), wymus=True)

        self.assertEqual((wynik.wyslane, len(mail.outbox)), (1, 1))
        self.assertEqual(mail.outbox[0].to, ["szef@urzad.example"])

    def test_blad_serwera_pocztowego_jest_policzony_i_wysylke_mozna_powtorzyc(self):
        with mock.patch("oceny.poczta.polaczenie", side_effect=SMTPException("serwer odrzucił połączenie")):
            wynik = przypomnienia.wyslij(date(2026, 11, 6))
        self.assertEqual((wynik.wyslane, wynik.bledy), (0, 1))
        self.assertEqual(WyslanePrzypomnienie.objects.count(), 0)

        self.assertEqual(przypomnienia.wyslij(date(2026, 11, 6)).wyslane, 1)

    def test_wylaczona_skrzynka_wstrzymuje_planowa_wysylke(self):
        SkrzynkaNadawcza.objects.create(pk=1, host="poczta.urzad.example", wlaczona=False)

        wynik = przypomnienia.wyslij(date(2026, 11, 6))

        self.assertEqual((wynik.wyslane, wynik.wstrzymane, len(mail.outbox)), (0, True, 0))

    def test_polecenie_do_harmonogramu_podaje_wynik(self):
        wyjscie = StringIO()
        with self.settings(ASYSTENT_DZIS="2026-11-06"):
            call_command("wyslij_przypomnienia", stdout=wyjscie)

        self.assertIn("Wysłano przypomnień: 1", wyjscie.getvalue())
        self.assertEqual(len(mail.outbox), 1)


class SkrzynkaNadawczaTest(Sprawa):
    def test_ustawienia_poczty_sa_tylko_dla_administratora(self):
        strona = self.przegladarka.get(POCZTA)
        self.assertContains(strona, "<h1>Poczta i przypomnienia</h1>")
        self.assertContains(self.przegladarka.get("/administracja/"), f'href="{POCZTA}"')
        self.assertEqual(bledy_dostepnosci(strona.content.decode()), [])
        for osoba in (self.z.kadry, self.z.szef, self.z.ola):
            self.assertEqual(klient(osoba).get(POCZTA).status_code, 403)
            self.assertEqual(klient(osoba).post(POCZTA, DANE).status_code, 403)
        self.assertFalse(SkrzynkaNadawcza.objects.exists())

    def test_zapisane_haslo_nie_wraca_na_strone_ani_do_dziennika(self):
        odpowiedz = self.przegladarka.post(POCZTA, DANE, follow=True)

        self.assertContains(odpowiedz, "Zapisano ustawienia skrzynki nadawczej.")
        skrzynka = SkrzynkaNadawcza.aktualna()
        self.assertEqual((skrzynka.host, skrzynka.port, skrzynka.zabezpieczenie, skrzynka.uzytkownik, skrzynka.haslo, skrzynka.nadawca,
                          skrzynka.adres_systemu, skrzynka.wlaczona, skrzynka.nazwiska),
                         ("poczta.urzad.example", 587, "starttls", "asystent", FIKCYJNE, "asystent@urzad.example",
                          "https://oceny.urzad.example", True, False))
        self.assertNotContains(odpowiedz, FIKCYJNE)
        self.assertContains(odpowiedz, "Hasło jest zapisane.")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])
        wpis = ZdarzenieBezpieczenstwa.objects.order_by("pk").last()
        self.assertEqual(wpis.dotyczy, "skrzynka nadawcza")
        self.assertIn("hasło: zmienione", wpis.opis)
        self.assertNotIn(FIKCYJNE, wpis.opis)

        # puste pole hasła zostawia zapisane hasło; zaznaczenie „usuń” je kasuje
        self.przegladarka.post(POCZTA, {**DANE, "haslo": "", "port": "465", "zabezpieczenie": "ssl"})
        skrzynka = SkrzynkaNadawcza.aktualna()
        self.assertEqual((skrzynka.haslo, skrzynka.port, skrzynka.zabezpieczenie), (FIKCYJNE, 465, "ssl"))
        self.przegladarka.post(POCZTA, {**DANE, "haslo": "", "usun_haslo": "on"})
        self.assertEqual(SkrzynkaNadawcza.aktualna().haslo, "")

    def test_bledne_dane_daja_komunikat_i_niczego_nie_zapisuja(self):
        for pole, wartosc in (("port", "abc"), ("port", "70000"), ("nadawca", "nie-adres"), ("zabezpieczenie", "inne"),
                              ("adres_systemu", "oceny bez protokołu"), ("host", "")):
            with self.subTest(pole=pole, wartosc=wartosc):
                odpowiedz = self.przegladarka.post(POCZTA, {**DANE, pole: wartosc})
                self.assertEqual(odpowiedz.status_code, 200)
                self.assertContains(odpowiedz, 'role="alert"')
                self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])
        self.assertFalse(SkrzynkaNadawcza.objects.exists())

    def test_polaczenie_bierze_ustawienia_skrzynki_a_haslo_ze_srodowiska_ma_pierwszenstwo(self):
        self.przegladarka.post(POCZTA, DANE)
        with mock.patch("oceny.poczta.get_connection") as polacz:
            poczta.polaczenie()
        polacz.assert_called_once_with(
            "django.core.mail.backends.smtp.EmailBackend", host="poczta.urzad.example", port=587, username="asystent",
            password=FIKCYJNE, use_tls=True, use_ssl=False, timeout=poczta.LIMIT_CZASU)

        with override_settings(EMAIL_HOST_PASSWORD="ze-srodowiska"), mock.patch("oceny.poczta.get_connection") as polacz:
            poczta.polaczenie()
            self.assertContains(self.przegladarka.get(POCZTA), "Hasło podano zmienną środowiskową")
        self.assertEqual(polacz.call_args.kwargs["password"], "ze-srodowiska")

    def test_bez_skrzynki_w_zapleczu_dziala_konfiguracja_serwera(self):
        with mock.patch("oceny.poczta.get_connection") as polacz:
            poczta.polaczenie()
        polacz.assert_called_once_with()

    def test_wiadomosc_probna_idzie_na_adres_administratora(self):
        bez_adresu = self.przegladarka.post(POCZTA, {"akcja": "probna"}, follow=True)
        self.assertContains(bez_adresu, "Twoje konto nie ma adresu e-mail")
        self.assertEqual(len(mail.outbox), 0)

        self.admin.email = "admin@urzad.example"
        self.admin.save(update_fields=["email"])
        odpowiedz = self.przegladarka.post(POCZTA, {"akcja": "probna"}, follow=True)

        self.assertContains(odpowiedz, "Wysłano wiadomość próbną na adres admin@urzad.example.")
        self.assertEqual([wiadomosc.to for wiadomosc in mail.outbox], [["admin@urzad.example"]])
        self.assertIn("próbna", mail.outbox[0].subject)

    def test_blad_wysylki_probnej_to_komunikat_a_nie_blad_serwera(self):
        self.admin.email = "admin@urzad.example"
        self.admin.save(update_fields=["email"])
        for wyjatek in (SMTPException("535 odmowa uwierzytelnienia"), OSError("brak połączenia"), TimeoutError()):
            with self.subTest(wyjatek=type(wyjatek).__name__), mock.patch("oceny.poczta.polaczenie", side_effect=wyjatek):
                odpowiedz = self.przegladarka.post(POCZTA, {"akcja": "probna"}, follow=True)
                self.assertEqual(odpowiedz.status_code, 200)
                self.assertContains(odpowiedz, "Nie udało się wysłać wiadomości próbnej")

    def test_administrator_wysyla_przypomnienia_od_reki_i_widzi_tylko_liczby(self):
        with self.settings(ASYSTENT_DZIS="2026-11-05"):  # 15 dni przed terminem - planowa wysyłka by czekała
            odpowiedz = self.przegladarka.post(POCZTA, {"akcja": "przypomnienia"}, follow=True)

        self.assertContains(odpowiedz, "Wysłano przypomnień: 1.")
        self.assertEqual([wiadomosc.to for wiadomosc in mail.outbox], [["szef@urzad.example"]])
        html = odpowiedz.content.decode()
        self.assertIn("szef@urzad.example", html)
        self.assertNotIn(TYTUL, html)  # administrator techniczny nie ogląda spraw - widzi adresata i liczbę terminów
        self.assertEqual(bledy_dostepnosci(html), [])
        wpis = ZdarzenieBezpieczenstwa.objects.order_by("pk").last()
        self.assertEqual(wpis.dotyczy, "przypomnienia e-mail")


class AdresKontaTest(Sprawa):
    def test_adres_konta_pracownika_da_sie_dopisac_bez_przepisywania_imienia_i_nazwiska(self):
        """Konta zakładane z ewidencji nie mają własnego imienia i nazwiska - formularz podpowiada je z karty pracownika."""
        konto = self.z.kadry.uzytkownik
        self.assertEqual((konto.first_name, konto.last_name, konto.email), ("", "", ""))
        adres = reverse("administracja_konto", args=[konto.pk])

        strona = self.przegladarka.get(adres)
        poczatkowe = strona.context["formularz"].initial
        self.assertEqual((poczatkowe["first_name"], poczatkowe["last_name"]), ("Kadry", "Testowy"))
        self.assertContains(strona, 'value="Kadry"')

        self.przegladarka.post(adres, {"first_name": "Kadry", "last_name": "Testowy", "email": "kadry@urzad.example",
                                       "pracownik": self.z.kadry.pk})
        konto.refresh_from_db()
        self.assertEqual((konto.first_name, konto.last_name, konto.email), ("Kadry", "Testowy", "kadry@urzad.example"))


class KalendarzOsobistyTest(Sprawa):
    def wlacz(self, osoba):
        przegladarka = klient(osoba)
        odpowiedz = przegladarka.post(reverse("konto_kalendarz"), {"akcja": "wlacz"}, follow=True)
        kalendarz = KalendarzOsobisty.objects.get(uzytkownik=osoba.uzytkownik)
        return przegladarka, odpowiedz, reverse("kalendarz_osobisty", args=[kalendarz.token])

    def test_program_kalendarza_pobiera_terminy_bez_logowania(self):
        _, odpowiedz, adres = self.wlacz(self.z.szef)
        self.assertContains(odpowiedz, adres)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

        with self.settings(ASYSTENT_DZIS="2026-11-06"):
            plik = Client().get(adres)

        self.assertEqual(plik.status_code, 200)
        self.assertEqual(plik["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("no-store", plik["Cache-Control"])
        tresc = plik.content.decode()
        self.assertIn("DTSTART;VALUE=DATE:20261120", tresc)
        self.assertIn("SUMMARY:Przeprowadź rozmowę oceniającą", tresc)
        self.assertNotIn("Testowy", tresc)

    def test_nowy_adres_uniewaznia_stary_a_wylaczenie_zamyka_kalendarz(self):
        przegladarka, _, stary = self.wlacz(self.z.szef)
        self.assertEqual(Client().get(reverse("kalendarz_osobisty", args=["x" * 43])).status_code, 404)

        przegladarka.post(reverse("konto_kalendarz"), {"akcja": "nowy"})
        nowy = reverse("kalendarz_osobisty", args=[KalendarzOsobisty.objects.get(uzytkownik=self.z.szef.uzytkownik).token])
        self.assertNotEqual(nowy, stary)
        self.assertEqual((Client().get(stary).status_code, Client().get(nowy).status_code), (404, 200))

        przegladarka.post(reverse("konto_kalendarz"), {"akcja": "wylacz"})
        self.assertEqual(Client().get(nowy).status_code, 404)
        self.assertFalse(KalendarzOsobisty.objects.exists())

    def test_kalendarz_bez_terminow_jest_pusty_a_konta_nieczynnego_nie_ma(self):
        _, _, adres = self.wlacz(self.z.ola)
        tresc = Client().get(adres).content.decode()
        self.assertIn("BEGIN:VCALENDAR", tresc)
        self.assertNotIn("BEGIN:VEVENT", tresc)

        self.z.ola.uzytkownik.is_active = False
        self.z.ola.uzytkownik.save(update_fields=["is_active"])
        self.assertEqual(Client().get(adres).status_code, 404)

    def test_moje_konto_pokazuje_adres_przypomnien_i_dzisiejsza_wiadomosc(self):
        przegladarka = klient(self.z.szef)
        konto = przegladarka.get(reverse("konto"))
        self.assertContains(konto, '<h2 id="n-przypomnienia">Przypomnienia i kalendarz</h2>')
        self.assertContains(konto, "szef@urzad.example")
        self.assertEqual(bledy_dostepnosci(konto.content.decode()), [])

        with self.settings(ASYSTENT_DZIS="2026-11-06"):
            podglad = przegladarka.get(reverse("konto_przypomnienie"))
        self.assertContains(podglad, "<h1>Podgląd przypomnienia</h1>")
        self.assertContains(podglad, TYTUL)
        self.assertContains(podglad, "20.11.2026 (zostało 14 dni)")
        self.assertEqual(bledy_dostepnosci(podglad.content.decode()), [])
        with self.settings(ASYSTENT_DZIS="2026-11-06"):
            self.assertContains(klient(self.z.ola).get(reverse("konto_przypomnienie")), "Nie masz dziś zadań z terminem")
