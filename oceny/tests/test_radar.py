"""Radar Dobrostanu i Doceniania na karcie oceny: karty obserwacji dla pracownika i przełożonego.

Wymaganie (decyzja prowadzącego projekt z 21.11.2026): radar pokazuje pracownikowi i jego przełożonemu neutralne
karty obserwacji zbudowane z liczb z EZD RP i systemu kadrowego; korzysta też z modelu językowego.
Reguły kart i klasyfikacja funkcji modelu - `tests/test_radar.py`.

Decyzje projektowe: karty widzą obie strony oceny i nikt poza nimi; zanim radar cokolwiek pokaże, muszą być
spełnione te same warunki Kodeksu pracy co przy karcie z EZD RP (art. 22[2] § 6-8 w zw. z art. 22[3] § 3-4 KP);
bez połączenia ze źródłami radar pokazuje dane tylko w trybie demonstracyjnym i oznacza je jako przykładowe;
pytania do kart układa model dopiero po decyzji urzędu (funkcja wysokiego ryzyka), dostaje same karty,
a podpowiedź nie jest zapisywana.
"""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings

from asystent_ocen.asystent_ai import BladModelu
from asystent_ocen.zgodnosc import wczytaj_wymogi
from oceny import uslugi
from oceny.models import UstaleniaMonitoringu, Zdarzenie
from oceny.radar import BRAK_ZRODLA, GOTOWY, WYLACZONY, ZABLOKOWANY, radar_oceny

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import Zespol
from .test_widoki import czynnosc, klient

DZIEN = date(2026, 11, 2)
NAGLOWEK = "Radar dobrostanu i doceniania"
PRZYCISK = "Zaproponuj pytania do kart obserwacji"
NAGLOWEK_AI = "Pytania do kart przygotowane przez model językowy"
WYSOKIE_RYZYKO = "Funkcja wysokiego ryzyka według AI Act"
ORGAN = "Dyrektor Generalny Urzędu Testowego"

# Decyzja fikcyjnego urzędu o włączeniu pytań do kart - z organem, datą i dokumentem każdej analizy.
_KATALOG = tempfile.TemporaryDirectory()
DECYZJE_Z_RADAREM = str(Path(_KATALOG.name) / "decyzje-ai.toml")
Path(DECYZJE_Z_RADAREM).write_text(
    '[[decyzje]]\nkod = "RADAR_PYTANIA_DO_KART"\n'
    f'organ = "{ORGAN}"\ndata = 2026-10-01\n'
    'decyzja_wlaczenia = "Zarządzenie nr 9/2026: pytania do kart obserwacji dla naczelników wydziałów."\n'
    "[decyzje.dokumenty]\n"
    + "".join(f'{warunek.kod} = "Dokument nr {numer}/2026"\n' for numer, warunek in enumerate(wczytaj_wymogi().warunki_wlaczenia, start=1)),
    encoding="utf-8",
)


def ustalenia(**zmiany) -> UstaleniaMonitoringu:
    dane = {
        "integracja_wlaczona": True, "data_poinformowania": DZIEN - timedelta(days=30),
        "podstawa": "Regulamin pracy, § 27a.", "cele": "Organizacja pracy i planowanie urlopów.",
        "zakres": "Liczby spraw w EZD RP, urlopy, godziny nadliczbowe i zastępstwa.", "sposob": "Karty obserwacji.",
        **zmiany,
    }
    return UstaleniaMonitoringu.objects.create(**dane)


class ModelAtrapa:
    """Zapamiętuje wiadomości; zwraca przygotowane pytania albo zgłasza ustalony błąd."""

    def __init__(self):
        self.pytania: list[dict] = []
        self.blad: Exception | None = None
        self.wiadomosci: list[list[dict]] = []

    def __call__(self, wiadomosci, schemat=None):
        self.wiadomosci.append(wiadomosci)
        if self.blad is not None:
            raise self.blad
        return json.dumps({"pytania": self.pytania}, ensure_ascii=False)

    @property
    def wyslane(self) -> str:
        return "\n".join(wiadomosc["content"] for rozmowa in self.wiadomosci for wiadomosc in rozmowa)


class Podstawa(TestCase):
    """Ocena na etapie oceniania, spełnione warunki Kodeksu pracy i lokalny model zastąpiony atrapą."""

    def setUp(self):
        self.z = Zespol(klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-anna")
        self.ocena = self.z.ocena_z_kryteriami()
        ustalenia()
        self.model = ModelAtrapa()
        atrapa = mock.patch("oceny.copilot.model", return_value=self.model)
        atrapa.start()
        self.addCleanup(atrapa.stop)
        self.adres = czynnosc(self.ocena, "pytania-radaru")
        self.karta = f"/oceny/{self.ocena.pk}/"

    def karty(self):
        return radar_oceny(self.ocena, DZIEN).karty

    def wpisy(self):
        return Zdarzenie.objects.filter(ocena=self.ocena, czynnosc=uslugi.CZYNNOSC_RADAR_AI)


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_TRYB_DEMO=True)
class KartyObserwacjiNaKarcieOcenyTest(Podstawa):
    def test_przelozony_i_pracownik_widza_te_same_karty(self):
        szef = klient(self.z.szef).get(self.karta)
        ola = klient(self.z.ola).get(self.karta)

        karty = self.karty()
        self.assertGreaterEqual(len(karty), 3)
        for odpowiedz in (szef, ola):
            self.assertContains(odpowiedz, NAGLOWEK, count=1)
            for karta in karty:
                self.assertContains(odpowiedz, karta.fakt, count=1)
                self.assertContains(odpowiedz, karta.podstawa)
            self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_karty_sa_podzielone_na_dobrostan_i_docenienie_i_oznaczone_jako_dane_przykladowe(self):
        odpowiedz = klient(self.z.szef).get(self.karta)

        radar = odpowiedz.context["radar"]
        self.assertEqual(radar.stan, GOTOWY)
        self.assertTrue(radar.dobrostan and radar.docenienie)
        self.assertEqual(len(radar.dobrostan) + len(radar.docenienie), len(radar.karty))
        self.assertContains(odpowiedz, "Pokaz: dane przykładowe zamiast połączenia z systemem kadrowym i EZD RP.")
        self.assertContains(odpowiedz, "Bez punktów, rankingu i wniosków o zdrowiu albo emocjach")
        self.assertContains(odpowiedz, "nie są kryterium oceny okresowej")

    def test_komorka_kadr_nie_widzi_radaru(self):
        """Minimalizacja danych: karty są dla pracownika i jego bezpośredniego przełożonego."""
        odpowiedz = klient(self.z.kadry).get(self.karta)

        self.assertNotContains(odpowiedz, NAGLOWEK)
        self.assertNotIn("radar", odpowiedz.context)

    def test_bez_wlaczonej_integracji_radaru_nie_ma(self):
        UstaleniaMonitoringu.objects.update(integracja_wlaczona=False)

        self.assertEqual(radar_oceny(self.ocena, DZIEN).stan, WYLACZONY)
        self.assertNotContains(klient(self.z.szef).get(self.karta), NAGLOWEK)

    def test_bez_informacji_dla_pracownika_radar_nie_pokazuje_danych(self):
        """Art. 22[2] § 8 w zw. z art. 22[3] § 3 i 4 KP: pracownik dostaje informację o celach, zakresie i sposobie."""
        self.z.ola.klauzula_ezd_potwierdzona = False
        self.z.ola.save()

        radar = radar_oceny(self.ocena, DZIEN)
        odpowiedz = klient(self.z.szef).get(self.karta)

        self.assertEqual((radar.stan, radar.karty), (ZABLOKOWANY, ()))
        self.assertEqual([blad.kod for blad in radar.przeszkody], ["BRAK_INFORMACJI_DLA_PRACOWNIKA"])
        self.assertContains(odpowiedz, NAGLOWEK, count=1)
        self.assertContains(odpowiedz, "Radar nie pokazuje danych, dopóki nie zostaną spełnione warunki Kodeksu pracy.")
        self.assertNotContains(odpowiedz, "Urlop zaległy")

    def test_za_wczesnie_po_poinformowaniu_radar_jest_zablokowany(self):
        """Art. 22[2] § 7 KP: pracowników informuje się nie później niż 2 tygodnie przed uruchomieniem."""
        UstaleniaMonitoringu.objects.update(data_poinformowania=DZIEN - timedelta(days=3))

        self.assertEqual(radar_oceny(self.ocena, DZIEN).stan, ZABLOKOWANY)

    @override_settings(ASYSTENT_TRYB_DEMO=False, ASYSTENT_EZD_ADRES=None)
    def test_poza_pokazem_bez_polaczenia_ze_zrodlami_radar_nie_zmysla_danych(self):
        radar = radar_oceny(self.ocena, DZIEN)

        self.assertEqual((radar.stan, radar.karty, radar.dane_przykladowe), (BRAK_ZRODLA, (), False))
        self.assertIn("nie jest skonfigurowane", radar.komunikat)


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_TRYB_DEMO=True)
class PytaniaDoKartPoInstalacjiTest(Podstawa):
    """Funkcja wysokiego ryzyka: bez decyzji urzędu model nie dostaje kart."""

    def test_przycisku_nie_ma_a_wywolanie_wprost_nie_uruchamia_modelu(self):
        szef = klient(self.z.szef)

        self.assertNotContains(szef.get(self.karta), PRZYCISK)
        odpowiedz = szef.post(self.adres)

        self.assertContains(odpowiedz, "Nie włączyła jej decyzja urzędu")
        self.assertNotContains(odpowiedz, NAGLOWEK_AI)
        self.assertEqual(self.model.wiadomosci, [])
        self.assertEqual(self.wpisy().count(), 0)


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_TRYB_DEMO=True, ASYSTENT_DECYZJE_AI=DECYZJE_Z_RADAREM)
class PytaniaDoKartPoDecyzjiUrzeduTest(Podstawa):
    def setUp(self):
        super().setUp()
        self.wybrane = self.karty()[:2]
        self.model.pytania = [
            {"kod": self.wybrane[0].kod, "pytanie": "Jak chce Pani/Pan zaplanować najbliższe tygodnie pracy?"},
            {"kod": self.wybrane[1].kod, "pytanie": "Czego potrzebuje Pani/Pan, żeby utrzymać ten sposób pracy?"},
        ]

    def test_przycisk_widzi_tylko_oceniajacy_razem_z_ostrzezeniem(self):
        szef = klient(self.z.szef).get(self.karta)

        self.assertContains(szef, PRZYCISK, count=1)
        self.assertContains(szef, "pytania do kart obserwacji")
        self.assertContains(szef, ORGAN)
        self.assertEqual(bledy_dostepnosci(szef.content.decode()), [])
        self.assertNotContains(klient(self.z.ola).get(self.karta), PRZYCISK)

    def test_model_dostaje_same_karty_a_strona_pokazuje_pytania_z_ostrzezeniem(self):
        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, NAGLOWEK_AI, count=1)
        self.assertContains(odpowiedz, 'id="radar-ai"', count=1)
        for pozycja, karta in zip(self.model.pytania, self.wybrane):
            self.assertContains(odpowiedz, pozycja["pytanie"], count=1)
            self.assertContains(odpowiedz, f"Do karty: {karta.tytul}")
        self.assertContains(odpowiedz, WYSOKIE_RYZYKO)
        self.assertIn(self.wybrane[0].fakt, self.model.wyslane)
        for dane_osobowe in ("Ola", "Testowy", "stanowisko-anna"):
            self.assertNotIn(dane_osobowe, self.model.wyslane)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_uzycie_zostaje_w_historii_a_pytania_nie_sa_zapisywane(self):
        szef = klient(self.z.szef)

        szef.post(self.adres, {"ocena_0": "7", "wnioski_iprz": "Własny wniosek."})

        self.ocena.refresh_from_db()
        self.assertEqual(self.wpisy().count(), 1)
        self.assertEqual(self.ocena.szkic["wnioski_iprz"], "Własny wniosek.")
        pytanie = self.model.pytania[0]["pytanie"]
        self.assertNotIn(pytanie, json.dumps(self.ocena.stan, ensure_ascii=False) + json.dumps(self.ocena.szkic, ensure_ascii=False))
        self.assertNotIn(pytanie, self.wpisy().get().opis)
        self.assertNotContains(szef.get(self.karta), pytanie)

    def test_slad_uzycia_jest_informacja_o_funkcji_wysokiego_ryzyka_dla_ocenianego(self):
        """Art. 26 ust. 11 AI Act: po sporządzeniu oceny oceniany widzi, z jakich funkcji modelu korzystano."""
        self.assertIn(uslugi.CZYNNOSC_RADAR_AI, uslugi.CZYNNOSCI_AI)
        self.assertEqual(uslugi.CZYNNOSCI_AI_WYSOKIEGO_RYZYKA[uslugi.CZYNNOSC_RADAR_AI], "RADAR_PYTANIA_DO_KART")
        klient(self.z.szef).post(self.adres)

        self.assertNotContains(klient(self.z.ola).get(self.karta), uslugi.CZYNNOSC_RADAR_AI)

    def test_pytanie_o_zdrowie_nie_trafia_do_przelozonego(self):
        self.model.pytania[1]["pytanie"] = "Czy czuje się Pani/Pan wypalona zawodowo?"

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertNotContains(odpowiedz, "wypalona zawodowo")
        self.assertContains(odpowiedz, "Kontrola podpowiedzi:")
        self.assertContains(odpowiedz, self.model.pytania[0]["pytanie"], count=1)

    def test_oceniany_nie_moze_uruchomic_modelu(self):
        odpowiedz = klient(self.z.ola).post(self.adres)

        self.assertNotContains(odpowiedz, NAGLOWEK_AI, status_code=odpowiedz.status_code)
        self.assertEqual(self.model.wiadomosci, [])
        self.assertEqual(self.wpisy().count(), 0)

    def test_bez_kart_model_nie_jest_pytany(self):
        UstaleniaMonitoringu.objects.update(integracja_wlaczona=False)

        klient(self.z.szef).post(self.adres)

        self.assertEqual(self.model.wiadomosci, [])
        self.assertEqual(self.wpisy().count(), 0)

    def test_niedostepny_model_daje_komunikat_bez_sladu_w_historii(self):
        self.model.blad = BladModelu("brak połączenia")

        odpowiedz = klient(self.z.szef).post(self.adres)

        self.assertContains(odpowiedz, "Lokalny model językowy jest teraz niedostępny")
        self.assertNotContains(odpowiedz, NAGLOWEK_AI)
        self.assertEqual(self.wpisy().count(), 0)
