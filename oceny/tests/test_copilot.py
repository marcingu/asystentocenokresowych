"""HR Copilot na karcie oceny: projekt uzasadnienia ułożony z notatek oceniającego.

Wymagania zespołu (architektura v3, moduł 2 „HR Copilot”; architektura v4, pkt 2 i 4): model lokalny i człowiek
w pętli - etykieta AI, brak autozapisu, przycisk „Wstaw do formularza”; HR Copilot nie dostaje wskaźników z EZD RP.
Decyzja projektowa ponad te wymagania: model nie dostaje też ocen cząstkowych, szkicu ani wyniku oceny.
"""

import dataclasses
import json
from datetime import date, timedelta
from unittest import mock

from django.test import TestCase, override_settings

from asystent_ocen.asystent_ai import FUNKCJA_REDAKCJI, BladModelu
from asystent_ocen.kryteria import kryteria_obowiazkowe
from asystent_ocen.zgodnosc import wczytaj_wymogi
from oceny import copilot, uslugi
from oceny.models import Ocena, UstaleniaMonitoringu, Zdarzenie

from .pomocnicze import DZIEN_OCENY, DZIEN_ROZMOWY, Zespol
from .test_widoki import czynnosc, klient

DZIEN = date(2026, 11, 2)
NOTATKA = "Ola Testowy przygotowała procedurę obiegu korespondencji; wdrożona bez poprawek."
PROJEKT = "Przygotowała procedurę obiegu korespondencji, którą wdrożono bez poprawek."
PRZYCISK = "Ułóż projekt uzasadnienia z moich notatek"


class ModelAtrapa:
    """Zapamiętuje wiadomości i zwraca ustaloną odpowiedź albo zgłasza ustalony błąd."""

    def __init__(self, odpowiedz: str = PROJEKT):
        self.odpowiedz = odpowiedz
        self.blad: Exception | None = None
        self.wiadomosci: list[list[dict]] = []

    def __call__(self, wiadomosci: list[dict]) -> str:
        self.wiadomosci.append(wiadomosci)
        if self.blad is not None:
            raise self.blad
        return self.odpowiedz

    @property
    def wyslane(self) -> str:
        return "\n".join(wiadomosc["content"] for rozmowa in self.wiadomosci for wiadomosc in rozmowa)


class Podstawa(TestCase):
    """Ocena na etapie oceniania i lokalny model zastąpiony atrapą."""

    pola_ocenianego: dict = {}

    def setUp(self):
        self.z = Zespol(**self.pola_ocenianego)
        self.ocena = self.z.ocena_z_kryteriami()
        self.model = ModelAtrapa()
        atrapa = mock.patch("oceny.copilot.model", return_value=self.model)
        atrapa.start()
        self.addCleanup(atrapa.stop)
        self.adres = czynnosc(self.ocena, "projekt-uzasadnienia")
        self.karta = f"/oceny/{self.ocena.pk}/"

    def notatka(self, tresc: str = NOTATKA) -> None:
        uslugi.dodaj_notatke(self.ocena, self.z.szef.uzytkownik, tresc=tresc, data=date(2025, 6, 10))


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat())
class ProjektUzasadnieniaTest(Podstawa):
    def test_przycisk_widzi_tylko_oceniajacy(self):
        self.assertContains(klient(self.z.szef).get(self.karta), PRZYCISK)
        self.assertNotContains(klient(self.z.ola).get(self.karta), PRZYCISK)
        self.assertNotContains(klient(self.z.kadry).get(self.karta), PRZYCISK)

    def test_oceniajacy_dostaje_projekt_z_etykieta_ai_i_przyciskiem_wstawienia(self):
        """Architektura v3: fragment oznaczony etykietą AI, przycisk „Wstaw do formularza”."""
        self.notatka()

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, PROJEKT)
        self.assertContains(odpowiedz, "Projekt przygotowany przez model językowy")
        self.assertContains(odpowiedz, "Wstaw do formularza")
        self.assertEqual(len(self.model.wiadomosci), 1)
        self.assertIn("przygotowała procedurę obiegu korespondencji", self.model.wyslane)

    def test_projekt_nie_zapisuje_sie_sam(self):
        """Architektura v3: brak autozapisu - w bazie zostaje tylko to, co wpisał i zatwierdził człowiek."""
        self.notatka()
        szef = klient(self.z.szef)

        szef.post(self.adres, {"uzasadnienie": "Tekst oceniającego."})

        z_bazy = Ocena.objects.get(pk=self.ocena.pk)
        self.assertEqual(z_bazy.szkic["uzasadnienie"], "Tekst oceniającego.")
        self.assertNotIn(PROJEKT, json.dumps([z_bazy.szkic, z_bazy.stan], ensure_ascii=False, default=str))
        self.assertNotContains(szef.get(self.karta), PROJEKT)

    def test_dane_wpisane_w_formularzu_nie_przepadaja(self):
        self.notatka()

        odpowiedz = klient(self.z.szef).post(self.adres, {"wnioski_iprz": "Szkolenie z KPA.", "ocena_0": "7"})

        self.assertContains(odpowiedz, "Szkolenie z KPA.")
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).szkic["oceny"], {kryteria_obowiazkowe("C")[0]: 7})

    def test_imie_i_nazwisko_ocenianego_nie_trafiaja_do_modelu(self):
        self.notatka()
        self.model.odpowiedz = "[OSOBA_1] przygotowała procedurę obiegu korespondencji."

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertNotIn("Testowy", self.model.wyslane)
        self.assertContains(odpowiedz, "Ola Testowy przygotowała procedurę obiegu korespondencji.")

    def test_tylko_oceniajacy_moze_poprosic_o_projekt(self):
        self.notatka()

        self.assertEqual(klient(self.z.ola).post(self.adres).status_code, 403)
        self.assertEqual(klient(self.z.kadry).post(self.adres).status_code, 403)
        self.assertEqual(klient(self.z.obcy).post(self.adres).status_code, 404)
        self.assertEqual(self.model.wiadomosci, [])

    def test_bez_notatek_model_nie_jest_wywolywany(self):
        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, "Nie ma jeszcze notatek")
        self.assertEqual(self.model.wiadomosci, [])
        self.assertFalse(Zdarzenie.objects.filter(czynnosc=uslugi.CZYNNOSC_PROJEKT_AI).exists())

    def test_niedostepny_model_nie_blokuje_oceny(self):
        self.notatka()
        self.model.blad = BladModelu("brak połączenia")

        odpowiedz = klient(self.z.szef).post(self.adres, {"uzasadnienie": "Tekst oceniającego."})

        self.assertContains(odpowiedz, copilot.MODEL_NIEDOSTEPNY)
        self.assertContains(odpowiedz, "Tekst oceniającego.")
        self.assertContains(odpowiedz, "Zatwierdź ocenę")

    def test_ostrzezenia_kontroli_projektu_sa_pokazane(self):
        self.notatka()
        self.model.odpowiedz = "Praca zasługuje na ocenę powyżej oczekiwań."

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, "Kontrola projektu")
        self.assertContains(odpowiedz, "ocenę i poziom ustala wyłącznie oceniający")

    def test_funkcja_wylaczona_w_rejestrze_znika_z_karty_i_nie_wywoluje_modelu(self):
        """Urząd wyłącza funkcję jedną zmianą w zgodnosc.toml."""
        self.notatka()
        wymogi = wczytaj_wymogi()
        bez_redakcji = dataclasses.replace(wymogi, funkcje_ai=tuple(
            dataclasses.replace(funkcja, wlaczona=funkcja.wlaczona and funkcja.kod != FUNKCJA_REDAKCJI)
            for funkcja in wymogi.funkcje_ai
        ))
        szef = klient(self.z.szef)

        with mock.patch("asystent_ocen.zgodnosc._wymogi_domyslne", return_value=bez_redakcji):
            self.assertNotContains(szef.get(self.karta), PRZYCISK)
            odpowiedz = szef.post(self.adres)

        self.assertContains(odpowiedz, "wyłączona w rejestrze funkcji AI")
        self.assertEqual(self.model.wiadomosci, [])


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_TRYB_DEMO=True)
class GraniceDanychTest(Podstawa):
    pola_ocenianego = {"klauzula_ezd_potwierdzona": True, "identyfikator_ezd": "stanowisko-ola"}

    def test_model_dostaje_tylko_notatki_bez_ocen_formularza_i_danych_z_ezd(self):
        """Architektura v3 i v4: HR Copilot nie otrzymuje wskaźników z EZD RP. Decyzja projektowa: ani ocen."""
        UstaleniaMonitoringu.objects.create(
            integracja_wlaczona=True, data_poinformowania=DZIEN - timedelta(days=30), podstawa="Regulamin pracy.",
            cele="Organizacja pracy.", zakres="Liczba i terminowość spraw.", sposob="Zestawienie zbiorcze.",
        )
        self.notatka("Prowadzi rejestr umów bez zaległości.")
        nazwy = kryteria_obowiazkowe("C") + self.z.dodatkowe()
        dane = {f"ocena_{numer}": "9" for numer in range(len(nazwy))}
        dane.update({"uzasadnienie": "Tekst-z-formularza.", "wnioski_iprz": "Wnioski-z-formularza."})

        odpowiedz = klient(self.z.szef).post(self.adres, dane)

        self.assertContains(odpowiedz, "Sprawy zakończone w okresie")  # karta faktów jest na stronie...
        wyslane = self.model.wyslane
        self.assertIn("Prowadzi rejestr umów bez zaległości.", wyslane)
        for obce in [*nazwy, "Tekst-z-formularza", "Wnioski-z-formularza", "Sprawy zakończone", "EZD", "9"]:
            self.assertNotIn(obce, wyslane)  # ...ale do modelu nie trafia nic poza notatkami


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat())
class SladUzyciaTest(Podstawa):
    def test_uzycie_ai_zostaje_w_historii_bez_tresci_projektu(self):
        self.notatka()

        klient(self.z.szef).post(self.adres)

        zdarzenie = Zdarzenie.objects.get(ocena=self.ocena, czynnosc=uslugi.CZYNNOSC_PROJEKT_AI)
        self.assertNotIn("procedur", zdarzenie.opis)
        self.assertContains(klient(self.z.szef).get(self.karta), uslugi.CZYNNOSC_PROJEKT_AI)

    def test_oceniany_widzi_slad_dopiero_po_sporzadzeniu_oceny(self):
        """Praca nad oceną jest niejawna do jej sporządzenia (jak szkic); potem użycie AI jest jawne dla stron."""
        self.notatka()
        klient(self.z.szef).post(self.adres)
        ola = klient(self.z.ola)

        self.assertNotContains(ola.get(self.karta), uslugi.CZYNNOSC_PROJEKT_AI)
        uslugi.sporzadz_ocene(
            self.ocena, self.z.szef.uzytkownik, data_rozmowy=DZIEN_ROZMOWY, oceny=self.z.oceny(7),
            wnioski_iprz="Szkolenie.", data=DZIEN_OCENY,
        )
        self.assertContains(ola.get(self.karta), uslugi.CZYNNOSC_PROJEKT_AI)


@override_settings(ASYSTENT_DZIS=DZIEN_OCENY.isoformat())
class PozaEtapemOcenianiaTest(TestCase):
    def test_po_sporzadzeniu_oceny_projektu_nie_da_sie_zamowic(self):
        z = Zespol()
        ocena = z.ocena_do_zapoznania()
        model = ModelAtrapa()

        with mock.patch("oceny.copilot.model", return_value=model):
            odpowiedz = klient(z.szef).post(czynnosc(ocena, "projekt-uzasadnienia"), follow=True)

        self.assertContains(odpowiedz, "tylko na etapie dokonywania oceny")
        self.assertNotContains(odpowiedz, PRZYCISK)
        self.assertEqual(model.wiadomosci, [])
