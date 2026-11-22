"""Sprzeciw od oceny: rozstrzyga dyrektor generalny urzędu, a stan sprzeciwu widać na liście zadań.

Art. 83 u.s.c.: sprzeciw służy do dyrektora generalnego urzędu (ust. 1) i jest rozpatrywany w terminie 14 dni
od wniesienia (ust. 3). Decyzje prowadzącego projekt z 21.11.2026: rozstrzygnięcie wprowadza w systemie dyrektor
generalny, a nie komórka kadr; strona „Moje zadania” pokazuje stan sprzeciwu.

Decyzje projektowe: dyrektor generalny widzi oceny, od których wniesiono sprzeciw, i tylko te; nie widzi
notatek oceniającego ani danych z EZD RP; sprzeciwu od własnej oceny nie rozstrzyga.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from asystent_ocen import terminy
from asystent_ocen.przebieg import BladUprawnien, Rola
from oceny import uprawnienia, uslugi
from oceny.models import Zdarzenie
from oceny.zadania import sprzeciwy_uzytkownika, zadania_uzytkownika

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import POCZATEK, Zespol, dyrektor_generalny, pracownik
from .test_widoki import czynnosc, klient

WNIESIONY = date(2026, 11, 10)
DZIEN = date(2026, 11, 11)
TRESC = "Ocena nie uwzględnia zadań wykonanych w zastępstwie."
FORMULARZ = "rozpatrz-sprzeciw"


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat())
class Podstawa(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.dyrektor = dyrektor_generalny()
        self.ocena = self.z.ocena_zakonczona(punkty=1)
        self.sprzeciw = uslugi.wnies_sprzeciw(self.ocena, self.z.ola.uzytkownik, tresc=TRESC, data=WNIESIONY)
        self.karta = f"/oceny/{self.ocena.pk}/"
        self.termin = terminy.termin_rozpatrzenia_sprzeciwu(WNIESIONY)


class RozstrzyganieTest(Podstawa):
    def test_dyrektor_generalny_ma_zadanie_z_terminem_14_dni_a_komorka_kadr_nie(self):
        zadania = zadania_uzytkownika(self.dyrektor.uzytkownik, DZIEN)

        self.assertEqual(
            [(zadanie.kod, zadanie.rola, zadanie.termin) for zadanie in zadania],
            [("ROZPATRZ_SPRZECIW", Rola.DYREKTOR_GENERALNY, self.termin)],
        )
        self.assertEqual(zadania_uzytkownika(self.z.kadry.uzytkownik, DZIEN), [])

    def test_dyrektor_widzi_ocene_ze_sprzeciwem_i_formularz_rozstrzygniecia(self):
        odpowiedz = klient(self.dyrektor).get(self.karta)

        self.assertContains(odpowiedz, TRESC)
        self.assertContains(odpowiedz, "Rozstrzygnięcie dyrektora generalnego", count=1)
        self.assertContains(odpowiedz, czynnosc(self.ocena, FORMULARZ))
        self.assertEqual(odpowiedz.context["role_opis"], "dyrektor generalny")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_dyrektor_nie_dostaje_notatek_oceniajacego_ani_danych_z_ezd_rp(self):
        odpowiedz = klient(self.dyrektor).get(self.karta)

        self.assertContains(klient(self.z.szef).get(self.karta), 'id="n-notatki"')  # oceniający ma panel notatek
        self.assertNotContains(odpowiedz, 'id="n-notatki"')
        for klucz in ("notatki", "karta_ezd", "radar"):
            self.assertNotIn(klucz, odpowiedz.context)

    def test_dyrektor_nie_widzi_ocen_bez_sprzeciwu(self):
        inny = pracownik("jan", przelozony=self.z.szef)
        bez_sprzeciwu = uslugi.rozpocznij_cykl(inny, self.z.kadry.uzytkownik, poczatek_cyklu=POCZATEK, data=POCZATEK)

        self.assertEqual(klient(self.dyrektor).get(f"/oceny/{bez_sprzeciwu.pk}/").status_code, 404)

    def test_komorka_kadr_nie_ma_formularza_i_nie_moze_rozstrzygnac(self):
        kadry = klient(self.z.kadry)

        self.assertNotContains(kadry.get(self.karta), FORMULARZ)
        odpowiedz = kadry.post(czynnosc(self.ocena, FORMULARZ), {"rozstrzygniecie": "nieuwzgledniony"})

        self.assertEqual(odpowiedz.status_code, 403)
        self.sprzeciw.refresh_from_db()
        self.assertFalse(self.sprzeciw.rozpatrzony)

    def test_dyrektor_rozstrzyga_sprzeciw_w_formularzu(self):
        odpowiedz = klient(self.dyrektor).post(
            czynnosc(self.ocena, FORMULARZ),
            {"rozstrzygniecie": "nieuwzgledniony", "uzasadnienie": "Ocena odnosi się do kryteriów."}, follow=True,
        )

        self.sprzeciw.refresh_from_db()
        self.assertEqual((self.sprzeciw.rozstrzygniecie, self.sprzeciw.data_rozstrzygniecia), ("nieuwzgledniony", DZIEN))
        wpis = Zdarzenie.objects.get(ocena=self.ocena, czynnosc="rozpatrzenie sprzeciwu")
        self.assertIn("dyrektor generalny urzędu", wpis.podpis)
        self.assertContains(odpowiedz, "Rozstrzygnięcie sprzeciwu zostało wprowadzone.")
        self.assertNotContains(odpowiedz, czynnosc(self.ocena, FORMULARZ))

    def test_dyrektor_nie_rozstrzyga_sprzeciwu_od_wlasnej_oceny(self):
        z = Zespol.__new__(Zespol)
        z.kadry, z.szef = self.z.kadry, self.z.szef
        self.dyrektor.przelozony = self.z.szef
        self.dyrektor.save()
        z.ola = self.dyrektor
        wlasna = z.ocena_zakonczona(punkty=1)
        uslugi.wnies_sprzeciw(wlasna, self.dyrektor.uzytkownik, tresc=TRESC, data=WNIESIONY)

        with self.assertRaises(BladUprawnien):
            uslugi.rozpatrz_sprzeciw(wlasna, self.dyrektor.uzytkownik, rozstrzygniecie="nieuwzgledniony", data=DZIEN)
        zadania = [zadanie.ocena for zadanie in zadania_uzytkownika(self.dyrektor.uzytkownik, DZIEN) if zadanie.kod == "ROZPATRZ_SPRZECIW"]
        self.assertEqual(zadania, [self.ocena])
        self.assertNotContains(klient(self.dyrektor).get(f"/oceny/{wlasna.pk}/"), czynnosc(wlasna, FORMULARZ))


class StanNaLiscieZadanTest(Podstawa):
    def test_oceniany_przelozony_kadry_i_dyrektor_widza_stan_sprzeciwu(self):
        for osoba in (self.z.ola, self.z.szef, self.z.kadry, self.dyrektor):
            odpowiedz = klient(osoba).get(reverse("zadania"))

            self.assertContains(odpowiedz, "<h2>Sprzeciwy od ocen</h2>", count=1, html=True, msg_prefix=osoba.imie)
            self.assertContains(odpowiedz, f"{WNIESIONY:%d.%m.%Y}", msg_prefix=osoba.imie)
            self.assertContains(odpowiedz, f"{self.termin:%d.%m.%Y}", msg_prefix=osoba.imie)
            self.assertContains(odpowiedz, "w toku - ", msg_prefix=osoba.imie)
            self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [], osoba.imie)

    def test_osoba_spoza_sprawy_nie_widzi_sprzeciwu(self):
        self.assertEqual(sprzeciwy_uzytkownika(self.z.obcy.uzytkownik, DZIEN), [])
        self.assertNotContains(klient(self.z.obcy).get(reverse("zadania")), "Sprzeciwy od ocen okresowych")

    def test_po_terminie_stan_mowi_o_ile_dni(self):
        po = date(2026, 12, 1)

        (wiersz,) = sprzeciwy_uzytkownika(self.z.ola.uzytkownik, po)

        self.assertEqual(wiersz["stan"], "po_terminie")
        self.assertIn(f"{(po - self.termin).days} dni po terminie", wiersz["powod"])

    def test_po_rozstrzygnieciu_widac_wynik_i_date(self):
        uslugi.rozpatrz_sprzeciw(self.ocena, self.dyrektor.uzytkownik, rozstrzygniecie="nieuwzgledniony", data=DZIEN)

        (wiersz,) = sprzeciwy_uzytkownika(self.z.ola.uzytkownik, DZIEN)
        odpowiedz = klient(self.z.ola).get(reverse("zadania"))

        self.assertEqual((wiersz["stan"], wiersz["stan_opis"]), ("pilne", "nieuwzględniony - rozstrzygnięcie czeka na doręczenie"))
        self.assertContains(odpowiedz, "nieuwzględniony - rozstrzygnięcie czeka na doręczenie")
        self.assertContains(odpowiedz, f"{DZIEN:%d.%m.%Y}")


class KontoAdministratoraTest(Podstawa):
    """Konto administratora to konto funkcyjne zaplecza: nie pokazuje ocen ani sprzeciwów. Pracownik, który ma
    także uprawnienia administratora, widzi wyłącznie sprawy wynikające z jego własnej roli w ocenie
    (decyzja prowadzącego projekt z 22.11.2026)."""

    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.create_superuser(username="admin")
        self.przegladarka = Client()
        self.przegladarka.force_login(self.admin)

    def test_konto_funkcyjne_nie_ma_sprzeciwow_zadan_ani_ocen(self):
        self.assertEqual(sprzeciwy_uzytkownika(self.admin, DZIEN), [])
        self.assertEqual(zadania_uzytkownika(self.admin, DZIEN), [])
        self.assertEqual(list(uprawnienia.oceny_widoczne(self.admin)), [])

        odpowiedz = self.przegladarka.get(reverse("zadania"))

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertNotContains(odpowiedz, "Sprzeciwy od ocen")
        self.assertNotContains(odpowiedz, self.z.ola.nazwisko)
        self.assertContains(odpowiedz, "konto funkcyjne")
        self.assertContains(odpowiedz, reverse("administracja"))
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_konto_funkcyjne_nie_otwiera_karty_arkusza_ani_kalendarza_oceny(self):
        for adres in (self.karta, reverse("arkusz_docx", args=[self.ocena.pk]), reverse("arkusz_pdf", args=[self.ocena.pk]),
                      reverse("kalendarz", args=[self.ocena.pk])):
            self.assertEqual(self.przegladarka.get(adres).status_code, 404, adres)
        odpowiedz = self.przegladarka.post(czynnosc(self.ocena, FORMULARZ), {"rozstrzygniecie": "nieuwzgledniony"})
        self.assertEqual(odpowiedz.status_code, 404)
        self.sprzeciw.refresh_from_db()
        self.assertFalse(self.sprzeciw.rozpatrzony)

    def test_pracownik_z_uprawnieniami_administratora_widzi_tylko_wlasna_sprawe(self):
        for osoba in (self.z.ola, self.z.obcy):
            osoba.uzytkownik.is_superuser = True
            osoba.uzytkownik.save()

        self.assertEqual([wiersz["sprzeciw"] for wiersz in sprzeciwy_uzytkownika(self.z.ola.uzytkownik, DZIEN)], [self.sprzeciw])
        self.assertEqual(klient(self.z.ola).get(self.karta).status_code, 200)
        self.assertEqual(sprzeciwy_uzytkownika(self.z.obcy.uzytkownik, DZIEN), [])
        self.assertEqual(klient(self.z.obcy).get(self.karta).status_code, 404)
        self.assertNotContains(klient(self.z.obcy).get(reverse("zadania")), "konto funkcyjne")


DORECZENIE = "doreczenie-rozstrzygniecia"
CZEKA = "nieuwzględniony - rozstrzygnięcie czeka na doręczenie"
PO_DORECZENIU = date(2026, 11, 12)
ODWOLANIE = "przysługuje odwołanie do sądu pracy - do 26.11.2026"   # 14 dni od doręczenia 12.11.2026


class Odmowa(Podstawa):
    """Sprzeciw nieuwzględniony przez dyrektora generalnego w terminie (11.11.2026)."""

    def setUp(self):
        super().setUp()
        uslugi.rozpatrz_sprzeciw(self.ocena, self.dyrektor.uzytkownik, rozstrzygniecie="nieuwzgledniony", data=DZIEN)
        self.sprzeciw.refresh_from_db()

    def doreczenie(self):
        self.sprzeciw.refresh_from_db()
        return self.sprzeciw.data_doreczenia

    def wpisy(self):
        return Zdarzenie.objects.filter(ocena=self.ocena, czynnosc="doręczenie rozstrzygnięcia sprzeciwu")


class DoreczenieRozstrzygnieciaTest(Odmowa):
    """Art. 83 ust. 5 u.s.c.: termin odwołania do sądu pracy biegnie od doręczenia decyzji, więc system potrzebuje
    daty doręczenia. Potwierdza ją oceniany albo wpisuje komórka kadr - tak jak przy zapoznaniu z oceną."""

    def test_przed_doreczeniem_status_nie_podaje_daty_a_oceniany_i_kadry_maja_formularz(self):
        for osoba, pole_daty in ((self.z.ola, False), (self.z.kadry, True)):
            odpowiedz = klient(osoba).get(self.karta)

            self.assertContains(odpowiedz, CZEKA, msg_prefix=osoba.imie)
            self.assertContains(odpowiedz, czynnosc(self.ocena, DORECZENIE), count=1, msg_prefix=osoba.imie)
            self.assertEqual('name="data_doreczenia"' in odpowiedz.content.decode(), pole_daty, osoba.imie)
            self.assertNotContains(odpowiedz, "przysługuje odwołanie", msg_prefix=osoba.imie)
            self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [], osoba.imie)

    def test_przelozony_i_dyrektor_widza_status_ale_nie_formularz(self):
        for osoba in (self.z.szef, self.dyrektor):
            odpowiedz = klient(osoba).get(self.karta)

            self.assertContains(odpowiedz, CZEKA, msg_prefix=osoba.imie)
            self.assertNotContains(odpowiedz, DORECZENIE, msg_prefix=osoba.imie)

    @override_settings(ASYSTENT_DZIS=PO_DORECZENIU.isoformat())
    def test_oceniany_potwierdza_odbior_z_dzisiejsza_data_i_status_podaje_termin_odwolania(self):
        odpowiedz = klient(self.z.ola).post(czynnosc(self.ocena, DORECZENIE), follow=True)

        self.assertEqual(self.doreczenie(), PO_DORECZENIU)
        self.assertContains(odpowiedz, ODWOLANIE)
        self.assertContains(odpowiedz, "Rozstrzygnięcie doręczono 12.11.2026.")
        self.assertContains(odpowiedz, "art. 83 ust. 5 u.s.c.")
        self.assertNotContains(odpowiedz, czynnosc(self.ocena, DORECZENIE))
        wpis = self.wpisy().get()
        self.assertEqual((wpis.uzytkownik, wpis.data), (self.z.ola.uzytkownik, PO_DORECZENIU))
        self.assertIn("potwierdził oceniany", wpis.opis)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    @override_settings(ASYSTENT_DZIS="2026-11-16")
    def test_komorka_kadr_wpisuje_date_doreczenia_z_przeszlosci(self):
        odpowiedz = klient(self.z.kadry).post(
            czynnosc(self.ocena, DORECZENIE), {"data_doreczenia": PO_DORECZENIU.isoformat()}, follow=True
        )

        self.assertEqual(self.doreczenie(), PO_DORECZENIU)
        self.assertContains(odpowiedz, ODWOLANIE)
        wpis = self.wpisy().get()
        self.assertEqual(wpis.uzytkownik, self.z.kadry.uzytkownik)
        self.assertIn("12.11.2026", wpis.opis)
        self.assertIn("komórka kadr", wpis.opis)

    @override_settings(ASYSTENT_DZIS="2026-11-16")
    def test_bledna_data_doreczenia_wraca_z_komunikatem_i_niczego_nie_zapisuje(self):
        przypadki = (
            ("2026-11-17", "nie może być późniejsza niż dzisiejsza"),
            ("2026-11-10", "nie może być wcześniejsza niż data rozstrzygnięcia (11.11.2026)"),
            ("12.11.2026", "Podaj datę: doręczenia rozstrzygnięcia"),
            ("", "Podaj datę: doręczenia rozstrzygnięcia"),
        )
        for wartosc, komunikat in przypadki:
            odpowiedz = klient(self.z.kadry).post(czynnosc(self.ocena, DORECZENIE), {"data_doreczenia": wartosc}, follow=True)

            self.assertEqual(odpowiedz.status_code, 200, wartosc)
            self.assertContains(odpowiedz, komunikat, msg_prefix=wartosc)
            self.assertIsNone(self.doreczenie(), wartosc)
        self.assertFalse(self.wpisy().exists())

    def test_przelozony_dyrektor_i_osoba_spoza_sprawy_nie_odnotuja_doreczenia(self):
        for osoba, kod in ((self.z.szef, 403), (self.dyrektor, 403), (self.z.obcy, 404)):
            odpowiedz = klient(osoba).post(czynnosc(self.ocena, DORECZENIE), {"data_doreczenia": DZIEN.isoformat()})

            self.assertEqual(odpowiedz.status_code, kod, osoba.imie)
        self.assertIsNone(self.doreczenie())
        self.assertFalse(self.wpisy().exists())

    def test_doreczenia_nie_odnotowuje_sie_drugi_raz(self):
        uslugi.odnotuj_doreczenie_rozstrzygniecia(self.ocena, self.z.ola.uzytkownik, data=DZIEN)

        odpowiedz = klient(self.z.kadry).post(
            czynnosc(self.ocena, DORECZENIE), {"data_doreczenia": DZIEN.isoformat()}, follow=True
        )

        self.assertContains(odpowiedz, "Nie ma rozstrzygnięcia, którego doręczenie trzeba odnotować.")
        self.assertEqual(self.wpisy().count(), 1)

    def test_po_uplywie_terminu_status_mowi_tylko_ze_termin_uplynal(self):
        uslugi.odnotuj_doreczenie_rozstrzygniecia(self.ocena, self.z.ola.uzytkownik, data=DZIEN)   # odwołanie do 25.11.2026

        (wiersz,) = sprzeciwy_uzytkownika(self.z.ola.uzytkownik, date(2026, 11, 26))

        self.assertEqual((wiersz["stan"], wiersz["stan_opis"]), ("informacja", "termin na odwołanie do sądu pracy upłynął 25.11.2026"))


class DoreczenieBezOdmowyTest(Podstawa):
    def test_przy_sprzeciwie_w_toku_nie_ma_formularza_ani_zapisu(self):
        self.assertNotContains(klient(self.z.ola).get(self.karta), DORECZENIE)

        odpowiedz = klient(self.z.ola).post(czynnosc(self.ocena, DORECZENIE), follow=True)

        self.assertContains(odpowiedz, "Nie ma rozstrzygnięcia, którego doręczenie trzeba odnotować.")
        self.sprzeciw.refresh_from_db()
        self.assertIsNone(self.sprzeciw.data_doreczenia)

    def test_po_uwzglednieniu_sprzeciwu_karta_nie_mowi_o_sadzie_pracy(self):
        uslugi.rozpatrz_sprzeciw(self.ocena, self.dyrektor.uzytkownik, rozstrzygniecie="ponowne_sporzadzenie", data=DZIEN)

        odpowiedz = klient(self.z.ola).get(self.karta)

        self.assertContains(odpowiedz, "uwzględniony - ponowne sporządzenie oceny")
        self.assertNotContains(odpowiedz, "sądu pracy")
        self.assertNotContains(odpowiedz, DORECZENIE)

    def test_sprzeciw_nierozpatrzony_w_terminie_daje_status_odwolania_a_dyrektor_nadal_ma_zadanie(self):
        po = date(2026, 12, 1)   # rozpatrzenie do 24.11.2026, więc odwołanie do 8.12.2026

        (wiersz,) = sprzeciwy_uzytkownika(self.z.ola.uzytkownik, po)
        with override_settings(ASYSTENT_DZIS=po.isoformat()):
            odpowiedz = klient(self.z.ola).get(self.karta)

        self.assertEqual((wiersz["stan"], wiersz["stan_opis"]), ("po_terminie", "przysługuje odwołanie do sądu pracy - do 08.12.2026"))
        self.assertIn("nierozpatrzony w terminie", wiersz["powod"])
        self.assertContains(odpowiedz, "Sprzeciwu nie rozpatrzono w terminie (do 24.11.2026).")
        self.assertNotContains(odpowiedz, DORECZENIE)
        self.assertEqual([zadanie.kod for zadanie in zadania_uzytkownika(self.dyrektor.uzytkownik, po)], ["ROZPATRZ_SPRZECIW"])


@override_settings(ASYSTENT_DZIS=PO_DORECZENIU.isoformat())
class StatusPrzyOcenieTest(Odmowa):
    """Ocena pozostaje zakończona; status po sprzeciwie widać obok etapu wszędzie tam, gdzie widać etap oceny."""

    def setUp(self):
        super().setUp()
        uslugi.odnotuj_doreczenie_rozstrzygniecia(self.ocena, self.z.ola.uzytkownik, data=PO_DORECZENIU)
        self.ocena.refresh_from_db()

    def test_ocena_pozostaje_zakonczona(self):
        self.assertTrue(self.ocena.zakonczona)
        self.assertEqual(self.ocena.po_sprzeciwie["stan_opis"], ODWOLANIE)

    def test_ocena_bez_sprzeciwu_nie_ma_statusu(self):
        inny = pracownik("jan", przelozony=self.z.szef)
        bez_sprzeciwu = uslugi.rozpocznij_cykl(inny, self.z.kadry.uzytkownik, poczatek_cyklu=POCZATEK, data=POCZATEK)

        self.assertIsNone(bez_sprzeciwu.po_sprzeciwie)

    def test_status_jest_na_liscie_moich_ocen_w_naglowku_karty_i_w_tabeli_sprzeciwow(self):
        lista = klient(self.z.ola).get(reverse("zadania"))
        karta = klient(self.z.ola).get(self.karta)

        self.assertContains(lista, ODWOLANIE, count=2)          # tabela sprzeciwów i pozycja „Moje oceny”
        self.assertContains(karta, "Status po sprzeciwie")
        self.assertContains(karta, ODWOLANIE, count=2)          # nagłówek karty i sekcja sprzeciwu
        for odpowiedz in (lista, karta):
            self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_status_widza_kadry_na_liscie_pracownikow_dopoki_ocena_jest_biezaca(self):
        """Po rozstrzygnięciu sprzeciwu rusza kolejny cykl i lista kadr pokazuje nową ocenę; status zostaje
        w tabeli sprzeciwów i na karcie oceny, której dotyczy."""
        from oceny.cykle import uzgodnij

        przed = klient(self.z.kadry).get(reverse("kadry"))
        uzgodnij(self.ocena.oceniany_id)
        po = klient(self.z.kadry).get(reverse("kadry"))

        self.assertContains(przed, ODWOLANIE)
        self.assertEqual(bledy_dostepnosci(przed.content.decode()), [])
        self.assertNotContains(po, ODWOLANIE)
        self.assertContains(klient(self.z.kadry).get(reverse("zadania")), ODWOLANIE)

    def test_karta_pokazuje_doreczenie_i_termin_odwolania_w_terminach(self):
        odpowiedz = klient(self.z.ola).get(self.karta)

        nazwy = {wiersz["nazwa"]: wiersz["data"] for wiersz in odpowiedz.context["terminy"]}
        self.assertEqual(nazwy["Doręczenie rozstrzygnięcia sprzeciwu"], PO_DORECZENIU)
        self.assertEqual(nazwy["Odwołanie do sądu pracy - najpóźniej"], date(2026, 11, 26))
