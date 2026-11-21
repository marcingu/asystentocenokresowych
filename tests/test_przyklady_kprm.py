"""Wymaganie: zgodność z faktycznymi arkuszami - testy referencyjne na przykładach KPRM.

Źródło: „5. Przykładowe wypełnione formularze oceny” (materiały KPRM do wyzwania, pliki DOCX).
Oceny cząstkowe przepisano z arkuszy (kolejność: kryteria obowiązkowe, potem dodatkowe).
Przykłady pokazują też błędy, które asystent ma wychwycić: zła średnia w arkuszu nr 09
i nazwa kryterium spoza wykazu w arkuszu nr 13.
"""

from fractions import Fraction

import pytest

from asystent_ocen.kryteria import bledy_kryteriow_dodatkowych
from asystent_ocen.wynik import NEGATYWNA, POZYTYWNA, niespojnosci_arkusza, oblicz_wynik

PRZYKLADY = [
    # (plik, arkusz, oceny cząstkowe, średnia dokładna, średnia wpisana w arkuszu, poziom w arkuszu, wynik w arkuszu)
    ("1) Arkusz oceny A - GLW", "A", [5, 5, 5, 7, 7, 5, 5, 5], Fraction(11, 2), "5,5", "na poziomie oczekiwań", POZYTYWNA),
    ("2) Arkusz oceny B - naczelnik", "B", [9, 5, 7, 7, 7, 5, 7, 7], Fraction(27, 4), "6,75", "powyżej oczekiwań", POZYTYWNA),
    ("3) Arkusz oceny B - kierownik odd.", "B", [9, 7, 9, 7, 7, 9, 7], Fraction(55, 7), "7,8", "powyżej oczekiwań", POZYTYWNA),
    ("4) Arkusz oceny C - główny spec.(neg)", "C", [5, 1, 5, 5, 5], Fraction(21, 5), "4,2", "na poziomie oczekiwań", NEGATYWNA),
    ("5) Arkusz oceny C - radca", "C", [5, 7, 7, 7, 7, 5], Fraction(19, 3), "6,3", "powyżej oczekiwań", POZYTYWNA),
    ("09) Arkusz oceny C - gł specjalista (neg.)", "C", [5, 1, 5, 1, 1, 5], Fraction(3), "3,3", "poniżej oczekiwań", NEGATYWNA),
    ("10) Arkusz oceny C - archiwista", "C", [5, 5, 5, 5, 5], Fraction(5), "5", "na poziomie oczekiwań", POZYTYWNA),
    ("11) Arkusz oceny C - główny analityk", "C", [7, 9, 7, 7, 5, 7], Fraction(7), "7", "powyżej oczekiwań", POZYTYWNA),
    ("12) Arkusz oceny C - specjalista (negatywna)", "C", [5, 5, 5, 3, 3, 3, 3], Fraction(27, 7), "3,8", "poniżej oczekiwań", NEGATYWNA),
    ("13) Arkusz oceny B - dyrektor dep.", "B", [9, 5, 7, 7, 7, 3, 7, 5], Fraction(25, 4), "6,25", "powyżej oczekiwań", POZYTYWNA),
]
IDS = [p[0] for p in PRZYKLADY]
ARKUSZ_Z_BLEDNA_SREDNIA = "09) Arkusz oceny C - gł specjalista (neg.)"


@pytest.mark.parametrize("plik, arkusz, oceny, srednia, srednia_wpisana, poziom, wynik", PRZYKLADY, ids=IDS)
def test_wynik_wyliczony_przez_asystenta_zgadza_sie_z_przykladowym_arkuszem(
    plik, arkusz, oceny, srednia, srednia_wpisana, poziom, wynik
):
    obliczony = oblicz_wynik(oceny)
    assert obliczony.srednia == srednia
    assert obliczony.poziom == poziom
    assert obliczony.ocena == wynik


@pytest.mark.parametrize(
    "plik, arkusz, oceny, srednia, srednia_wpisana, poziom, wynik",
    [p for p in PRZYKLADY if p[0] != ARKUSZ_Z_BLEDNA_SREDNIA],
    ids=[i for i in IDS if i != ARKUSZ_Z_BLEDNA_SREDNIA],
)
def test_poprawne_przykladowe_arkusze_nie_zglaszaja_niespojnosci(
    plik, arkusz, oceny, srednia, srednia_wpisana, poziom, wynik
):
    """Średnie obcięte do 1 miejsca (np. 27/7 -> „3,8”) są w arkuszach KPRM akceptowane."""
    assert niespojnosci_arkusza(oceny, srednia_wpisana=srednia_wpisana, poziom_wpisany=poziom, wynik_wpisany=wynik) == []


def test_jedna_ocena_1_przesadza_o_ocenie_negatywnej_mimo_sredniej_na_poziomie_oczekiwan():
    """Arkusz nr 4: średnia 4,2 (na poziomie oczekiwań), „Rzetelność” = 1 -> ocena NEGATYWNA."""
    wynik = oblicz_wynik([5, 1, 5, 5, 5])
    assert (wynik.poziom, wynik.ocena) == ("na poziomie oczekiwań", NEGATYWNA)


def test_asystent_wykrywa_bledna_srednia_wpisana_recznie_w_arkuszu_09():
    """W arkuszu nr 09 wpisano średnią 3,3, a z ocen 5, 1, 5, 1, 1, 5 wynika 3,0."""
    bledy = niespojnosci_arkusza(
        [5, 1, 5, 1, 1, 5], srednia_wpisana="3,3", poziom_wpisany="poniżej oczekiwań", wynik_wpisany=NEGATYWNA
    )
    assert {b.kod for b in bledy} == {"BLEDNA_SREDNIA"}


def test_asystent_wykrywa_nazwe_kryterium_spoza_wykazu_w_arkuszu_13():
    """W arkuszu nr 13 wpisano kryterium „Negocjacje”; w zał. nr 1 do rozp. jest „Negocjowanie”."""
    bledy = bledy_kryteriow_dodatkowych(
        "B", ["Wystąpienia publiczne", "Wykorzystywanie wiedzy i doskonalenie zawodowe", "Negocjacje"]
    )
    assert {b.kod for b in bledy} == {"KRYTERIUM_SPOZA_WYKAZU"}
