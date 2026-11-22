"""Przegląd współpracy: strona przełożonego o jednym pracowniku - notatki, Radar, nieobecności i oceny w jednym
miejscu - oraz szybka notatka i akcje przy ocenach na liście „Moje zadania”.

Wymaganie (decyzja prowadzącego projekt z 22.11.2026): przy każdym pracowniku na liście „Oceny, które prowadzę”
są dwie akcje - dodanie notatki i strona ze wszystkimi informacjami o pracowniku z wyborem zakresu dat; notatki
łączą się z Radarem Dobrostanu przez rodzaj wpisu.

Decyzje projektowe: strona nazywa się „Przegląd współpracy” (nie „teczka” ani „akta” - akta osobowe prowadzi
komórka kadr, nie „profil” - to nie profilowanie); widzi ją wyłącznie oceniający, bo zawiera jego notatki
(decyzja zespołu z 21.11.2026); zakres dat domyślnie obejmuje bieżący okres oceny i dotyczy notatek oraz
nieobecności, a karty Radaru pokazują stan na dziś.
"""

from datetime import date
from itertools import product

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from oceny import dziennik, uslugi
from oceny.models import Nieobecnosc, ZdarzenieBezpieczenstwa
from oceny.radar import radar_oceny

from .dostepnosc_html import bledy_dostepnosci, tytul_strony
from .pomocnicze import POCZATEK, Zespol, dyrektor_generalny
from .test_radar import DZIEN, ustalenia
from .test_widoki import klient

OBSERWACJA = "Sprawy zamknięte przed terminem."
OSIAGNIECIE = "Opracowała wzór decyzji przyjęty w całym urzędzie."
USTALENIE = "Ustalony urlop 14 dni w lipcu."


@override_settings(ASYSTENT_DZIS=DZIEN.isoformat(), ASYSTENT_TRYB_DEMO=True)
class Podstawa(TestCase):
    """Ocena na etapie oceniania, Radar z danymi przykładowymi; dziś jest 02.11.2026, okres oceny od 21.11.2024."""

    def setUp(self):
        self.z = Zespol(klauzula_ezd_potwierdzona=True, identyfikator_ezd="stanowisko-anna")
        self.ocena = self.z.ocena_z_kryteriami()
        ustalenia()
        self.szef = klient(self.z.szef)
        self.szef.raise_request_exception = False
        self.przeglad = reverse("przeglad_wspolpracy", args=[self.z.ola.pk])
        self.nowa = reverse("nowa_notatka", args=[self.ocena.pk])

    def notatka(self, tresc, rodzaj="obserwacja", dzien=date(2025, 6, 10)):
        uslugi.dodaj_notatke(self.ocena, self.z.szef.uzytkownik, tresc=tresc, rodzaj=rodzaj, data=dzien)

    def trzy_notatki(self):
        self.notatka(OBSERWACJA)
        self.notatka(OSIAGNIECIE, "osiagniecie", date(2025, 9, 1))
        self.notatka(USTALENIE, "dobrostan", date(2026, 10, 20))

    def sekcja(self, html, identyfikator):
        """Treść sekcji o podanym identyfikatorze nagłówka - do sprawdzenia, co pod którym nagłówkiem stoi."""
        poczatek = html.index(f'aria-labelledby="{identyfikator}"')
        return html[poczatek:html.index("</section>", poczatek)]


class DostepTest(Podstawa):
    def test_przeglad_widzi_tylko_oceniajacy(self):
        self.assertEqual(self.szef.get(self.przeglad).status_code, 200)
        for osoba in (self.z.ola, self.z.kadry, self.z.obcy, dyrektor_generalny()):
            with self.subTest(osoba=osoba.uzytkownik.username):
                self.assertEqual(klient(osoba).get(self.przeglad).status_code, 404)
        bez_logowania = Client().get(self.przeglad)
        self.assertEqual(bez_logowania.status_code, 302)
        self.assertTrue(bez_logowania["Location"].startswith(reverse("logowanie")))

    def test_nowy_oceniajacy_przejmuje_przeglad_a_poprzedni_go_traci(self):
        """Ta sama reguła co na karcie oceny: notatki widzi osoba, która jest oceniającym w tej ocenie."""
        self.notatka(OBSERWACJA)
        self.ocena.oceniajacy = self.z.obcy
        self.ocena.save(update_fields=["oceniajacy"])

        self.assertEqual(self.szef.get(self.przeglad).status_code, 404)
        self.assertContains(klient(self.z.obcy).get(self.przeglad), OBSERWACJA)

    def test_otwarcie_przegladu_zostawia_slad_w_dzienniku(self):
        self.szef.get(self.przeglad)

        wpis = ZdarzenieBezpieczenstwa.objects.order_by("pk").last()
        self.assertEqual((wpis.rodzaj, wpis.login, wpis.dotyczy), (dziennik.ODCZYT_OCENY, "szef", f"przegląd współpracy {self.z.ola.pk}"))


class TrescTest(Podstawa):
    def test_strona_ma_nazwe_pracownika_metryczke_i_poprawne_znaczniki(self):
        self.trzy_notatki()
        html = self.szef.get(self.przeglad).content.decode()

        self.assertEqual(tytul_strony(html), "Przegląd współpracy: Ola Testowy - Asystent ocen okresowych")
        for fragment in ("<h1>Ola Testowy</h1>", '<a href="/">Moje zadania</a> / przegląd współpracy',
                         "<dt>Stanowisko</dt><dd>specjalista</dd>", "<dt>Komórka organizacyjna</dt><dd>Wydział Organizacyjny</dd>",
                         "<dt>W urzędzie od</dt><dd>21.11.2024</dd>",
                         f'<dt>Bieżąca ocena</dt><dd><a href="/oceny/{self.ocena.pk}/">rozmowa oceniająca i dokonanie oceny</a>',
                         "Tę stronę widzisz tylko Ty jako oceniający."):
            self.assertIn(fragment, html)
        self.assertEqual(bledy_dostepnosci(html), [])

    def test_notatki_stoja_przy_kartach_radaru_tego_samego_rodzaju(self):
        self.trzy_notatki()
        html = self.szef.get(self.przeglad).content.decode()
        radar = radar_oceny(self.ocena, DZIEN)
        self.assertTrue(radar.dobrostan and radar.docenienie)

        dobrostan, docenianie, obserwacje = (self.sekcja(html, kod) for kod in ("n-dobrostan", "n-docenianie", "n-obserwacje"))
        self.assertIn("<h2 id=\"n-dobrostan\">Dobrostan i organizacja pracy</h2>", html)
        self.assertIn("<h2 id=\"n-docenianie\">Docenianie</h2>", html)
        self.assertIn("<h2 id=\"n-obserwacje\">Obserwacje z pracy</h2>", html)
        for karta in radar.dobrostan:
            self.assertIn(karta.fakt, dobrostan)
        for karta in radar.docenienie:
            self.assertIn(karta.fakt, docenianie)
        self.assertIn(f"<strong>20.10.2026</strong> {USTALENIE}", dobrostan)
        self.assertIn(f"<strong>01.09.2025</strong> {OSIAGNIECIE}", docenianie)
        self.assertIn(f"<strong>10.06.2025</strong> {OBSERWACJA}", obserwacje)
        for obca, sekcje in ((USTALENIE, (docenianie, obserwacje)), (OSIAGNIECIE, (dobrostan, obserwacje)), (OBSERWACJA, (dobrostan, docenianie))):
            for tresc in sekcje:
                self.assertNotIn(obca, tresc)
        self.assertIn("Karty Radaru pokazują stan na 02.11.2026", html)
        self.assertIn("Pokaz: dane przykładowe zamiast połączenia z systemem kadrowym i EZD RP.", html)

    def test_bez_radaru_strona_pokazuje_same_notatki(self):
        from oceny.models import UstaleniaMonitoringu

        UstaleniaMonitoringu.objects.all().delete()
        self.trzy_notatki()
        odpowiedz = self.szef.get(self.przeglad)

        self.assertEqual(odpowiedz.status_code, 200)
        for tresc in (OBSERWACJA, OSIAGNIECIE, USTALENIE):
            self.assertContains(odpowiedz, tresc)
        self.assertNotContains(odpowiedz, "Karty Radaru pokazują stan")
        self.assertEqual(bledy_dostepnosci(odpowiedz.content.decode()), [])

    def test_przeglad_ma_formularz_notatki_ktory_wraca_na_przeglad(self):
        html = self.szef.get(self.przeglad).content.decode()
        self.assertIn(f'<form method="post" action="/oceny/{self.ocena.pk}/czynnosc/notatka/" class="formularz">', html)
        self.assertIn('<input type="hidden" name="powrot" value="przeglad">', html)

        odpowiedz = self.szef.post(f"/oceny/{self.ocena.pk}/czynnosc/notatka/", {"tresc": USTALENIE, "rodzaj": "dobrostan", "powrot": "przeglad"})
        self.assertRedirects(odpowiedz, self.przeglad)
        self.assertContains(self.szef.get(self.przeglad), USTALENIE)

    def test_przeglad_pokazuje_oceny_ktore_prowadze_i_nieobecnosci(self):
        Nieobecnosc.objects.create(pracownik=self.z.ola, od=date(2025, 7, 1), do=date(2025, 7, 10))
        html = self.szef.get(self.przeglad).content.decode()

        oceny = self.sekcja(html, "n-oceny")
        self.assertIn(f'<a href="/oceny/{self.ocena.pk}/">Okres od 21.11.2024</a>', oceny)
        self.assertIn("termin oceny: 23.11.2026", oceny)
        self.assertIn("01.07.2025 - 10.07.2025", self.sekcja(html, "n-nieobecnosci"))


class ZakresDatTest(Podstawa):
    def pola(self, html):
        return tuple(html.split(f'id="zakres_{kod}"')[1].split(">")[0] for kod in ("od", "do"))

    def test_domyslnie_przeglad_obejmuje_biezacy_okres_oceny(self):
        self.trzy_notatki()
        html = self.szef.get(self.przeglad).content.decode()

        od, do = self.pola(html)
        self.assertIn(f'value="{POCZATEK.isoformat()}"', od)
        self.assertIn('value="2026-11-02"', do)
        self.assertIn('max="2026-11-02"', do)
        self.assertIn('<a href="?zakres=okres" aria-current="true">Bieżący okres oceny</a>', html)
        for adres, nazwa in (("3m", "Ostatnie 3 miesiące"), ("12m", "Ostatnie 12 miesięcy"), ("wszystko", "Cały okres zatrudnienia")):
            self.assertIn(f'<a href="?zakres={adres}">{nazwa}</a>', html)
        self.assertIn("<strong>21.11.2024 - 02.11.2026</strong> (bieżący okres oceny)", html)
        self.assertIn("Notatki: 3. Nieobecności: 0.", html)

    def test_gotowy_zakres_zaweza_notatki_i_nieobecnosci(self):
        self.trzy_notatki()
        Nieobecnosc.objects.create(pracownik=self.z.ola, od=date(2025, 7, 1), do=date(2025, 7, 10))
        html = self.szef.get(self.przeglad, {"zakres": "3m"}).content.decode()

        self.assertIn(USTALENIE, html)  # 20.10.2026
        self.assertNotIn(OBSERWACJA, html)  # 10.06.2025
        self.assertNotIn(OSIAGNIECIE, html)  # 01.09.2025
        self.assertNotIn("01.07.2025 - 10.07.2025", html)
        self.assertIn('<a href="?zakres=3m" aria-current="true">Ostatnie 3 miesiące</a>', html)
        self.assertIn("<strong>02.08.2026 - 02.11.2026</strong> (ostatnie 3 miesiące)", html)
        self.assertIn("Notatki: 1. Nieobecności: 0.", html)
        self.assertEqual(bledy_dostepnosci(html), [])

    def test_wlasny_zakres_obejmuje_oba_dni_graniczne(self):
        self.trzy_notatki()
        Nieobecnosc.objects.create(pracownik=self.z.ola, od=date(2025, 5, 20), do=date(2025, 6, 10))
        html = self.szef.get(self.przeglad, {"od": "2025-06-10", "do": "2025-09-01"}).content.decode()

        self.assertIn(OBSERWACJA, html)   # pierwszy dzień zakresu
        self.assertIn(OSIAGNIECIE, html)  # ostatni dzień zakresu
        self.assertNotIn(USTALENIE, html)
        self.assertIn("20.05.2025 - 10.06.2025", html)  # nieobecność zachodząca na zakres
        self.assertIn("<strong>10.06.2025 - 01.09.2025</strong> (własny zakres)", html)
        self.assertNotIn('aria-current="true"', self.sekcja(html, "n-zakres"))
        od, do = self.pola(html)
        self.assertIn('value="2025-06-10"', od)
        self.assertIn('value="2025-09-01"', do)

    def test_caly_okres_zatrudnienia_zaczyna_sie_w_dniu_zatrudnienia(self):
        self.z.ola.data_zatrudnienia = date(2023, 3, 1)
        self.z.ola.save(update_fields=["data_zatrudnienia"])

        self.assertContains(self.szef.get(self.przeglad, {"zakres": "wszystko"}), "<strong>01.03.2023 - 02.11.2026</strong> (cały okres zatrudnienia)")

    def test_bledny_zakres_daje_komunikat_i_zakres_domyslny(self):
        self.trzy_notatki()
        odwrocony = self.szef.get(self.przeglad, {"od": "2026-01-10", "do": "2026-01-01"})
        self.assertEqual(odwrocony.status_code, 200)
        self.assertContains(odwrocony, '<p class="komunikat komunikat-error" role="alert">Początek zakresu (10.01.2026) nie może być późniejszy niż koniec (01.01.2026). Pokazuję bieżący okres oceny.</p>')
        self.assertContains(odwrocony, "<strong>21.11.2024 - 02.11.2026</strong> (bieżący okres oceny)")
        self.assertEqual(bledy_dostepnosci(odwrocony.content.decode()), [])

        niepelny = self.szef.get(self.przeglad, {"od": "2026-01-10"})
        self.assertContains(niepelny, "Podaj obie daty zakresu: początek i koniec. Pokazuję bieżący okres oceny.")
        nieczytelny = self.szef.get(self.przeglad, {"od": "10 stycznia", "do": "2026-01-20"})
        self.assertContains(nieczytelny, "Podaj daty zakresu w postaci RRRR-MM-DD. Pokazuję bieżący okres oceny.")
        nieznany = self.szef.get(self.przeglad, {"zakres": "dekada"})
        self.assertContains(nieznany, "<strong>21.11.2024 - 02.11.2026</strong> (bieżący okres oceny)")

    def test_zadna_kombinacja_parametrow_zakresu_nie_konczy_sie_awaria(self):
        wartosci = ("", "2026-01-10", "2026-13-40", "0000-00-00", "9999-12-31", "abc", "2026-01-10T10:00", "\x00", "1-1-1")
        for od, do, zakres in product(wartosci, wartosci, ("", "okres", "3m", "12m", "wszystko", "x")):
            odpowiedz = self.szef.get(self.przeglad, {"od": od, "do": do, "zakres": zakres})
            self.assertEqual(odpowiedz.status_code, 200, (od, do, zakres))


class SzybkaNotatkaTest(Podstawa):
    """Formularz notatki bez reszty karty oceny - z listy zadań, z przeglądu i do karty Radaru."""

    def test_formularz_widzi_tylko_oceniajacy(self):
        self.assertEqual(self.szef.get(self.nowa).status_code, 200)
        for osoba in (self.z.ola, self.z.kadry, self.z.obcy, dyrektor_generalny()):
            with self.subTest(osoba=osoba.uzytkownik.username):
                self.assertEqual(klient(osoba).get(self.nowa).status_code, 404)

    def test_formularz_mowi_o_kim_jest_notatka_i_kto_ja_widzi(self):
        html = self.szef.get(self.nowa, {"powrot": "zadania"}).content.decode()

        self.assertEqual(tytul_strony(html), "Nowa notatka: Ola Testowy - Asystent ocen okresowych")
        for fragment in ("<h1>Nowa notatka: Ola Testowy</h1>", '<a href="/">Moje zadania</a> / nowa notatka',
                         "Notatki widzisz tylko Ty. Nie są częścią arkusza.",
                         f'<form method="post" action="/oceny/{self.ocena.pk}/czynnosc/notatka/" class="formularz">',
                         '<input type="hidden" name="powrot" value="zadania">',
                         '<option value="obserwacja" selected>obserwacja z pracy</option>',
                         f'<a href="{self.przeglad}">Przegląd współpracy</a>', f'<a href="/oceny/{self.ocena.pk}/">Karta oceny</a>'):
            self.assertIn(fragment, html)
        self.assertEqual(bledy_dostepnosci(html), [])

    def test_notatka_z_listy_zadan_wraca_na_liste_zadan(self):
        odpowiedz = self.szef.post(f"/oceny/{self.ocena.pk}/czynnosc/notatka/", {"tresc": OBSERWACJA, "powrot": "zadania"}, follow=True)

        self.assertRedirects(odpowiedz, reverse("zadania"))
        self.ocena.refresh_from_db()
        self.assertEqual([(n.rodzaj, n.tresc) for n in self.ocena.proces().notatki], [("obserwacja", OBSERWACJA)])
        self.assertContains(odpowiedz, "Notatka została zapisana. Widzi ją tylko oceniający.")

    def test_pusta_notatka_wraca_do_formularza_z_komunikatem(self):
        odpowiedz = self.szef.post(f"/oceny/{self.ocena.pk}/czynnosc/notatka/", {"tresc": "  ", "rodzaj": "dobrostan", "powrot": "zadania"})

        self.assertRedirects(odpowiedz, f"{self.nowa}?powrot=zadania&rodzaj=dobrostan", fetch_redirect_response=False)
        strona = self.szef.get(odpowiedz["Location"])  # komunikat pokazuje dopiero formularz, do którego wraca przełożony
        self.assertContains(strona, "Notatka nie może być pusta.")
        self.assertContains(strona, '<option value="dobrostan" selected>dobrostan i organizacja pracy</option>')
        self.ocena.refresh_from_db()
        self.assertEqual(self.ocena.proces().notatki, [])

    def test_notatka_do_karty_radaru_ma_rodzaj_karty_i_zaczyna_sie_od_jej_tytulu(self):
        radar = radar_oceny(self.ocena, DZIEN)
        for karta, rodzaj, nazwa in ((radar.dobrostan[0], "dobrostan", "dobrostan i organizacja pracy"),
                                     (radar.docenienie[0], "osiagniecie", "dodatkowe osiągnięcie pracownika")):
            with self.subTest(karta=karta.kod):
                html = self.szef.get(self.nowa, {"karta": karta.kod, "powrot": "przeglad"}).content.decode()
                self.assertIn(f'<option value="{rodzaj}" selected>{nazwa}</option>', html)
                self.assertIn(f'required>{karta.tytul}: </textarea>', html)
                self.assertIn(karta.fakt, html)  # przełożony widzi, do czego pisze notatkę
                self.assertIn('<input type="hidden" name="powrot" value="przeglad">', html)
                self.assertEqual(bledy_dostepnosci(html), [])

    def test_nieznane_parametry_sa_pomijane(self):
        html = self.szef.get(self.nowa, {"karta": "NIE_MA_TAKIEJ", "rodzaj": "nagana", "powrot": "https://example.org/"}).content.decode()

        self.assertIn('<option value="obserwacja" selected>obserwacja z pracy</option>', html)
        self.assertIn("required></textarea>", html)
        self.assertNotIn('name="powrot"', html)
        self.assertNotIn("example.org", html)

    def test_nieznany_powrot_w_wyslanym_formularzu_konczy_na_karcie_oceny(self):
        odpowiedz = self.szef.post(f"/oceny/{self.ocena.pk}/czynnosc/notatka/", {"tresc": OBSERWACJA, "powrot": "https://example.org/"})

        self.assertRedirects(odpowiedz, f"/oceny/{self.ocena.pk}/")

    def test_przy_zakonczonej_ocenie_formularza_nie_ma(self):
        from .pomocnicze import DZIEN_OCENY, DZIEN_ROZMOWY

        uslugi.sporzadz_ocene(self.ocena, self.z.szef.uzytkownik, data_rozmowy=DZIEN_ROZMOWY, oceny=self.z.oceny(7),
                              wnioski_iprz="Szkolenie.", data=DZIEN_OCENY)
        uslugi.potwierdz_zapoznanie(self.ocena, self.z.ola.uzytkownik, data=DZIEN_OCENY)

        odpowiedz = self.szef.get(self.nowa, follow=True)
        self.assertRedirects(odpowiedz, f"/oceny/{self.ocena.pk}/")
        self.assertContains(odpowiedz, "Ta ocena jest zakończona - notatki dodaje się w trakcie okresu oceny.")
        przeglad = self.szef.get(self.przeglad)
        self.assertEqual(przeglad.status_code, 200)
        self.assertNotContains(przeglad, 'name="tresc"')
        self.assertNotContains(przeglad, "Zanotuj")


class AkcjeNaLiscieZadanTest(Podstawa):
    """Przy każdej ocenie na liście „Oceny, które prowadzę” są dwie akcje: nowa notatka i przegląd współpracy."""

    def test_przelozony_ma_przy_ocenie_dodanie_notatki_i_przeglad_wspolpracy(self):
        html = self.szef.get(reverse("zadania")).content.decode()
        lista = html[html.index("<h2>Oceny, które prowadzę</h2>"):]
        lista = lista[:lista.index("</ul>")]

        self.assertIn(f'<a href="/oceny/{self.ocena.pk}/">Ola Testowy</a>', lista)
        self.assertIn(f'<a href="{self.nowa}?powrot=zadania" class="przycisk przycisk-drugi przycisk-maly" aria-label="Dodaj notatkę - Ola Testowy">', lista)
        self.assertIn(f'<a href="{self.przeglad}" class="przycisk przycisk-drugi przycisk-maly" aria-label="Przegląd współpracy - Ola Testowy">', lista)
        # ikona jest ozdobą: nazwę akcji daje widoczny podpis, od którego zaczyna się nazwa dla czytnika ekranu (2.5.3)
        self.assertEqual(lista.count('<svg class="ikona"'), 2)
        self.assertEqual(lista.count('aria-hidden="true" focusable="false"'), 2)
        for podpis in ("Dodaj notatkę</a>", "Przegląd współpracy</a>"):
            self.assertIn(podpis, lista)
        self.assertEqual(bledy_dostepnosci(html), [])

    def test_oceniany_i_kadry_nie_maja_tych_akcji(self):
        for osoba in (self.z.ola, self.z.kadry):
            with self.subTest(osoba=osoba.uzytkownik.username):
                odpowiedz = klient(osoba).get(reverse("zadania"))
                self.assertNotContains(odpowiedz, "Dodaj notatkę")
                self.assertNotContains(odpowiedz, "Przegląd współpracy")

    def test_obie_akcje_prowadza_do_dzialajacych_stron(self):
        for adres in (f"{self.nowa}?powrot=zadania", self.przeglad):
            self.assertEqual(self.szef.get(adres).status_code, 200, adres)


class RadarNaKarcieOcenyTest(Podstawa):
    def test_oceniajacy_ma_przy_karcie_radaru_odnosnik_do_notatki_a_oceniany_nie(self):
        karta_oceny = f"/oceny/{self.ocena.pk}/"
        radar = radar_oceny(self.ocena, DZIEN)
        html = self.szef.get(karta_oceny).content.decode()

        for karta in radar.dobrostan:
            self.assertIn(f'<a href="{self.nowa}?karta={karta.kod}" aria-label="Zanotuj ustalenie - {karta.tytul}">Zanotuj ustalenie</a>', html)
        for karta in radar.docenienie:
            self.assertIn(f'<a href="{self.nowa}?karta={karta.kod}" aria-label="Zanotuj osiągnięcie - {karta.tytul}">Zanotuj osiągnięcie</a>', html)
        self.assertEqual(bledy_dostepnosci(html), [])
        self.assertNotContains(klient(self.z.ola).get(karta_oceny), "Zanotuj")


class AdministratorTest(Podstawa):
    def test_administrator_nie_widzi_przegladu_ani_formularza_notatki(self):
        """Zaplecze administratora nie pokazuje notatek - także tą drogą."""
        from django.contrib.auth import get_user_model

        self.notatka(OBSERWACJA)
        admin = Client()
        admin.force_login(get_user_model().objects.create_user(username="admin", is_superuser=True))

        for adres in (self.przeglad, self.nowa):
            odpowiedz = admin.get(adres)
            self.assertEqual(odpowiedz.status_code, 404, adres)
            self.assertNotContains(odpowiedz, OBSERWACJA, status_code=404)
        # Konto administratora nie widzi oceny wcale, więc zapis kończy się tak jak przy cudzej ocenie.
        odpowiedz = admin.post(f"/oceny/{self.ocena.pk}/czynnosc/notatka/", {"tresc": "x", "powrot": "przeglad"})
        self.assertEqual(odpowiedz.status_code, 404)
        self.ocena.refresh_from_db()
        self.assertEqual([n.tresc for n in self.ocena.proces().notatki], [OBSERWACJA])
