"""Komórka kadr dodaje pracownika i ustawia jego parametry, w tym rodzaj arkusza oceny.

Wymaganie: decyzja prowadzącego projekt z 21.11.2026. Podstawy: § 3 rozp. (arkusz A, B albo C wynika z tego, czy
osoba jest kierownikiem urzędu albo kieruje bezpośrednio pracownikami) i art. 81 ust. 1 u.s.c. (obowiązek oceny
wynika z rodzaju zatrudnienia).

Decyzje projektowe: dane pracownika prowadzi komórka kadr, a konto do logowania powstaje przy dodaniu pracownika; formularz
nie nadaje uprawnień kadr ani dyrektora; dodanie i zmiana zostają w dzienniku zdarzeń bez danych osobowych;
arkusz cyklu, który trwa, się nie zmienia.
"""

from django.test import TestCase
from django.urls import reverse

from oceny import dziennik
from oceny.models import Ocena, Pracownik, Wydzial, ZdarzenieBezpieczenstwa

from .dostepnosc_html import bledy_dostepnosci
from .pomocnicze import Zespol
from .test_widoki import klient

NOWY = reverse("kadry_pracownik_nowy")
LISTA = reverse("kadry")


def dane(**zmiany) -> dict:
    podstawa = {
        "imie": "Jan", "nazwisko": "Nowicki", "stanowisko": "inspektor", "opis_stanowiska": "Prowadzenie spraw wydziału.",
        "wydzial": str(Wydzial.objects.get(nazwa="Wydział Organizacyjny").pk), "rodzaj_zatrudnienia": "umowa_na_czas_nieokreslony", "arkusz": "C",
        "przelozony": "", "data_zatrudnienia": "2026-11-02", "data_mianowania": "", "stopien_sluzbowy": "",
        "data_stopnia": "", "identyfikator_ezd": "",
    }
    podstawa.update(zmiany)
    return podstawa


class Podstawa(TestCase):
    def setUp(self):
        self.z = Zespol()
        self.kadry = klient(self.z.kadry)
        Wydzial.objects.filter(pk=self.z.ola.wydzial_id).update(kierownik=self.z.szef)

    def edycja(self, osoba) -> str:
        return reverse("kadry_pracownik", args=[osoba.pk])

    def wpisy(self, rodzaj):
        return ZdarzenieBezpieczenstwa.objects.filter(rodzaj=rodzaj)


class DostepTest(Podstawa):
    def test_lista_kadr_ma_przycisk_dodania_i_odnosniki_do_danych_pracownikow(self):
        odpowiedz = self.kadry.get(LISTA)

        self.assertContains(odpowiedz, f'href="{NOWY}"', count=1)
        self.assertContains(odpowiedz, f'href="{self.edycja(self.z.ola)}"', count=1)
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_formularz_jest_tylko_dla_komorki_kadr(self):
        for osoba in (self.z.szef, self.z.ola):
            self.assertEqual(klient(osoba).get(NOWY).status_code, 403)
            self.assertEqual(klient(osoba).post(NOWY, dane()).status_code, 403)
            self.assertEqual(klient(osoba).get(self.edycja(self.z.ola)).status_code, 403)
        self.assertEqual(self.client.get(NOWY).status_code, 302)
        self.assertFalse(Pracownik.objects.filter(nazwisko="Nowicki").exists())

    def test_formularz_nowego_pracownika_ma_parametry_oceny_i_przechodzi_kontrole_dostepnosci(self):
        odpowiedz = self.kadry.get(NOWY)

        for etykieta in ("Arkusz oceny", "Rodzaj zatrudnienia", "Bezpośredni przełożony", "Komórka organizacyjna"):
            self.assertContains(odpowiedz, etykieta)
        self.assertContains(odpowiedz, "§ 3 rozp.")
        self.assertContains(odpowiedz, "Konto do logowania powstaje automatycznie")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])


class DodawanieTest(Podstawa):
    def test_kadry_dodaja_pracownika_z_arkuszem_B(self):
        odpowiedz = self.kadry.post(NOWY, dane(arkusz="B", przelozony=str(self.z.szef.pk)), follow=True)

        osoba = Pracownik.objects.get(nazwisko="Nowicki")
        self.assertEqual((osoba.arkusz, osoba.kieruje_pracownikami, osoba.kierownik_urzedu), ("B", True, False))
        self.assertEqual((osoba.przelozony, osoba.uzytkownik.username), (self.z.szef, "jan.nowicki"))
        self.assertContains(odpowiedz, "Dodano pracownika: Jan Nowicki.")
        self.assertContains(odpowiedz, f'href="{self.edycja(osoba)}"')

    def test_arkusz_wynika_z_wybranego_parametru(self):
        """§ 3 rozp.: A - kierownik urzędu, B - bezpośrednie kierowanie pracownikami, C - pozostali."""
        for arkusz, kierownik, kieruje in (("A", True, True), ("B", False, True), ("C", False, False)):
            self.kadry.post(NOWY, dane(nazwisko=f"Arkusz{arkusz}", arkusz=arkusz))

            osoba = Pracownik.objects.get(nazwisko=f"Arkusz{arkusz}")
            self.assertEqual((osoba.arkusz, osoba.kierownik_urzedu, osoba.kieruje_pracownikami), (arkusz, kierownik, kieruje))

    def test_dodanie_zostaje_w_dzienniku_zdarzen_bez_danych_osobowych(self):
        self.kadry.post(NOWY, dane(arkusz="B"))

        wpis = self.wpisy(dziennik.PRACOWNIK_DODANY).get()
        osoba = Pracownik.objects.get(nazwisko="Nowicki")
        self.assertEqual((wpis.login, wpis.dotyczy), ("kadry", f"pracownik {osoba.pk}"))
        self.assertIn("arkusz B", wpis.opis)
        self.assertNotIn("Nowicki", wpis.opis + wpis.dotyczy)

    def test_braki_i_bledne_wartosci_niczego_nie_zapisuja(self):
        ilu = Pracownik.objects.count()

        bez_nazwiska = self.kadry.post(NOWY, dane(nazwisko=""))
        zly_rodzaj = self.kadry.post(NOWY, dane(rodzaj_zatrudnienia="wolontariat"))
        zly_arkusz = self.kadry.post(NOWY, dane(arkusz="D"))

        for odpowiedz in (bez_nazwiska, zly_rodzaj, zly_arkusz):
            self.assertEqual(odpowiedz.status_code, 200)
            self.assertContains(odpowiedz, 'role="alert"')
            self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])
        self.assertEqual(Pracownik.objects.count(), ilu)
        self.assertEqual(self.wpisy(dziennik.PRACOWNIK_DODANY).count(), 0)

    def test_formularz_nie_nadaje_uprawnien_kadr_ani_dyrektora(self):
        self.kadry.post(NOWY, dane(rola_kadry="on", rola_dyrektor="on", uzytkownik=str(self.z.kadry.uzytkownik.pk)))

        osoba = Pracownik.objects.get(nazwisko="Nowicki")
        self.assertNotEqual(osoba.uzytkownik_id, self.z.kadry.uzytkownik_id)
        self.assertEqual((osoba.rola_kadry, osoba.rola_dyrektor, osoba.uzytkownik.is_superuser), (False, False, False))


class ZmianaTest(Podstawa):
    def test_formularz_edycji_pokazuje_obecne_parametry(self):
        odpowiedz = self.kadry.get(self.edycja(self.z.szef))

        self.assertContains(odpowiedz, 'value="Szef"')
        self.assertEqual(odpowiedz.context["formularz"].initial["arkusz"], "B")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_zmiana_arkusza_zostaje_w_dzienniku_ze_starym_i_nowym_arkuszem(self):
        self.kadry.post(self.edycja(self.z.ola), dane(
            imie="Ola", nazwisko="Testowy", stanowisko="starszy specjalista", arkusz="B", przelozony=str(self.z.szef.pk),
            data_zatrudnienia=self.z.ola.data_zatrudnienia.isoformat(),
        ))

        self.z.ola.refresh_from_db()
        wpis = self.wpisy(dziennik.PRACOWNIK_ZMIENIONY).get()
        self.assertEqual((self.z.ola.arkusz, self.z.ola.stanowisko), ("B", "starszy specjalista"))
        self.assertIn("arkusz (C -> B)", wpis.opis)
        self.assertIn("stanowisko", wpis.opis)
        self.assertNotIn("Testowy", wpis.opis)

    def test_zapis_bez_zmian_nie_tworzy_wpisu(self):
        ola = self.z.ola
        self.kadry.post(self.edycja(ola), dane(
            imie=ola.imie, nazwisko=ola.nazwisko, stanowisko=ola.stanowisko, opis_stanowiska=ola.opis_stanowiska,
            wydzial=str(ola.wydzial_id), przelozony=str(self.z.szef.pk), data_zatrudnienia=ola.data_zatrudnienia.isoformat(),
        ))

        self.assertEqual(self.wpisy(dziennik.PRACOWNIK_ZMIENIONY).count(), 0)

    def test_podane_recznie_id_nie_zmienia_szefa_z_wydzialu(self):
        odpowiedz = self.kadry.post(self.edycja(self.z.ola), dane(przelozony=str(self.z.ola.pk)))

        self.assertEqual(odpowiedz.status_code, 302)
        self.z.ola.refresh_from_db()
        self.assertEqual(self.z.ola.przelozony, self.z.szef)

    def test_zmiana_arkusza_nie_zmienia_arkusza_cyklu_ktory_trwa(self):
        """Arkusz jest utrwalany na początku cyklu - nowy obowiązuje od kolejnego cyklu oceny."""
        ocena = self.z.ocena_z_kryteriami()
        ola = self.z.ola

        odpowiedz = self.kadry.post(self.edycja(ola), dane(
            imie=ola.imie, nazwisko=ola.nazwisko, arkusz="B", przelozony=str(self.z.szef.pk),
            data_zatrudnienia=ola.data_zatrudnienia.isoformat(),
        ), follow=True)

        self.assertEqual(Ocena.objects.get(pk=ocena.pk).proces().arkusz, "C")
        self.assertContains(odpowiedz, "od kolejnego cyklu oceny")


class MianowanieTest(Podstawa):
    def test_pelna_data_ustawia_mianowanie_bez_javascript(self):
        wynik = self.kadry.post(NOWY, dane(data_mianowania="2026-11-15", stopien_sluzbowy="2", data_stopnia="2026-11-16"))
        self.assertEqual(wynik.status_code, 302)
        osoba = Pracownik.objects.get(nazwisko="Nowicki")
        self.assertTrue(osoba.urzednik)
        self.assertEqual(osoba.data_mianowania.isoformat(), "2026-11-15")
        self.assertEqual(osoba.stopien_sluzbowy, 2)
        self.assertEqual(osoba.wydzial_id, self.z.ola.wydzial_id)

    def test_brak_stopnia_lub_daty_stopnia_blokuje_zapis(self):
        for stopien, data in (("", ""), ("2", ""), ("", "2026-11-16"), ("10", "2026-11-16"), ("0", "2026-11-16")):
            wynik = self.kadry.post(NOWY, dane(data_mianowania="2026-11-15", stopien_sluzbowy=stopien, data_stopnia=data))
            self.assertContains(wynik, 'role="alert"')
        self.assertFalse(Pracownik.objects.filter(nazwisko="Nowicki").exists())

    def test_wybor_mianowania_bez_daty_nie_wystarcza(self):
        self.assertContains(self.kadry.post(NOWY, dane(rodzaj_zatrudnienia="mianowanie", stopien_sluzbowy="1", data_stopnia="2026-11-02")), 'role="alert"')
        self.assertFalse(Pracownik.objects.filter(nazwisko="Nowicki").exists())

    def test_etykiety_i_pole_daty(self):
        wynik = self.kadry.get(NOWY)
        self.assertContains(wynik, "Data rozpoczęcia zatrudnienia")
        self.assertContains(wynik, 'type="date" name="data_mianowania"')
        self.assertNotContains(wynik, 'name="rok_mianowania"')
