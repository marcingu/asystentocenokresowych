"""Wynik oceny: oceny cząstkowe -> średnia -> poziom -> ocena pozytywna/negatywna (rozp. § 11)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from .bledy import Blad
from .konfiguracja import Przepisy, _ustal_przepisy
from .kryteria import _klucz, kryteria_obowiazkowe

POZYTYWNA = "POZYTYWNA"
NEGATYWNA = "NEGATYWNA"

_ZAPIS_SREDNIEJ = re.compile(r"(\d+)(?:[.,](\d+))?")


@dataclass(frozen=True)
class WynikOceny:
    srednia: Fraction  # dokładna średnia arytmetyczna (bez błędów zaokrągleń na granicach przedziałów)
    poziom: str  # np. "na poziomie oczekiwań"
    ocena: str  # POZYTYWNA albo NEGATYWNA


def _czy_w_skali(wartosc: object, przepisy: Przepisy) -> bool:
    """Ocena cząstkowa musi być liczbą całkowitą ze skali (wartości logiczne nie są ocenami)."""
    return isinstance(wartosc, int) and not isinstance(wartosc, bool) and wartosc in przepisy.skala


def oblicz_wynik(
    oceny_czastkowe: Sequence[int] | Mapping[str, int], przepisy: Przepisy | None = None
) -> WynikOceny:
    """§ 11 ust. 1 pkt 1-4 rozp. Wartości spoza skali lub brak ocen -> ValueError."""
    przepisy = _ustal_przepisy(przepisy)
    if isinstance(oceny_czastkowe, Mapping):
        wartosci = list(oceny_czastkowe.values())
    else:
        wartosci = list(oceny_czastkowe)
    if not wartosci:
        raise ValueError("Brak ocen cząstkowych - nie można ustalić wyniku oceny")
    spoza_skali = [wartosc for wartosc in wartosci if not _czy_w_skali(wartosc, przepisy)]
    if spoza_skali:
        skala = ", ".join(str(punkty) for punkty in przepisy.skala)
        raise ValueError(f"Oceny cząstkowe spoza skali ({skala}): {spoza_skali}")

    srednia = Fraction(sum(wartosci), len(wartosci))
    poziom = _poziom(srednia, przepisy)
    # § 11 ust. 1 pkt 3-4: ocena pozytywna wymaga odpowiedniego poziomu ogólnego i braku oceny cząstkowej
    # „znacznie poniżej oczekiwań”.
    wykluczona = przepisy.ocena_czastkowa_wykluczajaca_pozytywna in wartosci
    ocena = POZYTYWNA if poziom.pozytywny and not wykluczona else NEGATYWNA
    return WynikOceny(srednia=srednia, poziom=poziom.nazwa, ocena=ocena)


def _poziom(srednia: Fraction, przepisy: Przepisy):
    """Pierwszy poziom, którego górna granica nie jest mniejsza od średniej (przedziały lewostronnie otwarte)."""
    if srednia < min(przepisy.skala):
        raise ValueError(f"Średnia {srednia} jest niższa od najniższej oceny w skali")
    for poziom in przepisy.poziomy:
        if srednia <= poziom.do:
            return poziom
    raise ValueError(f"Średnia {srednia} przekracza górną granicę najwyższego poziomu")


def poziom_dla_sredniej(srednia: Fraction, przepisy: Przepisy | None = None) -> str:
    """§ 11 ust. 1 pkt 2 rozp.: [1-2], (2-4], (4-6], (6-8], (8-9]."""
    return _poziom(Fraction(srednia), _ustal_przepisy(przepisy)).nazwa


def _zaokraglij_do_calosci(wartosc: Fraction) -> int:
    """Zaokrąglenie arytmetyczne: połówki w górę (wartości są nieujemne)."""
    return (2 * wartosc.numerator + wartosc.denominator) // (2 * wartosc.denominator)


def formatuj_srednia(srednia: Fraction, przepisy: Przepisy | None = None) -> str:
    """Prezentacja średniej: przecinek dziesiętny, liczba miejsc z `miejsca_po_przecinku_sredniej`
    (domyślnie 1 - decyzja zespołu z 21.11.2026), zaokrąglenie arytmetyczne (połówki w górę)."""
    przepisy = _ustal_przepisy(przepisy)
    miejsca = przepisy.miejsca_po_przecinku_sredniej
    calosci, ulamek = divmod(_zaokraglij_do_calosci(Fraction(srednia) * 10**miejsca), 10**miejsca)
    return f"{calosci},{ulamek:0{miejsca}d}" if miejsca else str(calosci)


def bledy_ocen_czastkowych(
    arkusz: str,
    kryteria_dodatkowe: Sequence[str],
    oceny: Mapping[str, int],
    przepisy: Przepisy | None = None,
) -> list[Blad]:
    """Kody: BRAK_OCENY_KRYTERIUM, OCENA_SPOZA_SKALI, OCENA_NIEWYBRANEGO_KRYTERIUM."""
    przepisy = _ustal_przepisy(przepisy)
    wymagane: dict[str, str] = {}  # klucz porównawczy -> nazwa kryterium
    for nazwa in [*kryteria_obowiazkowe(arkusz, przepisy), *kryteria_dodatkowe]:
        if _klucz(nazwa):
            wymagane.setdefault(_klucz(nazwa), nazwa)
    wpisane = {_klucz(nazwa): (nazwa, wartosc) for nazwa, wartosc in oceny.items()}
    skala = ", ".join(str(punkty) for punkty in przepisy.skala)

    bledy: list[Blad] = []
    for klucz, nazwa in wymagane.items():
        if klucz not in wpisane or wpisane[klucz][1] is None:
            bledy.append(Blad(
                "BRAK_OCENY_KRYTERIUM",
                f"Kryterium „{nazwa}” nie ma oceny cząstkowej.",
                "§ 11 ust. 1 pkt 1 rozp.",
            ))
    for klucz, (nazwa, wartosc) in wpisane.items():
        if klucz not in wymagane:
            bledy.append(Blad(
                "OCENA_NIEWYBRANEGO_KRYTERIUM",
                f"Oceniono kryterium „{nazwa}”, które nie jest kryterium obowiązkowym arkusza ani wybranym "
                "kryterium dodatkowym.",
                "§ 5 ust. 2-3 i § 11 ust. 1 pkt 1 rozp.",
            ))
        elif wartosc is not None and not _czy_w_skali(wartosc, przepisy):
            bledy.append(Blad(
                "OCENA_SPOZA_SKALI",
                f"Ocena cząstkowa {wartosc!r} kryterium „{nazwa}” jest spoza skali ({skala}).",
                "§ 11 ust. 1 pkt 1 rozp.",
            ))
    return bledy


def _czy_srednia_zgodna(wpisana: str, srednia: Fraction) -> bool:
    """Czy zapis średniej to dokładna średnia zaokrąglona albo obcięta do zapisanej liczby miejsc."""
    zapis = _ZAPIS_SREDNIEJ.fullmatch(wpisana.strip())
    if zapis is None:
        return False
    cyfry_po_przecinku = zapis.group(2) or ""
    mnoznik = 10 ** len(cyfry_po_przecinku)
    jednostki = int(zapis.group(1) + cyfry_po_przecinku)
    przeskalowana = srednia * mnoznik
    obcieta = przeskalowana.numerator // przeskalowana.denominator
    return jednostki in (obcieta, _zaokraglij_do_calosci(przeskalowana))


def niespojnosci_arkusza(
    oceny: Sequence[int] | Mapping[str, int],
    *,
    srednia_wpisana: str | None = None,
    poziom_wpisany: str | None = None,
    wynik_wpisany: str | None = None,
    przepisy: Przepisy | None = None,
) -> list[Blad]:
    """Kontrola arkusza wypełnionego ręcznie lub zaimportowanego: BLEDNA_SREDNIA, BLEDNY_POZIOM,
    BLEDNY_WYNIK. Średnia wpisana (np. "3,8") jest zgodna, gdy równa się dokładnej średniej zaokrąglonej
    albo obciętej do liczby miejsc po przecinku zapisanej w arkuszu (przykładowe arkusze KPRM obcinają:
    27/7 -> „3,8”). Pusta średnia wpisana nie jest sprawdzana."""
    przepisy = _ustal_przepisy(przepisy)
    wynik = oblicz_wynik(oceny, przepisy)
    bledy: list[Blad] = []
    if srednia_wpisana is not None and str(srednia_wpisana).strip():
        if not _czy_srednia_zgodna(str(srednia_wpisana), wynik.srednia):
            bledy.append(Blad(
                "BLEDNA_SREDNIA",
                f"Wpisana średnia „{srednia_wpisana}” nie zgadza się z ocenami cząstkowymi - wynika z nich "
                f"{formatuj_srednia(wynik.srednia, przepisy)}.",
                "§ 11 ust. 1 pkt 2 rozp.",
            ))
    if poziom_wpisany is not None and _klucz(poziom_wpisany):
        if _klucz(poziom_wpisany) != _klucz(wynik.poziom):
            bledy.append(Blad(
                "BLEDNY_POZIOM",
                f"Wpisany poziom „{poziom_wpisany}” nie odpowiada średniej "
                f"{formatuj_srednia(wynik.srednia, przepisy)} - właściwy poziom to „{wynik.poziom}”.",
                "§ 11 ust. 1 pkt 2 rozp.",
            ))
    if wynik_wpisany is not None and _klucz(wynik_wpisany):
        if _klucz(wynik_wpisany) != _klucz(wynik.ocena):
            bledy.append(Blad(
                "BLEDNY_WYNIK",
                f"Wpisano ocenę „{wynik_wpisany}”, a z ocen cząstkowych wynika ocena {wynik.ocena}.",
                "§ 11 ust. 1 pkt 3 i 4 rozp.",
            ))
    return bledy
