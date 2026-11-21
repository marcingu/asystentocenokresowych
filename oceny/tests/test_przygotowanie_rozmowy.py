"""Wirtualny HR partner w aplikacji: pytania do rozmowy oceniającej i kierunki do IPRZ na karcie oceny.

Wymaganie: decyzja prowadzącego projekt z 21.11.2026 (wieczorem) - w widoku rozmowy oceniającej lokalny model
układa z notatek przełożonego 3-5 pytań do rozmowy i proponuje kierunki do IPRZ. Podstawy: § 10 i § 11 ust. 1
pkt 5 rozporządzenia, Poradnik KPRM pkt 6.2.4; klasyfikacja funkcji - `tests/test_przygotowanie_rozmowy.py`.

Decyzje projektowe: podpowiedź powstaje wyłącznie z notatek oceniającego, nie jest zapisywana i do formularza
przenosi ją oceniający; użycie funkcji zostaje w historii czynności; propozycja kierunków do IPRZ jest funkcją
wysokiego ryzyka, którą włącza decyzja urzędu.
"""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from asystent_ocen.asystent_ai import BladModelu
from asystent_ocen.zgodnosc import wczytaj_wymogi
from oceny import copilot, uslugi
from oceny.models import Zdarzenie

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import DZIEN_OCENY, DZIEN_ROZMOWY, Zespol
from .test_widoki import czynnosc, klient

DZIEN = date(2026, 11, 2)
PRZYCISK = "Przygotuj pytania do rozmowy z moich notatek"
NAGLOWEK = "Pytania przygotowane przez model językowy"
KIERUNKI_NAGLOWEK = "Proponowane kierunki do IPRZ"
WYSOKIE_RYZYKO = "Funkcja wysokiego ryzyka według AI Act"
ORGAN = "Dyrektor Generalny Urzędu Testowego"
NOTATKI = [
    "Ola Testowy przygotowała procedurę obiegu korespondencji; wdrożona bez poprawek.",
    "Sprawy z zakresu skarg załatwia przed terminem.",
    "2 projekty pism do ministerstwa wymagały poprawek stylistycznych.",
]
PYTANIA = [
    "Co pomogło przygotować procedurę obiegu korespondencji bez poprawek?",
    "Jak organizuje Pani/Pan pracę, żeby załatwiać skargi przed terminem?",
    "Jakiego wsparcia potrzebuje Pani/Pan przy redagowaniu pism do ministerstwa?",
]
KIERUNEK = "Szkolenie z redagowania pism urzędowych"
PODSTAWA = "Projekty pism wymagały poprawek stylistycznych."

# Decyzja fikcyjnego urzędu o włączeniu propozycji kierunków do IPRZ - z organem, datą i dokumentem każdej analizy.
_KATALOG = tempfile.TemporaryDirectory()
DECYZJE_Z_IPRZ = str(Path(_KATALOG.name) / "decyzje-ai.toml")
Path(DECYZJE_Z_IPRZ).write_text(
    '[[decyzje]]\nkod = "PROPOZYCJA_KIERUNKOW_IPRZ"\n'
    f'organ = "{ORGAN}"\ndata = 2026-10-01\n'
    'decyzja_wlaczenia = "Zarządzenie nr 8/2026: propozycje kierunków rozwoju dla naczelników wydziałów."\n'
    "[decyzje.dokumenty]\n"
    + "".join(f'{warunek.kod} = "Dokument nr {numer}/2026"\n' for numer, warunek in enumerate(wczytaj_wymogi().warunki_wlaczenia, start=1)),
    encoding="utf-8",
)


class ModelAtrapa:
    """Zapamiętuje wiadomości; zwraca przygotowane pytania i kierunki albo zgłasza ustalony błąd."""

    def __init__(self):
        self.odpowiedz = json.dumps(
            {"pytania": PYTANIA, "kierunki_iprz": [{"kierunek": KIERUNEK, "podstawa": PODSTAWA}]}, ensure_ascii=False
        )
        self.blad: Exception | None = None
        self.wiadomosci: list[list[dict]] = []

    def __call__(self, wiadomosci, schemat=None):
        self.wiadomosci.append(wiadomosci)
        if self.blad is not None:
            raise self.blad
        return self.odpowiedz

    @property
    def wyslane(self) -> str:
        return "\n".join(wiadomosc["content"] for rozmowa in self.wiadomosci for wiadomosc in rozmowa)


class Podstawa(TestCase):
    """Ocena na etapie oceniania i lokalny model zastąpiony atrapą."""

    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()
        self.model = ModelAtrapa()
        atrapa = mock.patch("oceny.copilot.model", return_value=self.model)
        atrapa.start()
        self.addCleanup(atrapa.stop)
        self.adres = czynnosc(self.ocena, "przygotowanie-rozmowy")
        self.karta = f"/oceny/{self.ocena.pk}/"

    def notatki(self, tresci=NOTATKI) -> None:
        for numer, tresc in enumerate(tresci):
            uslugi.dodaj_notatke(self.ocena, self.z.szef.uzytkownik, tresc=tresc, data=date(2025, 6, 10) + timedelta(days=numer))

    def wpisy(self, czynnosc_ai):
        return Zdarzenie.objects.filter(ocena=self.ocena, czynnosc=czynnosc_ai)


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat())
class PytaniaDoRozmowyTest(Podstawa):
    """Po instalacji: pytania działają, kierunków do IPRZ model nie proponuje."""

    def test_karta_oceniajacego_ma_przygotowanie_rozmowy_z_tematami_z_rozporzadzenia(self):
        odpowiedz = klient(self.z.szef).get(self.karta)

        self.assertContains(odpowiedz, "Przygotowanie rozmowy oceniającej")
        self.assertContains(odpowiedz, "§ 10 rozp.")
        self.assertContains(odpowiedz, "kierunki dalszego rozwoju zawodowego")
        self.assertContains(odpowiedz, "dialogiem")
        self.assertContains(odpowiedz, PRZYCISK, count=1)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_model_uklada_pytania_z_notatek_a_strona_je_pokazuje(self):
        self.notatki()

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, NAGLOWEK, count=1)
        for pytanie in PYTANIA:
            self.assertContains(odpowiedz, pytanie, count=1)
        self.assertContains(odpowiedz, 'id="rozmowa-ai"', count=1)
        self.assertContains(odpowiedz, "wyjątku z art. 6 ust. 3 AI Act")
        self.assertIn(NOTATKI[1], self.model.wyslane)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_po_instalacji_nie_ma_kierunkow_iprz_ani_ostrzezenia_o_wysokim_ryzyku(self):
        self.notatki()

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertNotContains(odpowiedz, KIERUNKI_NAGLOWEK)
        self.assertNotContains(odpowiedz, KIERUNEK)
        self.assertNotContains(odpowiedz, WYSOKIE_RYZYKO)
        self.assertEqual(self.wpisy(uslugi.CZYNNOSC_IPRZ_AI).count(), 0)

    def test_model_nie_dostaje_danych_osobowych_ocen_ani_danych_z_ezd_rp(self):
        self.notatki()
        szef = klient(self.z.szef)
        szef.post(czynnosc(self.ocena, "szkic"), {"ocena_0": "9", "uzasadnienie": "Tajny szkic uzasadnienia."})

        szef.post(self.adres, {"ocena_0": "9", "uzasadnienie": "Tajny szkic uzasadnienia."})

        self.assertNotIn("Ola", self.model.wyslane)
        self.assertNotIn("Testowy", self.model.wyslane)
        self.assertNotIn("Tajny szkic", self.model.wyslane)

    def test_pytania_nie_sa_zapisywane_a_dane_formularza_nie_przepadaja(self):
        self.notatki()
        szef = klient(self.z.szef)

        szef.post(self.adres, {"ocena_0": "7", "wnioski_iprz": "Własny wniosek."})

        self.ocena.refresh_from_db()
        self.assertEqual(self.ocena.szkic["wnioski_iprz"], "Własny wniosek.")
        self.assertNotIn(PYTANIA[0], json.dumps(self.ocena.szkic, ensure_ascii=False))
        self.assertNotIn(PYTANIA[0], json.dumps(self.ocena.stan, ensure_ascii=False))
        self.assertNotContains(szef.get(self.karta), PYTANIA[0])

    def test_bez_notatek_model_nie_jest_pytany(self):
        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, "Nie ma jeszcze notatek z okresu oceny")
        self.assertNotContains(odpowiedz, NAGLOWEK)
        self.assertEqual(self.model.wiadomosci, [])
        self.assertEqual(self.wpisy(uslugi.CZYNNOSC_ROZMOWA_AI).count(), 0)

    def test_niedostepny_model_daje_komunikat_a_formularz_dziala(self):
        self.notatki()
        self.model.blad = BladModelu("brak połączenia")

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, copilot.MODEL_NIEDOSTEPNY)
        self.assertContains(odpowiedz, "Zatwierdź ocenę")
        self.assertEqual(self.wpisy(uslugi.CZYNNOSC_ROZMOWA_AI).count(), 0)

    def test_oceniany_i_kadry_nie_widza_przycisku_i_nie_moga_wywolac_funkcji(self):
        self.notatki()
        for osoba in (self.z.ola, self.z.kadry):
            with self.subTest(osoba=osoba.imie):
                przegladarka = klient(osoba)
                self.assertNotContains(przegladarka.get(self.karta), PRZYCISK)
                self.assertEqual(przegladarka.post(self.adres).status_code, 403)
        self.assertEqual(klient(self.z.obcy).post(self.adres).status_code, 404)
        self.assertEqual(self.model.wiadomosci, [])

    def test_uzycie_zostaje_w_historii_bez_tresci_i_oceniany_widzi_je_po_sporzadzeniu_oceny(self):
        self.notatki()
        klient(self.z.szef).post(self.adres)

        wpis = self.wpisy(uslugi.CZYNNOSC_ROZMOWA_AI).get()
        self.assertNotIn("procedur", wpis.opis)
        ola = klient(self.z.ola)
        self.assertNotContains(ola.get(self.karta), uslugi.CZYNNOSC_ROZMOWA_AI)
        uslugi.sporzadz_ocene(
            self.ocena, self.z.szef.uzytkownik, data_rozmowy=DZIEN_ROZMOWY, oceny=self.z.oceny(7),
            wnioski_iprz="Szkolenie.", data=DZIEN_OCENY,
        )
        po = ola.get(self.karta)
        self.assertContains(po, uslugi.CZYNNOSC_ROZMOWA_AI)
        self.assertContains(po, "Informacja o użyciu AI przy tej ocenie", count=1)
        self.assertNotContains(po, "funkcja wysokiego ryzyka według AI Act")

    def test_funkcja_wylaczona_w_rejestrze_znika_z_karty_i_nie_wywoluje_modelu(self):
        import dataclasses

        self.notatki()
        wymogi = wczytaj_wymogi()
        bez_pytan = dataclasses.replace(wymogi, funkcje_ai=tuple(
            dataclasses.replace(f, wlaczona=f.wlaczona and f.kod != copilot.FUNKCJA_PYTAN_DO_ROZMOWY) for f in wymogi.funkcje_ai
        ))
        with mock.patch("asystent_ocen.zgodnosc._wymogi_domyslne", return_value=bez_pytan):
            szef = klient(self.z.szef)
            self.assertNotContains(szef.get(self.karta), PRZYCISK)
            self.assertContains(szef.post(self.adres), copilot.FUNKCJA_WYLACZONA)
        self.assertEqual(self.model.wiadomosci, [])


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_DECYZJE_AI=DECYZJE_Z_IPRZ)
class KierunkiIprzTest(Podstawa):
    """Po decyzji urzędu model proponuje także kierunki do IPRZ - funkcja wysokiego ryzyka."""

    def test_przy_przycisku_jest_informacja_o_funkcji_wysokiego_ryzyka_i_decyzji_urzedu(self):
        odpowiedz = klient(self.z.szef).get(self.karta)

        self.assertContains(odpowiedz, WYSOKIE_RYZYKO, count=1)
        self.assertContains(odpowiedz, ORGAN, count=1)
        self.assertContains(odpowiedz, "01.10.2026")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_strona_pokazuje_kierunki_z_podstawa_i_przyciskiem_wstawienia_do_wnioskow_iprz(self):
        self.notatki()

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, KIERUNKI_NAGLOWEK, count=1)
        self.assertContains(odpowiedz, KIERUNEK)
        self.assertContains(odpowiedz, PODSTAWA)
        self.assertContains(odpowiedz, 'data-wstaw-z="kierunki-iprz" data-wstaw-do="wnioski_iprz"', count=1)
        self.assertContains(odpowiedz, WYSOKIE_RYZYKO, count=2)  # przy przycisku i przy wygenerowanej treści
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_kierunki_nie_trafiaja_same_do_wnioskow_iprz(self):
        self.notatki()

        klient(self.z.szef).post(self.adres, {"wnioski_iprz": ""})

        self.ocena.refresh_from_db()
        self.assertEqual(self.ocena.szkic["wnioski_iprz"], "")

    def test_uzycie_funkcji_wysokiego_ryzyka_zostaje_w_historii_i_w_informacji_dla_ocenianego(self):
        self.notatki()
        klient(self.z.szef).post(self.adres)

        self.assertEqual(self.wpisy(uslugi.CZYNNOSC_IPRZ_AI).count(), 1)
        uslugi.sporzadz_ocene(
            self.ocena, self.z.szef.uzytkownik, data_rozmowy=DZIEN_ROZMOWY, oceny=self.z.oceny(7),
            wnioski_iprz="Szkolenie.", data=DZIEN_OCENY,
        )
        po = klient(self.z.ola).get(self.karta)
        self.assertContains(po, uslugi.CZYNNOSC_IPRZ_AI)
        self.assertContains(po, "funkcja wysokiego ryzyka według AI Act")
        self.assertContains(po, ORGAN)
        self.assertEqual(bledy_dostepnosci(po.content.decode()), [])

    def test_przy_mniej_niz_3_notatkach_sa_pytania_bez_kierunkow(self):
        self.notatki(NOTATKI[:2])

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, PYTANIA[0])
        self.assertNotContains(odpowiedz, KIERUNKI_NAGLOWEK)
        self.assertContains(odpowiedz, "co najmniej 3 notatek")
        self.assertEqual(self.wpisy(uslugi.CZYNNOSC_IPRZ_AI).count(), 0)
