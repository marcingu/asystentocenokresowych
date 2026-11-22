"""Lista zadań: co, kto i do kiedy ma zrobić - wynika z etapu procesu i roli użytkownika.

Terminy liczy rdzeń (`asystent_ocen.terminy`); tu sprawdzane jest, czy zadanie trafia do właściwej osoby
z właściwym terminem. Podstawy: § 5-7, § 10-12 rozp.; art. 81 ust. 4 i 8, art. 83 u.s.c.
"""

from datetime import date, timedelta

from django.test import TestCase, override_settings

from asystent_ocen import terminy
from asystent_ocen.przebieg import Rola
from oceny import uslugi
from oceny.zadania import opisy_skutkow, skutki_oceny_zakonczonej, zadania_uzytkownika

from .pomocnicze import DZIEN_OCENY, POCZATEK, TERMIN, Zespol, dyrektor_generalny, pracownik


def kody(zadania) -> list[str]:
    return [zadanie.kod for zadanie in zadania]


class ZadaniaTest(TestCase):
    def setUp(self):
        self.z = Zespol()

    def test_wyznaczenie_kryteriow_jest_zadaniem_oceniajacego_z_terminem_z_rozporzadzenia(self):
        """§ 7 pkt 1 rozp.: 30 dni od zatrudnienia na czas nieokreślony albo sporządzenia poprzedniej oceny."""
        ocena = self.z.nowa_ocena()

        zadania = zadania_uzytkownika(self.z.szef.uzytkownik, date(2024, 11, 25))

        self.assertEqual(kody(zadania), ["WYZNACZ_KRYTERIA"])
        zadanie = zadania[0]
        self.assertEqual((zadanie.ocena, zadanie.rola), (ocena, Rola.OCENIAJACY))
        self.assertEqual(zadanie.termin, terminy.termin_wyznaczenia_kryteriow(POCZATEK))
        self.assertEqual(zadanie.dni, (zadanie.termin - date(2024, 11, 25)).days)
        self.assertIn("§ 7", zadanie.podstawa)
        self.assertEqual(zadania_uzytkownika(self.z.ola.uzytkownik, date(2024, 11, 25)), [])

    def test_potwierdzenie_kryteriow_jest_zadaniem_ocenianego(self):
        ocena = self.z.nowa_ocena()
        uslugi.wyznacz_kryteria(
            ocena, self.z.szef.uzytkownik, kryteria_dodatkowe=self.z.dodatkowe(), termin=TERMIN, data=date(2024, 12, 2)
        )

        self.assertEqual(kody(zadania_uzytkownika(self.z.ola.uzytkownik, date(2024, 12, 2))), ["POTWIERDZ_KRYTERIA"])
        self.assertEqual(zadania_uzytkownika(self.z.szef.uzytkownik, date(2024, 12, 2)), [])

    def test_sporzadzenie_oceny_ma_termin_z_czesci_pierwszej_arkusza(self):
        self.z.ocena_z_kryteriami()

        zadanie = zadania_uzytkownika(self.z.szef.uzytkownik, TERMIN - timedelta(days=40))[0]

        self.assertEqual((zadanie.kod, zadanie.termin, zadanie.dni), ("SPORZADZ_OCENE", TERMIN, 40))
        self.assertEqual(zadanie.stan, "w_terminie")

    @override_settings(ASYSTENT_DNI_PILNE=14)
    def test_stan_zadania_zalezy_od_liczby_dni_do_terminu(self):
        self.z.ocena_z_kryteriami()
        szef = self.z.szef.uzytkownik

        self.assertEqual(zadania_uzytkownika(szef, TERMIN - timedelta(days=14))[0].stan, "pilne")
        self.assertEqual(zadania_uzytkownika(szef, TERMIN)[0].stan, "pilne")
        self.assertEqual(zadania_uzytkownika(szef, TERMIN + timedelta(days=1))[0].stan, "po_terminie")

    def test_wniosek_o_zmiane_terminu_trafia_do_oceniajacego(self):
        ocena = self.z.ocena_z_kryteriami()
        uslugi.zloz_wniosek_o_zmiane_terminu(ocena, self.z.ola.uzytkownik, data=date(2025, 6, 11))

        self.assertIn("ROZPATRZ_WNIOSEK_O_TERMIN", kody(zadania_uzytkownika(self.z.szef.uzytkownik, date(2025, 6, 12))))

    def test_zapoznanie_z_ocena_jest_zadaniem_ocenianego_bez_terminu_dziennego(self):
        """§ 12 ust. 1 rozp.: „niezwłocznie”."""
        self.z.ocena_do_zapoznania()

        zadanie = zadania_uzytkownika(self.z.ola.uzytkownik, DZIEN_OCENY)[0]

        self.assertEqual((zadanie.kod, zadanie.termin, zadanie.stan), ("ZAPOZNAJ_SIE_Z_OCENA", None, "bez_terminu"))

    def test_po_zakonczeniu_system_otwiera_kolejny_cykl_bez_zadania_dla_kadr(self):
        from oceny.cykle import uzgodnij
        ocena = self.z.ocena_zakonczona(punkty=1)
        nowa = uzgodnij(ocena.oceniany_id)
        self.assertEqual(nowa.poprzednia, ocena)
        self.assertIsNone(uzgodnij(ocena.oceniany_id))
        self.assertEqual(zadania_uzytkownika(self.z.kadry.uzytkownik, DZIEN_OCENY), [])
        zadanie = zadania_uzytkownika(self.z.szef.uzytkownik, DZIEN_OCENY)[0]
        self.assertEqual(zadanie.termin, terminy.termin_wyznaczenia_kryteriow(DZIEN_OCENY, po_negatywnej=True))

    def test_sprzeciw_wstrzymuje_kolejny_cykl_i_daje_dyrektorowi_generalnemu_termin_rozpatrzenia(self):
        """Art. 83 ust. 1 i 3 u.s.c.: sprzeciw służy do dyrektora generalnego; 14 dni od wniesienia."""
        dyrektor = dyrektor_generalny()
        ocena = self.z.ocena_zakonczona(punkty=1)
        uslugi.wnies_sprzeciw(ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 10))

        zadania = zadania_uzytkownika(dyrektor.uzytkownik, date(2026, 11, 11))

        self.assertEqual(kody(zadania), ["ROZPATRZ_SPRZECIW"])
        self.assertEqual(zadania[0].rola, Rola.DYREKTOR_GENERALNY)
        self.assertEqual(zadania[0].termin, terminy.termin_rozpatrzenia_sprzeciwu(date(2026, 11, 10)))
        self.assertEqual(zadania_uzytkownika(self.z.kadry.uzytkownik, date(2026, 11, 11)), [])

    def test_po_rozpoczeciu_kolejnego_cyklu_stara_ocena_nie_daje_zadan(self):
        ocena = self.z.ocena_zakonczona()
        uslugi.rozpocznij_kolejny_cykl(ocena, self.z.kadry.uzytkownik, data=date(2026, 11, 5))

        self.assertEqual(zadania_uzytkownika(self.z.kadry.uzytkownik, date(2026, 11, 5)), [])
        self.assertEqual(kody(zadania_uzytkownika(self.z.szef.uzytkownik, date(2026, 11, 5))), ["WYZNACZ_KRYTERIA"])

    def test_zadania_sa_ulozone_od_najblizszego_terminu_a_bez_terminu_na_koncu(self):
        self.z.ocena_z_kryteriami()
        drugi = pracownik("jan", przelozony=self.z.szef)
        uslugi.rozpocznij_cykl(drugi, self.z.kadry.uzytkownik, poczatek_cyklu=date(2026, 10, 1), data=date(2026, 10, 1))
        trzeci = pracownik("ewa", przelozony=self.z.szef)
        ocena_ewy = uslugi.rozpocznij_cykl(trzeci, self.z.kadry.uzytkownik, poczatek_cyklu=POCZATEK, data=POCZATEK)
        uslugi.wyznacz_kryteria(
            ocena_ewy, self.z.szef.uzytkownik, kryteria_dodatkowe=[], termin=TERMIN, data=date(2024, 12, 2)
        )
        uslugi.potwierdz_kryteria(ocena_ewy, trzeci.uzytkownik, data=date(2024, 12, 3))
        uslugi.zloz_wniosek_o_zmiane_terminu(ocena_ewy, trzeci.uzytkownik, data=date(2025, 6, 11))

        zadania = zadania_uzytkownika(self.z.szef.uzytkownik, date(2026, 10, 5))

        terminy_zadan = [zadanie.termin for zadanie in zadania]
        z_terminem = [termin for termin in terminy_zadan if termin is not None]
        self.assertEqual(z_terminem, sorted(z_terminem))
        self.assertIsNone(terminy_zadan[-1])
        self.assertEqual(len(zadania), 4)


class SkutkiTest(TestCase):
    def test_ocena_negatywna_daje_ponowna_ocene_i_krotki_termin_na_kryteria(self):
        """Art. 81 ust. 9 u.s.c., § 7 pkt 2 rozp."""
        z = Zespol()
        ocena = z.ocena_zakonczona(punkty=1)

        skutki = {skutek.kod: skutek for skutek in skutki_oceny_zakonczonej(ocena)}

        self.assertEqual(skutki["PONOWNA_OCENA"].termin, terminy.data_ponownej_oceny_po_negatywnej(DZIEN_OCENY))
        self.assertIn("NOWE_KRYTERIA", skutki)
        self.assertNotIn("ROZWIAZANIE_STOSUNKU_PRACY", skutki)

    def test_druga_kolejna_negatywna_ocena_urzednika_jest_sygnalizowana_z_podstawa(self):
        """Art. 71 ust. 1 pkt 1 u.s.c. System sygnalizuje przepis - niczego nie rozstrzyga."""
        z = Zespol(rodzaj_zatrudnienia="mianowanie", stopien_sluzbowy=3)
        pierwsza = z.ocena_zakonczona(punkty=1)
        druga = uslugi.rozpocznij_kolejny_cykl(pierwsza, z.kadry.uzytkownik, data=date(2026, 11, 5))
        uslugi.wyznacz_kryteria(
            druga, z.szef.uzytkownik, kryteria_dodatkowe=z.dodatkowe(), termin=date(2027, 5, 5), data=date(2026, 11, 6)
        )
        uslugi.potwierdz_kryteria(druga, z.ola.uzytkownik, data=date(2026, 11, 6))
        uslugi.sporzadz_ocene(
            druga, z.szef.uzytkownik, data_rozmowy=date(2027, 5, 4), oceny=z.oceny(1), wnioski_iprz="Szkolenie.",
            uzasadnienie="Zadania nadal wykonywane po terminie.", data=date(2027, 5, 5),
        )
        uslugi.potwierdz_zapoznanie(druga, z.ola.uzytkownik, data=date(2027, 5, 5))

        skutki = {skutek.kod: skutek for skutek in skutki_oceny_zakonczonej(druga)}

        self.assertEqual(skutki["ROZWIAZANIE_STOSUNKU_PRACY"].podstawa, "art. 71 ust. 1 pkt 1 u.s.c.")

    def test_dwie_kolejne_oceny_na_najwyzszych_poziomach_daja_stopien_z_mocy_prawa(self):
        """Art. 89 ust. 2 u.s.c."""
        z = Zespol(rodzaj_zatrudnienia="mianowanie", stopien_sluzbowy=3, data_stopnia=date(2020, 1, 15))
        pierwsza = z.ocena_zakonczona(punkty=7)
        druga = uslugi.rozpocznij_kolejny_cykl(pierwsza, z.kadry.uzytkownik, data=date(2026, 11, 5))
        uslugi.wyznacz_kryteria(
            druga, z.szef.uzytkownik, kryteria_dodatkowe=z.dodatkowe(), termin=date(2028, 11, 3), data=date(2026, 11, 6)
        )
        uslugi.potwierdz_kryteria(druga, z.ola.uzytkownik, data=date(2026, 11, 6))
        uslugi.sporzadz_ocene(
            druga, z.szef.uzytkownik, data_rozmowy=date(2028, 11, 2), oceny=z.oceny(9), wnioski_iprz="Szkolenie.",
            wniosek_o_stopien="NIE", data=date(2028, 11, 3),
        )
        uslugi.potwierdz_zapoznanie(druga, z.ola.uzytkownik, data=date(2028, 11, 3))

        skutki = {skutek.kod: skutek for skutek in skutki_oceny_zakonczonej(druga)}

        self.assertEqual(
            skutki["STOPIEN_OBLIGATORYJNY"].termin, terminy.termin_przyznania_stopnia_obligatoryjnego(date(2028, 11, 3))
        )
        self.assertNotIn("STOPIEN_OBLIGATORYJNY", {s.kod for s in skutki_oceny_zakonczonej(pierwsza)})

    def test_skutki_maja_opis_z_terminem_i_parametrami_z_przepisow(self):
        z = Zespol()
        ocena = z.ocena_zakonczona(punkty=1)

        opisy = {wiersz["kod"]: wiersz["opis"] for wiersz in opisy_skutkow(ocena)}

        termin = terminy.data_ponownej_oceny_po_negatywnej(DZIEN_OCENY)
        self.assertIn(f"{termin:%d.%m.%Y}", opisy["PONOWNA_OCENA"])
        self.assertIn("6 mies.", opisy["PONOWNA_OCENA"])
        self.assertIn("do ", opisy["NOWE_KRYTERIA"])

    def test_ocena_w_toku_nie_ma_skutkow(self):
        self.assertEqual(skutki_oceny_zakonczonej(Zespol().ocena_z_kryteriami()), [])
