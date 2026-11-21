"""Wiedza o pracy pracownika: jawne, sprawdzalne wskaźniki liczone z danych kancelaryjnych (np. EZD RP).

Zasady (dokumentacja/analiza-prawna-ai-act-kp-rodo.md):
- wskaźniki liczy zwykły kod według reguł określonych przez ludzi - to nie jest system AI (motyw 12 AI Act);
- nie ma oceny zbiorczej, rankingu ani propozycji ocen: wskaźniki są faktami dla oceniającego i ocenianego;
- każdy wskaźnik podaje liczność i źródła (znaki spraw, identyfikatory dokumentów), żeby dało się go sprawdzić;
- poniżej minimalnej liczności (`min_licznosc_wskaznika`) mediana i wskaźniki procentowe nie są liczone.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from .zgodnosc import Wymogi, wczytaj_wymogi

# statusy sprawy
W_TOKU = "w toku"
ZAKONCZONA = "zakończona"
ZAWIESZONA = "zawieszona"
ODLOZONA = "odłożona"
# wyniki akceptacji projektu pisma
ZAAKCEPTOWANY = "zaakceptowany"
ODRZUCONY = "odrzucony"
DO_AKCEPTACJI = "do akceptacji"
ANULOWANY = "anulowany"
# wyniki odwołania
UTRZYMANA = "utrzymana"
UCHYLONA = "uchylona"
ZMIENIONA = "zmieniona"
ODWOLANIE_W_TOKU = "w toku"
NIEROZPOZNANY = "nierozpoznany"

KODY_WSKAZNIKOW = (
    "SPRAWY_ZAKONCZONE",
    "MEDIANA_CZASU_ZALATWIENIA",
    "TERMINOWOSC",
    "SPRAWY_W_TOKU_PO_TERMINIE",
    "PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM",
    "PROJEKTY_ODRZUCONE",
    "ROZSTRZYGNIECIA_UTRZYMANE",
)

_NAZWY = {
    "SPRAWY_ZAKONCZONE": "Sprawy zakończone w okresie",
    "MEDIANA_CZASU_ZALATWIENIA": "Mediana czasu załatwienia sprawy (dni kalendarzowe od wszczęcia do zakończenia)",
    "TERMINOWOSC": "Sprawy zakończone w terminie (wśród zakończonych spraw z terminem załatwienia)",
    "SPRAWY_W_TOKU_PO_TERMINIE": "Sprawy w toku po terminie załatwienia (stan na koniec okresu)",
    "PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM": "Projekty pism zaakceptowane za pierwszym razem",
    "PROJEKTY_ODRZUCONE": "Odrzucenia projektów pism przez akceptującego",
    "ROZSTRZYGNIECIA_UTRZYMANE": "Rozstrzygnięcia utrzymane po odwołaniu",
}

# statusy, przy których sprawa niezakończona nie jest liczona jako przeterminowana
_STATUSY_POZA_PRZETERMINOWANIEM = (ZAWIESZONA, ODLOZONA)
# wyniki akceptacji będące rozstrzygnięciem o projekcie pisma
_ROZSTRZYGNIECIA_PROJEKTU = (ZAAKCEPTOWANY, ODRZUCONY)
# wyniki odwołania rozpoznanego przez organ odwoławczy
_ROZSTRZYGNIECIA_ODWOLANIA = (UTRZYMANA, UCHYLONA, ZMIENIONA)


@dataclass(frozen=True)
class SprawaEzd:
    id: str
    znak: str
    tytul: str
    status: str
    data_wszczecia: date
    termin_zalatwienia: date | None = None
    data_zakonczenia: date | None = None
    czas_realizacji_dni: int | None = None  # pole czasRealizacjiDni z API; znaczenie do potwierdzenia na instancji
    do_poprawy: bool = False


@dataclass(frozen=True)
class AkceptacjaEzd:
    id_dokumentu: str
    wynik: str
    data: date
    akceptujacy: str = ""
    opis: str = ""
    wersja: str | None = None


@dataclass(frozen=True)
class Odwolanie:
    znak_sprawy: str
    wynik: str
    data_rozstrzygniecia: date | None = None


@dataclass(frozen=True)
class Wskaznik:
    kod: str
    nazwa: str
    wartosc: Fraction | int | None  # dla "%" ułamek z przedziału 0-1; None = nie policzono
    jednostka: str  # "szt.", "dni" albo "%"
    licznosc: int  # liczba zdarzeń, z których policzono wskaźnik
    zrodla: tuple[str, ...] = ()  # znaki spraw albo identyfikatory dokumentów objętych wskaźnikiem
    szczegoly: tuple[str, ...] = ()  # opisy przypadków do sprawdzenia przez człowieka
    uwaga: str | None = None  # np. „za mało danych (n=4, wymagane 5)”


def wskazniki_pracy(
    *,
    sprawy: Iterable[SprawaEzd],
    akceptacje: Iterable[AkceptacjaEzd] = (),
    odwolania: Iterable[Odwolanie] = (),
    od: date,
    do: date,
    wymogi: Wymogi | None = None,
) -> list[Wskaznik]:
    """Karta faktów za okres [od, do] (obie daty włącznie). Zwraca dokładnie wskaźniki z KODY_WSKAZNIKOW,
    w tej kolejności.

    SPRAWY_ZAKONCZONE (szt.) - sprawy z `data_zakonczenia` w okresie. Źródła: znaki tych spraw w kolejności
        (data zakończenia, znak).
    MEDIANA_CZASU_ZALATWIENIA (dni) - mediana liczby dni kalendarzowych od wszczęcia do zakończenia tych samych
        spraw; przy parzystej liczbie spraw średnia dwóch środkowych wartości (Fraction).
    TERMINOWOSC (%) - wśród spraw zakończonych w okresie i mających termin załatwienia: udział zakończonych
        najpóźniej w dniu terminu. Liczność = liczba spraw z terminem. Szczegóły: po jednym opisie na każdą sprawę
        zakończoną po terminie (zawiera znak sprawy).
    SPRAWY_W_TOKU_PO_TERMINIE (szt.) - sprawy wszczęte najpóźniej w dniu `do`, niezakończone do dnia `do`
        (brak daty zakończenia albo data późniejsza), z terminem załatwienia wcześniejszym niż `do`;
        bez spraw zawieszonych i odłożonych. Źródła: znaki tych spraw w kolejności (termin załatwienia, znak),
        czyli od najdawniej przeterminowanej.
    PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM (%) - bierze akceptacje o wyniku zaakceptowany albo odrzucony
        z datą w okresie, grupuje po dokumencie i sprawdza pierwsze rozstrzygnięcie (najwcześniejsza data,
        przy równych datach kolejność wejściowa). Wartość = udział dokumentów, których pierwsze rozstrzygnięcie
        to akceptacja. Liczność = liczba dokumentów. Źródła: posortowane identyfikatory dokumentów.
    PROJEKTY_ODRZUCONE (szt.) - liczba rozstrzygnięć „odrzucony” w okresie. Szczegóły: dla każdego, w kolejności dat,
        opis zawierający datę, akceptującego i treść uwagi (`opis`).
    ROZSTRZYGNIECIA_UTRZYMANE (%) - wśród odwołań rozstrzygniętych w okresie (wynik utrzymana, uchylona albo
        zmieniona): udział utrzymanych. Liczność = liczba takich odwołań. Źródła: znaki spraw.

    Dla MEDIANA_CZASU_ZALATWIENIA, TERMINOWOSC, PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM i ROZSTRZYGNIECIA_UTRZYMANE:
    gdy liczność < `min_licznosc_wskaznika`, wartość = None, a `uwaga` zawiera „za mało danych” oraz liczność
    i wymagane minimum. Wskaźniki liczbowe (szt.) są podawane zawsze."""
    if od > do:
        raise ValueError(f"Początek okresu ({od}) jest późniejszy niż jego koniec ({do}).")
    minimum = (wczytaj_wymogi() if wymogi is None else wymogi).min_licznosc_wskaznika
    sprawy = list(sprawy)

    def w_okresie(dzien: date | None) -> bool:
        return dzien is not None and od <= dzien <= do

    # --- szybkość i terminowość spraw ---
    zakonczone = sorted(
        (s for s in sprawy if w_okresie(s.data_zakonczenia)), key=lambda s: (s.data_zakonczenia, s.znak)
    )
    znaki_zakonczonych = tuple(s.znak for s in zakonczone)
    czasy = [(s.data_zakonczenia - s.data_wszczecia).days for s in zakonczone]
    z_terminem = [s for s in zakonczone if s.termin_zalatwienia is not None]
    po_terminie = [s for s in z_terminem if s.data_zakonczenia > s.termin_zalatwienia]
    w_toku_po_terminie = sorted(
        (
            s
            for s in sprawy
            if s.data_wszczecia <= do
            and (s.data_zakonczenia is None or s.data_zakonczenia > do)
            and s.termin_zalatwienia is not None
            and s.termin_zalatwienia < do
            and s.status not in _STATUSY_POZA_PRZETERMINOWANIEM
        ),
        key=lambda s: (s.termin_zalatwienia, s.znak),
    )

    # --- uwagi przełożonych do projektów pism ---
    # wynik sprawdzany przed datą: wpisy bez rozstrzygnięcia nie biorą udziału w żadnym porównaniu dat
    rozstrzygniecia = [a for a in akceptacje if a.wynik in _ROZSTRZYGNIECIA_PROJEKTU and w_okresie(a.data)]
    pierwsze: dict[str, AkceptacjaEzd] = {}
    for akceptacja in rozstrzygniecia:
        dotychczasowa = pierwsze.get(akceptacja.id_dokumentu)
        # ostra nierówność: przy równych datach zostaje wpis wcześniejszy w kolejności wejściowej
        if dotychczasowa is None or akceptacja.data < dotychczasowa.data:
            pierwsze[akceptacja.id_dokumentu] = akceptacja
    zaakceptowane_od_razu = sum(1 for a in pierwsze.values() if a.wynik == ZAAKCEPTOWANY)
    odrzucenia = sorted((a for a in rozstrzygniecia if a.wynik == ODRZUCONY), key=lambda a: a.data)

    # --- utrzymanie rozstrzygnięć po odwołaniu ---
    rozstrzygniete = sorted(
        (o for o in odwolania if o.wynik in _ROZSTRZYGNIECIA_ODWOLANIA and w_okresie(o.data_rozstrzygniecia)),
        key=lambda o: (o.data_rozstrzygniecia, o.znak_sprawy),
    )
    utrzymane = sum(1 for o in rozstrzygniete if o.wynik == UTRZYMANA)

    karta = {
        w.kod: w
        for w in (
            _licznik("SPRAWY_ZAKONCZONE", len(zakonczone), zrodla=znaki_zakonczonych),
            _z_minimum(
                "MEDIANA_CZASU_ZALATWIENIA", "dni", _mediana(czasy), len(czasy), minimum, zrodla=znaki_zakonczonych
            ),
            _z_minimum(
                "TERMINOWOSC",
                "%",
                _udzial(len(z_terminem) - len(po_terminie), len(z_terminem)),
                len(z_terminem),
                minimum,
                zrodla=tuple(s.znak for s in z_terminem),
                szczegoly=tuple(_opis_sprawy_po_terminie(s) for s in po_terminie),
            ),
            _licznik(
                "SPRAWY_W_TOKU_PO_TERMINIE",
                len(w_toku_po_terminie),
                zrodla=tuple(s.znak for s in w_toku_po_terminie),
            ),
            _z_minimum(
                "PROJEKTY_ZAAKCEPTOWANE_ZA_PIERWSZYM_RAZEM",
                "%",
                _udzial(zaakceptowane_od_razu, len(pierwsze)),
                len(pierwsze),
                minimum,
                zrodla=tuple(sorted(pierwsze)),
            ),
            _licznik(
                "PROJEKTY_ODRZUCONE",
                len(odrzucenia),
                zrodla=tuple(sorted({a.id_dokumentu for a in odrzucenia})),
                szczegoly=tuple(_opis_odrzucenia(a) for a in odrzucenia),
            ),
            _z_minimum(
                "ROZSTRZYGNIECIA_UTRZYMANE",
                "%",
                _udzial(utrzymane, len(rozstrzygniete)),
                len(rozstrzygniete),
                minimum,
                zrodla=tuple(o.znak_sprawy for o in rozstrzygniete),
            ),
        )
    }
    return [karta[kod] for kod in KODY_WSKAZNIKOW]


def formatuj_wskaznik(wskaznik: Wskaznik) -> str:
    """Tekst do karty faktów: „5” (szt.), „20 dni”, „18,5 dni”, „80%” (zaokrąglenie arytmetyczne do pełnych
    procentów, połówki w górę); gdy wartość = None - treść pola `uwaga`."""
    if wskaznik.wartosc is None:
        return wskaznik.uwaga or ""
    wartosc = Fraction(wskaznik.wartosc)
    if wskaznik.jednostka == "%":
        return f"{_zaokraglij(wartosc * 100)}%"
    if wskaznik.jednostka == "szt.":
        return _liczba_pl(wartosc)
    if wskaznik.jednostka == "dni" and wartosc == 1:
        return "1 dzień"
    return f"{_liczba_pl(wartosc)} {wskaznik.jednostka}"


def _licznik(kod: str, liczba: int, *, zrodla: tuple[str, ...] = (), szczegoly: tuple[str, ...] = ()) -> Wskaznik:
    """Wskaźnik liczbowy (szt.) - podawany zawsze, także przy małej liczbie zdarzeń."""
    return Wskaznik(
        kod=kod, nazwa=_NAZWY[kod], wartosc=liczba, jednostka="szt.", licznosc=liczba, zrodla=zrodla, szczegoly=szczegoly
    )


def _z_minimum(
    kod: str,
    jednostka: str,
    wartosc: Fraction | int | None,
    licznosc: int,
    minimum: int,
    *,
    zrodla: tuple[str, ...] = (),
    szczegoly: tuple[str, ...] = (),
) -> Wskaznik:
    """Mediana albo udział: poniżej minimalnej liczności wartość nie jest podawana, a powód trafia do `uwaga`."""
    wymagane = max(minimum, 1)  # z zera zdarzeń nie da się policzyć mediany ani udziału
    uwaga = None
    if licznosc < wymagane:
        wartosc, uwaga = None, f"za mało danych (n={licznosc}, wymagane {wymagane})"
    return Wskaznik(
        kod=kod,
        nazwa=_NAZWY[kod],
        wartosc=wartosc,
        jednostka=jednostka,
        licznosc=licznosc,
        zrodla=zrodla,
        szczegoly=szczegoly,
        uwaga=uwaga,
    )


def _mediana(wartosci: list[int]) -> Fraction | int | None:
    """Wartość środkowa; przy parzystej liczbie - średnia dwóch środkowych jako Fraction. Pusta lista -> None."""
    if not wartosci:
        return None
    uporzadkowane = sorted(wartosci)
    srodek, nieparzysta = divmod(len(uporzadkowane), 2)
    if nieparzysta:
        return uporzadkowane[srodek]
    return Fraction(uporzadkowane[srodek - 1] + uporzadkowane[srodek], 2)


def _udzial(licznik: int, mianownik: int) -> Fraction | None:
    return Fraction(licznik, mianownik) if mianownik else None


def _zaokraglij(wartosc: Fraction) -> int:
    """Zaokrąglenie arytmetyczne do liczby całkowitej, połówki w górę (round() zaokrągla połówki do parzystej)."""
    return math.floor(wartosc + Fraction(1, 2))


def _liczba_pl(wartosc: Fraction) -> str:
    """Liczba całkowita bez części ułamkowej, pozostałe z jedną cyfrą po przecinku."""
    if wartosc.denominator == 1:
        return str(wartosc.numerator)
    dziesiate = _zaokraglij(abs(wartosc) * 10)
    return f"{'-' if wartosc < 0 else ''}{dziesiate // 10},{dziesiate % 10}"


def _dni_pl(liczba: int) -> str:
    return "1 dzień" if liczba == 1 else f"{liczba} dni"


def _opis_sprawy_po_terminie(sprawa: SprawaEzd) -> str:
    opoznienie = (sprawa.data_zakonczenia - sprawa.termin_zalatwienia).days
    return (
        f"{sprawa.znak}: zakończona {sprawa.data_zakonczenia:%d.%m.%Y}, termin załatwienia "
        f"{sprawa.termin_zalatwienia:%d.%m.%Y} ({_dni_pl(opoznienie)} po terminie)"
    )


def _opis_odrzucenia(akceptacja: AkceptacjaEzd) -> str:
    wersja = f" (wersja {akceptacja.wersja})" if akceptacja.wersja else ""
    return (
        f"{akceptacja.data:%d.%m.%Y}, dokument {akceptacja.id_dokumentu}{wersja}, "
        f"akceptujący: {akceptacja.akceptujacy or '(nie podano)'}, uwaga: {akceptacja.opis or '(bez uwag)'}"
    )
