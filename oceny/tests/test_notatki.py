"""Notatki oceniającego na karcie oceny: obserwacje, dodatkowe osiągnięcia pracownika i - przy pierwszej ocenie -
wynik egzaminu ze służby przygotowawczej.

Wymagania: decyzja zespołu z 21.11.2026 (pola na notatki i dodatkowe osiągnięcia; przy pierwszej ocenie wynik
egzaminu z liczbą punktów i informacją o egzaminie poprawkowym); wcześniejsza decyzja zespołu - notatek
oceniającego nie widzi nikt poza nim. Podstawa egzaminu: art. 36 ust. 5 u.s.c.
"""

from datetime import date

from django.test import TestCase, override_settings

from oceny import uslugi
from oceny.models import Zdarzenie

from .pomocnicze import Zespol
from .test_widoki import czynnosc, klient

OSIAGNIECIE = "Opracowała wzór decyzji przyjęty w całym urzędzie."
WYNIK = "Egzamin ze służby przygotowawczej: zdany 14.03.2025, 42 z 50 pkt, w pierwszym terminie."
DANE_EGZAMINU = {"punkty": "42", "punkty_max": "50", "data_egzaminu": "2025-03-14"}


@override_settings(ASYSTENT_DZIS="2026-06-01")
class Podstawa(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()
        self.szef = klient(self.z.szef)
        self.karta = f"/oceny/{self.ocena.pk}/"

    def notatki(self) -> list[tuple[str, str]]:
        self.ocena.refresh_from_db()
        return [(notatka.rodzaj, notatka.tresc) for notatka in self.ocena.proces().notatki]


class OsiagnieciaTest(Podstawa):
    def test_oceniajacy_zapisuje_dodatkowe_osiagniecie(self):
        odpowiedz = self.szef.post(
            czynnosc(self.ocena, "notatka"), {"tresc": OSIAGNIECIE, "rodzaj": "osiagniecie"}, follow=True
        )

        self.assertEqual(self.notatki(), [("osiagniecie", OSIAGNIECIE)])
        self.assertContains(odpowiedz, "Dodatkowe osiągnięcie zostało zapisane")

    def test_wpis_bez_rodzaju_jest_obserwacja(self):
        self.szef.post(czynnosc(self.ocena, "notatka"), {"tresc": "Sprawy zamknięte przed terminem."})

        self.assertEqual(self.notatki(), [("obserwacja", "Sprawy zamknięte przed terminem.")])

    def test_karta_pokazuje_osiagniecia_osobno_od_obserwacji(self):
        uslugi.dodaj_notatke(self.ocena, self.z.szef.uzytkownik, tresc="Obserwacja z czerwca.", data=date(2025, 6, 10))
        uslugi.dodaj_notatke(
            self.ocena, self.z.szef.uzytkownik, tresc=OSIAGNIECIE, rodzaj="osiagniecie", data=date(2025, 9, 1)
        )

        strona = self.szef.get(self.karta).content.decode()

        self.assertIn("Dodatkowe osiągnięcia (1)", strona)
        self.assertIn("Obserwacje (1)", strona)
        self.assertLess(strona.index("Dodatkowe osiągnięcia (1)"), strona.index(OSIAGNIECIE))
        self.assertLess(strona.index(OSIAGNIECIE), strona.index("Obserwacje (1)"))
        self.assertLess(strona.index("Obserwacje (1)"), strona.index("Obserwacja z czerwca."))

    def test_nieznany_rodzaj_wpisu_jest_odrzucany(self):
        odpowiedz = self.szef.post(
            czynnosc(self.ocena, "notatka"), {"tresc": "Treść.", "rodzaj": "nagana"}, follow=True
        )

        self.assertEqual(self.notatki(), [])
        self.assertContains(odpowiedz, "Notatka może być obserwacją albo dodatkowym osiągnięciem")

    def test_osiagniec_zapisanych_przez_przelozonego_nie_widzi_oceniany_ani_kadry(self):
        uslugi.dodaj_notatke(
            self.ocena, self.z.szef.uzytkownik, tresc=OSIAGNIECIE, rodzaj="osiagniecie", data=date(2025, 9, 1)
        )

        for osoba in (self.z.ola, self.z.kadry):
            with self.subTest(osoba=osoba.uzytkownik.username):
                odpowiedz = klient(osoba).get(self.karta)
                self.assertNotContains(odpowiedz, OSIAGNIECIE)
                self.assertNotContains(odpowiedz, "osiągnięci")


class EgzaminTest(Podstawa):
    def test_przy_pierwszej_ocenie_oceniajacy_ma_pole_na_wynik_egzaminu(self):
        self.assertContains(self.szef.get(self.karta), "Egzamin ze służby przygotowawczej")

    def test_oceniajacy_zapisuje_wynik_egzaminu_z_punktami(self):
        odpowiedz = self.szef.post(czynnosc(self.ocena, "egzamin"), DANE_EGZAMINU, follow=True)

        self.assertEqual(self.notatki(), [("egzamin", WYNIK)])
        self.assertContains(odpowiedz, WYNIK)

    def test_egzamin_poprawkowy_i_uwagi_trafiaja_do_wpisu(self):
        self.szef.post(
            czynnosc(self.ocena, "egzamin"),
            {**DANE_EGZAMINU, "punkty": "31", "poprawkowy": "1", "uwagi": "W pierwszym terminie 21 pkt."},
        )

        self.assertEqual(self.notatki(), [(
            "egzamin",
            "Egzamin ze służby przygotowawczej: zdany 14.03.2025, 31 z 50 pkt, po egzaminie poprawkowym. "
            "W pierwszym terminie 21 pkt.",
        )])

    def test_ponowny_zapis_zastepuje_wynik(self):
        self.szef.post(czynnosc(self.ocena, "egzamin"), DANE_EGZAMINU)
        self.szef.post(czynnosc(self.ocena, "egzamin"), {**DANE_EGZAMINU, "punkty": "45"})

        self.assertEqual([rodzaj for rodzaj, _ in self.notatki()], ["egzamin"])
        self.assertIn("45 z 50 pkt", self.notatki()[0][1])

    def test_bledne_punkty_daja_komunikat_i_niczego_nie_zapisuja(self):
        odpowiedz = self.szef.post(czynnosc(self.ocena, "egzamin"), {**DANE_EGZAMINU, "punkty": "60"}, follow=True)

        self.assertEqual(self.notatki(), [])
        self.assertContains(odpowiedz, "nie może być większa niż liczba punktów możliwych")

    def test_wyniku_egzaminu_nie_widzi_oceniany_ani_kadry(self):
        self.szef.post(czynnosc(self.ocena, "egzamin"), DANE_EGZAMINU)

        for osoba in (self.z.ola, self.z.kadry):
            with self.subTest(osoba=osoba.uzytkownik.username):
                odpowiedz = klient(osoba).get(self.karta)
                self.assertNotContains(odpowiedz, "42 z 50 pkt")
                self.assertNotContains(odpowiedz, "Egzamin ze służby przygotowawczej")

    def test_wynik_egzaminu_nie_trafia_do_dziennika(self):
        self.szef.post(czynnosc(self.ocena, "egzamin"), DANE_EGZAMINU)

        wpis = Zdarzenie.objects.filter(ocena=self.ocena).order_by("pk").last()
        self.assertEqual((wpis.czynnosc, wpis.opis), (uslugi.CZYNNOSC_NOTATKA, ""))

    def test_wyniku_egzaminu_nie_zapisze_oceniany(self):
        odpowiedz = klient(self.z.ola).post(czynnosc(self.ocena, "egzamin"), DANE_EGZAMINU)

        self.assertEqual(odpowiedz.status_code, 403)
        self.assertEqual(self.notatki(), [])


@override_settings(ASYSTENT_DZIS="2026-12-01")
class EgzaminPrzyKolejnejOcenieTest(TestCase):
    """Egzamin kończy służbę przygotowawczą na początku pracy w służbie cywilnej - przy kolejnych ocenach
    pola już nie ma."""

    def setUp(self):
        self.z = Zespol()
        pierwsza = self.z.ocena_zakonczona()
        self.druga = uslugi.rozpocznij_kolejny_cykl(pierwsza, self.z.kadry.uzytkownik, data=date(2026, 11, 5))
        self.szef = klient(self.z.szef)

    def test_przy_kolejnej_ocenie_pola_nie_ma(self):
        self.assertNotContains(self.szef.get(f"/oceny/{self.druga.pk}/"), "Egzamin ze służby przygotowawczej")

    def test_przy_kolejnej_ocenie_zapis_jest_odrzucany(self):
        odpowiedz = self.szef.post(czynnosc(self.druga, "egzamin"), DANE_EGZAMINU, follow=True)

        self.druga.refresh_from_db()
        self.assertEqual(self.druga.proces().notatki, [])
        self.assertContains(odpowiedz, "przy pierwszej ocenie pracownika")
