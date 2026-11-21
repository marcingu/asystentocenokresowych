"""Panel informatyka: uprawnienia, rzeczywisty skutek zmian, walidacja i dziennik."""
from datetime import date
from unittest.mock import patch

from django.test import override_settings

from asystent_ocen.konfiguracja import DOMYSLNY_PLIK
from oceny import uslugi
from oceny.models import ZdarzenieBezpieczenstwa

from .pomocnicze import dyrektor_generalny
from .test_administracja import Podstawa
from .test_widoki import klient

ADRES = "/przepisy/"
KOD = "PYTANIA_O_PROCEDURE"


class PanelTest(Podstawa):
    def test_dostep_i_menu(self):
        self.assertContains(self.przegladarka.get(ADRES), 'name="tresc"')
        for osoba in (self.z.kadry, dyrektor_generalny()):
            czytelnik = klient(osoba)
            self.assertNotContains(czytelnik.get(ADRES), 'name="tresc"')
            self.assertContains(czytelnik.get(ADRES), "Tylko podgląd")
            self.assertEqual(czytelnik.post(ADRES, {"akcja": "toml"}).status_code, 403)
        for osoba in (self.z.ola, self.z.szef):
            self.assertEqual(klient(osoba).get(ADRES).status_code, 403)
            self.assertNotContains(klient(osoba).get("/"), 'href="/przepisy/"')

    def zapisz(self, tekst, wersja=0):
        return self.przegladarka.post(ADRES, {"akcja": "toml", "tresc": tekst, "wersja": wersja})

    def przelacz(self, kod, stan, wersja):
        return self.przegladarka.post(ADRES, {"akcja": "opcja", "kod": kod, "stan": stan, "wersja": wersja})

    def test_zmieniony_termin_na_liscie_zadan_i_w_dzienniku(self):
        tekst = DOMYSLNY_PLIK.read_text(encoding="utf-8")
        nowy = tekst.replace("rozpatrzenie_sprzeciwu_dni = 14", "rozpatrzenie_sprzeciwu_dni = 21")
        ocena = self.z.ocena_zakonczona()
        uslugi.wnies_sprzeciw(ocena, self.z.ola.uzytkownik, tresc="Proszę o ponowną ocenę.", data=date(2026, 11, 10))
        self.assertEqual(self.zapisz(nowy).status_code, 302)
        self.assertContains(klient(self.z.ola).get("/"), "01.12.2026")
        self.assertContains(klient(self.z.kadry).get(ADRES), "rozpatrzenie_sprzeciwu_dni = 21")
        wpis = ZdarzenieBezpieczenstwa.objects.get(rodzaj="ZMIANA_KONFIGURACJI")
        self.assertEqual(wpis.login, self.admin.username)
        for slad in ("-rozpatrzenie_sprzeciwu_dni = 14", "+rozpatrzenie_sprzeciwu_dni = 21"):
            self.assertIn(slad, wpis.opis)
        self.assertEqual(self.zapisz(tekst).status_code, 409)
        self.assertContains(klient(self.z.kadry).get(ADRES), "rozpatrzenie_sprzeciwu_dni = 21")

    def test_blad_skladni_lub_parametrow_nie_zmienia_konfiguracji(self):
        for tekst in ("[", "[terminy]\nsprzeciw_dni = 7"):
            self.assertEqual(self.zapisz(tekst).status_code, 400)
        self.assertFalse(ZdarzenieBezpieczenstwa.objects.filter(rodzaj="ZMIANA_KONFIGURACJI").exists())

    @override_settings(ASYSTENT_DECYZJE_AI="")
    def test_wylaczenie_blokuje_model_w_aplikacji_i_mozna_je_cofnac(self):
        self.assertEqual(self.przelacz(KOD, "wylacz", 0).status_code, 302)
        with patch("oceny.copilot.KlientOllama.__call__") as model:
            self.assertContains(klient(self.z.ola).post("/asystent/", {"pytanie": "Ile dni na sprzeciw?"}), "wyłączona")
            model.assert_not_called()
        self.assertEqual(self.przelacz(KOD, "wlacz", 1).status_code, 302)
        wpisy = ZdarzenieBezpieczenstwa.objects.filter(rodzaj="ZMIANA_KONFIGURACJI").order_by("pk")
        self.assertEqual(len(wpisy), 2)
        self.assertIn(KOD, wpisy[0].opis)

    @override_settings(ASYSTENT_DECYZJE_AI="")
    def test_przelacznik_nie_zastepuje_decyzji_urzedu(self):
        for kod in ("ANALIZA_EMOCJI", "PROPOZYCJA_OCENY", "NIEZNANA_FUNKCJA"):
            self.assertEqual(self.przelacz(kod, "wlacz", 0).status_code, 400)
