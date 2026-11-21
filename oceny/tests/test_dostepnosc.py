"""Dostępność cyfrowa interfejsu: WCAG 2.1 na poziomach A i AA.

Wymaganie: decyzja prowadzącego projekt z 21.11.2026 o dopisaniu WCAG do wymagań systemu. Miara: załącznik do ustawy z dnia
4 kwietnia 2019 r. o dostępności cyfrowej stron internetowych i aplikacji mobilnych podmiotów publicznych
(t.j. Dz. U. z 2023 r. poz. 1440) - „Wytyczne dla dostępności treści internetowych 2.1”, do których odsyła
art. 5 ust. 1 tej ustawy. Numery w nazwach testów i komunikatach to numery kryteriów sukcesu z załącznika.

Progi kontrastu: 4,5:1 dla tekstu (kryterium 1.4.3) i 3:1 dla elementów interfejsu, w tym obrysu fokusu
(kryterium 1.4.11) - wartości z WCAG 2.1; załącznik do ustawy wymienia same kryteria.

Testy sprawdzają to, co widać w znacznikach i w arkuszu stylów. Układ przy 320 px, kolejność fokusu i pracę
z czytnikiem ekranu sprawdza się w przeglądarce - stan tych kontroli opisuje `dokumentacja/dostepnosc.md`.
"""

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from oceny.models import Ocena
from oceny.tests.dostepnosc_html import bledy_dostepnosci, tytul_strony
from oceny.tests.test_demo import zaladuj

STYL = Path(__file__).resolve().parents[1] / "static" / "oceny" / "styl.css"

POPRAWNA = """<!doctype html>
<html lang="pl">
<head><title>Kadry - Asystent ocen okresowych</title></head>
<body>
<a class="pomin" href="#tresc">Przejdź do treści</a>
<main id="tresc">
  <h1>Kadry</h1>
  <form method="get">
    <label for="q">Szukaj</label>
    <input type="search" name="q" id="q">
    <button type="submit">Pokaż</button>
    <p class="czekanie" role="status" data-komunikat="Model pracuje..."></p>
  </form>
  <ul><li class="termin termin-wykonane"><span class="termin-data">05.12.2024</span>
    <span class="termin-nazwa">Zapoznanie z kryteriami oceny</span> <span class="stan stan-wykonane">wykonano</span></li>
    <li class="termin termin-informacja"><span class="termin-data">26.11.2026</span> Termin ustawowy</li></ul>
  <h2>Lista</h2>
  <div class="przewijana" role="region" aria-labelledby="t-lista" tabindex="0">
  <table>
    <caption id="t-lista">Pracownicy</caption>
    <thead><tr><th scope="col">Pracownik</th><th scope="col">Stan</th></tr></thead>
    <tbody><tr><td><a href="/oceny/1/">Anna Nowak</a></td><td>w terminie</td></tr></tbody>
  </table>
  </div>
</main>
</body>
</html>"""

# (kryterium, fragment strony poprawnej, czym go zastąpić, żeby powstało naruszenie)
USTERKI = [
    ("3.1.1", '<html lang="pl">', "<html>"),
    ("2.4.2", "<title>Kadry - Asystent ocen okresowych</title>", "<title> </title>"),
    ("1.3.1", "<h1>Kadry</h1>", "<p>Kadry</p>"),
    ("1.3.1", "<h2>Lista</h2>", "<h3>Lista</h3>"),
    ("4.1.1", 'name="q" id="q">', 'name="q" id="q"><span id="q"></span>'),
    ("4.1.1", 'aria-labelledby="t-lista"', 'aria-labelledby="t-inna"'),
    ("3.3.2", '<label for="q">Szukaj</label>', "<span>Szukaj</span>"),
    ("3.3.2", '<label for="q">Szukaj</label>', '<label for="q"></label>'),
    ("4.1.2", '<button type="submit">Pokaż</button>', '<button type="submit"></button>'),
    ("4.1.2", '<a href="/oceny/1/">Anna Nowak</a>', '<a href="/oceny/1/"></a>'),
    ("1.1.1", "<h2>Lista</h2>", '<h2>Lista</h2><img src="wykres.png">'),
    ("1.3.1", '<caption id="t-lista">Pracownicy</caption>', '<caption id="t-lista"></caption>'),
    ("1.3.1", '<th scope="col">Stan</th>', "<th>Stan</th>"),
    ("1.4.10", '<div class="przewijana" role="region" aria-labelledby="t-lista" tabindex="0">', "<div>"),
    ("2.1.1", 'aria-labelledby="t-lista" tabindex="0">', 'aria-labelledby="t-lista">'),
    ("2.4.1", '<a class="pomin" href="#tresc">Przejdź do treści</a>', ""),
    ("4.1.1", '<main id="tresc">', "<main>"),
    ("1.4.1", ' <span class="stan stan-wykonane">wykonano</span>', ""),
    ("4.1.3", '<p class="czekanie" role="status" data-komunikat="Model pracuje..."></p>',
     '<p class="czekanie" hidden role="status">Model pracuje...</p>'),
    ("4.1.3", '<p class="czekanie" role="status" data-komunikat="Model pracuje..."></p>',
     '<p class="czekanie" role="status">Model pracuje...</p>'),
]


class KontrolerHtmlTest(SimpleTestCase):
    """Kontroler musi wykrywać naruszenia - inaczej przegląd stron niczego by nie dowodził."""

    def test_strona_poprawna_nie_ma_naruszen(self):
        self.assertEqual(bledy_dostepnosci(POPRAWNA), [])

    def test_kazda_usterka_jest_wykrywana_i_opisana_numerem_kryterium(self):
        for kryterium, fragment, zamiennik in USTERKI:
            with self.subTest(kryterium=kryterium, zamiennik=zamiennik):
                self.assertIn(fragment, POPRAWNA, "usterka musi zmieniać stronę wzorcową")
                bledy = bledy_dostepnosci(POPRAWNA.replace(fragment, zamiennik))
                self.assertTrue(any(blad.startswith(kryterium + " ") for blad in bledy), bledy)

    def test_pole_opisane_atrybutem_aria_label_albo_otoczone_etykieta_ma_nazwe(self):
        for pole in ('<input type="search" name="q" aria-label="Szukaj">', "<label>Szukaj <input name=\"q\"></label>"):
            strona = POPRAWNA.replace('<label for="q">Szukaj</label>', "").replace('<input type="search" name="q" id="q">', pole)
            self.assertEqual(bledy_dostepnosci(strona), [], pole)


@override_settings(ASYSTENT_DZIS="2026-11-21")
class PrzegladDostepnosciStronTest(TestCase):
    """Każda strona pokazu, dla każdego konta i na każdym etapie oceny, przechodzi kontrolę znaczników."""

    STRONY = ("zadania", "moje_dane_ezd", "kadry", "kadry_ezd", "statystyki", "przepisy", "asystent")
    maxDiff = None  # przy błędzie potrzebna jest pełna lista naruszeń, nie jej skrót

    @classmethod
    def setUpTestData(cls):
        zaladuj()

    def _strony(self):
        """(opis, odpowiedź) dla wszystkich stron HTML dostępnych w pokazie, także stron odmowy i błędu."""
        yield "niezalogowany: logowanie", Client().get(reverse("logowanie"))
        for konto in get_user_model().objects.order_by("username"):
            klient = Client()
            klient.force_login(konto)
            for nazwa in self.STRONY:
                yield f"{konto.username}: {nazwa}", klient.get(reverse(nazwa))
            yield f"{konto.username}: brak strony", klient.get("/nie-ma-takiej-strony/")
        kadry = get_user_model().objects.get(username="kadry")
        for ocena in Ocena.objects.select_related("oceniany__uzytkownik", "oceniajacy__uzytkownik"):
            for konto in (ocena.oceniany.uzytkownik, ocena.oceniajacy.uzytkownik, kadry):
                klient = Client()
                klient.force_login(konto)
                yield f"{konto.username}: ocena {ocena.pk} ({ocena.etap})", klient.get(reverse("ocena", args=[ocena.pk]))

    def test_zadna_strona_nie_narusza_wymagan_widocznych_w_znacznikach(self):
        naruszenia, zbadane = [], 0
        for opis, odpowiedz in self._strony():
            if odpowiedz.status_code == 302:
                continue  # strona niedostępna dla tej roli - przekierowanie nie ma treści
            self.assertIn(odpowiedz.status_code, (200, 403, 404), opis)
            zbadane += 1
            naruszenia += [f"{opis}: {blad}" for blad in bledy_dostepnosci(odpowiedz.content.decode())]
        self.assertGreater(zbadane, 60, "przegląd ma obejmować wszystkie konta i wszystkie oceny pokazu")
        self.assertEqual(naruszenia, [])

    def test_tytuly_stron_dwoch_ocen_tej_samej_osoby_roznia_sie(self):
        """2.4.2 Tytuł strony: karty kolejnych ocen tej samej osoby mają dać się rozróżnić na liście kart
        przeglądarki i w historii - dlatego tytuł zawiera początek okresu oceny."""
        klient = Client()
        klient.force_login(get_user_model().objects.get(username="kadry"))
        tytuly = [tytul_strony(klient.get(reverse("ocena", args=[ocena.pk])).content.decode()) for ocena in Ocena.objects.all()]
        self.assertGreater(len(tytuly), len({ocena.oceniany_id for ocena in Ocena.objects.all()}), "pokaz ma osobę z dwiema ocenami")
        self.assertEqual(len(tytuly), len(set(tytuly)), sorted(tytuly))


# --- arkusz stylów: kontrast liczony ze wzoru WCAG ---

def jasnosc(kolor: str) -> float:
    """Luminancja względna koloru #rgb albo #rrggbb (definicja z WCAG 2.1)."""
    zapis = kolor.lstrip("#")
    if len(zapis) == 3:
        zapis = "".join(znak * 2 for znak in zapis)
    kanaly = [int(zapis[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    liniowe = [kanal / 12.92 if kanal <= 0.04045 else ((kanal + 0.055) / 1.055) ** 2.4 for kanal in kanaly]
    return 0.2126 * liniowe[0] + 0.7152 * liniowe[1] + 0.0722 * liniowe[2]


def kontrast(pierwszy: str, drugi: str) -> float:
    jasniejszy, ciemniejszy = sorted((jasnosc(pierwszy), jasnosc(drugi)), reverse=True)
    return (jasniejszy + 0.05) / (ciemniejszy + 0.05)


class ArkuszStylow:
    """Reguły arkusza stylów w postaci wygodnej do liczenia kontrastu."""

    def __init__(self, tresc: str) -> None:
        bez_komentarzy = re.sub(r"/\*.*?\*/", "", tresc, flags=re.S)
        self.zmienne = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{3,6})\b", bez_komentarzy))
        self.reguly: list[tuple[str, dict[str, str]]] = []
        for selektory, cialo in re.findall(r"([^{}@;]+)\{([^{}]*)\}", bez_komentarzy):
            deklaracje = dict((nazwa.strip(), wartosc.strip()) for nazwa, wartosc in (d.split(":", 1) for d in cialo.split(";") if ":" in d))
            for selektor in selektory.split(","):
                self.reguly.append((" ".join(selektor.split()), deklaracje))

    def kolor(self, wartosc: str | None) -> str | None:
        """Kolor zapisany w wartości deklaracji: zmienna albo zapis szesnastkowy; None, gdy koloru nie ma."""
        if not wartosc:
            return None
        zmienna = re.search(r"var\(--([\w-]+)\)", wartosc)
        if zmienna:
            return self.zmienne.get(zmienna.group(1))
        zapis = re.search(r"#[0-9a-fA-F]{3,6}\b", wartosc)
        return zapis.group(0) if zapis else None

    def tlo(self, deklaracje: dict[str, str]) -> str | None:
        return self.kolor(deklaracje.get("background-color") or deklaracje.get("background"))

    def deklaracje(self, selektor: str) -> dict[str, str]:
        wynik: dict[str, str] = {}
        for nazwa, deklaracje in self.reguly:
            if nazwa == selektor:
                wynik.update(deklaracje)
        return wynik

    def tla(self) -> list[str]:
        """Wszystkie kolory tła używane w interfejsie."""
        tla = {self.tlo(deklaracje) for _, deklaracje in self.reguly} | {self.zmienne["tlo"], self.zmienne["karta"]}
        return sorted(tla - {None})

    def jasne_tla(self) -> list[str]:
        return [tlo for tlo in self.tla() if jasnosc(tlo) > 0.5]


# Jasny tekst stoi tylko na wskazanych ciemnych tłach: selektor tekstu -> selektory, które ustawiają jego tło.
JASNY_TEKST = {
    ".demo-konta button small": (".demo-konta button", ".demo-konta button:hover"),
}


class KontrastTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.styl = ArkuszStylow(STYL.read_text(encoding="utf-8"))

    def test_wzor_na_kontrast_daje_wartosci_wzorcowe(self):
        """Wartości kontrolne: czerń na bieli 21:1; szarość #767676 na bieli spełnia próg 4,5:1, a #777777 już nie."""
        self.assertAlmostEqual(kontrast("#000000", "#ffffff"), 21.0, places=2)
        self.assertGreaterEqual(kontrast("#767676", "#fff"), 4.5)
        self.assertLess(kontrast("#777777", "#fff"), 4.5)

    def test_1_4_3_tekst_i_tlo_ustawione_w_jednej_regule_maja_kontrast_co_najmniej_4_5(self):
        pary = [(selektor, self.styl.kolor(d.get("color")), self.styl.tlo(d)) for selektor, d in self.styl.reguly]
        pary = [para for para in pary if para[1] and para[2]]
        self.assertGreater(len(pary), 10)
        for selektor, tekst, tlo in pary:
            self.assertGreaterEqual(kontrast(tekst, tlo), 4.5, f"{selektor}: {tekst} na {tlo}")

    def test_1_4_3_ciemny_tekst_bez_wlasnego_tla_jest_czytelny_na_kazdym_jasnym_tle(self):
        """Kolor tekstu ustawiony bez tła może trafić na dowolną jasną powierzchnię (kartę, komunikat, pole)."""
        for selektor, deklaracje in self.styl.reguly:
            tekst = self.styl.kolor(deklaracje.get("color"))
            if not tekst or self.styl.tlo(deklaracje) or jasnosc(tekst) > 0.5:
                continue
            for tlo in self.styl.jasne_tla():
                self.assertGreaterEqual(kontrast(tekst, tlo), 4.5, f"{selektor}: {tekst} na {tlo}")

    def test_1_4_3_jasny_tekst_ma_wskazane_tlo_i_kontrast_takze_po_najechaniu(self):
        jasny_tekst = {
            selektor for selektor, d in self.styl.reguly
            if self.styl.kolor(d.get("color")) and not self.styl.tlo(d) and jasnosc(self.styl.kolor(d.get("color"))) > 0.5
        }
        self.assertEqual(jasny_tekst, set(JASNY_TEKST), "nowy jasny tekst wymaga wskazania tła, na którym stoi")
        for selektor, tla in JASNY_TEKST.items():
            tekst = self.styl.kolor(self.styl.deklaracje(selektor)["color"])
            for selektor_tla in tla:
                tlo = self.styl.tlo(self.styl.deklaracje(selektor_tla))
                self.assertIsNotNone(tlo, selektor_tla)
                self.assertGreaterEqual(kontrast(tekst, tlo), 4.5, f"{selektor}: {tekst} na {tlo} ({selektor_tla})")

    def test_1_4_3_podpowiedz_w_polu_ma_wlasny_kolor_o_kontrascie_co_najmniej_4_5(self):
        """Kolor podpowiedzi (placeholder) ustawia arkusz, bo domyślny zależy od przeglądarki."""
        deklaracje = self.styl.deklaracje("::placeholder")
        kolor = self.styl.kolor(deklaracje.get("color"))
        self.assertIsNotNone(kolor, "brak reguły ::placeholder z kolorem")
        self.assertEqual(deklaracje.get("opacity"), "1", "przeglądarka nie może rozjaśniać podpowiedzi")
        self.assertGreaterEqual(kontrast(kolor, "#ffffff"), 4.5)

    def test_1_4_11_obrys_fokusu_jest_dwukolorowy_i_widoczny_na_kazdym_tle(self):
        """Jeden kolor obrysu nie ma kontrastu 3:1 jednocześnie na jasnych kartach i na ciemnym nagłówku."""
        deklaracje = self.styl.deklaracje(":focus-visible")
        obrys, cien = self.styl.kolor(deklaracje.get("outline")), self.styl.kolor(deklaracje.get("box-shadow"))
        self.assertTrue(obrys and cien, f"obrys fokusu ma mieć dwa kolory (outline i box-shadow): {deklaracje}")
        for tlo in self.styl.tla():
            najlepszy = max(kontrast(obrys, tlo), kontrast(cien, tlo))
            self.assertGreaterEqual(najlepszy, 3.0, f"fokus na tle {tlo}: {obrys} i {cien}")

    def test_1_4_11_ramki_pol_formularza_maja_kontrast_co_najmniej_3_na_jasnych_tlach(self):
        ramki = [
            (selektor, self.styl.kolor(d["border"])) for selektor, d in self.styl.reguly
            if re.search(r"\b(input|select|textarea)\b", selektor) and self.styl.kolor(d.get("border"))
        ]
        self.assertGreater(len(ramki), 3)
        for selektor, ramka in ramki:
            for tlo in self.styl.jasne_tla():
                self.assertGreaterEqual(kontrast(ramka, tlo), 3.0, f"{selektor}: ramka {ramka} na tle {tlo}")

    def test_1_4_10_szeroka_tabela_przewija_sie_we_wlasnym_obszarze_a_kolumny_ukladu_moga_sie_zwezac(self):
        """Przy 320 px szerokości (powiększenie 400%) przewijać w poziomie wolno tylko tabelę, nie całą stronę.
        Kolumna siatki zapisana samym „1fr” nie zwęża się poniżej szerokości zawartości i rozpycha stronę."""
        self.assertEqual(self.styl.deklaracje(".przewijana").get("overflow-x"), "auto")
        siatki = 0
        for selektor, deklaracje in self.styl.reguly:
            kolumny = deklaracje.get("grid-template-columns", "")
            self.assertNotIn("fr", re.sub(r"minmax\([^()]*\)", "", kolumny), f"{selektor}: {kolumny}")
            if deklaracje.get("display") == "grid":
                # Siatka bez podanych kolumn dostaje kolumnę automatyczną, którą rozpycha najszersze pole
                # (np. lista wyboru z długą opcją) - wtedy zawartość wystaje poza kartę.
                siatki += 1
                self.assertTrue(self.styl.deklaracje(selektor).get("grid-template-columns"), f"{selektor}: siatka bez kolumn")
        self.assertGreater(siatki, 5)
        for selektor, deklaracje in self.styl.reguly:
            if deklaracje.get("white-space") == "nowrap":
                # Tekst bez zawijania rozpycha stronę, gdy jest dłuższy niż okno - wolno go użyć tylko w tabeli
                # (przewija się jej obszar) i w elemencie ukrytym wzrokowo.
                self.assertTrue(selektor.startswith(".tabela ") or selektor == ".ukryte", f"{selektor}: tekst bez zawijania")
