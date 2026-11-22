"""Pierwsza ocena i dostęp po umowie - przypadki z perspektywy użytkowników."""
import re
from datetime import date

from django.test import override_settings
from django.urls import reverse

from oceny.models import Pracownik
from .test_kadry_pracownik import NOWY, LISTA, Podstawa, dane
from .dostepnosc_html import bledy_dostepnosci, tytul_strony
from .test_widoki import klient


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
        raport = {"akcja": "raport", "zadania": "Realizacja zadań", "problemy": "Brak", "wiedza": "Nowe narzędzie", "wnioski": "Nowa instrukcja", "okres": "on"}
        with self.settings(ASYSTENT_DZIS="2026-09-03"):
            self.assertEqual(klient(osoba).post(adres, raport).status_code, 302)
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertEqual(szef.post(adres, self.ocena_dane()).status_code, 302)
            strona = klient(osoba).get(adres)
            for fragment in ('<div class="podglad wynik-pozytywna"><strong>Ocena POZYTYWNA</strong> - ocena łączna 5,0</div>',
                             "<strong>5</strong> - na poziomie oczekiwań", "Rozmowa oceniająca: 21.09.2026. Ocena dokonana: 21.09.2026."):
                self.assertContains(strona, fragment)
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
            self.assertContains(klient(osoba).get(adres), '<div class="podglad wynik-negatywna"><strong>Ocena NEGATYWNA</strong>')
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
            r = klient(osoba).post(adres, {"akcja": "raport", "zadania": opis, "problemy": "Brak", "wiedza": "Analiza", "wnioski": "Instrukcja", "okres": "on"})
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

    def test_pracownik_od_poczatku_przygotowuje_szkic_bez_skladania(self):
        from zipfile import ZipFile
        from io import BytesIO
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        pracownik, szef = klient(osoba), klient(self.z.szef)
        strona = pracownik.get(adres)
        self.assertContains(strona, "Zapisz szkic")
        self.assertNotContains(strona, 'value="raport"')
        pola = {"akcja": "szkic", "zadania": "Moja robocza treść"}
        self.assertEqual(pracownik.post(adres, pola).status_code, 302)
        self.assertContains(pracownik.get(adres), pola["zadania"])
        self.assertNotContains(szef.get(adres), pola["zadania"])
        self.assertEqual(szef.post(adres, pola).status_code, 403)
        self.assertEqual(pracownik.post(adres, {**pola, "akcja": "raport"}).status_code, 403)
        osoba.umowa.pierwsza.refresh_from_db()
        self.assertNotIn("raport", osoba.umowa.pierwsza.dane)
        with ZipFile(BytesIO(szef.get(adres + "sprawozdanie.docx").content)) as z:
            self.assertNotIn(pola["zadania"], z.read("word/document.xml").decode())

    def test_przygotowanie_szefa_i_poufna_obserwacja(self):
        from io import BytesIO
        from zipfile import ZipFile
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef, pracownik = klient(self.z.szef), klient(osoba)
        pola = {"akcja": "obserwacja", "element": "Komunikacja", "opis": "Fakt do rozmowy z zespołem"}
        self.assertContains(szef.get(adres), "Zapisz obserwację")
        self.assertEqual(pracownik.post(adres, pola).status_code, 403)
        self.assertEqual(szef.post(adres, pola).status_code, 302)
        self.assertContains(szef.get(adres), pola["opis"])
        self.assertNotContains(pracownik.get(adres), pola["opis"])
        for typ in ("arkusz", "sprawozdanie"):
            with ZipFile(BytesIO(pracownik.get(adres + typ + ".docx").content)) as z:
                self.assertNotIn(pola["opis"], z.read("word/document.xml").decode())
        egzamin = {"akcja": "egzamin", "wynik": "tak", "dzien_egzaminu": "2026-01-10"}
        self.assertEqual(pracownik.post(adres, egzamin).status_code, 403)
        self.assertContains(szef.post(adres, egzamin), "faktyczną datę")
        with self.settings(ASYSTENT_DZIS="2026-03-10"):
            self.assertEqual(szef.post(adres, egzamin).status_code, 302)
            self.assertContains(pracownik.get(adres), "Egzamin ze służby przygotowawczej: zaliczony")
            self.assertNotContains(pracownik.get(adres), 'value="obserwacja"')
            osoba.umowa.pierwsza.refresh_from_db()
            self.assertNotIn("ocena", osoba.umowa.pierwsza.dane)

    def test_rozpiska_wskazuje_osobe_i_nie_miesza_cykli(self):
        osoba = self.dodaj()
        strona = klient(osoba).get(f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/")
        for tekst in ('aria-label="Przebieg pierwszej oceny"', "Służba przygotowawcza", "Rozmowa wstępna", "wniosek do dyrektora generalnego"):
            self.assertContains(strona, tekst)
        self.assertEqual(bledy_dostepnosci(strona.content.decode()), [])
        self.assertNotContains(strona, 'name="kryterium_1"')

    def test_przed_wyznaczonym_terminem_jest_tylko_szkic(self):
        osoba, adres, szef = self.przygotuj_arkusz()
        with self.settings(ASYSTENT_DZIS="2026-09-02"):
            pracownik = klient(osoba)
            self.assertContains(pracownik.get(adres), "Zapisz szkic")
            self.assertNotContains(pracownik.get(adres), 'value="raport"')
            self.assertEqual(pracownik.post(adres, {"akcja": "raport"}).status_code, 403)
            self.assertNotContains(szef.get(adres), 'value="ocena"')

    # --- karta w układzie karty oceny okresowej ---

    WSTEPNA = {"akcja": "wstepna", "od": "2026-09-03", "do": "2026-09-20", "rozmowa": "2026-01-01"}

    def test_karta_ma_uklad_karty_oceny_okresowej(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        for sesja, rola, notatki in ((klient(self.z.szef), "bezpośredni przełożony, kierujący komórką", True), (klient(osoba), "oceniany", False)):
            html = sesja.get(adres).content.decode()
            for fragment in ('<p class="okruszki">', '<header class="naglowek-oceny">', "<h1>Jan Nowicki</h1>", '<dl class="metryczka">',
                             '<ol class="os-etapow" aria-label="Przebieg pierwszej oceny">', '<div class="uklad">', '<div class="kolumna-glowna">',
                             '<aside class="kolumna-boczna">', 'id="n-wstepna"', 'id="n-sprawozdanie"', 'id="n-terminy"', 'id="n-dokumenty"',
                             'id="n-dziennik"', f"<dd>{rola}</dd>"):
                self.assertIn(fragment, html)
            self.assertEqual('id="n-notatki"' in html, notatki)
            self.assertEqual(html.count('aria-current="step"'), 1)
            self.assertIn("Jan Nowicki", tytul_strony(html))
            self.assertEqual(bledy_dostepnosci(html), [])

    def test_pola_formularzy_maja_etykiety_nad_polem_jak_na_karcie_okresowej(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef = klient(self.z.szef).get(adres).content.decode()
        self.assertIn('<label for="id_wstepna_rozmowa">Data rozmowy wstępnej</label>', szef)
        pracownik = klient(osoba).get(adres).content.decode()
        self.assertIn('<label for="id_raport_zadania">Wykonane zadania</label>', pracownik)
        self.assertIn('class="przycisk przycisk-drugi" formnovalidate>Zapisz szkic</button>', pracownik)
        for html in (szef, pracownik):
            self.assertNotIn(":</label>", html)

    def test_os_etapow_pokazuje_biezacy_krok_na_kazdym_etapie(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef = klient(self.z.szef)

        def biezacy():
            kroki = re.findall(r'aria-current="step">([^<]+)</li>', szef.get(adres).content.decode())
            return kroki[0] if kroki else None

        self.assertEqual(biezacy(), "rozmowa wstępna")
        self.assertEqual(szef.post(adres, self.WSTEPNA).status_code, 302)
        self.assertEqual(biezacy(), "sprawozdanie ocenianego")
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertEqual(biezacy(), "rozmowa oceniająca i pierwsza ocena")
            self.assertEqual(szef.post(adres, self.ocena_dane(uzasadnienie="Nie złożono sprawozdania.")).status_code, 302)
            self.assertEqual(biezacy(), "wniosek do dyrektora generalnego")
            self.assertEqual(szef.post(adres, {"akcja": "wniosek", "wybor": "rozwiazanie"}).status_code, 302)
            self.assertIsNone(biezacy())
            self.assertEqual(szef.get(adres).content.decode().count('<li class="krok krok-zrobiony">'), 4)

    def test_do_zrobienia_widzi_tylko_osoba_ktora_ma_czynnosc(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef, pracownik = klient(self.z.szef), klient(osoba)
        self.assertContains(szef.get(adres), "<strong>Przeprowadź rozmowę wstępną i wyznacz termin sprawozdania</strong> - do 22.01.2026")
        self.assertNotContains(pracownik.get(adres), 'id="n-zadania"')
        self.assertEqual(szef.post(adres, self.WSTEPNA).status_code, 302)
        self.assertNotContains(szef.get(adres), 'id="n-zadania"')
        self.assertContains(pracownik.get(adres), "<strong>Złóż sprawozdanie</strong> - do 20.09.2026")
        with self.settings(ASYSTENT_DZIS="2026-12-01"):  # okres oceny minął: zadania, którego nie da się wykonać, nie ma
            self.assertNotContains(pracownik.get(adres), 'id="n-zadania"')
            self.assertContains(szef.get(adres), "Okres dokonania pierwszej oceny upłynął 30.11.2026")
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertContains(pracownik.get(adres), "<strong>Złóż sprawozdanie</strong> - do 20.09.2026")  # po terminie, ale jeszcze można
            self.assertContains(szef.get(adres), "<strong>Przeprowadź rozmowę oceniającą i dokonaj pierwszej oceny</strong> - do 30.11.2026")
            self.assertEqual(szef.post(adres, self.ocena_dane(uzasadnienie="Nie złożono sprawozdania.")).status_code, 302)
            self.assertContains(szef.get(adres), "<strong>Złóż wniosek do dyrektora generalnego</strong>")
            self.assertNotContains(pracownik.get(adres), 'id="n-zadania"')

    def test_oceny_czastkowe_wybiera_sie_w_tabeli_jak_na_karcie_okresowej(self):
        from oceny.pierwsza import ELEMENTY
        osoba, adres, szef = self.przygotuj_arkusz()
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertEqual(szef.post(adres, {"akcja": "egzamin", "dzien_egzaminu": "2026-06-10", "wynik": "tak"}).status_code, 302)
            html = szef.get(adres).content.decode()
            self.assertIn("Zapisany wynik egzaminu: zaliczony (10.06.2026). Wybór musi mu odpowiadać", html)
            self.assertIn('<option value="tak" selected>Zaliczony</option>', html)
            self.assertIn('<table class="tabela tabela-ocen">', html)
            self.assertEqual(html.count('type="radio"'), 15)
            self.assertIn('<input type="radio" name="pkt0" value="3" aria-label="Rzetelność: 3 - poniżej oczekiwań"', html)
            self.assertNotIn('<select name="pkt0"', html)
            self.assertEqual(bledy_dostepnosci(html), [])
            odrzucona = szef.post(adres, self.ocena_dane())
            self.assertContains(odrzucona, "Uzasadnij")
            self.assertContains(odrzucona, "Nie zapisano. Popraw błędy wskazane w formularzu.")
            self.assertContains(odrzucona, '<li id="id_ocena_uzasadnienie_error">Uzasadnienie przyznanej oceny: Uzasadnij ocenę negatywną.</li>')
            for numer, nazwa in enumerate(ELEMENTY):
                self.assertContains(odrzucona, f'name="pkt{numer}" value="5" aria-label="{nazwa}: 5 - na poziomie oczekiwań" checked')
            self.assertEqual(bledy_dostepnosci(odrzucona.content.decode()), [])

    def test_terminy_i_historia_sa_w_kolumnie_bocznej_bez_prywatnych_wpisow(self):
        osoba, adres, szef = self.przygotuj_arkusz()
        self.assertEqual(szef.post(adres, {"akcja": "obserwacja", "element": "Komunikacja", "opis": "Fakt do rozmowy"}).status_code, 302)
        for sesja in (szef, klient(osoba)):
            html = sesja.get(adres).content.decode()
            self.assertIn('<aside class="kolumna-boczna">', html)
            boczna = html[html.index('<aside class="kolumna-boczna">'):]
            boczna = boczna[:boczna.index("</aside>")]
            for fragment in ('<li class="termin termin-wykonane">', '<span class="termin-data">01.01.2026</span>', "Sprawozdanie - najpóźniej",
                             '<span class="termin-data">20.09.2026</span>', "Pierwsza ocena - najpóźniej", '<span class="termin-data">30.11.2026</span>'):
                self.assertIn(fragment, boczna)
            daty = [date(int(rok), int(miesiac), int(dzien)) for dzien, miesiac, rok in
                    re.findall(r'<span class="termin-data">(\d\d)\.(\d\d)\.(\d{4})</span>\s*<span class="termin-nazwa">', boczna)]
            self.assertGreaterEqual(len(daty), 5)
            self.assertEqual(daty, sorted(daty))  # terminy w kolejności kalendarzowej
            for nazwa in ("Arkusz pierwszej oceny - PDF do podpisu", "Arkusz pierwszej oceny - DOCX", "Sprawozdanie ocenianego - PDF do podpisu", "Sprawozdanie ocenianego - DOCX"):
                self.assertIn(f'aria-label="{nazwa}"', boczna)
            dziennik = boczna[boczna.index('id="n-dziennik"'):]
            self.assertIn("zapisanie rozmowy wstępnej", dziennik)
            self.assertNotIn("obserwac", dziennik.lower())
            self.assertEqual(bledy_dostepnosci(html), [])
        pracownik = klient(osoba).get(adres)
        self.assertNotContains(pracownik, "Fakt do rozmowy")
        self.assertNotContains(pracownik, "2026-09-")  # daty w treści karty mają postać dd.mm.rrrr

    def test_dyrektor_po_wniosku_widzi_zamknieta_karte_bez_notatek_i_formularzy(self):
        from .pomocnicze import dyrektor_generalny
        osoba, adres, szef = self.przygotuj_arkusz()
        self.assertEqual(szef.post(adres, {"akcja": "obserwacja", "element": "Komunikacja", "opis": "Fakt do rozmowy"}).status_code, 302)
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertEqual(klient(dyrektor_generalny()).get(adres).status_code, 403)  # przed wnioskiem sprawa nie jest u dyrektora
            self.assertEqual(szef.post(adres, self.ocena_dane(uzasadnienie="Nie złożono sprawozdania.")).status_code, 302)
            self.assertEqual(szef.post(adres, {"akcja": "wniosek", "wybor": "brak"}).status_code, 302)
            html = klient(dyrektor_generalny()).get(adres).content.decode()
        for fragment in ("<dd>dyrektor generalny</dd>", '<div class="podglad wynik-negatywna"><strong>Ocena NEGATYWNA</strong>',
                         "Niezawieranie umowy na czas nieokreślony", "<h3>Uzasadnienie</h3>", "Sprawozdania nie złożono przed dokonaniem oceny."):
            self.assertIn(fragment, html)
        for brak in ('id="n-notatki"', "Fakt do rozmowy", 'name="akcja"', 'aria-current="step"', 'id="n-zadania"'):
            self.assertNotIn(brak, html)
        self.assertEqual(html.count('<li class="krok krok-zrobiony">'), 4)
        self.assertEqual(bledy_dostepnosci(html), [])

    # --- błąd formularza nie może kończyć się awarią (zgłoszenie: data rozmowy wstępnej późniejsza niż dziś) ---

    def test_przyszla_data_rozmowy_wstepnej_to_blad_formularza_a_nie_awaria(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef = klient(self.z.szef)
        szef.raise_request_exception = False  # jak w przeglądarce: wyjątek w widoku to odpowiedź 500
        odpowiedz = szef.post(adres, {**self.WSTEPNA, "rozmowa": "2026-01-02"})  # dzień po „dziś” z ustawień testu
        self.assertEqual(odpowiedz.status_code, 200)
        self.assertContains(odpowiedz, '<li id="id_wstepna_rozmowa_error">Data rozmowy wstępnej:')
        self.assertContains(odpowiedz, 'name="rozmowa" value="2026-01-02"')  # wpisana wartość zostaje do poprawienia
        osoba.umowa.pierwsza.refresh_from_db()
        self.assertNotIn("wstepna", osoba.umowa.pierwsza.dane)

    def test_wynik_egzaminu_niezgodny_z_zapisem_to_blad_formularza_a_nie_awaria(self):
        osoba, adres, szef = self.przygotuj_arkusz()
        szef.raise_request_exception = False
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertEqual(szef.post(adres, {"akcja": "egzamin", "dzien_egzaminu": "2026-06-10", "wynik": "tak"}).status_code, 302)
            odpowiedz = szef.post(adres, {**self.ocena_dane(uzasadnienie="Egzamin niezaliczony."), "egzamin": "nie"})
            self.assertEqual(odpowiedz.status_code, 200)
            self.assertContains(odpowiedz, '<li id="id_ocena_egzamin_error">Egzamin ze służby przygotowawczej: Wynik musi odpowiadać zapisowi egzaminu.')
        osoba.umowa.pierwsza.refresh_from_db()
        self.assertNotIn("ocena", osoba.umowa.pierwsza.dane)

    def test_zadna_kombinacja_dat_i_wyborow_nie_konczy_sie_awaria(self):
        from itertools import product

        from django.db import transaction

        osoba, adres, szef = self.przygotuj_arkusz()  # rozmowa wstępna zapisana, termin 03.09-20.09.2026
        nowa = self.dodaj(imie="Ewa", nazwisko="Testowa")  # sprawa przed rozmową wstępną
        adres_nowej = f"/pierwsza-ocena/{nowa.umowa.pierwsza.pk}/"
        szef.raise_request_exception = False
        daty = ("2025-12-31", "2026-01-01", "2026-01-02", "2026-08-31", "2026-09-01", "2026-09-20", "2026-09-21", "2026-09-22",
                "2026-11-30", "2026-12-01", "2026-12-31", "2027-01-01")
        proby = [(adres_nowej, "2026-01-01", {"akcja": "wstepna", "rozmowa": rozmowa, "od": od, "do": do})
                 for rozmowa, od, do in product(daty, ("2026-08-31", "2026-09-01", "2026-09-20", "2026-12-01"), ("2026-09-01", "2026-11-30", "2026-12-01"))]
        proby += [(adres, "2026-09-10", {"akcja": "termin", "od": od, "do": do, "pismo": "on"}) for od, do in product(daty, daty[3:])]
        proby += [(adres, "2026-09-10", {"akcja": "egzamin", "dzien_egzaminu": data, "wynik": "tak"}) for data in daty]
        for zapisany_egzamin in (None, "tak", "nie"):
            for rozmowa, egzamin, punkty, uzasadnienie, rozwoj in product(daty[5:9], ("tak", "nie", "ksap", "wyzsze"), ((5,) * 5, (3, 3, 5, 5, 7)), ("", "Opis"), ("", "Kurs")):
                pola = {"akcja": "ocena", "rozmowa": rozmowa, "egzamin": egzamin, "porozumienie": "on", "uzasadnienie": uzasadnienie, "rozwoj": rozwoj}
                pola.update({f"pkt{numer}": wartosc for numer, wartosc in enumerate(punkty)})
                proby.append((adres, "2026-09-21", pola, zapisany_egzamin))
        self.assertGreater(len(proby), 600)
        for adres_proby, dzien, pola, *egzamin in proby:
            punkt = transaction.savepoint()  # każda próba na tym samym stanie sprawy
            with self.settings(ASYSTENT_DZIS=dzien):
                if egzamin and egzamin[0]:
                    self.assertEqual(szef.post(adres_proby, {"akcja": "egzamin", "dzien_egzaminu": "2026-06-10", "wynik": egzamin[0]}).status_code, 302)
                kod = szef.post(adres_proby, pola).status_code
            transaction.savepoint_rollback(punkt)
            if kod not in (200, 302):
                self.fail(f"odpowiedź {kod} dla {pola} w dniu {dzien} (zapisany egzamin: {egzamin})")

    def test_bledy_rozmowy_wstepnej_mowia_co_poprawic(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef = klient(self.z.szef)
        with self.settings(ASYSTENT_DZIS="2026-01-10"):
            jutro = szef.post(adres, {**self.WSTEPNA, "rozmowa": "2026-01-11"})
            self.assertContains(jutro, "Data rozmowy wstępnej: Podaj dzień, w którym rozmowa się odbyła: od 01.01.2026 do 10.01.2026. "
                                       "Rozmowy nie zapisuje się z wyprzedzeniem.")
            # błędna data rozmowy nie dokłada wtórnego błędu terminu sprawozdania
            self.assertNotContains(jutro, "id_wstepna_od_error")
            self.assertNotContains(jutro, "id_wstepna_do_error")
            self.assertEqual(bledy_dostepnosci(jutro.content.decode()), [])
        with self.settings(ASYSTENT_DZIS="2026-09-10"):
            przed_rozmowa = szef.post(adres, {"akcja": "wstepna", "rozmowa": "2026-09-10", "od": "2026-09-03", "do": "2026-09-20"})
            self.assertContains(przed_rozmowa, '<li id="id_wstepna_od_error">Termin złożenia sprawozdania - od: '
                                               "Termin sprawozdania nie może zaczynać się przed rozmową wstępną (10.09.2026).</li>")
            self.assertNotContains(przed_rozmowa, "id_wstepna_do_error")
            poza_okresem = szef.post(adres, {"akcja": "wstepna", "rozmowa": "2026-01-05", "od": "2026-09-03", "do": "2026-12-01"})
            self.assertContains(poza_okresem, '<li id="id_wstepna_do_error">Termin złożenia sprawozdania - do: '
                                              "Termin sprawozdania musi mieścić się w okresie dokonania pierwszej oceny: 01.09.2026 - 30.11.2026.</li>")
            odwrocony = szef.post(adres, {"akcja": "wstepna", "rozmowa": "2026-01-05", "od": "2026-09-20", "do": "2026-09-03"})
            self.assertContains(odwrocony, "Termin złożenia sprawozdania - do: Koniec terminu nie może być wcześniejszy niż jego początek.")
        with self.settings(ASYSTENT_DZIS="2025-12-20"):  # przed dniem zatrudnienia nie ma jeszcze rozmowy do zapisania
            przed_zatrudnieniem = szef.post(adres, {**self.WSTEPNA, "rozmowa": "2025-12-20"})
            self.assertContains(przed_zatrudnieniem, "Data rozmowy wstępnej: Rozmowę wstępną można zapisać najwcześniej 01.01.2026.")
            self.assertNotContains(przed_zatrudnieniem, 'max="2025-12-20"')  # odwróconego zakresu przeglądarka nie dostaje
        osoba.umowa.pierwsza.refresh_from_db()
        self.assertNotIn("wstepna", osoba.umowa.pierwsza.dane)

    def test_pola_dat_podpowiadaja_dozwolony_zakres_a_spozniona_rozmowa_zapisuje_sie_z_domyslnym_terminem(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef = klient(self.z.szef)

        def pole(html, identyfikator):
            """Wartości (min, max, value) pola daty; None, gdy atrybutu nie ma."""
            znacznik = re.search(rf'<input [^>]*id="{identyfikator}"[^>]*>', html).group(0)
            atrybuty = dict(re.findall(r'(\w+)="([^"]*)"', znacznik))
            return atrybuty.get("min"), atrybuty.get("max"), atrybuty.get("value")

        with self.settings(ASYSTENT_DZIS="2026-09-10"):  # rozmowa wstępna spóźniona, trwa już okres oceny
            html = szef.get(adres).content.decode()
            # rozmowa: nie wcześniej niż zatrudnienie i nie później niż dziś; bez podpowiedzianej daty
            self.assertEqual(pole(html, "id_wstepna_rozmowa"), ("2026-01-01", "2026-09-10", None))
            # termin sprawozdania: w okresie oceny, a podpowiedź nie zaczyna się w przeszłości
            self.assertEqual(pole(html, "id_wstepna_od"), ("2026-09-01", "2026-11-29", "2026-09-10"))
            self.assertEqual(pole(html, "id_wstepna_do"), ("2026-09-01", "2026-11-29", "2026-11-29"))
            self.assertEqual(pole(html, "id_egzamin_dzien_egzaminu"), ("2026-01-01", "2026-09-10", None))
            self.assertEqual(bledy_dostepnosci(html), [])
            # przełożony wpisuje dzisiejszą rozmowę i zostawia podpowiedziany termin - zapis przechodzi
            zapis = {"akcja": "wstepna", "rozmowa": "2026-09-10", "od": "2026-09-10", "do": "2026-11-29"}
            self.assertEqual(szef.post(adres, zapis).status_code, 302)
            self.assertEqual(pole(szef.get(adres).content.decode(), "id_termin_od")[:2], ("2026-09-01", "2026-11-29"))
            raport = {"akcja": "raport", "zadania": "Zadania", "problemy": "Brak", "wiedza": "Narzędzia", "wnioski": "Instrukcja", "okres": "on"}
            self.assertEqual(klient(osoba).post(adres, raport).status_code, 302)
        with self.settings(ASYSTENT_DZIS="2026-09-15"):  # rozmowa oceniająca: w okresie oceny i nie później niż dziś
            self.assertEqual(pole(szef.get(adres).content.decode(), "id_ocena_rozmowa"), ("2026-09-01", "2026-09-15", "2026-09-15"))

    # --- pierwsza ocena na liście „Moje zadania”: z terminem, stanem i podstawą, jak zadania ocen okresowych ---

    @staticmethod
    def wiersz_zadania(html, adres):
        """Wiersz tabeli zadań z odnośnikiem do podanej karty; pusty tekst, gdy takiego zadania nie ma."""
        tabela = html[html.index('<table class="tabela">'):html.index("</table>")] if '<table class="tabela">' in html else ""
        return next((wiersz for wiersz in tabela.split("<tr>") if f'<a href="{adres}">' in wiersz), "")

    def test_zadania_pierwszej_oceny_sa_na_liscie_zadan_z_terminem_stanem_i_podstawa(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef, pracownik = klient(self.z.szef), klient(osoba)

        html = szef.get("/").content.decode()
        wiersz = self.wiersz_zadania(html, adres)
        for fragment in ('<span class="stan stan-w_terminie">zostało 21 dni</span>',
                         f'<a href="{adres}">Przeprowadź rozmowę wstępną i wyznacz termin sprawozdania</a>',
                         "<small>pierwsza ocena, w roli: bezpośredni przełożony</small>", "Jan Nowicki",
                         "<td>22.01.2026</td>", "<td>§ 3 i § 4 rozp. o pierwszej ocenie</td>"):
            self.assertIn(fragment, wiersz)
        self.assertEqual(bledy_dostepnosci(html), [])
        self.assertEqual(self.wiersz_zadania(pracownik.get("/").content.decode(), adres), "")  # czynność ma przełożony

        self.assertEqual(szef.post(adres, self.WSTEPNA).status_code, 302)
        self.assertEqual(self.wiersz_zadania(szef.get("/").content.decode(), adres), "")
        wiersz = self.wiersz_zadania(pracownik.get("/").content.decode(), adres)
        dni = (date(2026, 9, 20) - date(2026, 1, 1)).days
        for fragment in (f'<span class="stan stan-w_terminie">zostało {dni} dni</span>', f'<a href="{adres}">Złóż sprawozdanie</a>',
                         "<small>pierwsza ocena, w roli: oceniany</small>", "<td>20.09.2026</td>",
                         "<td>§ 4 ust. 1 i § 6 rozp. o pierwszej ocenie</td>"):
            self.assertIn(fragment, wiersz)

        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            wiersz = self.wiersz_zadania(szef.get("/").content.decode(), adres)
            for fragment in (f'<a href="{adres}">Przeprowadź rozmowę oceniającą i dokonaj pierwszej oceny</a>', "<td>30.11.2026</td>",
                             "<td>art. 38 ust. 1 i 2 u.s.c.; § 8 ust. 1 rozp. o pierwszej ocenie</td>"):
                self.assertIn(fragment, wiersz)
            self.assertEqual(szef.post(adres, self.ocena_dane(uzasadnienie="Nie złożono sprawozdania.")).status_code, 302)
            wiersz = self.wiersz_zadania(szef.get("/").content.decode(), adres)
            for fragment in ('<span class="stan stan-bez_terminu">po dokonaniu oceny</span>', f'<a href="{adres}">Złóż wniosek do dyrektora generalnego</a>',
                             "<small>pierwsza ocena, w roli: kierujący komórką</small>", "<td>po dokonaniu oceny</td>", "<td>art. 38 ust. 3 u.s.c.</td>"):
                self.assertIn(fragment, wiersz)
            self.assertEqual(self.wiersz_zadania(pracownik.get("/").content.decode(), adres), "")
            self.assertEqual(szef.post(adres, {"akcja": "wniosek", "wybor": "brak"}).status_code, 302)
            html = szef.get("/").content.decode()
            self.assertEqual(self.wiersz_zadania(html, adres), "")
            self.assertEqual(bledy_dostepnosci(html), [])

    def test_zadania_obu_procesow_sa_w_jednej_kolejnosci_terminow(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        okresowa = self.z.ocena_z_kryteriami()  # zadanie przełożonego z terminem 20.11.2026
        html = klient(self.z.szef).get("/").content.decode()
        zadanie_pierwszej, zadanie_okresowej = f'<a href="{adres}">Przeprowadź rozmowę wstępną', f'<a href="/oceny/{okresowa.pk}/">Przeprowadź rozmowę oceniającą'
        self.assertIn(zadanie_pierwszej, html)
        self.assertIn(zadanie_okresowej, html)
        self.assertLess(html.index(zadanie_pierwszej), html.index(zadanie_okresowej))  # 22.01.2026 przed 20.11.2026
        with self.settings(ASYSTENT_DZIS="2026-09-21"):  # rozmowa wstępna nadal niezapisana, a jej termin jest najstarszy
            html = klient(self.z.szef).get("/").content.decode()
            self.assertIn('<span class="stan stan-po_terminie">242 dni po terminie</span>', self.wiersz_zadania(html, adres))
            self.assertLess(html.index(zadanie_pierwszej), html.index(zadanie_okresowej))
        self.assertIn("<small>w roli: oceniający</small>", html)  # zadania ocen okresowych wyglądają jak dotąd
        self.assertEqual(bledy_dostepnosci(html), [])

    def test_lista_spraw_pierwszej_oceny_pokazuje_etap_i_najblizszy_termin(self):
        from .pomocnicze import dyrektor_generalny
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef, pracownik = klient(self.z.szef), klient(osoba)

        def pozycja(html):
            lista = html[html.index('<h2>Pierwsza ocena w służbie cywilnej</h2>'):]
            lista = lista[:lista.index("</ul>")]
            return next(wpis for wpis in lista.split("<li>") if f'href="{adres}"' in wpis)

        for sesja in (szef, pracownik):  # każdy uczestnik ma stałe wejście do karty, także bez własnego zadania
            wpis = pozycja(sesja.get("/").content.decode())
            for fragment in (f'<a href="{adres}">Jan Nowicki - arkusz pierwszej oceny</a>', '<span class="etap">rozmowa wstępna</span>',
                             "<span>termin: 22.01.2026</span>"):
                self.assertIn(fragment, wpis)
        self.assertContains(pracownik.get("/"), "Nie masz teraz żadnych zadań.")
        self.assertEqual(szef.post(adres, self.WSTEPNA).status_code, 302)
        wpis = pozycja(szef.get("/").content.decode())
        self.assertIn('<span class="etap">sprawozdanie ocenianego</span>', wpis)
        self.assertIn("<span>termin: 20.09.2026</span>", wpis)
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertIn("<span>termin: 30.11.2026</span>", pozycja(szef.get("/").content.decode()))
            self.assertEqual(szef.post(adres, self.ocena_dane(uzasadnienie="Nie złożono sprawozdania.")).status_code, 302)
            wpis = pozycja(pracownik.get("/").content.decode())
            self.assertIn('<span class="etap">wniosek do dyrektora generalnego</span>', wpis)
            self.assertNotIn("termin:", wpis)  # po ocenie nie biegnie już termin dzienny
            self.assertEqual(szef.post(adres, {"akcja": "wniosek", "wybor": "brak"}).status_code, 302)
            html = klient(dyrektor_generalny()).get("/").content.decode()
            self.assertIn('<span class="etap">wniosek złożony</span>', pozycja(html))
            self.assertEqual(bledy_dostepnosci(html), [])

    # --- terminy pierwszej oceny w kalendarzu (.ics), jak przy ocenie okresowej ---

    def test_kalendarz_pierwszej_oceny_zawiera_terminy_ktore_biegna(self):
        osoba = self.dodaj()
        pk = osoba.umowa.pierwsza.pk
        adres, kalendarz = f"/pierwsza-ocena/{pk}/", f"/pierwsza-ocena/{pk}/terminy.ics"
        szef, pracownik = klient(self.z.szef), klient(osoba)
        przycisk = f'<a href="{kalendarz}" class="przycisk przycisk-drugi">Dodaj terminy do kalendarza (.ics)</a>'
        for sesja in (szef, pracownik):
            self.assertContains(sesja.get(adres), przycisk)

        odpowiedz = szef.get(kalendarz)
        self.assertEqual(odpowiedz.status_code, 200)
        self.assertTrue(odpowiedz["Content-Type"].startswith("text/calendar"))
        self.assertIn(f"terminy-pierwszej-oceny-{pk}.ics", odpowiedz["Content-Disposition"])
        ics = odpowiedz.content.decode().replace("\r\n ", "")  # cofnięcie łamania wierszy z RFC 5545
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 2)
        for fragment in ("DTSTART;VALUE=DATE:20260122",  # rozmowa wstępna: 21 dni od 01.01.2026 (§ 3 rozp.)
                         "DTSTART;VALUE=DATE:20261130",  # ostatni dzień okresu pierwszej oceny (art. 38 ust. 1 u.s.c.)
                         "SUMMARY:Rozmowa wstępna przed pierwszą oceną - Jan Nowicki",
                         "SUMMARY:Koniec okresu dokonania pierwszej oceny w służbie cywilnej - Jan Nowicki",
                         f"UID:pierwsza-ocena-{pk}-rozmowa-wstepna@asystent-ocen", f"UID:pierwsza-ocena-{pk}-pierwsza-ocena@asystent-ocen",
                         "Dz. U. poz. 1144", "art. 38 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej"):
            self.assertIn(fragment, ics)

        wlasny = pracownik.get(kalendarz).content.decode()  # oceniany dostaje te same terminy bez swojego nazwiska
        self.assertEqual(wlasny.count("BEGIN:VEVENT"), 2)
        self.assertIn("DTSTART;VALUE=DATE:20260122", wlasny)
        self.assertNotIn("Nowicki", wlasny)

        self.assertEqual(szef.post(adres, self.WSTEPNA).status_code, 302)  # po rozmowie biegnie termin sprawozdania
        ics = szef.get(kalendarz).content.decode().replace("\r\n ", "")
        self.assertEqual(ics.count("BEGIN:VEVENT"), 2)
        self.assertIn("DTSTART;VALUE=DATE:20260920", ics)
        self.assertIn("SUMMARY:Koniec terminu na sprawozdanie do pierwszej oceny - Jan Nowicki", ics)
        self.assertIn("DTSTART;VALUE=DATE:20261130", ics)
        self.assertNotIn("DTSTART;VALUE=DATE:20260122", ics)
        with self.settings(ASYSTENT_DZIS="2026-09-21"):  # termin sprawozdania upłynął - został termin oceny
            ics = szef.get(kalendarz).content.decode()
            self.assertEqual(ics.count("BEGIN:VEVENT"), 1)
            self.assertIn("DTSTART;VALUE=DATE:20261130", ics)

    def test_kalendarz_pierwszej_oceny_jest_dla_stron_sprawy_i_tylko_gdy_biegnie_termin(self):
        osoba, adres, szef = self.przygotuj_arkusz()
        kalendarz = adres + "terminy.ics"
        self.assertEqual(klient(self.z.obcy).get(kalendarz).status_code, 404)
        bez_logowania = self.client.get(kalendarz)
        self.assertEqual(bez_logowania.status_code, 302)
        self.assertIn("/logowanie/", bez_logowania["Location"])
        self.assertEqual(szef.post(kalendarz).status_code, 405)
        with self.settings(ASYSTENT_DZIS="2026-09-21"):
            self.assertEqual(szef.post(adres, self.ocena_dane(uzasadnienie="Nie złożono sprawozdania.")).status_code, 302)
            for sesja in (szef, klient(osoba)):
                self.assertNotContains(sesja.get(adres), "terminy.ics")  # po ocenie nie biegnie termin dzienny
            odpowiedz = szef.get(kalendarz, follow=True)
            self.assertRedirects(odpowiedz, adres)
            self.assertContains(odpowiedz, "nie biegnie żaden termin")

    # --- termin sprawozdania zostawia dzień na ocenę ---

    BLAD_OSTATNIEGO_DNIA = ("Termin sprawozdania nie może kończyć się w ostatnim dniu okresu dokonania pierwszej oceny (30.11.2026). "
                            "Wskaż najpóźniej 29.11.2026 - po upływie terminu potrzebny jest jeszcze dzień na rozmowę oceniającą i ocenę "
                            "(§ 4 ust. 1 i § 8 ust. 1 rozp.).")

    def test_termin_sprawozdania_nie_konczy_sie_w_ostatnim_dniu_okresu_oceny(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef = klient(self.z.szef)
        szef.raise_request_exception = False
        rozmowa = {"akcja": "wstepna", "rozmowa": "2026-09-10", "od": "2026-09-10"}
        with self.settings(ASYSTENT_DZIS="2026-09-10"):
            self.assertContains(szef.get(adres), "Termin sprawozdania musi skończyć się najpóźniej 29.11.2026")
            odrzucony = szef.post(adres, {**rozmowa, "do": "2026-11-30"})
            self.assertEqual(odrzucony.status_code, 200)
            self.assertContains(odrzucony, f'<li id="id_wstepna_do_error">Termin złożenia sprawozdania - do: {self.BLAD_OSTATNIEGO_DNIA}</li>')
            self.assertEqual(bledy_dostepnosci(odrzucony.content.decode()), [])
            osoba.umowa.pierwsza.refresh_from_db()
            self.assertNotIn("wstepna", osoba.umowa.pierwsza.dane)
            self.assertEqual(szef.post(adres, {**rozmowa, "do": "2026-11-29"}).status_code, 302)  # przedostatni dzień jest dozwolony
            osoba.umowa.pierwsza.refresh_from_db()
            self.assertEqual(osoba.umowa.pierwsza.dane["wstepna"]["do"], "2026-11-29")

    def test_nowy_termin_sprawozdania_tez_zostawia_dzien_na_ocene(self):
        osoba, adres, szef = self.przygotuj_arkusz()  # termin sprawozdania 03.09 - 20.09.2026
        szef.raise_request_exception = False
        with self.settings(ASYSTENT_DZIS="2026-09-10"):
            odrzucony = szef.post(adres, {"akcja": "termin", "od": "2026-09-10", "do": "2026-11-30", "pismo": "on"})
            self.assertEqual(odrzucony.status_code, 200)
            self.assertContains(odrzucony, f'<li id="id_termin_do_error">Nowy koniec terminu sprawozdania: {self.BLAD_OSTATNIEGO_DNIA}</li>')
            osoba.umowa.pierwsza.refresh_from_db()
            self.assertEqual(osoba.umowa.pierwsza.dane["wstepna"]["do"], "2026-09-20")
            self.assertEqual(szef.post(adres, {"akcja": "termin", "od": "2026-09-10", "do": "2026-11-29", "pismo": "on"}).status_code, 302)
            osoba.umowa.pierwsza.refresh_from_db()
            self.assertEqual(osoba.umowa.pierwsza.dane["wstepna"]["do"], "2026-11-29")

    def test_w_ostatnim_dniu_okresu_oceny_karta_mowi_ze_terminu_nie_da_sie_juz_wyznaczyc(self):
        osoba = self.dodaj()
        adres = f"/pierwsza-ocena/{osoba.umowa.pierwsza.pk}/"
        szef = klient(self.z.szef)
        szef.raise_request_exception = False
        with self.settings(ASYSTENT_DZIS="2026-11-29"):  # został jeden dzień: termin może skończyć się dziś
            self.assertNotContains(szef.get(adres), "nie da się już wyznaczyć")
        with self.settings(ASYSTENT_DZIS="2026-11-30"):
            strona = szef.get(adres)
            self.assertContains(strona, "Terminu sprawozdania nie da się już wyznaczyć tak, żeby po jego upływie został dzień na ocenę: "
                                        "okres dokonania pierwszej oceny kończy się 30.11.2026.")
            self.assertEqual(bledy_dostepnosci(strona.content.decode()), [])
            odrzucony = szef.post(adres, {"akcja": "wstepna", "rozmowa": "2026-11-30", "od": "2026-11-30", "do": "2026-11-30"})
            self.assertEqual(odrzucony.status_code, 200)
            self.assertContains(odrzucony, "Termin sprawozdania nie może kończyć się w ostatnim dniu okresu dokonania pierwszej oceny (30.11.2026).")
        osoba.umowa.pierwsza.refresh_from_db()
        self.assertNotIn("wstepna", osoba.umowa.pierwsza.dane)
