"""Sugestia ocen cząstkowych na karcie oceny - funkcja wysokiego ryzyka, którą włącza tylko decyzja urzędu.

Wymaganie: decyzje prowadzącego projekt z 21.11.2026 - model sugeruje oceniającemu oceny cząstkowe; w repozytorium
funkcja jest wyłączona, a włącza ją plik decyzji urzędu (w pokazie `decyzje-ai-pokaz.toml`).
Klasyfikacja: zał. III pkt 4 lit. b AI Act (dokumentacja/analiza-prawna-ai-act-kp-rodo.md, pkt 3.6).
Decyzje projektowe: sugestia powstaje z notatek oceniającego (bez danych z EZD RP i bez szkicu oceny), nie jest
zapisywana i nie da się jej przenieść do formularza; użycie funkcji zostaje w historii czynności.
"""

import json
import os
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from asystent_ocen.asystent_ai import MIN_NOTATEK_DO_SUGESTII, BladModelu
from asystent_ocen.kryteria import kryteria_obowiazkowe
from asystent_ocen.przebieg import OSIAGNIECIE
from oceny import copilot, uslugi
from oceny.models import Ocena, UstaleniaMonitoringu, Zdarzenie

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import DZIEN_OCENY, DZIEN_ROZMOWY, Zespol
from .test_widoki import czynnosc, klient

KATALOG = Path(__file__).resolve().parents[2]
DECYZJE_POKAZU = str(KATALOG / "decyzje-ai-pokaz.toml")
DZIEN = date(2026, 11, 2)
PRZYCISK = "Zasugeruj oceny cząstkowe z moich notatek"
NAGLOWEK = "Sugestia modelu językowego"
NOTATKI = [
    "Ola Testowy przygotowała procedurę obiegu korespondencji; wdrożona bez poprawek.",
    "Sprawy z zakresu skarg załatwia przed terminem.",
    "Na prośby innych wydziałów odpowiada tego samego dnia.",
]


class ModelAtrapa:
    """Zapamiętuje wiadomości i schemat; zwraca sugestię 7 dla każdego kryterium albo zgłasza ustalony błąd."""

    def __init__(self, kryteria: list[str]):
        self.odpowiedz = json.dumps(
            {nazwa: {"uzasadnienie": f"Podstawa: {nazwa}.", "ocena": 7} for nazwa in kryteria}, ensure_ascii=False
        )
        self.blad: Exception | None = None
        self.wiadomosci: list[list[dict]] = []

    def __call__(self, wiadomosci: list[dict], schemat: dict | None = None) -> str:
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
        self.kryteria = kryteria_obowiazkowe("C") + self.z.dodatkowe()
        self.model = ModelAtrapa(self.kryteria)
        atrapa = mock.patch("oceny.copilot.model", return_value=self.model)
        atrapa.start()
        self.addCleanup(atrapa.stop)
        self.adres = czynnosc(self.ocena, "sugestia-ocen")
        self.karta = f"/oceny/{self.ocena.pk}/"

    def notatki(self, tresci=NOTATKI, od: date = date(2025, 6, 10), **pola) -> None:
        for numer, tresc in enumerate(tresci):
            uslugi.dodaj_notatke(
                self.ocena, self.z.szef.uzytkownik, tresc=tresc, data=od + timedelta(days=numer), **pola
            )

    def wpisy(self):
        return Zdarzenie.objects.filter(ocena=self.ocena, czynnosc=uslugi.CZYNNOSC_SUGESTIA_AI)


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_DECYZJE_AI=None)
class BezDecyzjiUrzeduTest(Podstawa):
    """System po instalacji: żadna funkcja wysokiego ryzyka nie jest włączona."""

    def test_przycisku_nie_ma_nawet_u_oceniajacego(self):
        self.notatki()
        self.assertNotContains(klient(self.z.szef).get(self.karta), PRZYCISK)

    def test_wyslane_zadanie_nie_uruchamia_modelu(self):
        self.notatki()

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, copilot.SUGESTIA_NIEWLACZONA)
        self.assertNotContains(odpowiedz, NAGLOWEK)
        self.assertEqual(self.model.wiadomosci, [])
        self.assertFalse(self.wpisy().exists())

    def test_strona_przepisow_pokazuje_funkcje_jako_wylaczona(self):
        odpowiedz = klient(self.z.szef).get(reverse("przepisy"))

        self.assertContains(odpowiedz, "PROPOZYCJA_OCENY")
        self.assertNotContains(odpowiedz, "włączona decyzją urzędu")
        self.assertNotContains(odpowiedz, "Plik decyzji urzędu")


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_DECYZJE_AI=DECYZJE_POKAZU)
class SugestiaOcenTest(Podstawa):
    def test_przycisk_widzi_tylko_oceniajacy(self):
        self.assertContains(klient(self.z.szef).get(self.karta), PRZYCISK)
        self.assertNotContains(klient(self.z.ola).get(self.karta), PRZYCISK)
        self.assertNotContains(klient(self.z.kadry).get(self.karta), PRZYCISK)

    def test_oceniajacy_dostaje_sugestie_dla_kazdego_kryterium_z_podstawa(self):
        self.notatki()

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, NAGLOWEK)
        self.assertContains(odpowiedz, "wysokiego ryzyka")
        for nazwa in self.kryteria:
            self.assertContains(odpowiedz, f"Podstawa: {nazwa}.")
        self.assertContains(odpowiedz, "<strong>7</strong> - powyżej oczekiwań", count=len(self.kryteria))
        self.assertEqual(len(self.model.wiadomosci), 1)

    def test_sugestii_nie_da_sie_przeniesc_do_formularza_i_nie_zapisuje_sie_sama(self):
        """Oceny wpisuje oceniający: w bazie zostaje tylko to, co sam wybrał w formularzu."""
        self.notatki()
        szef = klient(self.z.szef)

        odpowiedz = szef.post(self.adres, {"ocena_0": "5", "uzasadnienie": "Tekst oceniającego."})

        self.assertNotContains(odpowiedz, "Wstaw do formularza")
        z_bazy = Ocena.objects.get(pk=self.ocena.pk)
        self.assertEqual(z_bazy.szkic["oceny"], {self.kryteria[0]: 5})
        self.assertNotIn("Podstawa:", json.dumps([z_bazy.szkic, z_bazy.stan], ensure_ascii=False, default=str))
        self.assertNotContains(szef.get(self.karta), NAGLOWEK)

    def test_dane_wpisane_w_formularzu_nie_przepadaja(self):
        self.notatki()

        odpowiedz = klient(self.z.szef).post(self.adres, {"wnioski_iprz": "Szkolenie z KPA.", "uzasadnienie": "Tekst."})

        self.assertContains(odpowiedz, "Szkolenie z KPA.")
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).szkic["uzasadnienie"], "Tekst.")

    def test_imie_i_nazwisko_ocenianego_nie_trafiaja_do_modelu(self):
        self.notatki()

        klient(self.z.szef).post(self.adres)

        self.assertNotIn("Testowy", self.model.wyslane)
        self.assertIn("przygotowała procedurę obiegu korespondencji", self.model.wyslane)

    def test_tylko_oceniajacy_moze_poprosic_o_sugestie(self):
        self.notatki()

        self.assertEqual(klient(self.z.ola).post(self.adres).status_code, 403)
        self.assertEqual(klient(self.z.kadry).post(self.adres).status_code, 403)
        self.assertEqual(klient(self.z.obcy).post(self.adres).status_code, 404)
        self.assertEqual(self.model.wiadomosci, [])

    def test_bez_notatek_model_nie_jest_wywolywany(self):
        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, "Nie ma jeszcze notatek")
        self.assertEqual(self.model.wiadomosci, [])
        self.assertFalse(self.wpisy().exists())

    def test_przy_zbyt_malej_liczbie_notatek_model_nie_jest_wywolywany(self):
        self.notatki(NOTATKI[:MIN_NOTATEK_DO_SUGESTII - 1])

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, f"minimalna liczba: {MIN_NOTATEK_DO_SUGESTII}")
        self.assertNotContains(odpowiedz, NAGLOWEK)
        self.assertEqual(self.model.wiadomosci, [])
        self.assertFalse(self.wpisy().exists())

    def test_niedostepny_model_nie_blokuje_oceny(self):
        self.notatki()
        self.model.blad = BladModelu("brak połączenia")

        odpowiedz = klient(self.z.szef).post(self.adres, {"uzasadnienie": "Tekst oceniającego."})

        self.assertContains(odpowiedz, copilot.MODEL_NIEDOSTEPNY)
        self.assertContains(odpowiedz, "Tekst oceniającego.")
        self.assertContains(odpowiedz, "Zatwierdź ocenę")
        self.assertFalse(self.wpisy().exists())

    def test_ostrzezenia_kontroli_sugestii_sa_pokazane(self):
        self.notatki()
        odpowiedz_modelu = json.loads(self.model.odpowiedz)
        odpowiedz_modelu[self.kryteria[0]]["ocena"] = 9
        self.model.odpowiedz = json.dumps(odpowiedz_modelu, ensure_ascii=False)

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, "Kontrola sugestii")
        self.assertContains(odpowiedz, "ocenę skrajną (9)")

    def test_kryterium_bez_podstaw_w_notatkach_nie_dostaje_liczby(self):
        self.notatki()
        odpowiedz_modelu = json.loads(self.model.odpowiedz)
        odpowiedz_modelu[self.kryteria[1]] = {"uzasadnienie": "", "ocena": 0}
        self.model.odpowiedz = json.dumps(odpowiedz_modelu, ensure_ascii=False)

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, "brak sugestii", count=1)
        self.assertContains(odpowiedz, "Notatki nie dają podstaw.", count=1)

    def test_strona_z_sugestia_spelnia_wymagania_dostepnosci_widoczne_w_znacznikach(self):
        """WCAG 2.1 A i AA (dokumentacja/dostepnosc.md): nowy blok ma tabelę z nazwą i nagłówkami w obszarze
        przewijania oraz komunikat o pracy modelu w elemencie role=status."""
        self.notatki()
        szef = klient(self.z.szef)

        self.assertEqual(bledy_dostepnosci(szef.get(self.karta).content.decode()), [])
        self.assertEqual(bledy_dostepnosci(szef.post(self.adres).content.decode()), [])

    def test_strona_przepisow_pokazuje_decyzje_urzedu(self):
        odpowiedz = klient(self.z.szef).get(reverse("przepisy"))

        self.assertContains(odpowiedz, "włączona decyzją urzędu", count=1)
        self.assertContains(odpowiedz, "Pokaz na danych fikcyjnych")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_DECYZJE_AI=DECYZJE_POKAZU, ASYSTENT_TRYB_DEMO=True)
class GraniceDanychTest(Podstawa):
    pola_ocenianego = {"klauzula_ezd_potwierdzona": True, "identyfikator_ezd": "stanowisko-ola"}

    def test_usluga_przekazuje_tylko_notatki_kryteria_i_dane_do_anonimizacji(self):
        """Model dostaje to, co oceniający sam zapisał: obserwacje, osiągnięcia (oznaczone) i wynik egzaminu -
        w kolejności dat."""
        self.notatki(NOTATKI[:2])
        self.notatki(["Przeprowadziła szkolenie dla nowych pracowników."], od=date(2025, 6, 20), rodzaj=OSIAGNIECIE)
        uslugi.zapisz_egzamin(self.ocena, self.z.szef.uzytkownik, punkty="44", punkty_max="50", data=date(2025, 7, 1))
        wywolania = []

        def doradca(*argumenty, **nazwane):
            wywolania.append((argumenty, nazwane))
            return {"blad": "atrapa"}

        uslugi.sugestia_ocen(self.ocena, self.z.szef.uzytkownik, doradca=doradca)

        (argumenty, nazwane), = wywolania
        notatki, kryteria, osoby = argumenty
        self.assertEqual(nazwane, {})
        self.assertEqual(notatki[:2], NOTATKI[:2])
        self.assertEqual(notatki[2], "Dodatkowe osiągnięcie: Przeprowadziła szkolenie dla nowych pracowników.")
        self.assertTrue(notatki[3].startswith("Egzamin ze służby przygotowawczej:"), notatki[3])
        self.assertEqual(kryteria, self.kryteria)
        self.assertEqual(osoby, ["Ola Testowy", "Ola", "Testowy"])

    def test_do_modelu_nie_trafiaja_dane_z_ezd_ani_tresc_formularza(self):
        """Architektura v4: model bez wskaźników z EZD RP. Decyzja projektowa: bez szkicu oceny."""
        UstaleniaMonitoringu.objects.create(
            integracja_wlaczona=True, data_poinformowania=DZIEN - timedelta(days=30), podstawa="Regulamin pracy.",
            cele="Organizacja pracy.", zakres="Liczba i terminowość spraw.", sposob="Zestawienie zbiorcze.",
        )
        self.notatki()
        dane = {"uzasadnienie": "Tekst-z-formularza.", "wnioski_iprz": "Wnioski-z-formularza."}

        odpowiedz = klient(self.z.szef).post(self.adres, dane)

        self.assertContains(odpowiedz, "Sprawy zakończone w okresie")  # karta faktów jest na stronie...
        for obce in ["Tekst-z-formularza", "Wnioski-z-formularza", "Sprawy zakończone", "EZD"]:
            self.assertNotIn(obce, self.model.wyslane)  # ...ale do modelu nie trafia


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_DECYZJE_AI=DECYZJE_POKAZU)
class SladUzyciaTest(Podstawa):
    def test_uzycie_ai_zostaje_w_historii_bez_tresci_sugestii(self):
        self.notatki()

        klient(self.z.szef).post(self.adres)

        zdarzenie = self.wpisy().get()
        self.assertNotIn("Podstawa", zdarzenie.opis)
        self.assertNotIn("7", zdarzenie.opis)
        self.assertContains(klient(self.z.szef).get(self.karta), uslugi.CZYNNOSC_SUGESTIA_AI)

    def test_oceniany_widzi_slad_dopiero_po_sporzadzeniu_oceny(self):
        """Praca nad oceną jest niejawna do jej sporządzenia (jak szkic); potem użycie AI jest jawne dla stron."""
        self.notatki()
        klient(self.z.szef).post(self.adres)
        ola = klient(self.z.ola)

        self.assertNotContains(ola.get(self.karta), uslugi.CZYNNOSC_SUGESTIA_AI)
        uslugi.sporzadz_ocene(
            self.ocena, self.z.szef.uzytkownik, data_rozmowy=DZIEN_ROZMOWY, oceny=self.z.oceny(7),
            wnioski_iprz="Szkolenie.", data=DZIEN_OCENY,
        )
        self.assertContains(ola.get(self.karta), uslugi.CZYNNOSC_SUGESTIA_AI)


@override_settings(ASYSTENT_DZIS=DZIEN_OCENY.isoformat(), ASYSTENT_DECYZJE_AI=DECYZJE_POKAZU)
class PozaEtapemOcenianiaTest(TestCase):
    def test_po_sporzadzeniu_oceny_sugestii_nie_da_sie_zamowic(self):
        z = Zespol()
        ocena = z.ocena_do_zapoznania()
        model = ModelAtrapa(kryteria_obowiazkowe("C") + z.dodatkowe())

        with mock.patch("oceny.copilot.model", return_value=model):
            odpowiedz = klient(z.szef).post(czynnosc(ocena, "sugestia-ocen"), follow=True)

        self.assertContains(odpowiedz, "tylko na etapie dokonywania oceny")
        self.assertNotContains(odpowiedz, PRZYCISK)
        self.assertEqual(model.wiadomosci, [])


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat())
class BlednyPlikDecyzjiTest(Podstawa):
    """Błąd w pliku decyzji niczego nie włącza i nie zatrzymuje reszty systemu."""

    def test_brak_wskazanego_pliku_wylacza_funkcje_i_jest_widoczny_na_stronie_przepisow(self):
        self.notatki()
        szef = klient(self.z.szef)

        with override_settings(ASYSTENT_DECYZJE_AI=str(KATALOG / "nie-ma-takiego-pliku.toml")):
            karta = szef.get(self.karta)
            przepisy = szef.get(reverse("przepisy"))
            odpowiedz = szef.post(self.adres)

        self.assertNotContains(karta, PRZYCISK)
        self.assertContains(karta, "Zatwierdź ocenę")
        self.assertContains(przepisy, "Plik decyzji urzędu")
        self.assertNotContains(przepisy, "włączona decyzją urzędu")
        self.assertNotContains(przepisy, str(KATALOG))  # komunikat nie ujawnia ścieżek serwera
        self.assertContains(odpowiedz, copilot.SUGESTIA_NIEWLACZONA)
        self.assertEqual(self.model.wiadomosci, [])


class PokazTest(TestCase):
    def test_skrypt_pokazu_wskazuje_plik_decyzji_pokazu(self):
        """Decyzja prowadzącego projekt z 21.11.2026: funkcja jest włączona tylko w pokazie na danych fikcyjnych."""
        skrypt = (KATALOG / "uruchom-demo.sh").read_text(encoding="utf-8")
        self.assertIn('ASYSTENT_DECYZJE_AI="${ASYSTENT_DECYZJE_AI-$PWD/decyzje-ai-pokaz.toml}"', skrypt)

    @unittest.skipIf(os.environ.get("ASYSTENT_DECYZJE_AI"), "zmienna ASYSTENT_DECYZJE_AI jest ustawiona w środowisku testów")
    def test_bez_zmiennej_srodowiskowej_zadna_decyzja_nie_obowiazuje(self):
        """Instalacja bez wskazanego pliku decyzji nie ma włączonej żadnej funkcji wysokiego ryzyka."""
        self.assertIsNone(settings.ASYSTENT_DECYZJE_AI)
