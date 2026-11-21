"""Modele, data bieżąca i uprawnienia.

Wymagania: dokumentacja/architektura.md (modele, role), decyzja zespołu z 21.11.2026: notatki oceniającego
widzi wyłącznie oceniający.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db.models import ProtectedError
from django.test import TestCase, override_settings

from asystent_ocen.przebieg import Etap, Rola
from oceny import uprawnienia
from oceny.czas import dzis
from oceny.models import Ocena, Zdarzenie

from .pomocnicze import DZIEN_OCENY, POCZATEK, TERMIN, Zespol, pracownik


class PracownikTest(TestCase):
    def test_arkusz_wynika_ze_stanowiska(self):
        """§ 3 rozp.: A - kierownik urzędu, B - kierujący pracownikami, C - pozostali."""
        self.assertEqual(pracownik("a", kierownik_urzedu=True, kieruje_pracownikami=True).arkusz, "A")
        self.assertEqual(pracownik("b", kieruje_pracownikami=True).arkusz, "B")
        self.assertEqual(pracownik("c").arkusz, "C")

    def test_urzednikiem_jest_osoba_mianowana(self):
        self.assertTrue(pracownik("u", rodzaj_zatrudnienia="mianowanie").urzednik)
        self.assertFalse(pracownik("p").urzednik)

    def test_ocenie_podlegaja_tylko_rodzaje_zatrudnienia_z_przepisow(self):
        """Art. 81 ust. 1 u.s.c."""
        self.assertTrue(pracownik("n").podlega_ocenie)
        self.assertTrue(pracownik("m", rodzaj_zatrudnienia="mianowanie").podlega_ocenie)
        self.assertFalse(pracownik("o", rodzaj_zatrudnienia="umowa_na_czas_okreslony").podlega_ocenie)

    def test_nieznany_rodzaj_zatrudnienia_nie_przechodzi_walidacji(self):
        osoba = pracownik("x")
        osoba.rodzaj_zatrudnienia = "umowa_zlecenie"
        with self.assertRaises(ValidationError):
            osoba.full_clean()


class OcenaTest(TestCase):
    def setUp(self):
        self.zespol = Zespol(rodzaj_zatrudnienia="mianowanie")

    def test_nowa_ocena_zaczyna_od_wyznaczenia_kryteriow(self):
        ocena = Ocena.utworz(oceniany=self.zespol.ola, oceniajacy=self.zespol.szef, poczatek_cyklu=POCZATEK)

        proces = ocena.proces()
        self.assertEqual(proces.etap, Etap.KRYTERIA_DO_WYZNACZENIA)
        self.assertEqual((proces.arkusz, proces.urzednik, proces.poczatek_cyklu), ("C", True, POCZATEK))
        self.assertEqual(ocena.etap, "KRYTERIA_DO_WYZNACZENIA")
        self.assertEqual(ocena.etap_rdzenia, Etap.KRYTERIA_DO_WYZNACZENIA)

    def test_stan_procesu_wraca_z_bazy_bez_zmian(self):
        ocena = self.zespol.ocena_zakonczona()
        proces = ocena.proces()

        z_bazy = Ocena.objects.get(pk=ocena.pk)

        self.assertEqual(z_bazy.proces(), proces)

    def test_zapis_procesu_odswieza_kopie_do_zapytan(self):
        ocena = self.zespol.ocena_zakonczona()

        z_bazy = Ocena.objects.get(pk=ocena.pk)

        self.assertEqual(z_bazy.etap, "ZAKONCZONA")
        self.assertEqual(z_bazy.termin, TERMIN)
        self.assertEqual(z_bazy.wynik, "POZYTYWNA")
        self.assertEqual(z_bazy.poziom, "powyżej oczekiwań")
        self.assertEqual(z_bazy.data_zapoznania, DZIEN_OCENY)

    def test_oceny_z_dziennikiem_nie_da_sie_usunac(self):
        ocena = self.zespol.nowa_ocena()
        with self.assertRaises(ProtectedError):
            ocena.delete()


class ZdarzenieTest(TestCase):
    def test_dziennik_jest_tylko_do_dopisywania(self):
        ocena = Zespol().nowa_ocena()
        wpis = Zdarzenie.objects.filter(ocena=ocena).first()

        wpis.opis = "zmienione"
        with self.assertRaises(ValueError):
            wpis.save()
        with self.assertRaises(ValueError):
            wpis.delete()
        with self.assertRaises(ValueError):
            Zdarzenie.objects.filter(ocena=ocena).delete()
        with self.assertRaises(ValueError):
            Zdarzenie.objects.filter(ocena=ocena).update(opis="zmienione")
        self.assertEqual(Zdarzenie.objects.get(pk=wpis.pk).opis, "")


class CzasTest(TestCase):
    def test_bez_ustawienia_dzis_to_data_systemowa(self):
        self.assertEqual(dzis(), date.today())

    @override_settings(ASYSTENT_DZIS="2026-11-23")
    def test_ustawienie_zastepuje_date_systemowa(self):
        self.assertEqual(dzis(), date(2026, 11, 23))

    @override_settings(ASYSTENT_DZIS="23.11.2026")
    def test_bledna_data_w_ustawieniach_jest_zglaszana(self):
        with self.assertRaises(ImproperlyConfigured):
            dzis()


class UprawnieniaTest(TestCase):
    def setUp(self):
        self.zespol = Zespol()
        self.ocena = self.zespol.nowa_ocena()

    def test_role_wynikaja_z_relacji_do_oceny(self):
        z = self.zespol
        self.assertEqual(uprawnienia.role_uzytkownika(z.ola.uzytkownik, self.ocena), {Rola.OCENIANY})
        self.assertEqual(uprawnienia.role_uzytkownika(z.szef.uzytkownik, self.ocena), {Rola.OCENIAJACY})
        self.assertEqual(uprawnienia.role_uzytkownika(z.kadry.uzytkownik, self.ocena), {Rola.ZARZADZAJACY})
        self.assertEqual(uprawnienia.role_uzytkownika(z.obcy.uzytkownik, self.ocena), set())

    def test_administrator_ma_role_admin_takze_bez_profilu_pracownika(self):
        admin = get_user_model().objects.create_superuser(username="admin")
        self.assertEqual(uprawnienia.role_uzytkownika(admin, self.ocena), {Rola.ADMIN})

    def test_konto_bez_profilu_pracownika_nie_ma_zadnej_roli(self):
        gosc = get_user_model().objects.create_user(username="gosc")
        self.assertEqual(uprawnienia.role_uzytkownika(gosc, self.ocena), set())

    def test_osoba_z_kadr_oceniana_we_wlasnej_ocenie_ma_obie_role(self):
        wlasna = Ocena.utworz(oceniany=self.zespol.kadry, oceniajacy=self.zespol.szef, poczatek_cyklu=POCZATEK)
        self.assertEqual(
            uprawnienia.role_uzytkownika(self.zespol.kadry.uzytkownik, wlasna), {Rola.OCENIANY, Rola.ZARZADZAJACY}
        )

    def test_notatki_widzi_wylacznie_oceniajacy(self):
        z = self.zespol
        admin = get_user_model().objects.create_superuser(username="admin")
        self.assertTrue(uprawnienia.widzi_notatki(z.szef.uzytkownik, self.ocena))
        for inny in (z.ola.uzytkownik, z.kadry.uzytkownik, z.obcy.uzytkownik, admin):
            self.assertFalse(uprawnienia.widzi_notatki(inny, self.ocena))

    def test_lista_widocznych_ocen_pomija_cudze(self):
        z = self.zespol
        cudza = Ocena.utworz(oceniany=z.obcy, oceniajacy=z.kadry, poczatek_cyklu=POCZATEK)

        self.assertEqual(set(uprawnienia.oceny_widoczne(z.ola.uzytkownik)), {self.ocena})
        self.assertEqual(set(uprawnienia.oceny_widoczne(z.szef.uzytkownik)), {self.ocena})
        self.assertEqual(set(uprawnienia.oceny_widoczne(z.kadry.uzytkownik)), {self.ocena, cudza})
        self.assertEqual(set(uprawnienia.oceny_widoczne(z.obcy.uzytkownik)), {cudza})

    def test_statystyki_widza_kadry_i_dyrektor(self):
        dyrektor = pracownik("dyrektor", rola_dyrektor=True)
        self.assertTrue(uprawnienia.widzi_statystyki(dyrektor.uzytkownik))
        self.assertTrue(uprawnienia.widzi_statystyki(self.zespol.kadry.uzytkownik))
        self.assertFalse(uprawnienia.widzi_statystyki(self.zespol.szef.uzytkownik))
