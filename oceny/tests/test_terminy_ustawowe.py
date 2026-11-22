"""Termin oceny okresowej wynika z ustawy, a nie z wyboru oceniającego.

Wymagania (prowadzący projekt, 22.11.2026) i źródła:
- art. 81 ust. 4 u.s.c.: ocenę sporządza się co 24 miesiące; § 5 ust. 3 rozp.: oceniający wpisuje termin do części I
  arkusza. System wylicza ten termin sam (art. 112 i 115 KC) - oceniający go nie wybiera;
- art. 81 ust. 7 u.s.c.: usprawiedliwiona nieobecność dłuższa niż miesiąc przedłuża termin o czas nieobecności -
  z mocy ustawy, bez czynności oceniającego;
- art. 81 ust. 8 u.s.c. i § 8 rozp.: oceniający może zmienić termin tylko w czterech przypadkach i dopiero po
  upływie ponad 6 miesięcy; o nowym terminie zawiadamia ocenianego na piśmie;
- art. 81 ust. 9 u.s.c.: termin ponownej oceny po ocenie negatywnej nie jest przedłużany (Poradnik KPRM, s. 14).
"""

from datetime import date

from django.test import TestCase, override_settings

from asystent_ocen import terminy
from asystent_ocen.bledy import BladWalidacji
from asystent_ocen.nieobecnosci import Nieobecnosc
from asystent_ocen.przebieg import Rola
from oceny import uslugi
from oceny.models import Ocena, Zdarzenie
from oceny.zadania import zadania_uzytkownika

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import DZIEN_KRYTERIOW, DZIEN_OCENY, POCZATEK, TERMIN, Zespol
from .test_widoki import czynnosc, klient

USTAWOWY = date(2026, 11, 23)        # 21.11.2024 + 24 mies. = 21.11.2026 (sobota), więc poniedziałek 23.11.2026
PO_6_MIESIACACH = date(2025, 6, 11)  # od początku cyklu upłynęło ponad 6 miesięcy
DLUGA = (date(2025, 3, 3), date(2025, 4, 15))   # 44 dni - dłużej niż miesiąc


class TerminZUstawyTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.nowa_ocena()
        self.karta = f"/oceny/{self.ocena.pk}/"

    def test_stala_testowa_to_termin_ustawowy(self):
        self.assertEqual((TERMIN, terminy.termin_oceny(POCZATEK)), (USTAWOWY, USTAWOWY))

    def test_system_sam_wpisuje_termin_24_miesiace_od_poczatku_cyklu(self):
        uslugi.wyznacz_kryteria(self.ocena, self.z.szef.uzytkownik, kryteria_dodatkowe=self.z.dodatkowe(), data=DZIEN_KRYTERIOW)

        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).termin, USTAWOWY)

    def test_termin_inny_niz_ustawowy_jest_odrzucany(self):
        for inny in (date(2026, 11, 20), date(2026, 11, 24), date(2025, 11, 21)):
            with self.assertRaises(BladWalidacji) as blad:
                uslugi.wyznacz_kryteria(
                    self.ocena, self.z.szef.uzytkownik, kryteria_dodatkowe=[], termin=inny, data=DZIEN_KRYTERIOW
                )
            self.assertIn("TERMIN_INNY_NIZ_USTAWOWY", blad.exception.kody, inny)
        self.assertIsNone(Ocena.objects.get(pk=self.ocena.pk).termin)

    def test_formularz_kryteriow_podaje_termin_ale_nie_pozwala_go_wpisac(self):
        odpowiedz = klient(self.z.szef).get(self.karta)

        self.assertNotContains(odpowiedz, 'name="termin"')
        self.assertContains(odpowiedz, "Termin sporządzenia oceny: <strong>23.11.2026</strong>", html=True)
        self.assertContains(odpowiedz, "art. 81 ust. 4 u.s.c.")
        self.assertNotContains(odpowiedz, "Możesz wyznaczyć termin wcześniejszy")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_formularz_kryteriow_zapisuje_termin_ustawowy_takze_gdy_ktos_dosle_inna_date(self):
        odpowiedz = klient(self.z.szef).post(czynnosc(self.ocena, "wyznacz-kryteria"), {"termin": "2027-06-30"}, follow=True)

        self.assertContains(odpowiedz, "Kryteria i termin oceny zostały przekazane ocenianemu do potwierdzenia.")
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).termin, USTAWOWY)

    def test_termin_uwzglednia_dluga_nieobecnosc_sprzed_wyznaczenia_kryteriow(self):
        """Poradnik KPRM s. 12: liczy się także nieobecność sprzed rozpoczęcia procesu oceniania."""
        od, do = date(2024, 11, 25), date(2025, 1, 7)
        uslugi.dodaj_nieobecnosc(self.z.ola, self.z.kadry.uzytkownik, od=od, do=do)

        uslugi.wyznacz_kryteria(self.ocena, self.z.szef.uzytkownik, kryteria_dodatkowe=[], data=date(2025, 1, 10))

        oczekiwany = terminy.termin_oceny(POCZATEK, [Nieobecnosc(od, do)])
        self.assertGreater(oczekiwany, USTAWOWY)
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).termin, oczekiwany)

    def test_ponowna_ocena_po_negatywnej_ma_termin_z_ust_9(self):
        z = Zespol.__new__(Zespol)
        z.kadry, z.szef, z.ola = self.z.kadry, self.z.szef, self.z.obcy
        z.ola.przelozony = z.szef
        z.ola.save()
        negatywna = z.ocena_zakonczona(punkty=1)
        ponowna = Ocena.objects.filter(poprzednia=negatywna).first() or uslugi.rozpocznij_kolejny_cykl(
            negatywna, z.kadry.uzytkownik, data=DZIEN_OCENY
        )

        uslugi.wyznacz_kryteria(ponowna, z.szef.uzytkownik, kryteria_dodatkowe=[], data=date(2026, 11, 6))

        self.assertEqual(Ocena.objects.get(pk=ponowna.pk).termin, terminy.data_ponownej_oceny_po_negatywnej(DZIEN_OCENY))


class PrzedluzenieTerminuTest(TestCase):
    """Art. 81 ust. 7 u.s.c.: termin przedłuża się z mocy ustawy - zadania i kalendarze mają to pokazać same."""

    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()
        self.karta = f"/oceny/{self.ocena.pk}/"

    def termin(self):
        return Ocena.objects.get(pk=self.ocena.pk).termin

    def wpisy(self):
        return Zdarzenie.objects.filter(ocena=self.ocena, czynnosc="przedłużenie terminu oceny")

    def test_nieobecnosc_dluzsza_niz_miesiac_przedluza_termin_bez_udzialu_oceniajacego(self):
        uslugi.dodaj_nieobecnosc(self.z.ola, self.z.kadry.uzytkownik, od=DLUGA[0], do=DLUGA[1])

        oczekiwany = terminy.termin_oceny(POCZATEK, [Nieobecnosc(*DLUGA)])
        self.assertEqual(self.termin(), oczekiwany)
        self.assertGreater(oczekiwany, USTAWOWY)
        wpis = self.wpisy().get()
        for fragment in ("23.11.2026", f"{oczekiwany:%d.%m.%Y}", "art. 81 ust. 7 u.s.c."):
            self.assertIn(fragment, wpis.opis)
        (zadanie,) = [z for z in zadania_uzytkownika(self.z.szef.uzytkownik, PO_6_MIESIACACH) if z.kod == "SPORZADZ_OCENE"]
        self.assertEqual(zadanie.termin, oczekiwany)

    def test_obie_strony_widza_na_karcie_nowy_termin_i_powod(self):
        uslugi.dodaj_nieobecnosc(self.z.ola, self.z.kadry.uzytkownik, od=DLUGA[0], do=DLUGA[1])
        oczekiwany = terminy.termin_oceny(POCZATEK, [Nieobecnosc(*DLUGA)])

        for osoba in (self.z.szef, self.z.ola):
            odpowiedz = klient(osoba).get(self.karta)
            self.assertContains(odpowiedz, f"{oczekiwany:%d.%m.%Y}", msg_prefix=osoba.imie)
            self.assertContains(odpowiedz, "przedłużenie terminu oceny", msg_prefix=osoba.imie)
            self.assertNotContains(odpowiedz, "oceniający może zmienić termin", msg_prefix=osoba.imie)

    def test_po_aktualizacji_aplikacji_uzgodnienie_przedluza_terminy_z_dawnych_nieobecnosci(self):
        """Nieobecność wpisana przed tą zmianą nie przedłużyła terminu - robi to polecenie uruchamiane po aktualizacji."""
        from io import StringIO

        from django.core.management import call_command

        from oceny.models import Nieobecnosc as WpisNieobecnosci

        WpisNieobecnosci.objects.create(pracownik=self.z.ola, od=DLUGA[0], do=DLUGA[1])
        self.assertEqual(self.termin(), USTAWOWY)

        wyjscie = StringIO()
        call_command("uzgodnij_cykle", stdout=wyjscie)

        self.assertEqual(self.termin(), terminy.termin_oceny(POCZATEK, [Nieobecnosc(*DLUGA)]))
        self.assertIn("Terminy przedłużone o nieobecności: 1", wyjscie.getvalue())
        wpis = self.wpisy().get()
        self.assertEqual((wpis.uzytkownik, wpis.podpis), (None, "System"))

        call_command("uzgodnij_cykle", stdout=StringIO())
        self.assertEqual(self.wpisy().count(), 1)

    def test_nieobecnosc_do_miesiaca_nie_zmienia_terminu(self):
        uslugi.dodaj_nieobecnosc(self.z.ola, self.z.kadry.uzytkownik, od=date(2025, 3, 3), do=date(2025, 4, 3))

        self.assertEqual(self.termin(), USTAWOWY)
        self.assertFalse(self.wpisy().exists())

    def test_terminu_zmienionego_przez_oceniajacego_system_nie_nadpisuje(self):
        uslugi.zmien_termin(
            self.ocena, self.z.szef.uzytkownik, nowy_termin=date(2026, 12, 10), przyczyna="NIEOBECNOSC_OCENIAJACEGO",
            data=PO_6_MIESIACACH,
        )

        uslugi.dodaj_nieobecnosc(self.z.ola, self.z.kadry.uzytkownik, od=date(2025, 7, 1), do=date(2025, 8, 20))

        self.assertEqual(self.termin(), date(2026, 12, 10))
        self.assertFalse(self.wpisy().exists())

    def test_termin_ponownej_oceny_po_negatywnej_nie_jest_przedluzany(self):
        z = Zespol.__new__(Zespol)
        z.kadry, z.szef, z.ola = self.z.kadry, self.z.szef, self.z.obcy
        z.ola.przelozony = z.szef
        z.ola.save()
        negatywna = z.ocena_zakonczona(punkty=1)
        ponowna = Ocena.objects.filter(poprzednia=negatywna).first() or uslugi.rozpocznij_kolejny_cykl(
            negatywna, z.kadry.uzytkownik, data=DZIEN_OCENY
        )
        uslugi.wyznacz_kryteria(ponowna, z.szef.uzytkownik, kryteria_dodatkowe=[], data=date(2026, 11, 6))
        uslugi.potwierdz_kryteria(ponowna, z.ola.uzytkownik, data=date(2026, 11, 6))
        przed = Ocena.objects.get(pk=ponowna.pk).termin

        uslugi.dodaj_nieobecnosc(z.ola, z.kadry.uzytkownik, od=date(2026, 12, 1), do=date(2027, 1, 20))

        self.assertEqual(Ocena.objects.get(pk=ponowna.pk).termin, przed)


@override_settings(ASYSTENT_DZIS=PO_6_MIESIACACH.isoformat())
class ZmianaTerminuPrzezOceniajacegoTest(TestCase):
    """Art. 81 ust. 8 u.s.c.: zamknięta lista przypadków; § 8 rozp.: pisemne zawiadomienie ocenianego."""

    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()
        self.karta = f"/oceny/{self.ocena.pk}/"
        self.adres = czynnosc(self.ocena, "zmien-termin")

    def termin(self):
        return Ocena.objects.get(pk=self.ocena.pk).termin

    def test_formularz_ma_przypadki_z_ustawy_a_zmiana_oceniajacego_dopiero_gdy_ja_odnotowano(self):
        przed = klient(self.z.szef).get(self.karta)
        uslugi.zmien_oceniajacego(self.ocena, self.z.kadry.uzytkownik, nowy_oceniajacy=self.z.obcy, data=PO_6_MIESIACACH)
        po = klient(self.z.obcy).get(self.karta)

        for odpowiedz in (przed, po):
            self.assertContains(odpowiedz, '<select name="przyczyna" id="przyczyna" required>')
            self.assertContains(odpowiedz, 'value="NIEOBECNOSC_OCENIANEGO"')
            self.assertContains(odpowiedz, 'value="NIEOBECNOSC_OCENIAJACEGO"')
            self.assertNotContains(odpowiedz, 'value="WNIOSEK_OCENIANEGO"')   # ten przypadek ma własną ścieżkę - wniosek
            self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])
        self.assertNotContains(przed, 'value="ZMIANA_OCENIAJACEGO"')
        self.assertContains(po, 'value="ZMIANA_OCENIAJACEGO"')

    def test_zmiana_z_przypadkiem_z_ustawy_zapisuje_zawiadomienie_z_podstawa(self):
        odpowiedz = klient(self.z.szef).post(self.adres, {
            "nowy_termin": "2026-12-10", "przyczyna": "NIEOBECNOSC_OCENIANEGO", "opis": "Urlop rodzicielski od maja.",
        }, follow=True)

        self.assertContains(odpowiedz, "Termin oceny został zmieniony.")
        self.assertEqual(self.termin(), date(2026, 12, 10))
        dokument = Ocena.objects.get(pk=self.ocena.pk).proces().dokumenty[-1]
        self.assertEqual((dokument.rodzaj, dokument.adresat), ("zawiadomienie o nowym terminie oceny", Rola.OCENIANY))
        self.assertIn("art. 81 ust. 8 pkt 2 u.s.c.", dokument.opis)
        self.assertIn("Urlop rodzicielski od maja.", dokument.opis)

    def test_bledne_dane_wracaja_z_komunikatem_i_nie_zmieniaja_terminu(self):
        przypadki = (
            ({"nowy_termin": "2026-12-10", "przyczyna": ""}, "Wybierz przypadek z ustawy"),
            ({"nowy_termin": "2026-12-10", "przyczyna": "reorganizacja"}, "Wybierz przypadek z ustawy"),
            ({"nowy_termin": "2026-12-10", "przyczyna": "ZMIANA_OCENIAJACEGO"}, "nie odnotowano zmiany na stanowisku oceniającego"),
            ({"nowy_termin": "2026-12-10", "przyczyna": "WNIOSEK_OCENIANEGO"}, "Oceniany nie złożył wniosku"),
            ({"nowy_termin": "2025-06-10", "przyczyna": "NIEOBECNOSC_OCENIANEGO"}, "nie może być wcześniejszy niż dzień zmiany"),
            ({"nowy_termin": "2026-11-23", "przyczyna": "NIEOBECNOSC_OCENIANEGO"}, "taki sam jak dotychczasowy"),
            ({"nowy_termin": "", "przyczyna": "NIEOBECNOSC_OCENIANEGO"}, "Podaj datę"),
        )
        for dane, komunikat in przypadki:
            odpowiedz = klient(self.z.szef).post(self.adres, dane, follow=True)

            self.assertEqual(odpowiedz.status_code, 200, dane)
            self.assertContains(odpowiedz, komunikat, msg_prefix=str(dane))
            self.assertEqual(self.termin(), USTAWOWY, dane)

    def test_przed_uplywem_6_miesiecy_zmiana_jest_odrzucana_z_podstawa(self):
        with override_settings(ASYSTENT_DZIS="2025-05-21"):
            odpowiedz = klient(self.z.szef).post(
                self.adres, {"nowy_termin": "2026-12-10", "przyczyna": "NIEOBECNOSC_OCENIANEGO"}, follow=True
            )

        self.assertContains(odpowiedz, "art. 81 ust. 8 in fine u.s.c.")
        self.assertEqual(self.termin(), USTAWOWY)

    def test_uwzgledniony_wniosek_ocenianego_daje_zawiadomienie_z_punktem_4(self):
        uslugi.zloz_wniosek_o_zmiane_terminu(self.ocena, self.z.ola.uzytkownik, uzasadnienie="Planowany urlop.", data=PO_6_MIESIACACH)

        klient(self.z.szef).post(czynnosc(self.ocena, "rozpatrz-wniosek"), {"decyzja": "uwzglednij", "nowy_termin": "2026-12-01"})

        self.assertEqual(self.termin(), date(2026, 12, 1))
        self.assertIn("art. 81 ust. 8 pkt 4 u.s.c.", Ocena.objects.get(pk=self.ocena.pk).proces().dokumenty[-1].opis)


@override_settings(ASYSTENT_DZIS=PO_6_MIESIACACH.isoformat())
class ZmianaStanowiskaTest(TestCase):
    """Art. 81 ust. 6 u.s.c., § 9 ust. 1-2 rozp.: zmiana stanowiska z istotną zmianą zakresu obowiązków."""

    NOWE = {"stanowisko": "główny specjalista", "opis_stanowiska": "Koordynacja kontroli zarządczej."}

    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()
        self.karta = f"/oceny/{self.ocena.pk}/"
        self.adres = f"/kadry/pracownik/{self.z.ola.pk}/stanowisko/"

    def zapisana(self):
        return Ocena.objects.get(pk=self.ocena.pk)

    def zadanie(self, kod):
        (zadanie,) = [z for z in zadania_uzytkownika(self.z.szef.uzytkownik, PO_6_MIESIACACH) if z.kod == kod]
        return zadanie

    def test_po_ponad_6_miesiacach_ocene_sporzadza_sie_wokol_dnia_zmiany_na_dotychczasowym_stanowisku(self):
        from oceny import drukowanie

        odpowiedz = klient(self.z.kadry).post(self.adres, {**self.NOWE, "data_zmiany": "2025-06-11"}, follow=True)

        self.assertContains(odpowiedz, "od 04.06.2025 do 11.07.2025")
        self.assertContains(odpowiedz, "art. 81 ust. 6 u.s.c.")
        ocena = self.zapisana()
        self.assertEqual((ocena.etap, ocena.termin), ("OCENIANIE", date(2025, 7, 11)))
        self.z.ola.refresh_from_db()
        self.assertEqual((self.z.ola.stanowisko, self.z.ola.opis_stanowiska), tuple(self.NOWE.values()))
        self.assertEqual(drukowanie.dane_arkusza(ocena).oceniany.stanowisko, "specjalista")
        zadanie = self.zadanie("SPORZADZ_OCENE")
        self.assertEqual(zadanie.termin, date(2025, 7, 11))
        self.assertIn("art. 81 ust. 6 u.s.c.", zadanie.podstawa)
        self.assertTrue(Zdarzenie.objects.filter(ocena=ocena, czynnosc="zmiana stanowiska pracy").exists())
        for osoba in (self.z.szef, self.z.ola):
            karta = klient(osoba).get(self.karta)
            self.assertContains(karta, "Ocena w związku ze zmianą stanowiska", msg_prefix=osoba.imie)
            self.assertContains(karta, "04.06.2025", msg_prefix=osoba.imie)
            self.assertNotContains(karta, "Sporządzenie oceny - termin ustawowy", msg_prefix=osoba.imie)
            self.assertEqual(bledy_dostepnosci(karta.content.decode()), [], osoba.imie)

    def test_ocena_sporzadzona_wczesniej_niz_7_dni_przed_zmiana_wraca_z_komunikatem(self):
        from asystent_ocen.kryteria import kryteria_obowiazkowe

        klient(self.z.kadry).post(self.adres, {**self.NOWE, "data_zmiany": "2025-06-25"})    # najwcześniej 18.06.2025
        nazwy = kryteria_obowiazkowe("C") + self.z.dodatkowe()
        dane = {f"ocena_{numer}": "7" for numer in range(len(nazwy))}
        dane.update({"data_rozmowy": "2025-06-10", "wnioski_iprz": "Szkolenie z postępowania administracyjnego."})

        odpowiedz = klient(self.z.szef).post(czynnosc(self.ocena, "sporzadz-ocene"), dane, follow=True)   # dziś 11.06.2025

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertContains(odpowiedz, "nie wcześniej niż 7 dni przed zmianą, czyli od 18.06.2025")
        self.assertEqual(self.zapisana().etap, "OCENIANIE")
        with override_settings(ASYSTENT_DZIS="2025-06-18"):
            dane["data_rozmowy"] = "2025-06-17"
            klient(self.z.szef).post(czynnosc(self.ocena, "sporzadz-ocene"), dane)
        self.assertEqual(self.zapisana().etap, "OCENA_DO_ZAPOZNANIA")

    def test_przy_pierwszej_ocenie_komunikat_mowi_o_okresie_podlegajacym_ocenie(self):
        odpowiedz = klient(self.z.kadry).post(self.adres, {**self.NOWE, "data_zmiany": "2025-03-03"}, follow=True)

        self.assertContains(odpowiedz, "okres podlegający ocenie nie jest dłuższy niż 6 miesięcy")
        self.assertNotContains(odpowiedz, "Od poprzedniej oceny")
        karta = klient(self.z.szef).get(self.karta)
        self.assertContains(karta, "okres podlegający ocenie nie jest dłuższy niż 6 miesięcy")
        self.assertNotContains(karta, "Od poprzedniej oceny")

    def test_terminu_oceny_po_zmianie_stanowiska_nie_zmienia_oceniajacy_ani_nieobecnosc(self):
        """Art. 81 ust. 7 i 8 u.s.c. dotyczą terminu z ust. 4, a nie oceny sporządzanej w związku ze zmianą stanowiska."""
        klient(self.z.kadry).post(self.adres, {**self.NOWE, "data_zmiany": "2025-06-11"})

        self.assertNotContains(klient(self.z.szef).get(self.karta), 'name="nowy_termin"')
        odpowiedz = klient(self.z.szef).post(
            czynnosc(self.ocena, "zmien-termin"), {"nowy_termin": "2025-08-29", "przyczyna": "NIEOBECNOSC_OCENIANEGO"}, follow=True
        )
        self.assertContains(odpowiedz, "w związku ze zmianą stanowiska")
        uslugi.dodaj_nieobecnosc(self.z.ola, self.z.kadry.uzytkownik, od=DLUGA[0], do=DLUGA[1])
        self.assertEqual(self.zapisana().termin, date(2025, 7, 11))

    def test_przed_uplywem_6_miesiecy_wraca_rozmowa_o_kryteriach_a_termin_oceny_zostaje(self):
        odpowiedz = klient(self.z.kadry).post(self.adres, {**self.NOWE, "data_zmiany": "2025-03-03"}, follow=True)

        self.assertContains(odpowiedz, "do 02.04.2025")
        self.assertContains(odpowiedz, "§ 9 ust. 1 rozp.")
        ocena = self.zapisana()
        self.assertEqual((ocena.etap, ocena.termin), ("KRYTERIA_DO_WYZNACZENIA", USTAWOWY))
        zadanie = self.zadanie("WYZNACZ_KRYTERIA")
        self.assertEqual((zadanie.termin, zadanie.podstawa), (date(2025, 4, 2), "§ 9 ust. 1 rozp."))
        karta = klient(self.z.szef).get(self.karta)
        self.assertContains(karta, "Termin sporządzenia oceny: <strong>23.11.2026</strong>", html=True)
        self.assertContains(karta, "02.04.2025")
        self.assertEqual(bledy_dostepnosci(karta.content.decode()), [])

        klient(self.z.szef).post(czynnosc(self.ocena, "wyznacz-kryteria"), {})
        self.assertEqual((self.zapisana().etap, self.zapisana().termin), ("KRYTERIA_DO_POTWIERDZENIA", USTAWOWY))

    def test_bledne_dane_i_brak_uprawnien(self):
        przypadki = (
            ({**self.NOWE, "data_zmiany": ""}, "Podaj datę: dzień zmiany stanowiska."),
            ({**self.NOWE, "stanowisko": " ", "data_zmiany": "2025-06-11"}, "Podaj nazwę nowego stanowiska"),
            ({**self.NOWE, "opis_stanowiska": "", "data_zmiany": "2025-06-11"}, "Podaj opis nowego stanowiska"),
            ({**self.NOWE, "data_zmiany": "2024-11-01"}, "nie może być wcześniejsza niż początek zatrudnienia"),
        )
        for dane, komunikat in przypadki:
            odpowiedz = klient(self.z.kadry).post(self.adres, dane, follow=True)
            self.assertEqual(odpowiedz.status_code, 200, dane)
            self.assertContains(odpowiedz, komunikat, msg_prefix=str(dane))
            self.assertEqual(self.zapisana().termin, USTAWOWY, dane)
        self.z.ola.refresh_from_db()
        self.assertEqual(self.z.ola.stanowisko, "specjalista")
        for osoba in (self.z.szef, self.z.ola):
            self.assertEqual(klient(osoba).post(self.adres, {**self.NOWE, "data_zmiany": "2025-06-11"}).status_code, 403)
        self.assertEqual(klient(self.z.kadry).get(self.adres).status_code, 405)

    def test_pracownik_bez_trwajacej_oceny_dostaje_tylko_nowe_stanowisko(self):
        adres = f"/kadry/pracownik/{self.z.obcy.pk}/stanowisko/"

        odpowiedz = klient(self.z.kadry).post(adres, {**self.NOWE, "data_zmiany": "2025-06-11"}, follow=True)

        self.assertContains(odpowiedz, "nie ma trwającej oceny okresowej")
        self.z.obcy.refresh_from_db()
        self.assertEqual(self.z.obcy.stanowisko, "główny specjalista")

    def test_karta_pracownika_w_kadrach_ma_formularz_zmiany_stanowiska(self):
        odpowiedz = klient(self.z.kadry).get(f"/kadry/pracownik/{self.z.ola.pk}/")

        self.assertContains(odpowiedz, "Zmiana stanowiska z istotną zmianą zakresu obowiązków")
        self.assertContains(odpowiedz, f'action="{self.adres}"')
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])
        self.assertNotContains(klient(self.z.kadry).get("/kadry/pracownik/nowy/"), "Zmiana stanowiska z istotną")
