"""Wydruk arkusza oceny okresowej (arkusze A, B i C) zgodny ze wzorem z rozporządzenia.

Wzory: załączniki nr 2-4 do rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków
i sposobu przeprowadzania ocen okresowych urzędników służby cywilnej i pracowników służby cywilnej (Dz. U. poz. 470).

- `tresc_arkusza(dane)` zwraca treść arkusza w kolejności wzoru: strony wzoru -> sekcje -> bloki. Służy testom
  i podglądowi HTML (każdy blok ma atrybut `rodzaj`, każda sekcja stały `kod`).
- `generuj_arkusz_docx(dane)` rysuje tę samą treść jako dokument DOCX w formacie A4.

Zasady:
- treści stałe (tytuły, nagłówki, opisy pól, przypisy) są przepisane ze wzoru; nazwy kryteriów, skala, progi,
  limit kryteriów dodatkowych, termin sprzeciwu i precyzja średniej pochodzą z rdzenia i `przepisy.toml`;
- dane identyfikacyjne (urząd, osoby) są drukowane zawsze, a pola wynikające z czynności procesu dopiero po tej
  czynności - arkusz można wydrukować na każdym etapie (puste pola mają opisy ze wzoru, np. „(dd.mm.rrrr)”);
- część III powstaje tylko wtedy, gdy pozwala na to `walidacja.czy_drukowac_czesc_III` (przypis do części III);
- przypisy są numerowane w kolejności wystąpienia i grupowane tak jak na czterech stronach wzoru.

Kody sekcji: nazwa_urzedu, dane_ocenianego, dane_oceniajacego, kryteria_i_termin, potwierdzenie_kryteriow (część I);
rozmowa_oceniajaca, okres_oceny, oceny_czastkowe, przyznanie_oceny, uzasadnienie, wnioski_iprz, poprzednia_ocena,
wniosek_o_stopien, oceniajacy_ocena, zapoznanie_z_ocena, pouczenie (część II); wniosek_wstep, dane_urzednika,
wniosek, umotywowanie_wniosku (część III).

Źródło brzmienia: tekst rozporządzenia; kropki w przypisach, dwukropek po „Potwierdzamy” i druga strona części II
arkusza A - według skanów wzoru i przykładów KPRM (tekst wyodrębniony z PDF gubi te znaki).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from .konfiguracja import Przepisy, _ustal_przepisy
from .kryteria import _klucz, _symbol_arkusza, kryteria_obowiazkowe
from .przebieg import ProcesOceny
from .stopnie import kolejny_stopien_slownie
from .terminy import okres_podlegania_ocenie
from .walidacja import (
    NIE,
    NIE_DOTYCZY,
    TAK,
    czy_aktywna_sekcja_poprzedniej_oceny,
    czy_drukowac_czesc_III,
    pouczenie_o_sprzeciwie,
)
from .wynik import NEGATYWNA, POZYTYWNA, formatuj_srednia

ZNAK_WYBORU = "X"
JEZYK_DOKUMENTU = "pl-PL"

_OPIS_DATY = "(dd.mm.rrrr)"
_OPIS_ROKU = "(rrrr)"
_MIEJSCE_NA_STOPIEN = "………."
_MIEJSCE_NA_PODPIS = "…………………………………."


# === Dane wejściowe ===

@dataclass(frozen=True)
class Osoba:
    imie: str
    nazwisko: str
    stanowisko: str
    komorka_organizacyjna: str = ""  # wzór arkusza A nie ma tego pola

    @property
    def imie_i_nazwisko(self) -> str:
        return f"{self.imie} {self.nazwisko}".strip()


@dataclass(frozen=True)
class PoprzedniaOcena:
    """Dane sekcji „DANE DOTYCZĄCE POPRZEDNIEJ OCENY OKRESOWEJ URZĘDNIKA SŁUŻBY CYWILNEJ”."""

    ocena: str  # „pozytywna” albo „negatywna” (także stałe POZYTYWNA / NEGATYWNA z modułu `wynik`)
    poziom: str  # np. „na poziomie oczekiwań”
    data_sporzadzenia: date | None = None


@dataclass(frozen=True)
class DaneArkusza:
    """Dane do wydruku. Pola po `proces` to informacje wymagane przez wzór, których nie ma w procesie oceny."""

    nazwa_urzedu: str
    oceniany: Osoba
    oceniajacy: Osoba  # obecny oceniający (część II i III; część I - gdy nie podano `oceniajacy_czesc_I`)
    proces: ProcesOceny
    miejscowosc_oceniajacego: str = ""  # „miejscowość” przy podpisach oceniającego
    miejscowosc_ocenianego: str = ""  # „miejscowość” przy podpisach ocenianego
    oceniajacy_czesc_I: Osoba | None = None  # kto wyznaczył kryteria, gdy oceniający się zmienił (§ 9 ust. 3 rozp.)
    ostatni_dzien_na_stanowisku: date | None = None  # pole „DO” przy art. 81 ust. 6 u.s.c. (przypis do części II)
    poprzednia_ocena: PoprzedniaOcena | None = None  # drukowana tylko dla urzędnika służby cywilnej
    urzad_ma_dyrektora_generalnego: bool = True  # arkusze B i C: adresat sprzeciwu (przypis do pouczenia)
    adresat_sprzeciwu: str | None = None  # arkusz A: adresata sprzeciwu wpisuje oceniający
    rok_mianowania: int | None = None  # część III
    posiadany_stopien: int | None = None  # część III; pierwszeństwo ma wartość z formularza procesu
    data_przyznania_stopnia: date | None = None  # część III


# === Treść arkusza ===

@dataclass(frozen=True)
class Tekst:
    """Napis ze wzoru z opcjonalnym odsyłaczem do przypisu, np. „OD5):” = Tekst("OD", 5, ":")."""

    tekst: str
    przypis: int | None = None
    po_przypisie: str = ""

    @property
    def tresc(self) -> str:
        """Napis bez odsyłacza."""
        return self.tekst + self.po_przypisie


@dataclass(frozen=True)
class Przypis:
    numer: int
    tresc: str


@dataclass(frozen=True)
class Pole:
    etykieta: Tekst
    wartosc: str = ""
    podpowiedz: str = ""  # opis ze wzoru drukowany w pustym polu, np. „(dd.mm.rrrr)”

    @property
    def widoczne(self) -> str:
        return self.wartosc or self.podpowiedz


@dataclass(frozen=True)
class BlokPol:
    """Pola „etykieta - wartość”: jedno pod drugim albo (`w_wierszu`) obok siebie."""

    rodzaj: ClassVar[str] = "pola"
    pola: tuple[Pole, ...]
    w_wierszu: bool = False

    def teksty(self) -> list[str]:
        return [napis for pole in self.pola for napis in (pole.etykieta.tresc, pole.widoczne) if napis]


@dataclass(frozen=True)
class BlokKryteriow:
    """Tabela części I: kryteria obowiązkowe, kryteria dodatkowe i termin sporządzenia oceny."""

    rodzaj: ClassVar[str] = "kryteria"
    naglowek_obowiazkowych: Tekst
    naglowek_dodatkowych: Tekst
    obowiazkowe: tuple[str, ...]
    dodatkowe: tuple[str, ...]
    liczba_pol_dodatkowych: int  # liczba wierszy na kryteria dodatkowe (limit z przepisów)
    termin: Pole

    def teksty(self) -> list[str]:
        napisy = [self.naglowek_obowiazkowych.tresc, self.naglowek_dodatkowych.tresc]
        napisy += [*self.obowiazkowe, *self.dodatkowe, self.termin.etykieta.tresc, self.termin.widoczne]
        return [napis for napis in napisy if napis]


@dataclass(frozen=True)
class KolumnaSkali:
    punkty: int
    nazwa: str  # np. „Znacznie poniżej oczekiwań”; pusta, gdy przepisy nie nazywają ocen cząstkowych
    jednostka: str  # „punkt”, „punkty” albo „punktów”

    @property
    def opis_punktow(self) -> str:
        return f"{self.punkty} {self.jednostka}"


@dataclass(frozen=True)
class WierszOceny:
    nazwa: str
    ocena: int | None  # punkty ze skali albo None, gdy kryterium nie zostało jeszcze ocenione


@dataclass(frozen=True)
class BlokOcen:
    """Tabela ocen cząstkowych: kryteria w wierszach, skala w kolumnach, na końcu średnia."""

    rodzaj: ClassVar[str] = "oceny"
    naglowek_obowiazkowych: Tekst
    naglowek_ocen: Tekst  # „OCENA CZĄSTKOWA” - we wzorze nad obiema grupami kryteriów
    skala: tuple[KolumnaSkali, ...]
    obowiazkowe: tuple[WierszOceny, ...]
    naglowek_dodatkowych: Tekst
    dodatkowe: tuple[WierszOceny, ...]
    liczba_pol_dodatkowych: int
    srednia: Pole

    def teksty(self) -> list[str]:
        def wiersze(grupa: tuple[WierszOceny, ...]) -> list[str]:
            return [n for w in grupa for n in (w.nazwa, ZNAK_WYBORU if w.ocena is not None else "")]

        napisy = [self.naglowek_obowiazkowych.tresc, self.naglowek_ocen.tresc]
        napisy += [napis for kolumna in self.skala for napis in (kolumna.nazwa, kolumna.opis_punktow)]
        napisy += wiersze(self.obowiazkowe)
        napisy += [self.naglowek_dodatkowych.tresc, self.naglowek_ocen.tresc]
        napisy += wiersze(self.dodatkowe)
        napisy += [self.srednia.etykieta.tresc, self.srednia.widoczne]
        return [napis for napis in napisy if napis]


@dataclass(frozen=True)
class WierszPoziomu:
    zaznaczony: bool
    przedzial: str  # np. „powyżej 4 punktów do 6 punktów”
    poziom: str


@dataclass(frozen=True)
class Opcja:
    etykieta: Tekst
    zaznaczona: bool = False


@dataclass(frozen=True)
class BlokPrzyznaniaOceny:
    """Tabela „PRZYZNANIE OCENY”: poziomy z przedziałami średniej oraz ocena pozytywna / negatywna."""

    rodzaj: ClassVar[str] = "przyznanie_oceny"
    naglowki: tuple[Tekst, Tekst, Tekst]
    wiersze: tuple[WierszPoziomu, ...]
    naglowek_oceny: Tekst
    opcje: tuple[Opcja, ...]

    def teksty(self) -> list[str]:
        napisy = [naglowek.tresc for naglowek in self.naglowki]
        for wiersz in self.wiersze:
            napisy += [ZNAK_WYBORU if wiersz.zaznaczony else "", wiersz.przedzial, wiersz.poziom]
        napisy.append(self.naglowek_oceny.tresc)
        for opcja in self.opcje:
            napisy += [opcja.etykieta.tresc, ZNAK_WYBORU if opcja.zaznaczona else ""]
        return [napis for napis in napisy if napis]


@dataclass(frozen=True)
class BlokWyboru:
    """Pola wyboru oznaczane znakiem „X”."""

    rodzaj: ClassVar[str] = "wybor"
    opcje: tuple[Opcja, ...]

    def teksty(self) -> list[str]:
        napisy = []
        for opcja in self.opcje:
            napisy += [opcja.etykieta.tresc, ZNAK_WYBORU if opcja.zaznaczona else ""]
        return [napis for napis in napisy if napis]


@dataclass(frozen=True)
class BlokTekstu:
    """Stały tekst wzoru: akapity i (opcjonalnie) wyliczenie od myślników."""

    rodzaj: ClassVar[str] = "tekst"
    akapity: tuple[Tekst, ...]
    punkty: tuple[Tekst, ...] = ()

    def teksty(self) -> list[str]:
        return [napis.tresc for napis in (*self.akapity, *self.punkty) if napis.tresc]


@dataclass(frozen=True)
class BlokOpisowy:
    """Duże pole tekstowe (uzasadnienie, wnioski do IPRZ, umotywowanie wniosku)."""

    rodzaj: ClassVar[str] = "pole_tekstowe"
    tresc: str = ""

    def teksty(self) -> list[str]:
        return [self.tresc] if self.tresc.strip() else []


@dataclass(frozen=True)
class BlokPodpisow:
    """Wiersz podpisów: wartość nad kreską (np. miejscowość, data), opis pola pod kreską."""

    rodzaj: ClassVar[str] = "podpisy"
    kolumny: tuple[Pole, ...]

    def teksty(self) -> list[str]:
        wartosci = [kolumna.wartosc for kolumna in self.kolumny if kolumna.wartosc]
        return wartosci + [kolumna.etykieta.tresc for kolumna in self.kolumny]


@dataclass(frozen=True)
class BlokAdnotacji:
    """Adnotacja systemu, której wzór nie przewiduje (np. o fikcji zapoznania z oceną)."""

    rodzaj: ClassVar[str] = "adnotacja"
    tekst: str

    def teksty(self) -> list[str]:
        return [self.tekst]


Blok = (
    BlokPol | BlokKryteriow | BlokOcen | BlokPrzyznaniaOceny | BlokWyboru | BlokTekstu | BlokOpisowy | BlokPodpisow
    | BlokAdnotacji
)


@dataclass(frozen=True)
class Sekcja:
    kod: str
    naglowek: Tekst | None
    bloki: tuple[Blok, ...]

    def teksty(self) -> list[str]:
        napisy = [self.naglowek.tresc] if self.naglowek is not None else []
        for blok in self.bloki:
            napisy += blok.teksty()
        return napisy


@dataclass(frozen=True)
class Strona:
    """Strona wzoru: część I, część II (tabele ocen), dalszy ciąg części II, część III - z własnymi przypisami."""

    czesc: str  # „I”, „II” albo „III”
    tytul: str  # „CZĘŚĆ I” itd.; pusty na stronie będącej dalszym ciągiem części
    sekcje: tuple[Sekcja, ...]
    przypisy: tuple[Przypis, ...]

    def teksty(self) -> list[str]:
        napisy = [self.tytul] if self.tytul else []
        for sekcja in self.sekcje:
            napisy += sekcja.teksty()
        return napisy + [przypis.tresc for przypis in self.przypisy]


@dataclass(frozen=True)
class TrescArkusza:
    arkusz: str  # symbol arkusza: „A”, „B” albo „C”
    naglowek: tuple[Tekst, ...]  # tytuł arkusza
    strony: tuple[Strona, ...]

    def sekcja(self, kod: str) -> Sekcja:
        """Sekcja o podanym kodzie (lista kodów w opisie modułu); brak sekcji -> KeyError."""
        for strona in self.strony:
            for sekcja in strona.sekcje:
                if sekcja.kod == kod:
                    return sekcja
        raise KeyError(f"Arkusz {self.arkusz} nie ma sekcji o kodzie {kod!r}")

    def teksty(self) -> list[str]:
        """Wszystkie napisy widoczne na wydruku, w kolejności wzoru (bez odsyłaczy do przypisów)."""
        napisy = [naglowek.tresc for naglowek in self.naglowek]
        for strona in self.strony:
            napisy += strona.teksty()
        return napisy


# === Treści stałe wzoru (załączniki nr 2-4 do rozporządzenia) ===

@dataclass(frozen=True)
class _Wzor:
    """Różnice między wzorami arkuszy."""

    przypis_arkusza: str  # przypis nr 1 - do kogo stosuje się arkusz
    komorka_organizacyjna: bool  # pole „Komórka organizacyjna” w danych osób
    stanowisko_oceniajacego: str  # etykieta stanowiska w „DANE OCENIAJĄCEGO”
    przypis_stanowiska: bool  # przypis przy „Stanowisko pracy” ocenianego
    przypis_pouczenia: bool  # przypis o urzędzie bez dyrektora generalnego


_ARKUSZ_SLUZY = (
    "Arkusz służy do sporządzenia oceny okresowej urzędnika służby cywilnej lub pracownika służby cywilnej, "
    "zatrudnionego na stanowisku"
)
_WZORY = {
    "A": _Wzor(
        przypis_arkusza=f"{_ARKUSZ_SLUZY} kierownika urzędu, które jest stanowiskiem pracy w służbie cywilnej.",
        komorka_organizacyjna=False,
        stanowisko_oceniajacego="Stanowisko",
        przypis_stanowiska=False,
        przypis_pouczenia=False,
    ),
    "B": _Wzor(
        przypis_arkusza=f"{_ARKUSZ_SLUZY}, na którym praca polega na bezpośrednim kierowaniu pracownikami.",
        komorka_organizacyjna=True,
        stanowisko_oceniajacego="Stanowisko pracy",
        przypis_stanowiska=True,
        przypis_pouczenia=True,
    ),
    "C": _Wzor(
        przypis_arkusza=(
            f"{_ARKUSZ_SLUZY}, które nie jest:\n"
            "– stanowiskiem kierownika urzędu, będącym stanowiskiem pracy w służbie cywilnej, ani\n"
            "– stanowiskiem, na którym praca polega na bezpośrednim kierowaniu pracownikami."
        ),
        komorka_organizacyjna=True,
        stanowisko_oceniajacego="Stanowisko pracy",
        przypis_stanowiska=True,
        przypis_pouczenia=True,
    ),
}

_ROZPORZADZENIE = (
    "rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania "
    "ocen okresowych urzędników służby cywilnej i pracowników służby cywilnej"
)
_USTAWA = "ustawy z dnia 21 listopada 2008 r. o służbie cywilnej"

_POTWIERDZENIE_ROZMOWY = (
    f"przeprowadzenie rozmowy, o której mowa w § 5 ust. 1 {_ROZPORZADZENIE} (Dz. U. poz. 470), i omówienie "
    "w trakcie tej rozmowy wszystkich wymaganych zagadnień"
)
_POTWIERDZENIE_ZAPOZNANIA = "zapoznanie ocenianego z kryteriami oceny oraz terminem sporządzenia oceny."
_OSWIADCZENIE_OCENIANEGO = (
    "Przeprowadzono ze mną rozmowę oceniającą oraz zapoznałem(-łam) się z oceną okresową i wnioskami "
    "dotyczącymi indywidualnego programu rozwoju zawodowego."
)
_WSTEP_CZESCI_III = (
    "Wniosek jest wypełniany i dołączany do arkusza oceny okresowej ocenianego tylko w sytuacji skorzystania "
    f"przez oceniającego z możliwości przewidzianej w art. 89 ust. 1 {_USTAWA}."
)

_P_STANOWISKO = (
    "Należy wskazać pełną nazwę stanowiska pracy wraz z jego rozszerzeniem określającym, do jakich spraw jest to "
    "stanowisko (jeżeli zostało to określone w opisie stanowiska pracy)."
)
_P_KRYTERIA = f"Należy wpisać nazwy wybranych kryteriów, korzystając z załącznika nr 1 do {_ROZPORZADZENIE}."
_P_ROZMOWA = (
    "W trakcie rozmowy omawiane są: 1) główne obowiązki wynikające z opisu stanowiska pracy zajmowanego przez "
    "ocenianego, 2) kryteria obowiązkowe i kryteria dodatkowe, jeżeli są wybierane przez oceniającego, "
    "3) oczekiwania oceniającego co do sposobu spełniania kryteriów oceny przez ocenianego, 4) cele do "
    "osiągnięcia w okresie, w którym oceniany podlega ocenie, jeżeli ich określenie jest uzasadnione ze względu "
    "na charakter obowiązków wynikających z opisu stanowiska pracy zajmowanego przez ocenianego, a także sposób "
    "realizacji wyznaczonych celów."
)
_P_ROZMOWA_OCENIAJACA = (
    "W trakcie rozmowy oceniającej omawia się: 1) główne obowiązki wykonywane przez ocenianego w okresie, "
    "w którym podlegał ocenie, oraz sposób ich realizacji, z uwzględnieniem spełniania przez ocenianego "
    "ustalonych kryteriów oceny, 2) sposób realizowania przez ocenianego celów do osiągnięcia w okresie, "
    "w którym oceniany podlegał ocenie, jeżeli cele te zostały wyznaczone, 3) kierunki dalszego rozwoju "
    "zawodowego i potrzeby ocenianego w zakresie podnoszenia kwalifikacji i doskonalenia umiejętności."
)
_P_OD = "Data „od” oznacza datę zapoznania ocenianego z kryteriami oceny – z części I arkusza oceny."
_P_DO = (
    "Data „do” oznacza datę sporządzenia oceny na piśmie. Jeżeli ocena okresowa jest sporządzana w związku "
    f"z zastosowaniem art. 81 ust. 6 {_USTAWA} (Dz. U. z 2014 r. poz. 1111, z późn. zm.) i nie została "
    "sporządzona przed zmianą stanowiska pracy, należy w tym polu wpisać ostatni dzień pracy na zajmowanym "
    "stanowisku pracy."
)
_P_ZNAK = "Należy wstawić znak „X” w odpowiednie pole."
_P_UZASADNIENIE = (
    "Uzasadnienie jest obligatoryjne w przypadku otrzymania przez ocenianego negatywnej oceny okresowej. "
    "W przypadku przyznania oceny pozytywnej uzasadnienie jest fakultatywne. Sporządzenie uzasadnienia oceny "
    "może polegać na ogólnym omówieniu oceny lub na szczegółowym odniesieniu się do wszystkich ocen cząstkowych "
    "albo tylko do niektórych z nich."
)
_P_IPRZ = (
    "Uwzględniając sporządzoną ocenę, realizowane i przyszłe zadania oraz oczekiwania ocenianego, należy określić "
    "kierunki rozwoju zawodowego ocenianego, biorąc pod uwagę obszary wiedzy i umiejętności wymagające "
    "doskonalenia, oraz zaproponować optymalne formy i metody ich realizacji."
)
_P_OCENA = "Należy wpisać „pozytywna” lub „negatywna”."
_P_POZIOM = (
    "Należy wpisać, na jakim poziomie była przyznana poprzednia ocena okresowa (np. „na poziomie oczekiwań”)."
)
_P_DYREKTOR = (
    "W urzędzie, w którym przepisy nie przewidują tworzenia stanowiska dyrektora generalnego urzędu, sprzeciw "
    "składa się do kierownika tego urzędu."
)
_P_CZESC_III = (
    "Części III nie drukuje się i nie dołącza do arkusza oceny okresowej w przypadku ocenianego będącego "
    "pracownikiem służby cywilnej oraz w razie nieskładania wniosku o przyznanie urzędnikowi służby cywilnej "
    "kolejnego stopnia służbowego."
)


# === Pomocnicze: liczby, daty, nazwy z konfiguracji ===

def _data(dzien: date | None) -> str:
    return f"{dzien:%d.%m.%Y}" if dzien is not None else ""


def _liczba(wartosc: int | float) -> str:
    if isinstance(wartosc, float) and wartosc.is_integer():
        wartosc = int(wartosc)
    return str(wartosc).replace(".", ",")


def _punkty_po_liczebniku(liczba: int) -> str:
    """Forma po liczebniku: 1 punkt, 3 punkty, 5 punktów."""
    liczba = abs(liczba)
    if liczba == 1:
        return "punkt"
    if liczba % 10 in (2, 3, 4) and liczba % 100 not in (12, 13, 14):
        return "punkty"
    return "punktów"


def _punktow(wartosc: int | float) -> str:
    """Granica przedziału w dopełniaczu: „od 1 punktu”, „do 2 punktów”, „do 2,5 punktu”."""
    calkowita = not isinstance(wartosc, float) or wartosc.is_integer()
    return f"{_liczba(wartosc)} {'punktów' if calkowita and wartosc != 1 else 'punktu'}"


def _od_wielkiej(nazwa: str) -> str:
    return nazwa[:1].upper() + nazwa[1:]


def _nazwy_ocen_czastkowych(przepisy: Przepisy) -> dict[int, str]:
    """Nazwy ocen cząstkowych (§ 11 ust. 1 pkt 1 rozp.). Przepisy podają osobno skalę punktów i nazwy poziomów;
    w rozporządzeniu obie listy mają tę samą kolejność, więc łączy się je pozycjami. Gdy liczby pozycji się
    różnią, nazw nie ma (kolumny skali opisują wtedy same punkty)."""
    skala = sorted(przepisy.skala)
    if len(skala) != len(przepisy.poziomy):
        return {}
    return {punkty: poziom.nazwa for punkty, poziom in zip(skala, przepisy.poziomy)}


def _wylicz(nazwy: list[str]) -> str:
    """„a”, „b” albo „c” - wyliczenie nazw poziomów jak w przypisach wzoru."""
    cytaty = [f"„{nazwa}”" for nazwa in nazwy]
    if len(cytaty) <= 1:
        return "".join(cytaty)
    return f"{', '.join(cytaty[:-1])} albo {cytaty[-1]}"


def _przypisy_o_ocenie(przepisy: Przepisy) -> tuple[str, str]:
    """Przypisy przy „POZYTYWNA” i „NEGATYWNA” (§ 11 ust. 1 pkt 3 i 4 rozp.) z nazwami poziomów z przepisów."""
    pozytywne = [poziom.nazwa for poziom in reversed(przepisy.poziomy) if poziom.pozytywny]
    negatywne = [poziom.nazwa for poziom in reversed(przepisy.poziomy) if not poziom.pozytywny]
    wykluczajaca = przepisy.ocena_czastkowa_wykluczajaca_pozytywna
    nazwa = _nazwy_ocen_czastkowych(przepisy).get(wykluczajaca)
    czastkowa = f"„{nazwa}”" if nazwa else f"{wykluczajaca} {_punkty_po_liczebniku(wykluczajaca)}"
    wstep = "w przypadku ustalenia ogólnego poziomu spełniania kryteriów oceny na poziomie"
    return (
        f"{POZYTYWNA} – {wstep} {_wylicz(pozytywne)}, pod warunkiem nieuzyskania przez ocenianego żadnej z ocen "
        f"cząstkowych na poziomie {czastkowa}.",
        f"{NEGATYWNA} – {wstep} {_wylicz(negatywne)}, a także w przypadku uzyskania przez ocenianego co najmniej "
        f"jednej oceny cząstkowej na poziomie {czastkowa}.",
    )


class _Przypisy:
    """Numeruje przypisy w kolejności wystąpienia i oddaje je stronami."""

    def __init__(self) -> None:
        self._wszystkie: list[Przypis] = []
        self._oddane = 0

    def dodaj(self, tresc: str) -> int:
        self._wszystkie.append(Przypis(len(self._wszystkie) + 1, tresc))
        return len(self._wszystkie)

    def nowe(self) -> tuple[Przypis, ...]:
        nowe = tuple(self._wszystkie[self._oddane:])
        self._oddane = len(self._wszystkie)
        return nowe


def _podpis(miejscowosc: str, dzien: date | None, *dalsze: Pole) -> BlokPodpisow:
    """Miejscowość i data są wpisywane dopiero wtedy, gdy czynność została wykonana (`dzien` jest znany)."""
    return BlokPodpisow((
        Pole(Tekst("miejscowość"), miejscowosc if dzien is not None else ""),
        Pole(Tekst(f"data {_OPIS_DATY}"), _data(dzien)),
        *dalsze,
    ))


def _pola_osoby(osoba: Osoba, wzor: _Wzor, stanowisko: Tekst) -> BlokPol:
    pola = [Pole(Tekst("Imię"), osoba.imie), Pole(Tekst("Nazwisko"), osoba.nazwisko)]
    if wzor.komorka_organizacyjna:
        pola.append(Pole(Tekst("Komórka organizacyjna"), osoba.komorka_organizacyjna))
    pola.append(Pole(stanowisko, osoba.stanowisko))
    return BlokPol(tuple(pola))


# === Budowa treści ===

def tresc_arkusza(dane: DaneArkusza, przepisy: Przepisy | None = None) -> TrescArkusza:
    """Treść arkusza w kolejności wzoru. Przepisy: podane w wywołaniu, potem przepisy procesu, potem domyślne.

    Arkusz spoza wykazu w przepisach albo bez wzoru w rozporządzeniu -> ValueError.
    """
    proces = dane.proces
    przepisy = przepisy if przepisy is not None else _ustal_przepisy(proces.przepisy)
    symbol = _symbol_arkusza(proces.arkusz, przepisy)
    wzor = _WZORY.get(symbol)
    if wzor is None:
        raise ValueError(f"Rozporządzenie nie określa wzoru arkusza {symbol!r} (wzory: {', '.join(_WZORY)})")

    przypisy = _Przypisy()
    formularz = proces.formularz
    wynik = proces.wynik
    oceniono = wynik is not None
    oceniany = dane.oceniany
    oceniajacy = dane.oceniajacy
    obowiazkowe = tuple(kryteria_obowiazkowe(symbol, przepisy))
    dodatkowe = tuple(proces.kryteria_dodatkowe)
    liczba_pol_dodatkowych = max(przepisy.max_kryteriow_dodatkowych, len(dodatkowe))

    naglowek = (
        Tekst(f"ARKUSZ {symbol}"),
        Tekst("OCENA OKRESOWA"),
        Tekst("URZĘDNIKA SŁUŻBY CYWILNEJ LUB PRACOWNIKA SŁUŻBY CYWILNEJ", przypisy.dodaj(wzor.przypis_arkusza)),
    )

    # --- strona 1: CZĘŚĆ I ---
    przypis_stanowiska = przypisy.dodaj(_P_STANOWISKO) if wzor.przypis_stanowiska else None
    sekcje_I = (
        Sekcja("nazwa_urzedu", None, (BlokPol((Pole(Tekst("NAZWA URZĘDU"), dane.nazwa_urzedu),)),)),
        Sekcja("dane_ocenianego", Tekst("DANE OCENIANEGO"), (
            _pola_osoby(oceniany, wzor, Tekst("Stanowisko pracy", przypis_stanowiska)),
        )),
        Sekcja("dane_oceniajacego", Tekst("DANE OCENIAJĄCEGO"), (
            _pola_osoby(dane.oceniajacy_czesc_I or oceniajacy, wzor, Tekst(wzor.stanowisko_oceniajacego)),
        )),
        Sekcja("kryteria_i_termin", Tekst("KRYTERIA OCENY I TERMIN SPORZĄDZENIA OCENY"), (
            BlokKryteriow(
                naglowek_obowiazkowych=Tekst("Kryteria obowiązkowe"),
                naglowek_dodatkowych=Tekst(
                    "Kryteria dodatkowe wybrane przez oceniającego "
                    f"(nie więcej niż {przepisy.max_kryteriow_dodatkowych})",
                    przypisy.dodaj(_P_KRYTERIA),
                ),
                obowiazkowe=obowiazkowe,
                dodatkowe=dodatkowe,
                liczba_pol_dodatkowych=liczba_pol_dodatkowych,
                termin=Pole(Tekst("Termin sporządzenia oceny"), _data(proces.termin), _OPIS_DATY),
            ),
        )),
        Sekcja("potwierdzenie_kryteriow", None, (
            BlokTekstu(
                akapity=(Tekst("Potwierdzamy:"),),
                punkty=(
                    Tekst(_POTWIERDZENIE_ROZMOWY, przypisy.dodaj(_P_ROZMOWA), ","),
                    Tekst(_POTWIERDZENIE_ZAPOZNANIA),
                ),
            ),
            _podpis(dane.miejscowosc_oceniajacego, proces.data_wyznaczenia_kryteriow,
                    Pole(Tekst("podpis oceniającego"))),
            _podpis(dane.miejscowosc_ocenianego, proces.data_zapoznania_z_kryteriami,
                    Pole(Tekst("podpis ocenianego"))),
        )),
    )
    strony = [Strona("I", "CZĘŚĆ I", sekcje_I, przypisy.nowe())]

    # --- strona 2: CZĘŚĆ II - rozmowa, okres i tabele ocen ---
    okres_od = okres_do = None
    if proces.data_zapoznania_z_kryteriami is not None and proces.data_sporzadzenia is not None:
        okres_od, okres_do = okres_podlegania_ocenie(
            proces.data_zapoznania_z_kryteriami, proces.data_sporzadzenia, dane.ostatni_dzien_na_stanowisku
        )
    pole_rozmowy = Pole(
        Tekst("DATA PRZEPROWADZENIA ROZMOWY OCENIAJĄCEJ", przypisy.dodaj(_P_ROZMOWA_OCENIAJACA)),
        _data(proces.data_rozmowy_oceniajacej), _OPIS_DATY,
    )
    pola_okresu = (
        Pole(Tekst("OD", przypisy.dodaj(_P_OD), ":"), _data(okres_od), _OPIS_DATY),
        Pole(Tekst("DO", przypisy.dodaj(_P_DO), ":"), _data(okres_do), _OPIS_DATY),
    )
    nazwy_ocen = _nazwy_ocen_czastkowych(przepisy)
    przyznane = {_klucz(nazwa): punkty for nazwa, punkty in proces.oceny.items()}
    naglowek_ocen = Tekst("OCENA CZĄSTKOWA", przypisy.dodaj(_P_ZNAK))
    naglowek_dodatkowych = Tekst("KRYTERIA DODATKOWE WYBRANE PRZEZ OCENIAJĄCEGO", przypisy.dodaj(_P_KRYTERIA))
    przypis_pozytywnej, przypis_negatywnej = _przypisy_o_ocenie(przepisy)

    def wiersze_ocen(nazwy: tuple[str, ...]) -> tuple[WierszOceny, ...]:
        return tuple(WierszOceny(nazwa, przyznane.get(_klucz(nazwa))) for nazwa in nazwy)

    wiersze_poziomow = []
    dolna_granica: int | float | None = None
    for poziom in przepisy.poziomy:
        poczatek = f"od {_punktow(min(przepisy.skala))}" if dolna_granica is None else f"powyżej {_punktow(dolna_granica)}"
        wiersze_poziomow.append(WierszPoziomu(
            zaznaczony=oceniono and _klucz(poziom.nazwa) == _klucz(wynik.poziom),
            przedzial=f"{poczatek} do {_punktow(poziom.do)}",
            poziom=poziom.nazwa,
        ))
        dolna_granica = poziom.do

    sekcje_II = (
        Sekcja("rozmowa_oceniajaca", None, (BlokPol((pole_rozmowy,)),)),
        Sekcja("okres_oceny", Tekst("OKRES, W KTÓRYM OCENIANY PODLEGAŁ OCENIE"), (
            BlokPol(pola_okresu, w_wierszu=True),
        )),
        Sekcja("oceny_czastkowe", None, (
            BlokOcen(
                naglowek_obowiazkowych=Tekst("KRYTERIA OBOWIĄZKOWE"),
                naglowek_ocen=naglowek_ocen,
                skala=tuple(
                    KolumnaSkali(punkty, _od_wielkiej(nazwy_ocen.get(punkty, "")), _punkty_po_liczebniku(punkty))
                    for punkty in sorted(przepisy.skala)
                ),
                obowiazkowe=wiersze_ocen(obowiazkowe),
                naglowek_dodatkowych=naglowek_dodatkowych,
                dodatkowe=wiersze_ocen(dodatkowe),
                liczba_pol_dodatkowych=liczba_pol_dodatkowych,
                srednia=Pole(
                    Tekst("Średnia arytmetyczna z ocen cząstkowych przyznanych za poszczególne kryteria oceny:"),
                    formatuj_srednia(wynik.srednia, przepisy) if oceniono else "",
                ),
            ),
        )),
        Sekcja("przyznanie_oceny", Tekst("PRZYZNANIE OCENY"), (
            BlokPrzyznaniaOceny(
                naglowki=(
                    Tekst("Należy wstawić znak „X” w odpowiednie pole"),
                    Tekst("Liczba punktów stanowiąca średnią arytmetyczną ze wszystkich ocen cząstkowych"),
                    Tekst("Ogólny poziom spełnienia kryteriów oceny"),
                ),
                wiersze=tuple(wiersze_poziomow),
                naglowek_oceny=Tekst("OCENA OKRESOWA W SŁUŻBIE CYWILNEJ"),
                opcje=(
                    Opcja(Tekst(POZYTYWNA, przypisy.dodaj(przypis_pozytywnej)), oceniono and wynik.ocena == POZYTYWNA),
                    Opcja(Tekst(NEGATYWNA, przypisy.dodaj(przypis_negatywnej)), oceniono and wynik.ocena == NEGATYWNA),
                ),
            ),
        )),
    )
    strony.append(Strona("II", "CZĘŚĆ II", sekcje_II, przypisy.nowe()))

    # --- strona 3: dalszy ciąg części II ---
    naglowek_uzasadnienia = Tekst("UZASADNIENIE PRZYZNANEJ OCENY OKRESOWEJ", przypisy.dodaj(_P_UZASADNIENIE))
    naglowek_iprz = Tekst(
        "WNIOSKI DOTYCZĄCE INDYWIDUALNEGO PROGRAMU ROZWOJU ZAWODOWEGO", przypisy.dodaj(_P_IPRZ)
    )
    poprzednia = dane.poprzednia_ocena
    if not (oceniono and czy_aktywna_sekcja_poprzedniej_oceny(urzednik=proces.urzednik)):
        poprzednia = None
    pola_poprzedniej = (
        Pole(Tekst("Ocena", przypisy.dodaj(_P_OCENA)), str(poprzednia.ocena).strip().lower() if poprzednia else ""),
        Pole(Tekst("Poziom", przypisy.dodaj(_P_POZIOM)), str(poprzednia.poziom).strip() if poprzednia else ""),
        Pole(Tekst("Data sporządzenia"), _data(poprzednia.data_sporzadzenia) if poprzednia else "", _OPIS_DATY),
    )
    odpowiedz = _klucz(formularz.wniosek_o_stopien or "") if formularz is not None else ""
    naglowek_wniosku = Tekst(
        "CZY DO OCENY OKRESOWEJ DOŁĄCZONO WNIOSEK O PRZYZNANIE KOLEJNEGO STOPNIA SŁUŻBOWEGO?",
        przypisy.dodaj(_P_ZNAK),
    )
    opcje_wniosku = (
        Opcja(Tekst(TAK), odpowiedz == _klucz(TAK)),
        Opcja(Tekst(NIE), odpowiedz == _klucz(NIE)),
        Opcja(Tekst(f"{NIE_DOTYCZY} (oceniany jest pracownikiem służby cywilnej)"), odpowiedz == _klucz(NIE_DOTYCZY)),
    )
    fikcja = bool(proces.zapoznanie_fikcyjne)
    bloki_zapoznania: list[Blok] = [
        BlokTekstu((Tekst(_OSWIADCZENIE_OCENIANEGO),)),
        _podpis(
            dane.miejscowosc_ocenianego,
            None if fikcja else proces.data_zapoznania_z_ocena,
            Pole(Tekst("imię i nazwisko lub pieczątka ocenianego"), oceniany.imie_i_nazwisko),
            Pole(Tekst("podpis ocenianego")),
        ),
    ]
    if fikcja:
        bloki_zapoznania.append(BlokAdnotacji(_adnotacja_o_fikcji(proces)))
    pouczenie = pouczenie_o_sprzeciwie(
        symbol,
        urzad_ma_dyrektora_generalnego=dane.urzad_ma_dyrektora_generalnego,
        adresat=dane.adresat_sprzeciwu,
        przepisy=przepisy,
    )
    if wzor.przypis_pouczenia:
        # We wzorze odsyłacz stoi przed kropką kończącą pouczenie: „...dyrektora generalnego urzędu17).”
        kropka = "." if pouczenie.endswith(".") else ""
        tekst_pouczenia = Tekst(pouczenie.removesuffix("."), przypisy.dodaj(_P_DYREKTOR), kropka)
    else:
        tekst_pouczenia = Tekst(pouczenie)

    sekcje_II_cd = (
        Sekcja("uzasadnienie", naglowek_uzasadnienia, (BlokOpisowy(formularz.uzasadnienie if formularz else ""),)),
        Sekcja("wnioski_iprz", naglowek_iprz, (BlokOpisowy(formularz.wnioski_iprz if formularz else ""),)),
        Sekcja(
            "poprzednia_ocena",
            Tekst("DANE DOTYCZĄCE POPRZEDNIEJ OCENY OKRESOWEJ URZĘDNIKA SŁUŻBY CYWILNEJ"),
            (BlokPol(pola_poprzedniej, w_wierszu=True),),
        ),
        Sekcja("wniosek_o_stopien", naglowek_wniosku, (BlokWyboru(opcje_wniosku),)),
        Sekcja("oceniajacy_ocena", Tekst("DANE OCENIAJĄCEGO"), (
            _pola_osoby(oceniajacy, wzor, Tekst(wzor.stanowisko_oceniajacego)),
            _podpis(dane.miejscowosc_oceniajacego, proces.data_sporzadzenia, Pole(Tekst("podpis oceniającego"))),
        )),
        Sekcja("zapoznanie_z_ocena", None, tuple(bloki_zapoznania)),
        Sekcja("pouczenie", Tekst("Pouczenie"), (BlokTekstu((tekst_pouczenia,)),)),
    )
    strony.append(Strona("II", "", sekcje_II_cd, przypisy.nowe()))

    # --- strona 4: CZĘŚĆ III - tylko przy wniosku o stopień dla urzędnika ---
    wniosek_o_stopien = formularz.wniosek_o_stopien if formularz is not None else None
    if czy_drukowac_czesc_III(urzednik=proces.urzednik, wniosek_o_stopien=wniosek_o_stopien):
        stopien = formularz.posiadany_stopien if formularz.posiadany_stopien is not None else dane.posiadany_stopien
        try:
            kolejny = kolejny_stopien_slownie(stopien, przepisy) if stopien is not None else _MIEJSCE_NA_STOPIEN
        except ValueError:  # stopień spoza zakresu albo najwyższy - miejsce do wypełnienia ręcznie
            kolejny = _MIEJSCE_NA_STOPIEN
        sekcje_III = (
            Sekcja("wniosek_wstep", None, (
                BlokTekstu((Tekst(_WSTEP_CZESCI_III, przypisy.dodaj(_P_CZESC_III)),)),
            )),
            Sekcja("dane_urzednika", Tekst("DANE URZĘDNIKA SŁUŻBY CYWILNEJ"), (
                BlokPol((
                    Pole(Tekst("Imię"), oceniany.imie),
                    Pole(Tekst("Nazwisko"), oceniany.nazwisko),
                    Pole(Tekst("Rok mianowania"), str(dane.rok_mianowania or ""), _OPIS_ROKU),
                    Pole(Tekst("Posiadany stopień służbowy"), "" if stopien is None else str(stopien)),
                    Pole(Tekst("Data przyznania stopnia służbowego"), _data(dane.data_przyznania_stopnia), _OPIS_DATY),
                )),
            )),
            Sekcja(
                "wniosek",
                Tekst("WNIOSEK O PRZYZNANIE URZĘDNIKOWI SŁUŻBY CYWILNEJ KOLEJNEGO STOPNIA SŁUŻBOWEGO"),
                (BlokTekstu((
                    Tekst("W związku z uzyskaniem przez Panią/Pana"),
                    Tekst(oceniany.imie_i_nazwisko),
                    Tekst(
                        f"pozytywnej oceny okresowej, na podstawie art. 89 ust. 1 {_USTAWA} wnioskuję "
                        f"o przyznanie {kolejny} stopnia służbowego."
                    ),
                )),),
            ),
            Sekcja("umotywowanie_wniosku", Tekst("Umotywowanie wniosku"), (
                BlokOpisowy(formularz.umotywowanie_wniosku or ""),
                _podpis(
                    dane.miejscowosc_oceniajacego,
                    proces.data_sporzadzenia,
                    Pole(Tekst("imię i nazwisko lub pieczątka oceniającego"), oceniajacy.imie_i_nazwisko),
                    Pole(Tekst("podpis oceniającego")),
                ),
            )),
        )
        strony.append(Strona("III", "CZĘŚĆ III", sekcje_III, przypisy.nowe()))

    return TrescArkusza(arkusz=symbol, naglowek=naglowek, strony=tuple(strony))


def _adnotacja_o_fikcji(proces: ProcesOceny) -> str:
    """Przypadek użycia KPRM „stwierdzenie fikcji zapoznania z oceną”; wzór arkusza takiej adnotacji nie ma."""
    kto = getattr(proces.fikcje_stwierdzil, "value", proces.fikcje_stwierdzil)
    stwierdzajacy = f" (stwierdzający: {kto})" if kto else ""
    return (
        "Adnotacja: oceniany nie potwierdził zapoznania się z oceną okresową. W dniu "
        f"{_data(proces.data_zapoznania_z_ocena)} stwierdzono fikcję zapoznania z oceną{stwierdzajacy}; "
        "dzień ten przyjmuje się za dzień zapoznania się z oceną."
    )


# === Dokument DOCX ===

_SZEROKOSC_MM = 174.0  # A4 (210 mm) minus marginesy boczne 2 x 18 mm


def generuj_arkusz_docx(dane: DaneArkusza, przepisy: Przepisy | None = None) -> bytes:
    """Arkusz jako dokument DOCX (A4) o treści z `tresc_arkusza`; każda strona wzoru zaczyna nową stronę."""
    return _Rysownik().rysuj(tresc_arkusza(dane, przepisy))


class _Rysownik:
    """Zamienia `TrescArkusza` na dokument python-docx."""

    def __init__(self) -> None:
        from docx import Document
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.shared import Mm, Pt

        self._Mm, self._Pt = Mm, Pt
        self._do_lewej = WD_ALIGN_PARAGRAPH.LEFT
        self._do_srodka = WD_ALIGN_PARAGRAPH.CENTER
        self._do_prawej = WD_ALIGN_PARAGRAPH.RIGHT
        self._obustronnie = WD_ALIGN_PARAGRAPH.JUSTIFY
        self._tabela_na_srodku = WD_TABLE_ALIGNMENT.CENTER
        self._w_pionie_na_srodku = WD_CELL_VERTICAL_ALIGNMENT.CENTER

        self.doc = Document()
        # Język treści: czytnik ekranu i konwerter PDF biorą go ze stylów dokumentu, nie z właściwości pliku
        # (dostępność cyfrowa - WCAG 2.1, kryterium 3.1.1). Szablon python-docx ma tu język angielski.
        for jezyk in self.doc.styles.element.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:lang"):
            jezyk.set(qn("w:val"), JEZYK_DOKUMENTU)
            jezyk.set(qn("w:eastAsia"), JEZYK_DOKUMENTU)
        sekcja = self.doc.sections[0]
        sekcja.page_width, sekcja.page_height = Mm(210), Mm(297)
        sekcja.left_margin = sekcja.right_margin = Mm(18)
        sekcja.top_margin = sekcja.bottom_margin = Mm(15)
        styl = self.doc.styles["Normal"]
        styl.font.name = "Times New Roman"
        styl.font.size = Pt(10)
        styl.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Times New Roman")
        styl.paragraph_format.space_before = Pt(0)
        styl.paragraph_format.space_after = Pt(0)

    # --- całość ---

    def rysuj(self, tresc: TrescArkusza) -> bytes:
        wlasciwosci = self.doc.core_properties
        wlasciwosci.title = f"Arkusz {tresc.arkusz} - ocena okresowa"
        wlasciwosci.author = "Cyfrowy Asystent Ocen Okresowych"
        wlasciwosci.language = JEZYK_DOKUMENTU

        self._akapit(tresc.naglowek[0], pogrubienie=True, rozmiar=12)
        for linia in tresc.naglowek[1:]:
            self._akapit(linia, pogrubienie=True, rozmiar=12, wyrownanie=self._do_srodka)
        for numer, strona in enumerate(tresc.strony):
            if numer:
                self.doc.add_page_break()
            if strona.tytul:
                self._akapit(strona.tytul, pogrubienie=True, rozmiar=11, wyrownanie=self._do_srodka, przed=6, po=4)
            for sekcja in strona.sekcje:
                if sekcja.naglowek is not None:
                    self._akapit(sekcja.naglowek, pogrubienie=True, przed=6, po=2, z_nastepnym=True)
                for blok in sekcja.bloki:
                    getattr(self, f"_blok_{blok.rodzaj}")(blok)
            self._przypisy(strona.przypisy)
        bufor = io.BytesIO()
        self.doc.save(bufor)
        return bufor.getvalue()

    # --- akapity i komórki ---

    def _wpisz(self, akapit, tekst: Tekst | str, *, pogrubienie=False, kursywa=False, rozmiar=None) -> None:
        if isinstance(tekst, str):
            tekst = Tekst(tekst)
        fragmenty = [(tekst.tekst, False)]
        if tekst.przypis is not None:
            fragmenty.append((f"{tekst.przypis})", True))
        fragmenty.append((tekst.po_przypisie, False))
        for napis, odsylacz in fragmenty:
            if not napis:
                continue
            run = akapit.add_run(napis)
            run.bold = pogrubienie or None
            run.italic = kursywa or None
            if rozmiar is not None:
                run.font.size = self._Pt(rozmiar)
            if odsylacz:
                run.font.superscript = True

    def _formatuj(self, akapit, *, wyrownanie=None, przed=0, po=0, z_nastepnym=False) -> None:
        if wyrownanie is not None:
            akapit.alignment = wyrownanie
        if przed:
            akapit.paragraph_format.space_before = self._Pt(przed)
        if po:
            akapit.paragraph_format.space_after = self._Pt(po)
        if z_nastepnym:
            akapit.paragraph_format.keep_with_next = True

    def _akapit(self, tekst: Tekst | str = "", *, wyrownanie=None, przed=0, po=0, z_nastepnym=False, **format):
        akapit = self.doc.add_paragraph()
        self._wpisz(akapit, tekst, **format)
        self._formatuj(akapit, wyrownanie=wyrownanie, przed=przed, po=po, z_nastepnym=z_nastepnym)
        return akapit

    def _odstep(self, punkty: float = 4) -> None:
        """Wąski pusty akapit - oddziela tabele (dwie tabele bez akapitu między nimi edytor łączy w jedną)."""
        akapit = self.doc.add_paragraph()
        akapit.paragraph_format.line_spacing = self._Pt(punkty)

    def _w_komorce(self, komorka, tekst: Tekst | str = "", *, wyrownanie=None, nowy=False, **format) -> None:
        """Wpisuje tekst do komórki: do jej pierwszego akapitu albo (`nowy`) do kolejnego."""
        akapit = komorka.add_paragraph() if nowy else komorka.paragraphs[0]
        self._wpisz(akapit, tekst, **format)
        self._formatuj(akapit, wyrownanie=wyrownanie)
        komorka.vertical_alignment = self._w_pionie_na_srodku

    def _wartosc(self, komorka, pole: Pole, *, wyrownanie=None, **format) -> None:
        """Wartość pola, a w pustym polu - opis ze wzoru drobną kursywą."""
        if pole.wartosc:
            self._w_komorce(komorka, pole.wartosc, wyrownanie=wyrownanie, **format)
        elif pole.podpowiedz:
            self._w_komorce(komorka, pole.podpowiedz, wyrownanie=wyrownanie or self._do_prawej, kursywa=True, rozmiar=8)

    def _tabela(self, wiersze: int, szerokosci: list[float], *, ramka: bool = True):
        tabela = self.doc.add_table(rows=wiersze, cols=len(szerokosci))
        if ramka:
            tabela.style = "Table Grid"
        tabela.autofit = False
        tabela.alignment = self._tabela_na_srodku
        for numer, szerokosc in enumerate(szerokosci):
            tabela.columns[numer].width = self._Mm(szerokosc)
            for wiersz in tabela.rows:
                wiersz.cells[numer].width = self._Mm(szerokosc)
        return tabela

    # --- bloki ---

    def _blok_pola(self, blok: BlokPol) -> None:
        if blok.w_wierszu:
            para = _SZEROKOSC_MM / len(blok.pola)
            etykieta = min(30.0 if len(blok.pola) > 2 else 18.0, para / 2)
            tabela = self._tabela(1, [etykieta, para - etykieta] * len(blok.pola))
            for numer, pole in enumerate(blok.pola):
                self._w_komorce(tabela.cell(0, 2 * numer), pole.etykieta, pogrubienie=True, wyrownanie=self._do_prawej)
                self._wartosc(tabela.cell(0, 2 * numer + 1), pole, wyrownanie=self._do_srodka)
        else:
            tabela = self._tabela(len(blok.pola), [62.0, _SZEROKOSC_MM - 62.0])
            for numer, pole in enumerate(blok.pola):
                self._w_komorce(tabela.cell(numer, 0), pole.etykieta, pogrubienie=True)
                self._wartosc(tabela.cell(numer, 1), pole)
        self._odstep()

    def _blok_kryteria(self, blok: BlokKryteriow) -> None:
        pola_dodatkowe = blok.liczba_pol_dodatkowych
        wiersze = max(len(blok.obowiazkowe), pola_dodatkowe + 1)
        tabela = self._tabela(1 + wiersze, [88.0, 48.0, 38.0])
        self._w_komorce(tabela.cell(0, 0), blok.naglowek_obowiazkowych, pogrubienie=True, wyrownanie=self._do_srodka)
        naglowek = tabela.cell(0, 1).merge(tabela.cell(0, 2))
        self._w_komorce(naglowek, blok.naglowek_dodatkowych, pogrubienie=True, wyrownanie=self._do_srodka)
        for numer in range(wiersze):
            if numer < len(blok.obowiazkowe):
                self._w_komorce(tabela.cell(1 + numer, 0), blok.obowiazkowe[numer])
            if numer < pola_dodatkowe:
                komorka = tabela.cell(1 + numer, 1).merge(tabela.cell(1 + numer, 2))
                if numer < len(blok.dodatkowe):
                    self._w_komorce(komorka, blok.dodatkowe[numer])
        etykieta = tabela.cell(1 + pola_dodatkowe, 1).merge(tabela.cell(wiersze, 1))
        self._w_komorce(etykieta, blok.termin.etykieta, pogrubienie=True, wyrownanie=self._do_srodka)
        wartosc = tabela.cell(1 + pola_dodatkowe, 2).merge(tabela.cell(wiersze, 2))
        self._wartosc(wartosc, blok.termin, wyrownanie=self._do_srodka)
        self._odstep()

    def _blok_tekst(self, blok: BlokTekstu) -> None:
        for akapit in blok.akapity:
            self._akapit(akapit, wyrownanie=self._obustronnie, przed=2)
        for punkt in blok.punkty:
            # Myślnik jak we wzorze („−”); wcięcie wyrównuje kolejne wiersze punktu.
            akapit = self._akapit(_z_przedrostkiem(punkt, "−\t"), wyrownanie=self._obustronnie)
            akapit.paragraph_format.left_indent = self._Mm(6)
            akapit.paragraph_format.first_line_indent = self._Mm(-6)
            akapit.paragraph_format.tab_stops.add_tab_stop(self._Mm(6))

    def _blok_pole_tekstowe(self, blok: BlokOpisowy) -> None:
        komorka = self._tabela(1, [_SZEROKOSC_MM]).cell(0, 0)
        linie = blok.tresc.splitlines() if blok.tresc.strip() else ["", "", "", ""]  # puste pole - miejsce na wpis
        for numer, linia in enumerate(linie):
            akapit = komorka.paragraphs[0] if numer == 0 else komorka.add_paragraph()
            self._wpisz(akapit, linia)
            self._formatuj(akapit, wyrownanie=self._obustronnie)
        self._odstep()

    def _blok_oceny(self, blok: BlokOcen) -> None:
        kolumny = len(blok.skala)
        szerokosc_oceny = min(21.0, 105.0 / max(kolumny, 1))
        dodatkowe = list(blok.dodatkowe)
        dodatkowe += [WierszOceny("", None)] * (blok.liczba_pol_dodatkowych - len(dodatkowe))
        wiersze = 2 + len(blok.obowiazkowe) + 1 + len(dodatkowe) + 1
        tabela = self._tabela(wiersze, [_SZEROKOSC_MM - kolumny * szerokosc_oceny] + [szerokosc_oceny] * kolumny)

        def naglowek_ocen(wiersz: int) -> None:
            komorka = tabela.cell(wiersz, 1).merge(tabela.cell(wiersz, kolumny))
            self._w_komorce(komorka, blok.naglowek_ocen, pogrubienie=True, wyrownanie=self._do_srodka)

        def wiersz_oceny(wiersz: int, kryterium: WierszOceny) -> None:
            self._w_komorce(tabela.cell(wiersz, 0), kryterium.nazwa)
            for numer, kolumna in enumerate(blok.skala):
                if kryterium.ocena == kolumna.punkty:
                    self._w_komorce(tabela.cell(wiersz, 1 + numer), ZNAK_WYBORU, pogrubienie=True,
                                    wyrownanie=self._do_srodka)

        naglowek = tabela.cell(0, 0).merge(tabela.cell(1, 0))
        self._w_komorce(naglowek, blok.naglowek_obowiazkowych, pogrubienie=True)
        naglowek_ocen(0)
        for numer, kolumna in enumerate(blok.skala):
            komorka = tabela.cell(1, 1 + numer)
            if kolumna.nazwa:
                self._w_komorce(komorka, kolumna.nazwa, wyrownanie=self._do_srodka, rozmiar=8)
            self._w_komorce(komorka, str(kolumna.punkty), wyrownanie=self._do_srodka, pogrubienie=True,
                            nowy=bool(kolumna.nazwa))
            self._w_komorce(komorka, kolumna.jednostka, wyrownanie=self._do_srodka, rozmiar=8, nowy=True)
        wiersz = 2
        for kryterium in blok.obowiazkowe:
            wiersz_oceny(wiersz, kryterium)
            wiersz += 1
        self._w_komorce(tabela.cell(wiersz, 0), blok.naglowek_dodatkowych, pogrubienie=True)
        naglowek_ocen(wiersz)
        wiersz += 1
        for kryterium in dodatkowe:
            wiersz_oceny(wiersz, kryterium)
            wiersz += 1
        na_wartosc = min(2, kolumny)  # średnia zajmuje dwie ostatnie kolumny skali
        etykieta = tabela.cell(wiersz, 0).merge(tabela.cell(wiersz, kolumny - na_wartosc))
        self._w_komorce(etykieta, blok.srednia.etykieta, pogrubienie=True)
        if na_wartosc:
            wartosc = tabela.cell(wiersz, kolumny - na_wartosc + 1).merge(tabela.cell(wiersz, kolumny))
            self._wartosc(wartosc, blok.srednia, wyrownanie=self._do_srodka, pogrubienie=True)
        self._odstep()

    def _blok_przyznanie_oceny(self, blok: BlokPrzyznaniaOceny) -> None:
        tabela = self._tabela(1 + len(blok.wiersze) + 1, [36.0, 51.0, 16.0, 55.0, 16.0])

        def para(wiersz: int, pierwsza: int):
            return tabela.cell(wiersz, pierwsza).merge(tabela.cell(wiersz, pierwsza + 1))

        self._w_komorce(tabela.cell(0, 0), blok.naglowki[0], wyrownanie=self._do_srodka, rozmiar=9)
        self._w_komorce(para(0, 1), blok.naglowki[1], pogrubienie=True, wyrownanie=self._do_srodka)
        self._w_komorce(para(0, 3), blok.naglowki[2], pogrubienie=True, wyrownanie=self._do_srodka)
        for numer, poziom in enumerate(blok.wiersze, start=1):
            if poziom.zaznaczony:
                self._w_komorce(tabela.cell(numer, 0), ZNAK_WYBORU, pogrubienie=True, wyrownanie=self._do_srodka)
            self._w_komorce(para(numer, 1), poziom.przedzial, wyrownanie=self._do_srodka)
            self._w_komorce(para(numer, 3), poziom.poziom, pogrubienie=True, wyrownanie=self._do_srodka)
        ostatni = len(blok.wiersze) + 1
        self._w_komorce(tabela.cell(ostatni, 0), blok.naglowek_oceny, pogrubienie=True, wyrownanie=self._do_srodka)
        for numer, opcja in enumerate(blok.opcje[:2]):
            self._w_komorce(tabela.cell(ostatni, 1 + 2 * numer), opcja.etykieta, pogrubienie=True,
                            wyrownanie=self._do_prawej)
            if opcja.zaznaczona:
                self._w_komorce(tabela.cell(ostatni, 2 + 2 * numer), ZNAK_WYBORU, pogrubienie=True,
                                wyrownanie=self._do_srodka)
        self._odstep()

    def _blok_wybor(self, blok: BlokWyboru) -> None:
        znak = 12.0
        na_etykiety = _SZEROKOSC_MM - znak * len(blok.opcje)
        dlugosci = [max(len(opcja.etykieta.tresc), 8) for opcja in blok.opcje]
        szerokosci: list[float] = []
        for dlugosc in dlugosci:
            szerokosci += [na_etykiety * dlugosc / sum(dlugosci), znak]
        tabela = self._tabela(1, szerokosci)
        for numer, opcja in enumerate(blok.opcje):
            self._w_komorce(tabela.cell(0, 2 * numer), opcja.etykieta, pogrubienie=True, wyrownanie=self._do_prawej)
            if opcja.zaznaczona:
                self._w_komorce(tabela.cell(0, 2 * numer + 1), ZNAK_WYBORU, pogrubienie=True,
                                wyrownanie=self._do_srodka)
        self._odstep()

    def _blok_podpisy(self, blok: BlokPodpisow) -> None:
        self._odstep(10)
        tabela = self._tabela(2, [_SZEROKOSC_MM / len(blok.kolumny)] * len(blok.kolumny), ramka=False)
        for numer, kolumna in enumerate(blok.kolumny):
            self._w_komorce(tabela.cell(0, numer), kolumna.wartosc or _MIEJSCE_NA_PODPIS, wyrownanie=self._do_srodka)
            self._w_komorce(tabela.cell(1, numer), kolumna.etykieta, wyrownanie=self._do_srodka, kursywa=True,
                            rozmiar=8)
        self._odstep()

    def _blok_adnotacja(self, blok: BlokAdnotacji) -> None:
        self._akapit(blok.tekst, kursywa=True, wyrownanie=self._obustronnie, przed=4, po=4)

    def _przypisy(self, przypisy: tuple[Przypis, ...]) -> None:
        if not przypisy:
            return
        self._akapit("_" * 30, rozmiar=6, przed=6)
        for przypis in przypisy:
            akapit = self.doc.add_paragraph()
            self._wpisz(akapit, Tekst("", przypis.numer, f" {przypis.tresc}"), rozmiar=8)
            self._formatuj(akapit, wyrownanie=self._obustronnie)


def _z_przedrostkiem(tekst: Tekst, przedrostek: str) -> Tekst:
    """Kopia napisu z przedrostkiem (np. myślnikiem wyliczenia) - odsyłacz i końcówka bez zmian."""
    return Tekst(przedrostek + tekst.tekst, tekst.przypis, tekst.po_przypisie)
