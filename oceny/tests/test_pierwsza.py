"""Pierwsza ocena i dostęp po umowie - przypadki z perspektywy użytkowników."""
from datetime import date

from django.test import override_settings
from django.urls import reverse

from oceny.models import Pracownik
from .test_kadry_pracownik import NOWY, LISTA, Podstawa, dane
from .test_widoki import klient
from .dostepnosc_html import bledy_dostepnosci


@override_settings(ASYSTENT_DZIS="2026-01-01")
class PierwszaTest(Podstawa):
    def dodaj(self, **pola):
        parametry = dict(rodzaj_zatrudnienia="umowa_na_czas_okreslony", data_zatrudnienia="2026-01-01")
        parametry.update(pola)
        self.assertEqual(self.kadry.post(NOWY, dane(**parametry)).status_code, 302)
        return Pracownik.objects.get(nazwisko=parametry.get("nazwisko", "Nowicki"))

    def test_pierwsze_zatrudnienie_otwiera_odrebny_arkusz(self):
        osoba = self.dodaj()
        self.assertContains(self.kadry.get(LISTA), "Pierwsza ocena w służbie cywilnej")
        self.assertEqual(osoba.umowa.koniec, date(2026, 12, 31))
        self.assertEqual(osoba.umowa.pierwsza.szef, self.z.szef)
        self.assertEqual(osoba.uzytkownik.username, "jan.nowicki")
        self.assertFalse(osoba.oceny.exists())

    def test_dostep_do_ostatniego_dnia_i_odciecie_otwartej_sesji(self):
        osoba = self.dodaj()
        sesja = klient(osoba)
        with self.settings(ASYSTENT_DZIS="2026-12-31"):
            self.assertEqual(sesja.get("/").status_code, 200)
        with self.settings(ASYSTENT_DZIS="2027-01-01"):
            self.assertEqual(sesja.get("/").status_code, 302)
            osoba.uzytkownik.refresh_from_db()
            self.assertFalse(osoba.uzytkownik.is_active)

    def test_nowa_umowa_nie_zmienia_starej_przed_czasem(self):
        osoba = self.dodaj()
        adres = f"/kadry/umowa/{osoba.umowa.pk}/"
        dane_umowy = {"akcja": "stala", "potwierdzenie": "on", "data": "2027-01-01"}
        self.assertEqual(klient(self.z.obcy).post(adres, dane_umowy).status_code, 403)
        self.assertEqual(self.kadry.post(adres, dane_umowy).status_code, 302)
        osoba.refresh_from_db()
        self.assertEqual(osoba.rodzaj_zatrudnienia, "umowa_na_czas_okreslony")
        sesja = klient(osoba)
        with self.settings(ASYSTENT_DZIS="2027-01-01"):
            self.assertEqual(sesja.get("/").status_code, 200)
            osoba.refresh_from_db()
            self.assertEqual(osoba.rodzaj_zatrudnienia, "umowa_na_czas_nieokreslony")
            self.assertTrue(osoba.uzytkownik.is_active)
            self.assertEqual(osoba.umowa.koniec, date(2026, 12, 31))

    def test_wyjatki_i_udokumentowane_przedluzenie(self):
        for tryb, podlega in (("inna", False), ("ksap", False), ("zastepstwo", False), ("zastepstwo_ocena", True)):
            osoba = self.dodaj(nazwisko=f"Test{tryb}", rodzaj_zatrudnienia=f"terminowa_{tryb}", ustalenie="2026-01-01" if tryb == "zastepstwo_ocena" else "", koniec_umowy="" if tryb == "ksap" else "2026-12-31")
            self.assertEqual(hasattr(osoba.umowa, "pierwsza"), podlega)
        osoba = self.dodaj()
        adres = f"/kadry/umowa/{osoba.umowa.pk}/"
        self.assertEqual(self.kadry.post(adres, {"akcja": "przedluzenie", "data": "2027-04-15", "potwierdzenie": "on"}).status_code, 302)
        with self.settings(ASYSTENT_DZIS="2027-01-01"):
            self.assertEqual(klient(osoba).get("/").status_code, 200)
            osoba.umowa.refresh_from_db()
            self.assertEqual(osoba.umowa.koniec, date(2027, 4, 15))

    def przygotuj_arkusz(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef = klient(self.z.szef)
        self.assertContains(szef.get("/"), f'href="{adres}"')
        self.assertEqual(klient(self.z.obcy).get(adres).status_code, 403)
        dane_rozmowy = {"akcja": "wstepna", "od": "2026-09-03", "do": "2026-09-20", "rozmowa": "2026-01-01"}
        self.assertEqual(klient(osoba).post(adres, dane_rozmowy).status_code, 403)
        self.assertEqual(szef.post(adres, dane_rozmowy).status_code, 302)
        self.assertEqual(bledy_dostepnosci(szef.get(adres).content.decode()), [])
        return osoba, adres, szef

    def ocena_dane(self, **inne):
        wynik = {f"pkt{i}": 5 for i in range(5)}
        wynik.update(akcja="ocena", egzamin="tak", porozumienie="on", rozmowa="2026-09-21", **inne)
        return wynik

    def test_pozytywny_wynik_i_wniosek_nie_sa_nowa_umowa(self):
        from .pomocnicze import dyrektor_generalny
        osoba, adres, szef = self.przygotuj_arkusz()
        raport = {"akcja": "raport", "tresc": "Zadania, usprawnienia, wnioski i zdobyta wiedza.", "okres": "on"}
        with self.settings(ASYSTENT_DZIS="2026-09-03"):
            self.assertEqual(klient(osoba).post(adres, raport).status_code, 302)
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertEqual(szef.post(adres, self.ocena_dane()).status_code, 302)
            self.assertContains(klient(osoba).get(adres), "Pozytywna")
            self.assertEqual(szef.post(adres, {"akcja": "wniosek", "wybor": "stala"}).status_code, 302)
            dyrektor = klient(dyrektor_generalny())
            self.assertContains(dyrektor.get("/"), f'href="{adres}"')
            self.assertContains(dyrektor.get(adres), "Zawarcie umowy na czas nieokreślony")
        osoba.refresh_from_db()
        self.assertIsNone(osoba.umowa.stala_od)

    def test_brak_sprawozdania_nie_blokuje_negatywnej_ale_wymaga_uzasadnienia(self):
        osoba, adres, szef = self.przygotuj_arkusz()
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertContains(szef.post(adres, self.ocena_dane()), "Uzasadnij")
            self.assertEqual(szef.post(adres, self.ocena_dane(uzasadnienie="Nie złożono sprawozdania.")).status_code, 302)
            self.assertContains(klient(osoba).get(adres), "Negatywna")
            self.assertEqual(szef.post(adres, {"akcja": "wniosek", "wybor": "rozwiazanie"}).status_code, 302)
            self.assertTrue(osoba.uzytkownik.is_active)

    def test_zastepstwo_z_ocena_wymaga_daty_ustalenia_stron(self):
        odp = self.kadry.post(NOWY, dane(rodzaj_zatrudnienia="terminowa_zastepstwo_ocena", koniec_umowy="2027-12-31"))
        self.assertContains(odp, "Podaj datę ustalenia")

    def test_brak_obsady_mozna_uzupelnic_bez_nadpisania_przypisanych(self):
        from oceny.models import Wydzial
        from oceny.podleglosc import ustaw_obsade
        wydzial = Wydzial.objects.create(nazwa="Nowa komórka")
        ocena = self.dodaj(wydzial=wydzial.pk).umowa.pierwsza
        self.assertIsNone(ocena.szef_id)
        ustaw_obsade(wydzial, self.z.szef, None)
        ocena.refresh_from_db()
        self.assertEqual(ocena.szef, self.z.szef)
        ustaw_obsade(wydzial, self.z.obcy, None)
        ocena.refresh_from_db()
        self.assertEqual(ocena.kierujacy, self.z.szef)

    def test_koniec_miesiaca_i_okno_oceny(self):
        osoba = self.dodaj(data_zatrudnienia="2024-02-29")
        self.assertEqual(osoba.umowa.koniec, date(2025, 2, 28))
        with self.settings(ASYSTENT_DZIS="2024-09-01"):
            strona = klient(self.z.szef).get(f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/")
            self.assertContains(strona, "29.10.2024 - 28.01.2025")

    def test_nie_mozna_wystawic_po_terminie_ani_wymusic_wyniku(self):
        osoba, adres, szef = self.przygotuj_arkusz()
        for dzien in ("2026-08-31", "2026-12-01"):
            with self.settings(ASYSTENT_DZIS=dzien):
                pola = self.ocena_dane(uzasadnienie="Brak sprawozdania")
                pola.update(rozmowa=dzien, wynik="Pozytywna")
                self.assertEqual(szef.post(adres, pola).status_code, 200)
                osoba.umowa.pierwsza.refresh_from_db()
                self.assertNotIn("ocena", osoba.umowa.pierwsza.dane)

    def test_przedluzenie_nie_wymazuje_innej_blokady(self):
        osoba = self.dodaj()
        osoba.uzytkownik.is_active = False
        osoba.uzytkownik.save(update_fields=["is_active"])
        self.kadry.post(f"/kadry/umowa/{osoba.umowa.pk}/", {"akcja":"stala", "data":"2027-01-01", "potwierdzenie":"on"})
        with self.settings(ASYSTENT_DZIS="2027-01-01"):
            self.kadry.get(LISTA)
            osoba.uzytkownik.refresh_from_db()
            self.assertFalse(osoba.uzytkownik.is_active)

    def test_nie_trzeba_wybierac_arkusza_okresowego_dla_umowy_terminowej(self):
        self.assertTrue(self.dodaj(arkusz="").umowa.pierwsza.pk)

    def test_po_przedluzeniu_szef_moze_wyznaczyc_nowy_termin_sprawozdania(self):
        osoba, adres, szef = self.przygotuj_arkusz()
        self.kadry.post(f"/kadry/umowa/{osoba.umowa.pk}/", {"akcja": "przedluzenie", "data": "2027-04-15", "potwierdzenie": "on"})
        pola = {"akcja": "termin", "od": "2027-01-01", "do": "2027-01-10", "pismo": "on"}
        self.assertEqual(szef.post(adres, pola).status_code, 302)
        osoba.umowa.pierwsza.refresh_from_db()
        self.assertEqual(osoba.umowa.pierwsza.dane["wstepna"]["do"], "2027-01-10")

    def test_punkty_egzamin_i_warunki_laczne(self):
        from oceny.pierwsza import wynik_pozytywny
        for pkt, egzamin, na_czas, wynik in (([3,5,5,5,7], "tak", True, True), ([3,3,7,7,7], "tak", True, False),
                ([3,5,5,5,5], "tak", True, False), ([7]*5, "nie", True, False), ([7]*5, "zastepstwo", False, False), ([5]*5, "ksap", True, True)):
            self.assertEqual(wynik_pozytywny(pkt, egzamin, na_czas), wynik)

    def test_poczatek_okresowej_po_kontynuacji_nie_siega_do_umowy_terminowej(self):
        from oceny import uslugi
        osoba = self.dodaj()
        self.kadry.post(f"/kadry/umowa/{osoba.umowa.pk}/", {"akcja":"stala", "data":"2027-01-01", "potwierdzenie":"on"})
        with self.settings(ASYSTENT_DZIS="2027-01-01"):
            self.kadry.get(LISTA)
            osoba.refresh_from_db()
            okresowa = osoba.oceny.get()
            self.assertEqual(okresowa.poczatek_cyklu, date(2027,1,1))

    def test_jeden_wybor_umowy_bez_dodatkowego_pola(self):
        formularz = self.kadry.get(NOWY)
        self.assertNotContains(formularz, 'name="kwalifikacja"')
        self.assertContains(formularz, "12 miesięcy")
        self.assertEqual(formularz.context["formularz"].initial["rodzaj_zatrudnienia"], "umowa_na_czas_okreslony")
        self.assertEqual(self.dodaj().umowa.kwalifikacja, "pierwsza")

    def test_stala_automatycznie_raz_po_dodaniu_i_edycji(self):
        osoba = self.dodaj(rodzaj_zatrudnienia="umowa_na_czas_nieokreslony")
        pierwsza = osoba.oceny.get()
        self.assertEqual(pierwsza.oceniajacy, self.z.szef)
        self.kadry.post(self.edycja(osoba), dane(data_zatrudnienia="2026-01-01"))
        self.assertEqual(osoba.oceny.get().pk, pierwsza.pk)
        self.assertNotContains(self.kadry.get(LISTA), "Rozpocznij cykl oceny")

    def test_korekta_zostawia_stary_arkusz_poza_zadaniami(self):
        from oceny.korekta import skoryguj
        from oceny.models import Ocena, UmowaTerminowa
        osoba = self.z.ola
        osoba.data_zatrudnienia = date(2026, 1, 1)
        osoba.rodzaj_zatrudnienia = "umowa_na_czas_okreslony"
        osoba.save()
        stara = Ocena.utworz(oceniany=osoba, oceniajacy=self.z.szef, poczatek_cyklu=osoba.data_zatrudnienia)
        stara.szkic = {"uwaga": "w toku"}
        stara.save()
        with self.assertRaises(ValueError):
            skoryguj(osoba.pk, stara.pk)
        self.assertFalse(UmowaTerminowa.objects.filter(osoba=osoba).exists())
        stara.szkic = None
        stara.save()
        nowa = skoryguj(osoba.pk, stara.pk)
        self.assertEqual(skoryguj(osoba.pk, stara.pk), nowa)
        self.assertFalse(osoba.oceny.exists())
        self.assertEqual(Ocena.wszystkie.get(pk=stara.pk).stan, stara.stan)
        self.assertTrue(stara.zdarzenia.filter(czynnosc="korekta rodzaju oceny").exists())
        sesja = klient(osoba)
        self.assertContains(sesja.get("/"), f'/pierwsza-ocena/{nowa.pk}/')
        self.assertNotContains(sesja.get("/"), f'href="/oceny/{stara.pk}/"')
        self.assertEqual(sesja.get(f'/oceny/{stara.pk}/').status_code, 404)

    def test_dwa_urzedowe_wzory_tylko_dla_uprawnionych(self):
        from io import BytesIO
        from zipfile import ZipFile
        from lxml import etree
        osoba, adres, szef = self.przygotuj_arkusz()
        for typ, nr in (("arkusz", 2), ("sprawozdanie", 3)):
            url = adres + typ + ".docx"
            self.assertContains(klient(osoba).get(adres), url)
            self.assertEqual(klient(self.z.obcy).get(url).status_code, 404)
            r = szef.get(url)
            self.assertEqual(r.status_code, 200)
            with ZipFile(BytesIO(r.content)) as plik:
                self.assertIn('word/footnotes.xml', plik.namelist())
                xml = etree.fromstring(plik.read('word/document.xml'))
                tekst = ''.join(xml.itertext())
            for pole in (f'Załącznik nr {nr}', osoba.nazwisko, "03.09.2026", "20.09.2026", "podpis ocenianego"):
                self.assertIn(pole, tekst)

    def test_wynik_na_arkuszu_i_tresc_w_sprawozdaniu_bez_podpisu(self):
        from io import BytesIO
        from zipfile import ZipFile
        from docx.oxml import parse_xml
        osoba, adres, szef = self.przygotuj_arkusz()
        opis = "Rozwiązałem trudny problem.\nWdrożyłem usprawnienie."
        with self.settings(ASYSTENT_DZIS="2026-09-03"):
            r = klient(osoba).post(adres, {"akcja": "raport", "tresc": opis, "okres": "on"})
            self.assertEqual(r.status_code, 302)
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertEqual(szef.post(adres, self.ocena_dane(rozwoj="Nauka analizy danych.")).status_code, 302)
            for typ in ("arkusz", "sprawozdanie"):
                r = szef.get(adres + typ + ".docx")
                with ZipFile(BytesIO(r.content)) as z:
                    p = parse_xml(z.read("word/document.xml")).xpath(".//w:body//w:p")
                    tekst = lambda nr: "".join(p[nr].xpath(".//w:t/text()"))
                    if typ == "arkusz":
                        for i in (102, 106, 110, 114, 118, 126, 134, 140):
                            self.assertEqual(tekst(i), "X")
                        self.assertEqual(tekst(142), "")
                        self.assertEqual(tekst(164), "Nauka analizy danych.")
                        self.assertTrue(tekst(177).startswith("…"))
                    else:
                        self.assertIn("Wdrożyłem usprawnienie.", tekst(23))
                        self.assertTrue(tekst(26).startswith("…"))
