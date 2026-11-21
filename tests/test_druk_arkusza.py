"""Wymaganie: wydruk arkusza oceny okresowej zgodny ze wzorem z rozporządzenia (arkusze A, B i C).

Źródła (ścieżki względem katalogu `kod/`):
- WZÓR: `../tekst/1. Akty prawne/1. Rozporządzenie w sprawie ocen okresowych.pdf.txt` - rozporządzenie Prezesa Rady
  Ministrów z dnia 4 kwietnia 2016 r. (Dz. U. poz. 470): załącznik nr 2 - arkusz A (wiersze 333-671 pliku),
  załącznik nr 3 - arkusz B (wiersze 675-946), załącznik nr 4 - arkusz C (wiersze 950-1222);
- skany wzoru: `../tekst/4. Formularze ocen/schematy widoku formularza X oceny okresowej/wzór formularza oceny
  okresowej arkusz X.pdf.ocr.txt` i opis pól `formularz oceny okresowej X - schemat pól formularza.docx.md`;
- przykłady KPRM: `../tekst/5. Przykładowe wypełnione formularze oceny/` (pliki wskazane przy testach).

Rozbieżności źródeł: tekst rozporządzenia wyodrębniony z PDF gubi kropki w przypisach i dwukropek po słowie
„Potwierdzamy”, a stronę 10 Dz. U. (druga strona części II arkusza A) zapisuje podwójnie i nieczytelnie. W tych
miejscach testy przyjmują brzmienie ze skanów wzoru (OCR) i z przykładów KPRM, zgodne z analogicznymi stronami
arkuszy B i C w tekście rozporządzenia. Nagłówków „Załącznik nr ...” i „WZÓR” wydruk nie powtarza.
"""

from __future__ import annotations

import io
from dataclasses import fields, is_dataclass, replace

import pytest
from docx import Document
from docx.text.paragraph import Paragraph

from asystent_ocen.druk import (
    BlokAdnotacji,
    BlokKryteriow,
    BlokOcen,
    BlokOpisowy,
    BlokPodpisow,
    BlokPol,
    BlokPrzyznaniaOceny,
    BlokWyboru,
    DaneArkusza,
    Osoba,
    PoprzedniaOcena,
    Tekst,
    generuj_arkusz_docx,
    tresc_arkusza,
)
from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.przebieg import ProcesOceny, Rola
from asystent_ocen.walidacja import pouczenie_o_sprzeciwie
from stale import OBOWIAZKOWE_A, OBOWIAZKOWE_B, OBOWIAZKOWE_C, d

OBOWIAZKOWE = {"A": OBOWIAZKOWE_A, "B": OBOWIAZKOWE_B, "C": OBOWIAZKOWE_C}

# --- Treści stałe przepisane ze wzoru (rozporządzenie, załączniki nr 2-4) ---

POTWIERDZENIE_ROZMOWY = (
    "przeprowadzenie rozmowy, o której mowa w § 5 ust. 1 rozporządzenia Prezesa Rady Ministrów z dnia "
    "4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych urzędników służby cywilnej "
    "i pracowników służby cywilnej (Dz. U. poz. 470), i omówienie w trakcie tej rozmowy wszystkich wymaganych "
    "zagadnień"
)
OSWIADCZENIE_OCENIANEGO = (
    "Przeprowadzono ze mną rozmowę oceniającą oraz zapoznałem(-łam) się z oceną okresową i wnioskami "
    "dotyczącymi indywidualnego programu rozwoju zawodowego."
)
WSTEP_CZESCI_III = (
    "Wniosek jest wypełniany i dołączany do arkusza oceny okresowej ocenianego tylko w sytuacji skorzystania "
    "przez oceniającego z możliwości przewidzianej w art. 89 ust. 1 ustawy z dnia 21 listopada 2008 r. "
    "o służbie cywilnej."
)
PYTANIE_O_WNIOSEK = "CZY DO OCENY OKRESOWEJ DOŁĄCZONO WNIOSEK O PRZYZNANIE KOLEJNEGO STOPNIA SŁUŻBOWEGO?"
SREDNIA = "Średnia arytmetyczna z ocen cząstkowych przyznanych za poszczególne kryteria oceny:"

SKALA_WZORU = [
    ("Znacznie poniżej oczekiwań", "1 punkt"),
    ("Poniżej oczekiwań", "3 punkty"),
    ("Na poziomie oczekiwań", "5 punktów"),
    ("Powyżej oczekiwań", "7 punktów"),
    ("Znacznie powyżej oczekiwań", "9 punktów"),
]
PRZEDZIALY_WZORU = [
    ("od 1 punktu do 2 punktów", "znacznie poniżej oczekiwań"),
    ("powyżej 2 punktów do 4 punktów", "poniżej oczekiwań"),
    ("powyżej 4 punktów do 6 punktów", "na poziomie oczekiwań"),
    ("powyżej 6 punktów do 8 punktów", "powyżej oczekiwań"),
    ("powyżej 8 punktów do 9 punktów", "znacznie powyżej oczekiwań"),
]

# Przypisy wzoru (kropki wg skanów wzoru i przykładów KPRM - patrz opis modułu).
P_ARKUSZ = {
    "A": (
        "Arkusz służy do sporządzenia oceny okresowej urzędnika służby cywilnej lub pracownika służby cywilnej, "
        "zatrudnionego na stanowisku kierownika urzędu, które jest stanowiskiem pracy w służbie cywilnej."
    ),
    "B": (
        "Arkusz służy do sporządzenia oceny okresowej urzędnika służby cywilnej lub pracownika służby cywilnej, "
        "zatrudnionego na stanowisku, na którym praca polega na bezpośrednim kierowaniu pracownikami."
    ),
    "C": (
        "Arkusz służy do sporządzenia oceny okresowej urzędnika służby cywilnej lub pracownika służby cywilnej, "
        "zatrudnionego na stanowisku, które nie jest:\n"
        "– stanowiskiem kierownika urzędu, będącym stanowiskiem pracy w służbie cywilnej, ani\n"
        "– stanowiskiem, na którym praca polega na bezpośrednim kierowaniu pracownikami."
    ),
}
P_STANOWISKO = (
    "Należy wskazać pełną nazwę stanowiska pracy wraz z jego rozszerzeniem określającym, do jakich spraw jest to "
    "stanowisko (jeżeli zostało to określone w opisie stanowiska pracy)."
)
P_KRYTERIA = (
    "Należy wpisać nazwy wybranych kryteriów, korzystając z załącznika nr 1 do rozporządzenia Prezesa Rady "
    "Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych urzędników "
    "służby cywilnej i pracowników służby cywilnej."
)
P_ROZMOWA = (
    "W trakcie rozmowy omawiane są: 1) główne obowiązki wynikające z opisu stanowiska pracy zajmowanego przez "
    "ocenianego, 2) kryteria obowiązkowe i kryteria dodatkowe, jeżeli są wybierane przez oceniającego, "
    "3) oczekiwania oceniającego co do sposobu spełniania kryteriów oceny przez ocenianego, 4) cele do "
    "osiągnięcia w okresie, w którym oceniany podlega ocenie, jeżeli ich określenie jest uzasadnione ze względu "
    "na charakter obowiązków wynikających z opisu stanowiska pracy zajmowanego przez ocenianego, a także sposób "
    "realizacji wyznaczonych celów."
)
P_ROZMOWA_OCENIAJACA = (
    "W trakcie rozmowy oceniającej omawia się: 1) główne obowiązki wykonywane przez ocenianego w okresie, "
    "w którym podlegał ocenie, oraz sposób ich realizacji, z uwzględnieniem spełniania przez ocenianego "
    "ustalonych kryteriów oceny, 2) sposób realizowania przez ocenianego celów do osiągnięcia w okresie, "
    "w którym oceniany podlegał ocenie, jeżeli cele te zostały wyznaczone, 3) kierunki dalszego rozwoju "
    "zawodowego i potrzeby ocenianego w zakresie podnoszenia kwalifikacji i doskonalenia umiejętności."
)
P_OD = "Data „od” oznacza datę zapoznania ocenianego z kryteriami oceny – z części I arkusza oceny."
P_DO = (
    "Data „do” oznacza datę sporządzenia oceny na piśmie. Jeżeli ocena okresowa jest sporządzana w związku "
    "z zastosowaniem art. 81 ust. 6 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej (Dz. U. z 2014 r. "
    "poz. 1111, z późn. zm.) i nie została sporządzona przed zmianą stanowiska pracy, należy w tym polu wpisać "
    "ostatni dzień pracy na zajmowanym stanowisku pracy."
)
P_X = "Należy wstawić znak „X” w odpowiednie pole."
P_POZYTYWNA = (
    "POZYTYWNA – w przypadku ustalenia ogólnego poziomu spełniania kryteriów oceny na poziomie „znacznie powyżej "
    "oczekiwań”, „powyżej oczekiwań” albo „na poziomie oczekiwań”, pod warunkiem nieuzyskania przez ocenianego "
    "żadnej z ocen cząstkowych na poziomie „znacznie poniżej oczekiwań”."
)
P_NEGATYWNA = (
    "NEGATYWNA – w przypadku ustalenia ogólnego poziomu spełniania kryteriów oceny na poziomie „poniżej "
    "oczekiwań” albo „znacznie poniżej oczekiwań”, a także w przypadku uzyskania przez ocenianego co najmniej "
    "jednej oceny cząstkowej na poziomie „znacznie poniżej oczekiwań”."
)
P_UZASADNIENIE = (
    "Uzasadnienie jest obligatoryjne w przypadku otrzymania przez ocenianego negatywnej oceny okresowej. "
    "W przypadku przyznania oceny pozytywnej uzasadnienie jest fakultatywne. Sporządzenie uzasadnienia oceny "
    "może polegać na ogólnym omówieniu oceny lub na szczegółowym odniesieniu się do wszystkich ocen cząstkowych "
    "albo tylko do niektórych z nich."
)
P_IPRZ = (
    "Uwzględniając sporządzoną ocenę, realizowane i przyszłe zadania oraz oczekiwania ocenianego, należy określić "
    "kierunki rozwoju zawodowego ocenianego, biorąc pod uwagę obszary wiedzy i umiejętności wymagające "
    "doskonalenia, oraz zaproponować optymalne formy i metody ich realizacji."
)
P_OCENA = "Należy wpisać „pozytywna” lub „negatywna”."
P_POZIOM = (
    "Należy wpisać, na jakim poziomie była przyznana poprzednia ocena okresowa (np. „na poziomie oczekiwań”)."
)
P_DYREKTOR = (
    "W urzędzie, w którym przepisy nie przewidują tworzenia stanowiska dyrektora generalnego urzędu, sprzeciw "
    "składa się do kierownika tego urzędu."
)
P_CZESC_III = (
    "Części III nie drukuje się i nie dołącza do arkusza oceny okresowej w przypadku ocenianego będącego "
    "pracownikiem służby cywilnej oraz w razie nieskładania wniosku o przyznanie urzędnikowi służby cywilnej "
    "kolejnego stopnia służbowego."
)
_PRZYPISY_CZESCI_II = [
    P_ROZMOWA_OCENIAJACA, P_OD, P_DO, P_X, P_KRYTERIA, P_POZYTYWNA, P_NEGATYWNA, P_UZASADNIENIE, P_IPRZ, P_OCENA,
    P_POZIOM, P_X,
]
PRZYPISY_WZORU = {
    "A": [P_ARKUSZ["A"], P_KRYTERIA, P_ROZMOWA, *_PRZYPISY_CZESCI_II, P_CZESC_III],
    "B": [P_ARKUSZ["B"], P_STANOWISKO, P_KRYTERIA, P_ROZMOWA, *_PRZYPISY_CZESCI_II, P_DYREKTOR, P_CZESC_III],
    "C": [P_ARKUSZ["C"], P_STANOWISKO, P_KRYTERIA, P_ROZMOWA, *_PRZYPISY_CZESCI_II, P_DYREKTOR, P_CZESC_III],
}


def kolejnosc_wzoru(symbol: str) -> list[str]:
    """Nagłówki, etykiety i opisy pól w kolejności wzoru arkusza (bez wartości i przypisów)."""
    oceniany = ["Imię", "Nazwisko", "Stanowisko pracy"]
    oceniajacy = ["Imię", "Nazwisko", "Stanowisko"]
    if symbol != "A":  # arkusze B i C: dodatkowe pole i ta sama etykieta stanowiska dla obu osób
        oceniany = oceniajacy = ["Imię", "Nazwisko", "Komórka organizacyjna", "Stanowisko pracy"]
    return [
        f"ARKUSZ {symbol}",
        "OCENA OKRESOWA",
        "URZĘDNIKA SŁUŻBY CYWILNEJ LUB PRACOWNIKA SŁUŻBY CYWILNEJ",
        "CZĘŚĆ I",
        "NAZWA URZĘDU",
        "DANE OCENIANEGO", *oceniany,
        "DANE OCENIAJĄCEGO", *oceniajacy,
        "KRYTERIA OCENY I TERMIN SPORZĄDZENIA OCENY",
        "Kryteria obowiązkowe",
        "Kryteria dodatkowe wybrane przez oceniającego (nie więcej niż 3)",
        "Termin sporządzenia oceny",
        "Potwierdzamy:",
        POTWIERDZENIE_ROZMOWY + ",",
        "zapoznanie ocenianego z kryteriami oceny oraz terminem sporządzenia oceny.",
        "miejscowość", "data (dd.mm.rrrr)", "podpis oceniającego",
        "miejscowość", "data (dd.mm.rrrr)", "podpis ocenianego",
        "CZĘŚĆ II",
        "DATA PRZEPROWADZENIA ROZMOWY OCENIAJĄCEJ",
        "OKRES, W KTÓRYM OCENIANY PODLEGAŁ OCENIE",
        "KRYTERIA OBOWIĄZKOWE", "OCENA CZĄSTKOWA",
        "KRYTERIA DODATKOWE WYBRANE PRZEZ OCENIAJĄCEGO", "OCENA CZĄSTKOWA",
        SREDNIA,
        "PRZYZNANIE OCENY",
        "Należy wstawić znak „X” w odpowiednie pole",
        "Liczba punktów stanowiąca średnią arytmetyczną ze wszystkich ocen cząstkowych",
        "Ogólny poziom spełnienia kryteriów oceny",
        "OCENA OKRESOWA W SŁUŻBIE CYWILNEJ", "POZYTYWNA", "NEGATYWNA",
        "UZASADNIENIE PRZYZNANEJ OCENY OKRESOWEJ",
        "WNIOSKI DOTYCZĄCE INDYWIDUALNEGO PROGRAMU ROZWOJU ZAWODOWEGO",
        "DANE DOTYCZĄCE POPRZEDNIEJ OCENY OKRESOWEJ URZĘDNIKA SŁUŻBY CYWILNEJ",
        "Ocena", "Poziom", "Data sporządzenia",
        PYTANIE_O_WNIOSEK, "TAK", "NIE", "NIE DOTYCZY (oceniany jest pracownikiem służby cywilnej)",
        "DANE OCENIAJĄCEGO", *oceniajacy,
        "miejscowość", "data (dd.mm.rrrr)", "podpis oceniającego",
        OSWIADCZENIE_OCENIANEGO,
        "miejscowość", "data (dd.mm.rrrr)", "imię i nazwisko lub pieczątka ocenianego", "podpis ocenianego",
        "Pouczenie",
        "CZĘŚĆ III",
        WSTEP_CZESCI_III,
        "DANE URZĘDNIKA SŁUŻBY CYWILNEJ",
        "Imię", "Nazwisko", "Rok mianowania", "Posiadany stopień służbowy", "Data przyznania stopnia służbowego",
        "WNIOSEK O PRZYZNANIE URZĘDNIKOWI SŁUŻBY CYWILNEJ KOLEJNEGO STOPNIA SŁUŻBOWEGO",
        "W związku z uzyskaniem przez Panią/Pana",
        "Umotywowanie wniosku",
        "miejscowość", "data (dd.mm.rrrr)", "imię i nazwisko lub pieczątka oceniającego", "podpis oceniającego",
    ]


# --- Dane testowe: przykłady KPRM (osoby i urzędy fikcyjne, z materiałów organizatora) ---

ETAPY = ("nowy", "kryteria", "potwierdzone", "ocena", "zapoznanie", "fikcja")

DODATKOWE_A = ["Negocjowanie", "Radzenie sobie w sytuacjach kryzysowych"]
OCENY_A = dict(zip(OBOWIAZKOWE_A + DODATKOWE_A, [5, 5, 5, 7, 7, 5, 5, 5]))
DODATKOWE_B = ["Wystąpienia publiczne", "Wykorzystywanie wiedzy i doskonalenie zawodowe", "Kreatywność"]
OCENY_B = dict(zip(OBOWIAZKOWE_B + DODATKOWE_B, [9, 5, 7, 7, 7, 5, 7, 7]))
OCENY_C = dict(zip(OBOWIAZKOWE_C, [5, 1, 5, 5, 5]))

UZASADNIENIE_B = (
    "Oceniana realizowała wszystkie zadania rzetelnie i terminowo.\n"
    "W związku z dużym spiętrzeniem zadań Naczelnik wprowadziła kilka usprawnień organizacyjnych."
)
WNIOSKI_B = "Zalecane odbycie akademii trenerskiej z elementami storytellingu."
UMOTYWOWANIE_B = "Oceniana odznacza się wzorową postawą i doskonałą realizacją zadań."
UZASADNIENIE_C = "Stopień realizacji kryterium rzetelności należy ocenić jako niezadowalający."
WNIOSKI_C = "Udział w szkoleniach z zakresu weryfikacji dokumentacji projektowej i finansowej."


def _doprowadz(proces, etap, *, dodatkowe, termin, kryteria, potwierdzenie, rozmowa, sporzadzenie, zapoznanie,
               oceny, **formularz):
    """Prowadzi proces metodami rdzenia do wskazanego etapu (jak w `tests/test_przebieg_procesu.py`)."""
    krok = ETAPY.index(etap)
    if krok >= 1:
        proces.wyznacz_kryteria(Rola.OCENIAJACY, dodatkowe, termin=termin, data=kryteria)
    if krok >= 2:
        proces.potwierdz_kryteria(Rola.OCENIANY, data=potwierdzenie)
    if krok >= 3:
        proces.sporzadz_ocene(Rola.OCENIAJACY, data=sporzadzenie, data_rozmowy=rozmowa, oceny=oceny, **formularz)
    if etap == "zapoznanie":
        proces.potwierdz_zapoznanie(Rola.OCENIANY, data=zapoznanie)
    if etap == "fikcja":
        proces.stwierdz_fikcje_zapoznania(Rola.OCENIAJACY, data=zapoznanie)
    return proces


def arkusz_A(etap="zapoznanie", **zmiany) -> DaneArkusza:
    """`1) Arkusz oceny A - GLW.docx.md` - kierownik urzędu, pracownik służby cywilnej."""
    proces = _doprowadz(
        ProcesOceny(arkusz="A", urzednik=False, poczatek_cyklu=d(2023, 5, 12)), etap,
        dodatkowe=DODATKOWE_A, termin=d(2025, 5, 12), kryteria=d(2023, 5, 15), potwierdzenie=d(2023, 5, 16),
        rozmowa=d(2025, 5, 12), sporzadzenie=d(2025, 5, 12), zapoznanie=d(2025, 5, 14), oceny=OCENY_A,
        wnioski_iprz="Rozwijanie umiejętności kierowniczych w praktyce.",
        uzasadnienie="Pracownik spełniał oczekiwania we wszystkich kryteriach.",
    )
    dane = DaneArkusza(
        nazwa_urzedu="Graniczny Inspektorat Weterynarii w Testowie",
        oceniany=Osoba("Janina", "Kowalska", "Graniczny Lekarz Weterynarii w Testowie"),
        oceniajacy=Osoba("Adam", "Nowak", "Główny Lekarz Weterynarii"),
        proces=proces,
        miejscowosc_oceniajacego="Warszawa",
        miejscowosc_ocenianego="Testowo",
        adresat_sprzeciwu="Głównego Lekarza Weterynarii",
    )
    return replace(dane, **zmiany)


def arkusz_B(etap="zapoznanie", *, wniosek="TAK", stopien=4, przepisy_procesu=None, **zmiany) -> DaneArkusza:
    """`2) Arkusz oceny B - naczelnik.docx.md` - urzędnik służby cywilnej z wnioskiem o kolejny stopień."""
    proces = _doprowadz(
        ProcesOceny(arkusz="B", urzednik=True, poczatek_cyklu=d(2024, 10, 2), przepisy=przepisy_procesu), etap,
        dodatkowe=DODATKOWE_B, termin=d(2026, 10, 2), kryteria=d(2024, 10, 3), potwierdzenie=d(2024, 10, 3),
        rozmowa=d(2026, 10, 1), sporzadzenie=d(2026, 10, 2), zapoznanie=d(2026, 10, 2), oceny=OCENY_B,
        wnioski_iprz=WNIOSKI_B, uzasadnienie=UZASADNIENIE_B, wniosek_o_stopien=wniosek,
        umotywowanie_wniosku=UMOTYWOWANIE_B if wniosek == "TAK" else "", posiadany_stopien=stopien,
    )
    dane = DaneArkusza(
        nazwa_urzedu="Urząd Ministerstwa Testowego w Kropce Wielkopolskiej",
        oceniany=Osoba("Janina", "Nowak", "Naczelnik Wydziału", "Wydział Rozwoju"),
        oceniajacy=Osoba("Romuald", "Gut", "Zastępca dyrektora", "Biuro Zarządzania Kapitałem Ludzkim"),
        proces=proces,
        miejscowosc_oceniajacego="Warszawa",
        miejscowosc_ocenianego="Warszawa",
        poprzednia_ocena=PoprzedniaOcena("POZYTYWNA", "powyżej oczekiwań", d(2024, 10, 2)),
        rok_mianowania=2010,
        data_przyznania_stopnia=d(2024, 11, 1),
    )
    return replace(dane, **zmiany)


def arkusz_C(etap="zapoznanie", **zmiany) -> DaneArkusza:
    """`4) Arkusz oceny C - główny spec.(neg).docx.md` - pracownik służby cywilnej, ocena negatywna."""
    proces = _doprowadz(
        ProcesOceny(arkusz="C", urzednik=False, poczatek_cyklu=d(2024, 10, 14)), etap,
        dodatkowe=[], termin=d(2026, 10, 14), kryteria=d(2024, 10, 17), potwierdzenie=d(2024, 10, 18),
        rozmowa=d(2026, 10, 12), sporzadzenie=d(2026, 10, 14), zapoznanie=d(2026, 10, 14), oceny=OCENY_C,
        wnioski_iprz=WNIOSKI_C, uzasadnienie=UZASADNIENIE_C,
    )
    dane = DaneArkusza(
        nazwa_urzedu="Urząd Centralny Spraw Ważnych",
        oceniany=Osoba("Adam", "Kowalik", "Główny specjalista", "Biuro Funduszy Europejskich"),
        oceniajacy=Osoba("Miranda", "Wąsik", "Zastępca dyrektora", "Biuro Funduszy Europejskich"),
        proces=proces,
        miejscowosc_oceniajacego="Warszawa",
        miejscowosc_ocenianego="Warszawa",
    )
    return replace(dane, **zmiany)


def pelny_arkusz(symbol: str) -> DaneArkusza:
    """Urzędnik z oceną pozytywną i wnioskiem o stopień - arkusz z kompletem części I-III (dane fikcyjne)."""
    kryteria = OBOWIAZKOWE[symbol] + ["Kreatywność"]
    proces = _doprowadz(
        ProcesOceny(arkusz=symbol, urzednik=True, poczatek_cyklu=d(2026, 1, 12)), "zapoznanie",
        dodatkowe=["Kreatywność"], termin=d(2028, 1, 12), kryteria=d(2026, 1, 20), potwierdzenie=d(2026, 1, 21),
        rozmowa=d(2028, 1, 5), sporzadzenie=d(2028, 1, 10), zapoznanie=d(2028, 1, 11),
        oceny=dict.fromkeys(kryteria, 7), wnioski_iprz="Szkolenie z analizy danych.", wniosek_o_stopien="TAK",
        umotywowanie_wniosku="Wzorowa realizacja zadań.", posiadany_stopien=1,
    )
    return DaneArkusza(
        nazwa_urzedu="Urząd Testowy w Testowie",
        oceniany=Osoba("Anna", "Testowa", "Radca", "Wydział Prawny"),
        oceniajacy=Osoba("Jan", "Przykładowy", "Dyrektor", "Wydział Prawny"),
        proces=proces,
        miejscowosc_oceniajacego="Testowo",
        miejscowosc_ocenianego="Testowo",
        adresat_sprzeciwu="Ministra Testów",
        rok_mianowania=2015,
        data_przyznania_stopnia=d(2015, 6, 1),
    )


# --- Pomocnicze odczyty treści ---

def blok(tresc, kod_sekcji, typ):
    """Pierwszy blok danego typu w sekcji o podanym kodzie."""
    return next(b for b in tresc.sekcja(kod_sekcji).bloki if isinstance(b, typ))


def pola(tresc, kod_sekcji) -> dict[str, str]:
    return {pole.etykieta.tekst: pole.wartosc for pole in blok(tresc, kod_sekcji, BlokPol).pola}


def podpisy(tresc, kod_sekcji) -> list[list[tuple[str, str]]]:
    """Wiersze podpisów sekcji: lista kolumn (wartość nad kreską, opis pod kreską)."""
    return [
        [(kolumna.wartosc, kolumna.etykieta.tekst) for kolumna in b.kolumny]
        for b in tresc.sekcja(kod_sekcji).bloki if isinstance(b, BlokPodpisow)
    ]


def oceny_w_tabeli(tresc) -> list[tuple[str, int | None]]:
    tabela = blok(tresc, "oceny_czastkowe", BlokOcen)
    return [(wiersz.nazwa, wiersz.ocena) for wiersz in (*tabela.obowiazkowe, *tabela.dodatkowe)]


def czesci(dane, przepisy=None) -> list[str]:
    return [strona.tytul for strona in tresc_arkusza(dane, przepisy).strony if strona.tytul]


def obiekty(obiekt, typ):
    """Wszystkie obiekty danego typu w strukturze treści (przejście po polach klas danych)."""
    if isinstance(obiekt, typ):
        yield obiekt
    if is_dataclass(obiekt) and not isinstance(obiekt, type):
        for pole in fields(obiekt):
            yield from obiekty(getattr(obiekt, pole.name), typ)
    elif isinstance(obiekt, (tuple, list)):
        for element in obiekt:
            yield from obiekty(element, typ)


def brakujacy_w_kolejnosci(oczekiwane, teksty):
    """Pierwszy element `oczekiwane`, którego nie ma w `teksty` w wymaganej kolejności (None = komplet).
    `teksty` to lista napisów (porównanie całych elementów) albo jeden napis (wyszukiwanie fragmentów)."""
    pozycja = 0
    for element in oczekiwane:
        if isinstance(teksty, str):
            znaleziono = teksty.find(element, pozycja)
            if znaleziono < 0:
                return element
            pozycja = znaleziono + len(element)
        else:
            try:
                pozycja = teksty.index(element, pozycja) + 1
            except ValueError:
                return element
    return None


def _spacje(tekst: str) -> str:
    return " ".join(tekst.split())


def otworz_docx(dane, przepisy=None):
    return Document(io.BytesIO(generuj_arkusz_docx(dane, przepisy)))


@pytest.mark.parametrize("symbol", ["A", "B", "C"])
def test_tresc_dokumentu_ma_jezyk_polski(symbol):
    """Dostępność cyfrowa, WCAG 2.1 kryterium 3.1.1 „Język strony” (załącznik do ustawy o dostępności cyfrowej,
    t.j. Dz. U. z 2023 r. poz. 1440): czytnik ekranu dobiera wymowę do języka dokumentu. Język treści zapisują
    style dokumentu (w:lang) - z nich bierze go też konwerter PDF; właściwość pliku „język” na to nie wpływa."""
    dokument = otworz_docx(pelny_arkusz(symbol))

    jezyki = dokument.styles.element.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:lang/@w:val")

    assert jezyki == ["pl-PL"]
    assert dokument.core_properties.language == "pl-PL"
    assert dokument.core_properties.title == f"Arkusz {symbol} - ocena okresowa"


def teksty_docx(dokument) -> list[str]:
    """Niepuste akapity dokumentu w kolejności czytania (także z komórek tabel), bez odsyłaczy przypisów
    (tekst w indeksie górnym), z pojedynczymi odstępami."""
    zebrane: list[str] = []

    def dodaj(element) -> None:
        if isinstance(element, Paragraph):
            zebrane.append("".join(run.text for run in element.runs if not run.font.superscript))
            return
        widziane = set()
        for wiersz in element.rows:
            for komorka in wiersz.cells:
                if komorka._tc in widziane:  # komórki scalone występują w wierszu wielokrotnie
                    continue
                widziane.add(komorka._tc)
                for wewnetrzny in komorka.iter_inner_content():
                    dodaj(wewnetrzny)

    for element in dokument.iter_inner_content():
        dodaj(element)
    return [_spacje(tekst) for tekst in zebrane if tekst.strip()]


def tekst_docx(dokument) -> str:
    return " ".join(teksty_docx(dokument))


def oceny_w_tabeli_docx(dokument, kryteria) -> dict[str, list[int]]:
    """Dla każdego kryterium: numery kolumn skali (od 0), w których stoi znak „X”."""
    tabela = next(t for t in dokument.tables if "KRYTERIA OBOWIĄZKOWE" in t.rows[0].cells[0].text)
    wynik = {}
    for wiersz in tabela.rows:
        komorki = wiersz.cells
        nazwa = _spacje(komorki[0].text)
        if nazwa in kryteria:
            wynik[nazwa] = [nr for nr, komorka in enumerate(komorki[1:]) if komorka.text.strip() == "X"]
    return wynik


# === Struktura i treści stałe wzoru ===

@pytest.mark.parametrize("symbol", ["A", "B", "C"])
def test_naglowki_i_pola_arkusza_sa_w_kolejnosci_wzoru(symbol):
    """Rozporządzenie (plik `1. Rozporządzenie w sprawie ocen okresowych.pdf.txt`): arkusz A - wiersze 337-663,
    arkusz B - wiersze 679-938, arkusz C - wiersze 954-1215; kolejność: tytuł, CZĘŚĆ I, CZĘŚĆ II, CZĘŚĆ III.
    Druga strona części II arkusza A (wiersze 490-606, zapis nieczytelny) - wg skanu wzoru
    `wzór formularza oceny okresowej arkusz A.pdf.ocr.txt`, strona p-3."""
    teksty = tresc_arkusza(pelny_arkusz(symbol)).teksty()
    assert brakujacy_w_kolejnosci(kolejnosc_wzoru(symbol), teksty) is None


def test_arkusz_A_nie_ma_komorki_organizacyjnej_a_oceniajacy_ma_pole_stanowisko():
    """Zał. nr 2, CZĘŚĆ I (wiersze 347-355): DANE OCENIANEGO - Imię, Nazwisko, Stanowisko pracy;
    DANE OCENIAJĄCEGO - Imię, Nazwisko, Stanowisko. To samo w części II (skan arkusza A, strona p-3)."""
    tresc = tresc_arkusza(arkusz_A())
    assert list(pola(tresc, "dane_ocenianego")) == ["Imię", "Nazwisko", "Stanowisko pracy"]
    assert list(pola(tresc, "dane_oceniajacego")) == ["Imię", "Nazwisko", "Stanowisko"]
    assert list(pola(tresc, "oceniajacy_ocena")) == ["Imię", "Nazwisko", "Stanowisko"]
    assert "Komórka organizacyjna" not in tresc.teksty()


@pytest.mark.parametrize("budowniczy", ["B", "C"])
def test_arkusze_B_i_C_maja_komorke_organizacyjna_i_stanowisko_pracy(budowniczy):
    """Zał. nr 3 i 4, CZĘŚĆ I (wiersze 689-699 i 964-974) oraz DANE OCENIAJĄCEGO w części II (wiersze 858-862
    i 1133-1137): Imię, Nazwisko, Komórka organizacyjna, Stanowisko pracy."""
    tresc = tresc_arkusza({"B": arkusz_B, "C": arkusz_C}[budowniczy]())
    etykiety = ["Imię", "Nazwisko", "Komórka organizacyjna", "Stanowisko pracy"]
    for kod in ("dane_ocenianego", "dane_oceniajacego", "oceniajacy_ocena"):
        assert list(pola(tresc, kod)) == etykiety


def test_dane_urzedu_i_osob_trafiaja_do_czesci_I():
    """Przykład KPRM `2) Arkusz oceny B - naczelnik.docx.md`, CZĘŚĆ I."""
    tresc = tresc_arkusza(arkusz_B())
    assert pola(tresc, "nazwa_urzedu") == {"NAZWA URZĘDU": "Urząd Ministerstwa Testowego w Kropce Wielkopolskiej"}
    assert pola(tresc, "dane_ocenianego") == {
        "Imię": "Janina", "Nazwisko": "Nowak", "Komórka organizacyjna": "Wydział Rozwoju",
        "Stanowisko pracy": "Naczelnik Wydziału",
    }
    assert pola(tresc, "dane_oceniajacego") == {
        "Imię": "Romuald", "Nazwisko": "Gut", "Komórka organizacyjna": "Biuro Zarządzania Kapitałem Ludzkim",
        "Stanowisko pracy": "Zastępca dyrektora",
    }


@pytest.mark.parametrize("symbol", ["A", "B", "C"])
def test_przypisy_maja_brzmienie_i_numeracje_wzoru(symbol):
    """Przypisy arkusza A: 1-3 (wiersze 389-399), 4-10 (465-486), 11-15 (611-623), 16 (669-671); arkusza B:
    1-4 (733-746), 5-11 (813-834), 12-17 (884-898), 18 (944-946); arkusza C: 1-4 (1007-1021), 5-11 (1089-1110),
    12-17 (1160-1174), 18 (1220-1222). Kropki wg skanów wzoru (pliki `*.pdf.ocr.txt`)."""
    tresc = tresc_arkusza(pelny_arkusz(symbol))
    przypisy = [(p.numer, p.tresc) for strona in tresc.strony for p in strona.przypisy]
    assert przypisy == list(enumerate(PRZYPISY_WZORU[symbol], start=1))


@pytest.mark.parametrize("symbol, liczby", [("A", [3, 7, 5, 1]), ("B", [4, 7, 6, 1]), ("C", [4, 7, 6, 1])])
def test_przypisy_sa_pogrupowane_jak_na_stronach_wzoru(symbol, liczby):
    """Wzór ma cztery strony: CZĘŚĆ I, CZĘŚĆ II (tabele ocen), dalszy ciąg części II, CZĘŚĆ III - każda
    z własnymi przypisami (np. arkusz B: strony 12-15 Dz. U., wiersze 675, 748, 836 i 900 pliku)."""
    tresc = tresc_arkusza(pelny_arkusz(symbol))
    assert [strona.czesc for strona in tresc.strony] == ["I", "II", "II", "III"]
    assert [strona.tytul for strona in tresc.strony] == ["CZĘŚĆ I", "CZĘŚĆ II", "", "CZĘŚĆ III"]
    assert [len(strona.przypisy) for strona in tresc.strony] == liczby


@pytest.mark.parametrize("symbol", ["A", "B", "C"])
def test_odsylacze_do_przypisow_stoja_przy_tych_samych_tresciach_co_we_wzorze(symbol):
    """Np. arkusz B: „Stanowisko pracy2)” (wiersz 693), „(nie więcej niż 3)3)” (704), „zagadnień4),” (717),
    „OCENIAJĄCEJ5)” (753), „OD6):”, „DO7):” (755), „OCENA CZĄSTKOWA8)” (759 i 783), „OCENIAJĄCEGO9)” (784),
    „POZYTYWNA10)”, „NEGATYWNA11)” (808), „OKRESOWEJ12)” (838), „ZAWODOWEGO13)” (843), „Ocena14)”,
    „Poziom15)” (850), „SŁUŻBOWEGO?16)” (854), „urzędu17).” (881), „cywilnej.18)” (906)."""
    przesuniecie = 0 if symbol == "A" else 1  # arkusze B i C mają dodatkowy przypis nr 2 (stanowisko pracy)
    oczekiwane = {
        ("URZĘDNIKA SŁUŻBY CYWILNEJ LUB PRACOWNIKA SŁUŻBY CYWILNEJ", 1),
        ("Kryteria dodatkowe wybrane przez oceniającego (nie więcej niż 3)", 2 + przesuniecie),
        (POTWIERDZENIE_ROZMOWY, 3 + przesuniecie),
        ("DATA PRZEPROWADZENIA ROZMOWY OCENIAJĄCEJ", 4 + przesuniecie),
        ("OD", 5 + przesuniecie),
        ("DO", 6 + przesuniecie),
        ("OCENA CZĄSTKOWA", 7 + przesuniecie),
        ("KRYTERIA DODATKOWE WYBRANE PRZEZ OCENIAJĄCEGO", 8 + przesuniecie),
        ("POZYTYWNA", 9 + przesuniecie),
        ("NEGATYWNA", 10 + przesuniecie),
        ("UZASADNIENIE PRZYZNANEJ OCENY OKRESOWEJ", 11 + przesuniecie),
        ("WNIOSKI DOTYCZĄCE INDYWIDUALNEGO PROGRAMU ROZWOJU ZAWODOWEGO", 12 + przesuniecie),
        ("Ocena", 13 + przesuniecie),
        ("Poziom", 14 + przesuniecie),
        (PYTANIE_O_WNIOSEK, 15 + przesuniecie),
        (WSTEP_CZESCI_III, 16 if symbol == "A" else 18),
    }
    if symbol != "A":
        oczekiwane.add(("Stanowisko pracy", 2))
        oczekiwane.add((pouczenie_o_sprzeciwie(symbol).removesuffix("."), 17))
    tresc = tresc_arkusza(pelny_arkusz(symbol))
    assert {(t.tekst, t.przypis) for t in obiekty(tresc, Tekst) if t.przypis is not None} == oczekiwane


# === Kryteria (część I i tabela ocen w części II) ===

@pytest.mark.parametrize("symbol", ["A", "B", "C"])
def test_komplet_kryteriow_obowiazkowych_w_kolejnosci_rozporzadzenia(symbol):
    """§ 4 ust. 1-3 rozp. (wiersze 43-78 pliku) oraz wzory: arkusz A - wiersze 361-366 i 421-431, arkusz B -
    705-710 i 769-780, arkusz C - 980-985 i 1044-1056."""
    tresc = tresc_arkusza({"A": arkusz_A, "B": arkusz_B, "C": arkusz_C}[symbol]("nowy"))
    assert list(blok(tresc, "kryteria_i_termin", BlokKryteriow).obowiazkowe) == OBOWIAZKOWE[symbol]
    assert [w.nazwa for w in blok(tresc, "oceny_czastkowe", BlokOcen).obowiazkowe] == OBOWIAZKOWE[symbol]


def test_wybrane_kryteria_dodatkowe_sa_w_czesci_I_i_w_tabeli_ocen():
    """§ 5 ust. 3 rozp.: oceniający wpisuje do części I kryteria dodatkowe; przykład KPRM
    `2) Arkusz oceny B - naczelnik.docx.md` (Wystąpienia publiczne, Wykorzystywanie wiedzy..., Kreatywność)."""
    tresc = tresc_arkusza(arkusz_B("kryteria"))
    assert list(blok(tresc, "kryteria_i_termin", BlokKryteriow).dodatkowe) == DODATKOWE_B
    assert [w.nazwa for w in blok(tresc, "oceny_czastkowe", BlokOcen).dodatkowe] == DODATKOWE_B


def test_arkusz_bez_kryteriow_dodatkowych_zostawia_puste_miejsca_wg_limitu_z_przepisow():
    """§ 5 ust. 2 rozp. („nie więcej niż 3 kryteria dodatkowe”); przykład KPRM
    `4) Arkusz oceny C - główny spec.(neg).docx.md` - trzy puste wiersze kryteriów dodatkowych."""
    kryteria = blok(tresc_arkusza(arkusz_C()), "kryteria_i_termin", BlokKryteriow)
    assert list(kryteria.dodatkowe) == []
    assert kryteria.liczba_pol_dodatkowych == 3


# === Skala, progi i wynik ===

def test_skala_ocen_czastkowych_i_przedzialy_poziomow_maja_brzmienie_wzoru():
    """Zał. nr 3, CZĘŚĆ II: nagłówki skali (wiersze 760-766: „Znacznie poniżej oczekiwań 1 punkt” ...
    „Znacznie powyżej oczekiwań 9 punktów”) i tabela PRZYZNANIE OCENY (wiersze 798-806)."""
    tresc = tresc_arkusza(arkusz_B())
    skala = blok(tresc, "oceny_czastkowe", BlokOcen).skala
    assert [(k.nazwa, k.opis_punktow) for k in skala] == SKALA_WZORU
    assert [k.punkty for k in skala] == [1, 3, 5, 7, 9]
    wiersze = blok(tresc, "przyznanie_oceny", BlokPrzyznaniaOceny).wiersze
    assert [(w.przedzial, w.poziom) for w in wiersze] == PRZEDZIALY_WZORU


def test_przyklad_kprm_arkusz_B_naczelnik_oceny_srednia_poziom_i_ocena_pozytywna():
    """`2) Arkusz oceny B - naczelnik.docx.md`: oceny 9, 5, 7, 7, 7 oraz 5, 7, 7; średnia 54/8 = 6,75 (przy
    jednym miejscu po przecinku - decyzja zespołu z 21.11.2026 - wydruk pokazuje 6,8); znak „X” przy poziomie
    „powyżej oczekiwań” i przy ocenie POZYTYWNA."""
    tresc = tresc_arkusza(arkusz_B())
    assert oceny_w_tabeli(tresc) == list(OCENY_B.items())
    assert blok(tresc, "oceny_czastkowe", BlokOcen).srednia.wartosc == "6,8"
    przyznanie = blok(tresc, "przyznanie_oceny", BlokPrzyznaniaOceny)
    assert [w.poziom for w in przyznanie.wiersze if w.zaznaczony] == ["powyżej oczekiwań"]
    assert [(o.etykieta.tekst, o.zaznaczona) for o in przyznanie.opcje] == [
        ("POZYTYWNA", True), ("NEGATYWNA", False),
    ]


def test_przyklad_kprm_arkusz_C_ocena_negatywna_mimo_sredniej_na_poziomie_oczekiwan():
    """`4) Arkusz oceny C - główny spec.(neg).docx.md`: oceny 5, 1, 5, 5, 5; średnia 4,2; „X” przy poziomie
    „na poziomie oczekiwań” i przy ocenie NEGATYWNA; uzasadnienie wypełnione; „NIE DOTYCZY” przy wniosku."""
    tresc = tresc_arkusza(arkusz_C())
    assert oceny_w_tabeli(tresc) == list(OCENY_C.items())
    assert blok(tresc, "oceny_czastkowe", BlokOcen).srednia.wartosc == "4,2"
    przyznanie = blok(tresc, "przyznanie_oceny", BlokPrzyznaniaOceny)
    assert [w.poziom for w in przyznanie.wiersze if w.zaznaczony] == ["na poziomie oczekiwań"]
    assert [o.etykieta.tekst for o in przyznanie.opcje if o.zaznaczona] == ["NEGATYWNA"]
    assert blok(tresc, "uzasadnienie", BlokOpisowy).tresc == UZASADNIENIE_C
    assert blok(tresc, "wnioski_iprz", BlokOpisowy).tresc == WNIOSKI_C
    wybor = blok(tresc, "wniosek_o_stopien", BlokWyboru)
    assert [o.etykieta.tekst for o in wybor.opcje if o.zaznaczona] == [
        "NIE DOTYCZY (oceniany jest pracownikiem służby cywilnej)"
    ]


def test_przyklad_kprm_arkusz_A_srednia_i_poziom():
    """`1) Arkusz oceny A - GLW.docx.md`: oceny 5, 5, 5, 7, 7, 5 oraz 5, 5; średnia 5,5; poziom „na poziomie
    oczekiwań”; ocena pozytywna."""
    tresc = tresc_arkusza(arkusz_A())
    assert oceny_w_tabeli(tresc) == list(OCENY_A.items())
    assert blok(tresc, "oceny_czastkowe", BlokOcen).srednia.wartosc == "5,5"
    przyznanie = blok(tresc, "przyznanie_oceny", BlokPrzyznaniaOceny)
    assert [w.poziom for w in przyznanie.wiersze if w.zaznaczony] == ["na poziomie oczekiwań"]
    assert [o.etykieta.tekst for o in przyznanie.opcje if o.zaznaczona] == ["POZYTYWNA"]


def test_daty_i_okres_oceny_w_czesci_II():
    """Przypisy 6 i 7 do części II arkusza B (wiersze 818-823): „od” = zapoznanie z kryteriami, „do” =
    sporządzenie oceny; przykład KPRM `2) Arkusz oceny B - naczelnik.docx.md`: rozmowa 01.10.2026, okres
    03.10.2024-02.10.2026."""
    tresc = tresc_arkusza(arkusz_B())
    assert pola(tresc, "rozmowa_oceniajaca") == {"DATA PRZEPROWADZENIA ROZMOWY OCENIAJĄCEJ": "01.10.2026"}
    assert tresc.sekcja("okres_oceny").naglowek.tekst == "OKRES, W KTÓRYM OCENIANY PODLEGAŁ OCENIE"
    assert pola(tresc, "okres_oceny") == {"OD": "03.10.2024", "DO": "02.10.2026"}


def test_okres_oceny_konczy_sie_ostatnim_dniem_na_stanowisku_gdy_oceny_nie_sporzadzono_przed_zmiana():
    """Przypis 7 do części II arkusza B (wiersze 820-823): przy art. 81 ust. 6 u.s.c. w polu „do” wpisuje się
    ostatni dzień pracy na zajmowanym stanowisku (rdzeń: `terminy.okres_podlegania_ocenie`)."""
    tresc = tresc_arkusza(arkusz_B(ostatni_dzien_na_stanowisku=d(2026, 9, 30)))
    assert pola(tresc, "okres_oceny") == {"OD": "03.10.2024", "DO": "30.09.2026"}


def test_dane_poprzedniej_oceny_sa_wypelniane_tylko_dla_urzednika():
    """Schemat pól formularza B: sekcja nieaktywna, jeżeli oceniany nie jest urzędnikiem; przypis 14 do wzoru
    (wiersz 892): należy wpisać „pozytywna” lub „negatywna”. Przykład KPRM `2) Arkusz oceny B - naczelnik`:
    pozytywna, powyżej oczekiwań, 02.10.2024."""
    urzednik = pola(tresc_arkusza(arkusz_B()), "poprzednia_ocena")
    assert urzednik == {"Ocena": "pozytywna", "Poziom": "powyżej oczekiwań", "Data sporządzenia": "02.10.2024"}
    poprzednia = PoprzedniaOcena("POZYTYWNA", "na poziomie oczekiwań", d(2024, 10, 14))
    pracownik = pola(tresc_arkusza(arkusz_C(poprzednia_ocena=poprzednia)), "poprzednia_ocena")
    assert pracownik == {"Ocena": "", "Poziom": "", "Data sporządzenia": ""}


# === Część III ===

def test_czesc_III_jest_drukowana_tylko_przy_wniosku_o_stopien_dla_urzednika():
    """Przypis 18 do części III arkusza B (wiersze 944-946): części III nie drukuje się dla pracownika służby
    cywilnej ani w razie nieskładania wniosku (rdzeń: `walidacja.czy_drukowac_czesc_III`)."""
    assert czesci(arkusz_B()) == ["CZĘŚĆ I", "CZĘŚĆ II", "CZĘŚĆ III"]
    assert czesci(arkusz_B(wniosek="NIE")) == ["CZĘŚĆ I", "CZĘŚĆ II"]
    assert czesci(arkusz_C()) == ["CZĘŚĆ I", "CZĘŚĆ II"]
    assert czesci(arkusz_B("kryteria")) == ["CZĘŚĆ I", "CZĘŚĆ II"]


def test_czesc_III_zawiera_dane_urzednika_i_tresc_wniosku():
    """Zał. nr 3, CZĘŚĆ III (wiersze 902-938); przykład KPRM `2) Arkusz oceny B - naczelnik.docx.md`: rok
    mianowania 2010, posiadany stopień IV, wniosek o V stopień (schemat pól: kolejny stopień słownie)."""
    tresc = tresc_arkusza(arkusz_B())
    assert pola(tresc, "dane_urzednika") == {
        "Imię": "Janina", "Nazwisko": "Nowak", "Rok mianowania": "2010", "Posiadany stopień służbowy": "4",
        "Data przyznania stopnia służbowego": "01.11.2024",
    }
    teksty = tresc.teksty()
    assert brakujacy_w_kolejnosci([
        "W związku z uzyskaniem przez Panią/Pana",
        "Janina Nowak",
        "pozytywnej oceny okresowej, na podstawie art. 89 ust. 1 ustawy z dnia 21 listopada 2008 r. "
        "o służbie cywilnej wnioskuję o przyznanie piątego stopnia służbowego.",
        "Umotywowanie wniosku",
        UMOTYWOWANIE_B,
    ], teksty) is None
    wybor = blok(tresc, "wniosek_o_stopien", BlokWyboru)
    assert [o.etykieta.tekst for o in wybor.opcje if o.zaznaczona] == ["TAK"]


def test_bez_posiadanego_stopnia_wniosek_zostawia_miejsce_na_wpisanie_kolejnego_stopnia():
    """Zał. nr 3, CZĘŚĆ III (wiersze 929-930): „wnioskuję o przyznanie ………. stopnia służbowego.”"""
    tresc = tresc_arkusza(arkusz_B(stopien=None))
    assert pola(tresc, "dane_urzednika")["Posiadany stopień służbowy"] == ""
    assert (
        "pozytywnej oceny okresowej, na podstawie art. 89 ust. 1 ustawy z dnia 21 listopada 2008 r. "
        "o służbie cywilnej wnioskuję o przyznanie ………. stopnia służbowego."
    ) in tresc.teksty()


def test_posiadany_stopien_mozna_podac_w_danych_arkusza_gdy_nie_ma_go_w_formularzu_procesu():
    tresc = tresc_arkusza(arkusz_B(stopien=None, posiadany_stopien=3))
    assert pola(tresc, "dane_urzednika")["Posiadany stopień służbowy"] == "3"
    assert any("wnioskuję o przyznanie czwartego stopnia służbowego." in tekst for tekst in tresc.teksty())


# === Pouczenie ===

@pytest.mark.parametrize("budowniczy, zmiany, argumenty", [
    (arkusz_A, {}, {"arkusz": "A", "adresat": "Głównego Lekarza Weterynarii"}),
    (arkusz_A, {"adresat_sprzeciwu": None}, {"arkusz": "A"}),
    (arkusz_B, {}, {"arkusz": "B"}),
    (arkusz_C, {"urzad_ma_dyrektora_generalnego": False}, {"arkusz": "C", "urzad_ma_dyrektora_generalnego": False}),
])
def test_pouczenie_o_sprzeciwie_pochodzi_z_rdzenia(budowniczy, zmiany, argumenty):
    """Wzory: arkusz A - skan `wzór formularza oceny okresowej arkusz A.pdf.ocr.txt`, strona p-3 („Na podstawie
    art. 83 ust. 1 ... sprzeciw do:”); arkusze B i C - wiersze 880-881 i 1154-1155 pliku rozporządzenia wraz
    z przypisem 17 (kierownik urzędu, gdy nie ma dyrektora generalnego)."""
    teksty = tresc_arkusza(budowniczy(**zmiany)).teksty()
    assert brakujacy_w_kolejnosci(["Pouczenie", pouczenie_o_sprzeciwie(**argumenty)], teksty) is None


def test_pouczenie_arkusza_B_ma_brzmienie_wzoru():
    """Zał. nr 3, wiersze 880-881 pliku rozporządzenia."""
    assert (
        "Zgodnie z art. 83 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej od oceny okresowej "
        "służy, w terminie 7 dni od dnia zapoznania się z oceną, sprzeciw do dyrektora generalnego urzędu."
    ) in tresc_arkusza(arkusz_B()).teksty()


# === Etapy procesu ===

def test_arkusz_mozna_wydrukowac_przed_wyznaczeniem_kryteriow():
    """Wydruk na początku cyklu: kryteria obowiązkowe ze wzoru, reszta pusta - z opisami pól ze wzoru
    (zał. nr 3, wiersze 709-728: „Termin sporządzenia oceny (dd.mm.rrrr)”, „miejscowość”, „data (dd.mm.rrrr)”)."""
    tresc = tresc_arkusza(arkusz_B("nowy"))
    kryteria = blok(tresc, "kryteria_i_termin", BlokKryteriow)
    assert list(kryteria.dodatkowe) == []
    assert (kryteria.termin.etykieta.tekst, kryteria.termin.wartosc, kryteria.termin.podpowiedz) == (
        "Termin sporządzenia oceny", "", "(dd.mm.rrrr)",
    )
    assert podpisy(tresc, "potwierdzenie_kryteriow") == [
        [("", "miejscowość"), ("", "data (dd.mm.rrrr)"), ("", "podpis oceniającego")],
        [("", "miejscowość"), ("", "data (dd.mm.rrrr)"), ("", "podpis ocenianego")],
    ]


def test_po_wyznaczeniu_kryteriow_czesc_I_jest_wypelniona_a_arkusz_nie_zawiera_ocen():
    """§ 5 ust. 3 i § 6 rozp.: po rozmowie oceniający wpisuje do części I kryteria dodatkowe i termin; oceniany
    potwierdza zapoznanie podpisem. Część II powstaje dopiero przy sporządzaniu oceny (§ 11 rozp.)."""
    tresc = tresc_arkusza(arkusz_B("kryteria"))
    assert blok(tresc, "kryteria_i_termin", BlokKryteriow).termin.wartosc == "02.10.2026"
    assert podpisy(tresc, "potwierdzenie_kryteriow") == [
        [("Warszawa", "miejscowość"), ("03.10.2024", "data (dd.mm.rrrr)"), ("", "podpis oceniającego")],
        [("", "miejscowość"), ("", "data (dd.mm.rrrr)"), ("", "podpis ocenianego")],
    ]
    assert [ocena for _, ocena in oceny_w_tabeli(tresc)] == [None] * 8
    assert blok(tresc, "oceny_czastkowe", BlokOcen).srednia.wartosc == ""
    przyznanie = blok(tresc, "przyznanie_oceny", BlokPrzyznaniaOceny)
    assert not any(w.zaznaczony for w in przyznanie.wiersze)
    assert not any(o.zaznaczona for o in przyznanie.opcje)
    assert not any(o.zaznaczona for o in blok(tresc, "wniosek_o_stopien", BlokWyboru).opcje)
    assert blok(tresc, "uzasadnienie", BlokOpisowy).tresc == ""
    assert pola(tresc, "okres_oceny") == {"OD": "", "DO": ""}
    assert "X" not in tresc.teksty()


def test_po_potwierdzeniu_kryteriow_czesc_I_ma_date_zapoznania_ocenianego():
    """§ 6 ust. 2 rozp.; przykład KPRM `4) Arkusz oceny C - główny spec.(neg).docx.md`: oceniający 17.10.2024,
    oceniany 18.10.2024."""
    tresc = tresc_arkusza(arkusz_C("potwierdzone"))
    assert podpisy(tresc, "potwierdzenie_kryteriow") == [
        [("Warszawa", "miejscowość"), ("17.10.2024", "data (dd.mm.rrrr)"), ("", "podpis oceniającego")],
        [("Warszawa", "miejscowość"), ("18.10.2024", "data (dd.mm.rrrr)"), ("", "podpis ocenianego")],
    ]


def test_po_sporzadzeniu_oceny_czesc_II_jest_wypelniona_a_miejsce_na_zapoznanie_czeka_na_ocenianego():
    """§ 11 i § 12 ust. 1 rozp.; zał. nr 3, wiersze 865-875 (podpis oceniającego, potem oświadczenie i podpis
    ocenianego)."""
    tresc = tresc_arkusza(arkusz_B("ocena"))
    assert blok(tresc, "oceny_czastkowe", BlokOcen).srednia.wartosc == "6,8"
    assert blok(tresc, "uzasadnienie", BlokOpisowy).tresc == UZASADNIENIE_B
    assert podpisy(tresc, "oceniajacy_ocena") == [
        [("Warszawa", "miejscowość"), ("02.10.2026", "data (dd.mm.rrrr)"), ("", "podpis oceniającego")],
    ]
    assert podpisy(tresc, "zapoznanie_z_ocena") == [[
        ("", "miejscowość"), ("", "data (dd.mm.rrrr)"), ("Janina Nowak", "imię i nazwisko lub pieczątka ocenianego"),
        ("", "podpis ocenianego"),
    ]]
    assert list(obiekty(tresc, BlokAdnotacji)) == []


def test_po_zapoznaniu_arkusz_ma_date_zapoznania_i_podpisy_czesci_III():
    """Przykład KPRM `2) Arkusz oceny B - naczelnik.docx.md`: Warszawa, 02.10.2026 w części II i III."""
    tresc = tresc_arkusza(arkusz_B("zapoznanie"))
    assert podpisy(tresc, "zapoznanie_z_ocena") == [[
        ("Warszawa", "miejscowość"), ("02.10.2026", "data (dd.mm.rrrr)"),
        ("Janina Nowak", "imię i nazwisko lub pieczątka ocenianego"), ("", "podpis ocenianego"),
    ]]
    assert podpisy(tresc, "umotywowanie_wniosku") == [[
        ("Warszawa", "miejscowość"), ("02.10.2026", "data (dd.mm.rrrr)"),
        ("Romuald Gut", "imię i nazwisko lub pieczątka oceniającego"), ("", "podpis oceniającego"),
    ]]


@pytest.mark.decyzja_projektowa
def test_fikcja_zapoznania_daje_adnotacje_zamiast_potwierdzenia_ocenianego():
    """Przypadek użycia KPRM „stwierdzenie fikcji zapoznania z oceną” (`use cases - opis.docx.md`): oceniany nie
    mógł lub nie chciał potwierdzić zapoznania. Wzór nie przewiduje takiej adnotacji - wydruk dodaje ją pod
    miejscem na podpis ocenianego, a daty i miejscowości przy jego podpisie nie wypełnia."""
    tresc = tresc_arkusza(arkusz_B("fikcja"))
    adnotacje = list(obiekty(tresc, BlokAdnotacji))
    assert len(adnotacje) == 1
    assert "fikcj" in adnotacje[0].tekst and "02.10.2026" in adnotacje[0].tekst
    assert "oceniający" in adnotacje[0].tekst  # kto stwierdził (rola z procesu)
    assert adnotacje[0] in tresc.sekcja("zapoznanie_z_ocena").bloki
    assert podpisy(tresc, "zapoznanie_z_ocena")[0][:2] == [("", "miejscowość"), ("", "data (dd.mm.rrrr)")]


def test_po_zmianie_oceniajacego_czesc_I_wskazuje_osobe_ktora_wyznaczyla_kryteria():
    """§ 9 ust. 3 rozp.: po zmianie na stanowisku oceniającego ocena jest sporządzana na podstawie wybranych
    wcześniej kryteriów - część I podpisał poprzedni oceniający, część II i III podpisuje obecny."""
    poprzedni = Osoba("Ewa", "Dawna", "Dyrektor", "Biuro Zarządzania Kapitałem Ludzkim")
    tresc = tresc_arkusza(arkusz_B(oceniajacy_czesc_I=poprzedni))
    assert pola(tresc, "dane_oceniajacego")["Nazwisko"] == "Dawna"
    assert pola(tresc, "oceniajacy_ocena")["Nazwisko"] == "Gut"
    assert podpisy(tresc, "umotywowanie_wniosku")[0][2][0] == "Romuald Gut"


# === Konfiguracja przepisów ===

def test_zmiana_liczby_miejsc_po_przecinku_w_konfiguracji_zmienia_wydruk_sredniej():
    """Arkusz KPRM `2) Arkusz oceny B - naczelnik.docx.md` podaje średnią 6,75 - tak drukuje asystent po
    zmianie `miejsca_po_przecinku_sredniej` na 2 (bez zmiany kodu)."""
    dwa_miejsca = replace(wczytaj_przepisy(), miejsca_po_przecinku_sredniej=2)
    assert blok(tresc_arkusza(arkusz_B(), dwa_miejsca), "oceny_czastkowe", BlokOcen).srednia.wartosc == "6,75"
    assert blok(tresc_arkusza(arkusz_B()), "oceny_czastkowe", BlokOcen).srednia.wartosc == "6,8"


def test_bez_podanych_przepisow_wydruk_uzywa_przepisow_procesu():
    dwa_miejsca = replace(wczytaj_przepisy(), miejsca_po_przecinku_sredniej=2)
    tresc = tresc_arkusza(arkusz_B(przepisy_procesu=dwa_miejsca))
    assert blok(tresc, "oceny_czastkowe", BlokOcen).srednia.wartosc == "6,75"


def test_skala_progi_nazwy_poziomow_i_limit_kryteriow_pochodza_z_konfiguracji():
    przepisy = wczytaj_przepisy()
    pierwszy, *pozostale = przepisy.poziomy
    zmienione = replace(
        przepisy,
        poziomy=(replace(pierwszy, nazwa="zdecydowanie poniżej oczekiwań", do=3), *pozostale),
        max_kryteriow_dodatkowych=2,
        sprzeciw_dni=14,
        arkusze={**przepisy.arkusze, "C": ("Rzetelność", "Współpraca")},
    )
    tresc = tresc_arkusza(arkusz_C("nowy"), zmienione)
    kryteria = blok(tresc, "kryteria_i_termin", BlokKryteriow)
    assert list(kryteria.obowiazkowe) == ["Rzetelność", "Współpraca"]
    assert kryteria.naglowek_dodatkowych.tekst == "Kryteria dodatkowe wybrane przez oceniającego (nie więcej niż 2)"
    assert blok(tresc, "oceny_czastkowe", BlokOcen).skala[0].nazwa == "Zdecydowanie poniżej oczekiwań"
    wiersze = blok(tresc, "przyznanie_oceny", BlokPrzyznaniaOceny).wiersze
    assert (wiersze[0].przedzial, wiersze[0].poziom) == ("od 1 punktu do 3 punktów", "zdecydowanie poniżej oczekiwań")
    assert wiersze[1].przedzial == "powyżej 3 punktów do 4 punktów"
    assert any("w terminie 14 dni od dnia zapoznania się z oceną" in tekst for tekst in tresc.teksty())
    przypisy = [p.tresc for strona in tresc.strony for p in strona.przypisy]
    assert any(p.startswith("NEGATYWNA") and "„zdecydowanie poniżej oczekiwań”" in p for p in przypisy)


def test_arkusz_bez_wzoru_w_rozporzadzeniu_nie_jest_drukowany():
    """Rozporządzenie określa wzory tylko arkuszy A, B i C (§ 3 ust. 2-4, załączniki nr 2-4)."""
    przepisy = wczytaj_przepisy()
    z_arkuszem_d = replace(przepisy, arkusze={**przepisy.arkusze, "D": ("Rzetelność",)})
    dane = replace(arkusz_C("nowy"), proces=ProcesOceny(arkusz="D", urzednik=False, poczatek_cyklu=d(2026, 1, 12)))
    with pytest.raises(ValueError, match="wzoru"):
        tresc_arkusza(dane, z_arkuszem_d)


# === Dokument DOCX ===

@pytest.mark.parametrize("symbol", ["A", "B", "C"])
def test_docx_otwiera_sie_i_ma_tresci_w_kolejnosci_wzoru(symbol):
    """Te same wzory co w teście kolejności treści; dokument czytany biblioteką python-docx."""
    zawartosc = generuj_arkusz_docx(pelny_arkusz(symbol))
    assert isinstance(zawartosc, bytes) and zawartosc[:2] == b"PK"
    tekst = tekst_docx(Document(io.BytesIO(zawartosc)))
    assert brakujacy_w_kolejnosci(kolejnosc_wzoru(symbol), tekst) is None


@pytest.mark.parametrize("budowniczy", [arkusz_A, arkusz_B, arkusz_C])
@pytest.mark.parametrize("etap", ETAPY)
def test_docx_zawiera_te_same_tresci_co_tresc_arkusza(budowniczy, etap):
    dane = budowniczy(etap)
    tekst = tekst_docx(otworz_docx(dane))
    brakujace = [t for t in tresc_arkusza(dane).teksty() if _spacje(t) not in tekst]
    assert brakujace == []


def test_docx_ma_format_A4():
    sekcja = otworz_docx(arkusz_B()).sections[0]
    assert (round(sekcja.page_width.mm), round(sekcja.page_height.mm)) == (210, 297)


def test_docx_ma_znak_X_w_kolumnie_przyznanej_oceny_czastkowej():
    """Zał. nr 3, CZĘŚĆ II (wiersze 759-784): kryteria w wierszach, skala 1, 3, 5, 7, 9 punktów w kolumnach;
    przykład KPRM `2) Arkusz oceny B - naczelnik.docx.md`."""
    dokument = otworz_docx(arkusz_B())
    kolumny = {1: 0, 3: 1, 5: 2, 7: 3, 9: 4}  # punkty -> numer kolumny skali we wzorze
    assert oceny_w_tabeli_docx(dokument, set(OCENY_B)) == {
        nazwa: [kolumny[punkty]] for nazwa, punkty in OCENY_B.items()
    }
    teksty = teksty_docx(dokument)
    assert brakujacy_w_kolejnosci(["1", "punkt", "3", "punkty", "5", "punktów", "7", "punktów", "9", "punktów"],
                                  teksty) is None
    assert brakujacy_w_kolejnosci([SREDNIA, "6,8"], teksty) is None


def test_docx_na_etapie_kryteriow_nie_zawiera_ocen():
    dokument = otworz_docx(arkusz_B("kryteria"))
    teksty = teksty_docx(dokument)
    assert "X" not in teksty
    assert oceny_w_tabeli_docx(dokument, set(OCENY_B)) == {nazwa: [] for nazwa in OCENY_B}
    assert "6,8" not in teksty
    assert brakujacy_w_kolejnosci(["Termin sporządzenia oceny", "02.10.2026"], teksty) is None


def test_docx_zawiera_czesc_III_tylko_gdy_jest_wniosek_o_stopien():
    assert "CZĘŚĆ III" in teksty_docx(otworz_docx(arkusz_B()))
    assert "CZĘŚĆ III" not in teksty_docx(otworz_docx(arkusz_B(wniosek="NIE")))
    assert "CZĘŚĆ III" not in teksty_docx(otworz_docx(arkusz_C()))


def test_docx_zmienia_sie_po_zmianie_konfiguracji():
    dwa_miejsca = replace(wczytaj_przepisy(), miejsca_po_przecinku_sredniej=2)
    assert "6,75" in teksty_docx(otworz_docx(arkusz_B(), dwa_miejsca))
    assert "6,75" not in teksty_docx(otworz_docx(arkusz_B()))


def test_docx_zawiera_adnotacje_o_fikcji_zapoznania():
    adnotacja = next(obiekty(tresc_arkusza(arkusz_B("fikcja")), BlokAdnotacji)).tekst
    assert _spacje(adnotacja) in teksty_docx(otworz_docx(arkusz_B("fikcja")))
    assert not any("fikcj" in tekst for tekst in teksty_docx(otworz_docx(arkusz_B("zapoznanie"))))
