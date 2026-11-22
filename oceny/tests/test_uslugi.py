"""Usługi: jedna funkcja na czynność procesu, w transakcji, z wpisem w dzienniku zdarzeń.

Wymagania: dokumentacja/architektura.md (usługi), model BPMN KPRM (tory ról), u.s.c. art. 81 i 83.
Reguły prawne sprawdza rdzeń - tu testowane jest spięcie rdzenia z bazą, rolami użytkowników i dziennikiem.
"""

from datetime import date

from django.test import TestCase

from asystent_ocen.bledy import BladWalidacji
from asystent_ocen.przebieg import BladEtapu, BladUprawnien, Etap, Rola
from oceny import uslugi
from oceny.models import Nieobecnosc, Ocena, Sprzeciw, Zdarzenie

from .pomocnicze import DZIEN_KRYTERIOW, DZIEN_OCENY, DZIEN_ROZMOWY, POCZATEK, TERMIN, Zespol, pracownik


from .pomocnicze import dyrektor_generalny  # noqa: E402


def czynnosci(ocena) -> list[str]:
    return list(Zdarzenie.objects.filter(ocena=ocena).order_by("pk").values_list("czynnosc", flat=True))


class RozpoczecieCykluTest(TestCase):
    def setUp(self):
        self.z = Zespol()

    def test_kadry_rozpoczynaja_cykl_z_przelozonym_jako_oceniajacym(self):
        ocena = self.z.nowa_ocena()

        self.assertEqual((ocena.oceniany, ocena.oceniajacy, ocena.poczatek_cyklu), (self.z.ola, self.z.szef, POCZATEK))
        self.assertEqual(ocena.etap, "KRYTERIA_DO_WYZNACZENIA")
        wpis = Zdarzenie.objects.get(ocena=ocena)
        self.assertEqual((wpis.czynnosc, wpis.uzytkownik), ("rozpoczęcie cyklu oceny", self.z.kadry.uzytkownik))

    def test_poczatkiem_pierwszego_cyklu_jest_domyslnie_dzien_zatrudnienia(self):
        ocena = uslugi.rozpocznij_cykl(self.z.ola, self.z.kadry.uzytkownik)
        self.assertEqual(ocena.poczatek_cyklu, self.z.ola.data_zatrudnienia)

    def test_cykl_rozpoczynaja_tylko_kadry(self):
        with self.assertRaises(BladUprawnien):
            uslugi.rozpocznij_cykl(self.z.ola, self.z.szef.uzytkownik)
        self.assertFalse(Ocena.objects.exists())

    def test_nie_rozpoczyna_sie_cyklu_dla_osoby_niepodlegajacej_ocenie(self):
        """Art. 81 ust. 1 u.s.c. - umowa na czas określony nie podlega ocenie."""
        osoba = pracownik("okresowy", rodzaj_zatrudnienia="umowa_na_czas_okreslony", przelozony=self.z.szef)

        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.rozpocznij_cykl(osoba, self.z.kadry.uzytkownik)

        self.assertEqual(kontekst.exception.kody, {"NIE_PODLEGA_OCENIE"})
        self.assertIn("art. 81 ust. 1", kontekst.exception.bledy[0].podstawa)

    def test_cykl_wymaga_przelozonego_i_opisu_stanowiska(self):
        """Architektura v3: blokada aktywacji cyklu bez opisu stanowiska; ocenia bezpośredni przełożony."""
        osoba = pracownik("sam", opis_stanowiska="")

        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.rozpocznij_cykl(osoba, self.z.kadry.uzytkownik)

        self.assertEqual(kontekst.exception.kody, {"BRAK_PRZELOZONEGO", "BRAK_OPISU_STANOWISKA"})

    def test_nie_ma_dwoch_otwartych_ocen_jednej_osoby(self):
        self.z.nowa_ocena()
        with self.assertRaises(BladWalidacji) as kontekst:
            self.z.nowa_ocena()
        self.assertEqual(kontekst.exception.kody, {"OCENA_W_TOKU"})


class PrzebiegTest(TestCase):
    def setUp(self):
        self.z = Zespol()

    def test_pelny_przebieg_zapisuje_stan_i_dziennik(self):
        z = self.z
        ocena = z.ocena_z_kryteriami()
        uslugi.dodaj_notatke(ocena, z.szef.uzytkownik, tresc="Terminowo zamknięte sprawy.", data=date(2025, 6, 10))
        uslugi.sporzadz_ocene(
            ocena, z.szef.uzytkownik, data_rozmowy=DZIEN_ROZMOWY, oceny=z.oceny(7),
            wnioski_iprz="Szkolenie z postępowania administracyjnego.", data=DZIEN_OCENY,
        )
        uslugi.potwierdz_zapoznanie(ocena, z.ola.uzytkownik, data=DZIEN_OCENY)

        z_bazy = Ocena.objects.get(pk=ocena.pk)
        proces = z_bazy.proces()
        self.assertEqual(proces.etap, Etap.ZAKONCZONA)
        self.assertEqual((proces.wynik.ocena, proces.wynik.poziom), ("POZYTYWNA", "powyżej oczekiwań"))
        self.assertEqual(proces.kryteria_dodatkowe, z.dodatkowe())
        self.assertEqual(proces.formularz.wniosek_o_stopien, "NIE DOTYCZY")
        self.assertEqual(ocena.etap, "ZAKONCZONA")  # przekazany obiekt jest odświeżany
        self.assertEqual(czynnosci(ocena), [
            "rozpoczęcie cyklu oceny", "wyznaczenie kryteriów", "potwierdzenie kryteriów", "notatka",
            "sporządzenie oceny", "potwierdzenie zapoznania z oceną",
        ])

    def test_tresc_notatki_nie_trafia_do_dziennika(self):
        ocena = self.z.ocena_z_kryteriami()
        uslugi.dodaj_notatke(ocena, self.z.szef.uzytkownik, tresc="Poufna obserwacja.", data=date(2025, 6, 10))

        self.assertFalse(Zdarzenie.objects.filter(opis__contains="Poufna").exists())
        self.assertEqual(ocena.proces().notatki[0].tresc, "Poufna obserwacja.")

    def test_nikt_nie_dziala_w_roli_ktorej_nie_ma_w_tej_ocenie(self):
        ocena = self.z.nowa_ocena()

        for uzytkownik in (self.z.ola.uzytkownik, self.z.kadry.uzytkownik, self.z.obcy.uzytkownik):
            with self.assertRaises(BladUprawnien):
                uslugi.wyznacz_kryteria(
                    ocena, uzytkownik, kryteria_dodatkowe=self.z.dodatkowe(), termin=TERMIN, data=DZIEN_KRYTERIOW
                )

        self.assertEqual(Ocena.objects.get(pk=ocena.pk).etap, "KRYTERIA_DO_WYZNACZENIA")
        self.assertEqual(czynnosci(ocena), ["rozpoczęcie cyklu oceny"])

    def test_blad_walidacji_rdzenia_nie_zmienia_stanu_i_niesie_podstawe_prawna(self):
        """§ 5 ust. 2 rozp. - nie więcej niż 3 kryteria dodatkowe."""
        ocena = self.z.nowa_ocena()

        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.wyznacz_kryteria(
                ocena, self.z.szef.uzytkownik, kryteria_dodatkowe=self.z.dodatkowe(4), termin=TERMIN,
                data=DZIEN_KRYTERIOW,
            )

        self.assertEqual(kontekst.exception.kody, {"ZA_DUZO_KRYTERIOW_DODATKOWYCH"})
        self.assertEqual(kontekst.exception.bledy[0].podstawa, "§ 5 ust. 2 rozp.")
        self.assertEqual(Ocena.objects.get(pk=ocena.pk).etap, "KRYTERIA_DO_WYZNACZENIA")
        self.assertEqual(czynnosci(ocena), ["rozpoczęcie cyklu oceny"])

    def test_czynnosc_na_zlym_etapie_jest_odrzucana(self):
        ocena = self.z.nowa_ocena()
        with self.assertRaises(BladEtapu):
            uslugi.potwierdz_zapoznanie(ocena, self.z.ola.uzytkownik, data=DZIEN_OCENY)

    def test_ocena_negatywna_bez_uzasadnienia_nie_przechodzi(self):
        """§ 11 ust. 3 rozp."""
        ocena = self.z.ocena_z_kryteriami()

        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.sporzadz_ocene(
                ocena, self.z.szef.uzytkownik, data_rozmowy=DZIEN_ROZMOWY, oceny=self.z.oceny(1),
                wnioski_iprz="Szkolenie.", data=DZIEN_OCENY,
            )

        self.assertIn("BRAK_UZASADNIENIA_NEGATYWNEJ", kontekst.exception.kody)
        self.assertEqual(Ocena.objects.get(pk=ocena.pk).etap, "OCENIANIE")

    def test_posiadany_stopien_urzednika_pochodzi_z_danych_kadrowych(self):
        z = Zespol.__new__(Zespol)
        z.kadry = self.z.kadry
        z.szef = self.z.szef
        z.ola = pracownik("urzedniczka", przelozony=z.szef, rodzaj_zatrudnienia="mianowanie", stopien_sluzbowy=9)
        ocena = z.ocena_z_kryteriami()

        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.sporzadz_ocene(
                ocena, z.szef.uzytkownik, data_rozmowy=DZIEN_ROZMOWY, oceny=z.oceny(7), wnioski_iprz="Szkolenie.",
                wniosek_o_stopien="TAK", umotywowanie_wniosku="Wysoka jakość pracy.", data=DZIEN_OCENY,
            )

        self.assertEqual(kontekst.exception.kody, {"NAJWYZSZY_STOPIEN"})

    def test_fikcje_zapoznania_stwierdza_strona_we_wskazanej_roli(self):
        ocena = self.z.ocena_do_zapoznania()

        with self.assertRaises(BladUprawnien):
            uslugi.stwierdz_fikcje_zapoznania(ocena, self.z.obcy.uzytkownik, rola=Rola.OCENIAJACY, data=DZIEN_OCENY)
        uslugi.stwierdz_fikcje_zapoznania(ocena, self.z.kadry.uzytkownik, rola=Rola.ZARZADZAJACY, data=DZIEN_OCENY)

        proces = ocena.proces()
        self.assertTrue(proces.zapoznanie_fikcyjne)
        self.assertEqual(proces.fikcje_stwierdzil, Rola.ZARZADZAJACY)


class TerminTest(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_z_kryteriami()

    def test_zmiana_terminu_tworzy_zawiadomienie_i_odswieza_kopie(self):
        """Art. 81 ust. 8 u.s.c., § 8 rozp."""
        uslugi.zmien_termin(
            self.ocena, self.z.szef.uzytkownik, nowy_termin=date(2026, 11, 27),
            przyczyna="NIEOBECNOSC_OCENIAJACEGO", data=date(2025, 6, 11),
        )

        z_bazy = Ocena.objects.get(pk=self.ocena.pk)
        self.assertEqual(z_bazy.termin, date(2026, 11, 27))
        dokument = z_bazy.proces().dokumenty[-1]
        self.assertEqual((dokument.rodzaj, dokument.adresat), ("zawiadomienie o nowym terminie oceny", Rola.OCENIANY))

    def test_wniosek_ocenianego_czeka_na_rozpatrzenie_przez_oceniajacego(self):
        wniosek = uslugi.zloz_wniosek_o_zmiane_terminu(
            self.ocena, self.z.ola.uzytkownik, uzasadnienie="Planowany urlop.", data=date(2025, 6, 11)
        )
        self.assertEqual(wniosek.status, "oczekuje")

        uslugi.rozpatrz_wniosek_o_zmiane_terminu(
            self.ocena, self.z.szef.uzytkownik, uwzglednic=True, nowy_termin=date(2026, 12, 1), data=date(2025, 6, 12)
        )

        wniosek.refresh_from_db()
        self.assertEqual((wniosek.status, wniosek.data_rozpatrzenia), ("uwzględniony", date(2025, 6, 12)))
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).termin, date(2026, 12, 1))

    def test_odrzucenie_wniosku_nie_zmienia_terminu(self):
        uslugi.zloz_wniosek_o_zmiane_terminu(self.ocena, self.z.ola.uzytkownik, data=date(2025, 6, 11))

        uslugi.rozpatrz_wniosek_o_zmiane_terminu(
            self.ocena, self.z.szef.uzytkownik, uwzglednic=False, data=date(2025, 6, 12)
        )

        self.assertEqual(self.ocena.wnioski_o_termin.get().status, "odrzucony")
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).termin, TERMIN)

    def test_wniosek_przed_uplywem_szesciu_miesiecy_jest_odrzucany_przez_rdzen(self):
        """Art. 81 ust. 8 in fine u.s.c."""
        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.zloz_wniosek_o_zmiane_terminu(self.ocena, self.z.ola.uzytkownik, data=date(2025, 1, 10))
        self.assertEqual(kontekst.exception.kody, {"ZMIANA_TERMINU_ZBYT_WCZESNIE"})
        self.assertFalse(self.ocena.wnioski_o_termin.exists())

    def test_nieobecnosc_wprowadzaja_kadry(self):
        with self.assertRaises(BladUprawnien):
            uslugi.dodaj_nieobecnosc(self.z.ola, self.z.szef.uzytkownik, od=date(2025, 3, 1), do=date(2025, 5, 31))
        uslugi.dodaj_nieobecnosc(self.z.ola, self.z.kadry.uzytkownik, od=date(2025, 3, 1), do=date(2025, 5, 31))
        self.assertEqual(Nieobecnosc.objects.filter(pracownik=self.z.ola).count(), 1)

    def test_nieobecnosc_z_data_koncowa_przed_poczatkowa_jest_odrzucana(self):
        with self.assertRaises(BladWalidacji):
            uslugi.dodaj_nieobecnosc(self.z.ola, self.z.kadry.uzytkownik, od=date(2025, 5, 31), do=date(2025, 3, 1))


class SprzeciwTest(TestCase):
    """Art. 83 u.s.c.: sprzeciw w 7 dni od zapoznania, rozpatrzenie w 14 dni, zmiana albo ponowne sporządzenie."""

    def setUp(self):
        self.z = Zespol()
        self.ocena = self.z.ocena_zakonczona(punkty=1)  # zapoznanie 4.11.2026 -> sprzeciw do 12.11.2026

    def test_sprzeciw_wnosi_oceniany_po_zapoznaniu_z_ocena(self):
        with self.assertRaises(BladUprawnien):
            uslugi.wnies_sprzeciw(self.ocena, self.z.szef.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 10))

        sprzeciw = uslugi.wnies_sprzeciw(
            self.ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 12)
        )

        self.assertEqual((sprzeciw.data_wniesienia, sprzeciw.po_terminie), (date(2026, 11, 12), False))
        self.assertIn("wniesienie sprzeciwu", czynnosci(self.ocena))

    def test_sprzeciw_po_terminie_jest_rejestrowany_z_oznaczeniem(self):
        """Decyzja projektowa: system nie rozstrzyga o skutkach uchybienia terminu - rejestruje i oznacza."""
        sprzeciw = uslugi.wnies_sprzeciw(
            self.ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 13)
        )
        self.assertTrue(sprzeciw.po_terminie)

    def test_pusty_sprzeciw_i_drugi_sprzeciw_w_toku_sa_odrzucane(self):
        with self.assertRaises(BladWalidacji):
            uslugi.wnies_sprzeciw(self.ocena, self.z.ola.uzytkownik, tresc="  ", data=date(2026, 11, 10))
        uslugi.wnies_sprzeciw(self.ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 10))
        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.wnies_sprzeciw(self.ocena, self.z.ola.uzytkownik, tresc="Ponownie.", data=date(2026, 11, 11))
        self.assertEqual(kontekst.exception.kody, {"SPRZECIW_W_TOKU"})

    def test_sprzeciwu_nie_wnosi_sie_przed_zapoznaniem_z_ocena(self):
        z = Zespol.__new__(Zespol)
        z.kadry, z.szef = self.z.kadry, self.z.szef
        z.ola = pracownik("jan", przelozony=z.szef)
        ocena = z.ocena_do_zapoznania()
        with self.assertRaises(BladEtapu):
            uslugi.wnies_sprzeciw(ocena, z.ola.uzytkownik, tresc="Nie zgadzam się.", data=DZIEN_OCENY)

    def test_uwzglednienie_przez_ponowne_sporzadzenie_cofa_proces_do_oceniania(self):
        sprzeciw = uslugi.wnies_sprzeciw(
            self.ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 10)
        )

        uslugi.rozpatrz_sprzeciw(
            self.ocena, dyrektor_generalny().uzytkownik, rozstrzygniecie="ponowne_sporzadzenie",
            uzasadnienie="Ocena nie odnosi się do kryteriów.", data=date(2026, 11, 20),
        )

        sprzeciw.refresh_from_db()
        self.assertEqual((sprzeciw.rozstrzygniecie, sprzeciw.data_rozstrzygniecia), ("ponowne_sporzadzenie", date(2026, 11, 20)))
        z_bazy = Ocena.objects.get(pk=self.ocena.pk)
        self.assertEqual((z_bazy.etap, z_bazy.wynik), ("OCENIANIE", ""))
        self.assertEqual(len(z_bazy.proces().oceny_anulowane), 1)

    def test_uwzglednienie_przez_zmiane_oceny_przelicza_wynik(self):
        uslugi.wnies_sprzeciw(self.ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 10))

        uslugi.rozpatrz_sprzeciw(
            self.ocena, dyrektor_generalny().uzytkownik, rozstrzygniecie="zmiana", nowe_oceny=self.z.oceny(5),
            data=date(2026, 11, 20),
        )

        z_bazy = Ocena.objects.get(pk=self.ocena.pk)
        self.assertEqual((z_bazy.etap, z_bazy.wynik, z_bazy.poziom), ("ZAKONCZONA", "POZYTYWNA", "na poziomie oczekiwań"))

    def test_nieuwzglednienie_zostawia_ocene_bez_zmian(self):
        sprzeciw = uslugi.wnies_sprzeciw(
            self.ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 10)
        )

        uslugi.rozpatrz_sprzeciw(
            self.ocena, dyrektor_generalny().uzytkownik, rozstrzygniecie="nieuwzgledniony", data=date(2026, 11, 20)
        )

        sprzeciw.refresh_from_db()
        self.assertEqual(sprzeciw.rozstrzygniecie, "nieuwzgledniony")
        self.assertEqual(Ocena.objects.get(pk=self.ocena.pk).wynik, "NEGATYWNA")

    def test_sprzeciwu_nie_rozstrzyga_przelozony_komorka_kadr_ani_oceniany(self):
        """Art. 83 ust. 1 u.s.c.: sprzeciw służy do dyrektora generalnego urzędu - i to on rozstrzyga go w systemie."""
        uslugi.wnies_sprzeciw(self.ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 10))
        for osoba in (self.z.szef, self.z.kadry, self.z.ola):
            with self.assertRaises(BladUprawnien):
                uslugi.rozpatrz_sprzeciw(
                    self.ocena, osoba.uzytkownik, rozstrzygniecie="nieuwzgledniony", data=date(2026, 11, 20)
                )
        self.assertEqual(Sprzeciw.objects.get().rozstrzygniecie, "")


class KolejnyCyklTest(TestCase):
    def setUp(self):
        self.z = Zespol()

    def test_po_ocenie_pozytywnej_nowy_cykl_zaczyna_sie_w_dniu_jej_sporzadzenia(self):
        """§ 7 pkt 1 rozp.: 30 dni od sporządzenia poprzedniej oceny."""
        ocena = self.z.ocena_zakonczona()

        nowa = uslugi.rozpocznij_kolejny_cykl(ocena, self.z.kadry.uzytkownik, data=date(2026, 11, 5))

        self.assertEqual((nowa.poprzednia, nowa.poczatek_cyklu, nowa.po_negatywnej), (ocena, DZIEN_OCENY, False))
        self.assertEqual(nowa.etap, "KRYTERIA_DO_WYZNACZENIA")
        self.assertIn("rozpoczęcie kolejnego cyklu", czynnosci(ocena))

    def test_po_ocenie_negatywnej_nowy_cykl_jest_oznaczony(self):
        """§ 7 pkt 2 rozp. i art. 81 ust. 9 u.s.c."""
        ocena = self.z.ocena_zakonczona(punkty=1)
        nowa = uslugi.rozpocznij_kolejny_cykl(ocena, self.z.kadry.uzytkownik, data=date(2026, 11, 5))
        self.assertTrue(nowa.po_negatywnej)

    def test_kolejny_cykl_tylko_raz_i_tylko_po_zakonczonej_ocenie(self):
        w_toku = self.z.ocena_z_kryteriami()
        with self.assertRaises(BladEtapu):
            uslugi.rozpocznij_kolejny_cykl(w_toku, self.z.kadry.uzytkownik, data=date(2026, 11, 5))

    def test_drugi_kolejny_cykl_jest_odrzucany(self):
        ocena = self.z.ocena_zakonczona()
        uslugi.rozpocznij_kolejny_cykl(ocena, self.z.kadry.uzytkownik, data=date(2026, 11, 5))
        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.rozpocznij_kolejny_cykl(ocena, self.z.kadry.uzytkownik, data=date(2026, 11, 6))
        self.assertEqual(kontekst.exception.kody, {"KOLEJNY_CYKL_ISTNIEJE"})

    def test_kolejnego_cyklu_nie_rozpoczyna_sie_przy_nierozpatrzonym_sprzeciwie(self):
        ocena = self.z.ocena_zakonczona(punkty=1)
        uslugi.wnies_sprzeciw(ocena, self.z.ola.uzytkownik, tresc="Nie zgadzam się.", data=date(2026, 11, 10))
        with self.assertRaises(BladWalidacji) as kontekst:
            uslugi.rozpocznij_kolejny_cykl(ocena, self.z.kadry.uzytkownik, data=date(2026, 11, 11))
        self.assertEqual(kontekst.exception.kody, {"SPRZECIW_W_TOKU"})
