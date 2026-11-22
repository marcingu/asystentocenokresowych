"""Partner HR: obraz sytuacji i działania możliwe do ustalenia w rozmowie - na podstawie kart obserwacji Radaru.

Karty Radaru to same fakty. Tutaj zwykły kod - nie system AI - łączy je w sygnały: spiętrzenie pracy, odkładany
wypoczynek, zakres zadań szerszy niż stałe obowiązki, dobre wyniki przy obciążeniu, moment na docenienie.
Sygnał opisuje organizację pracy, a nie osobę: nie ocenia pracownika i nie wnioskuje o emocjach ani zdrowiu.
Każdy sygnał podaje pytanie na początek rozmowy i działania, które przełożony i pracownik mogą razem ustalić.

Każde działanie ma podstawę: przepis ustawy o służbie cywilnej albo Kodeksu pracy, albo punkt Standardów
zarządzania zasobami ludzkimi w służbie cywilnej (załącznik do zarządzenia nr 6 Szefa Służby Cywilnej z 2020 r.;
dalej „Standardy ZZL”). Standardy są zaleceniami - o tym, które narzędzia działają w urzędzie, decyduje urząd.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .radar import DOBROSTAN, DOCENIENIE, KartaObserwacji
from .zasady_hr import CEL, ZASADY  # noqa: F401 - zasady są częścią interfejsu tego modułu

STANDARDY = "Standardy zarządzania zasobami ludzkimi w służbie cywilnej (zarządzenie nr 6 Szefa Służby Cywilnej z 2020 r.)"
_ORGANIZACJA = "Standardy ZZL, cz. IV pkt 4 (optymalizowanie organizacji pracy)"
_INFORMACJA_ZWROTNA = "Standardy ZZL, cz. IV pkt 6 (informacja zwrotna bieżąca i cykliczna)"
_IPRZ = "art. 108 u.s.c. (indywidualny program rozwoju zawodowego)"

_OBCIAZENIE = ("NADGODZINY", "SPRAWY_W_TOKU", "PRACA_POZA_GODZINAMI")
_WYPOCZYNEK = ("URLOP_ZALEGLY", "DLUGI_WYPOCZYNEK")
_ZAKRES = ("PRZEJETE_SPRAWY", "ZASTEPSTWA")
_WYNIKI = ("TERMINOWOSC", "PISMA_BEZ_POPRAWEK")


@dataclass(frozen=True)
class Dzialanie:
    tekst: str     # co można ustalić w rozmowie - równoważnik zdania, czytelny i dla przełożonego, i dla pracownika
    podstawa: str  # przepis albo punkt Standardów, w których ramach działanie jest możliwe


@dataclass(frozen=True)
class Sygnal:
    kod: str
    rodzaj: str                       # DOBROSTAN albo DOCENIENIE - jak rodzaj karty i notatki
    tytul: str
    obserwacja: str                   # zdanie o organizacji pracy, nie o osobie
    rozmowa: str                      # pytanie otwarte na początek rozmowy
    dzialania: tuple[Dzialanie, ...]
    karty: tuple[str, ...] = ()       # kody kart, z których sygnał wynika


def _lista(karty: Sequence[KartaObserwacji]) -> str:
    return ", ".join(karta.tytul[0].lower() + karta.tytul[1:] for karta in karty)


def sygnaly(karty: Sequence[KartaObserwacji]) -> tuple[Sygnal, ...]:
    """Sygnały w stałej kolejności: najpierw dobrostan i organizacja pracy, potem docenienie.
    Bez kart powstaje jeden sygnał z działaniami prewencyjnymi."""
    karty = tuple(karty)

    def wybrane(kody: tuple[str, ...]) -> tuple[KartaObserwacji, ...]:
        return tuple(karta for karta in karty if karta.kod in kody)

    def kody(wybor: Sequence[KartaObserwacji]) -> tuple[str, ...]:
        return tuple(karta.kod for karta in wybor)

    if not karty:
        return (Sygnal(
            "BEZ_SYGNALOW", DOBROSTAN, "Spokojny moment - dobry na rozmowę o planach",
            "W danych nie ma dziś sygnałów, które wymagają uwagi. To dobry moment na rozmowę o planach, "
            "zanim pojawią się trudności.",
            "Co w najbliższych miesiącach chciałaby Pani/chciałby Pan robić częściej, a czego mniej?",
            (
                Dzialanie("Stały rytm krótkich rozmów - co miesiąc albo co kwartał - z powrotem do wcześniejszych ustaleń.", _INFORMACJA_ZWROTNA),
                Dzialanie("Zadania, które dają satysfakcję - do uwzględnienia przy planowaniu rozwoju.", _IPRZ),
                Dzialanie("Urlop zaplanowany z wyprzedzeniem, w tym część trwająca co najmniej 14 kolejnych dni.", "art. 162 i 163 KP"),
            ),
        ),)

    wynik: list[Sygnal] = []
    obciazenie, wypoczynek = wybrane(_OBCIAZENIE), wybrane(_WYPOCZYNEK)
    zakres, docenienie = wybrane(_ZAKRES), tuple(karta for karta in karty if karta.rodzaj == DOCENIENIE)

    if obciazenie:
        if len(obciazenie) == 1:
            tytul = "Podwyższone obciążenie pracą"
            obserwacja = (f"Obserwujemy podwyższone obciążenie w obszarze: {_lista(obciazenie)}. "
                          "Jeżeli utrzyma się dłużej, może rodzić ryzyko przemęczenia.")
        else:
            tytul = "Spiętrzenie pracy w kilku obszarach"
            obserwacja = (f"Obserwujemy spiętrzenie pracy w {len(obciazenie)} obszarach jednocześnie: {_lista(obciazenie)}. "
                          "Taki układ może rodzić ryzyko przemęczenia.")
        dzialania = [
            Dzialanie("Priorytety po wspólnym przejrzeniu listy spraw: co jest pilne, co może poczekać, a co może przejąć ktoś inny.", _ORGANIZACJA),
            Dzialanie("Zmiana podziału czynności w komórce albo czasowe wsparcie drugiej osoby przy najbardziej pracochłonnych sprawach.", _ORGANIZACJA),
        ]
        if any(karta.kod == "NADGODZINY" for karta in obciazenie):
            dzialania.append(Dzialanie(
                "Odbiór czasu wolnego za pracę w godzinach nadliczbowych - na wniosek także bezpośrednio przed urlopem albo po nim.",
                "art. 97 ust. 6, 7 i 9 u.s.c."))
        dzialania.append(Dzialanie("Termin, w którym sprawdzicie, czy ustalenia pomogły.", _INFORMACJA_ZWROTNA))
        wynik.append(Sygnal(
            "SPIETRZENIE_PRACY", DOBROSTAN, tytul, obserwacja,
            "Które zadania zajmują Pani/Panu teraz najwięcej czasu i co możemy przesunąć albo podzielić inaczej?",
            tuple(dzialania), kody(obciazenie)))

    if wypoczynek:
        urlop = "art. 162 i 163 KP" + ("; urlop zaległy: art. 168 KP" if any(karta.kod == "URLOP_ZALEGLY" for karta in wypoczynek) else "")
        wynik.append(Sygnal(
            "ODKLADANY_WYPOCZYNEK", DOBROSTAN, "Odkładany wypoczynek",
            f"Obserwujemy odkładany wypoczynek ({_lista(wypoczynek)}). Dłuższa praca bez przerwy na odpoczynek "
            "może rodzić ryzyko przemęczenia.",
            "Kiedy w najbliższych miesiącach chciałaby Pani/chciałby Pan wziąć dłuższy urlop i co musimy przygotować, żeby było to możliwe?",
            (
                Dzialanie("Termin urlopu, w tym części trwającej co najmniej 14 kolejnych dni, wpisany do planu urlopów.", urlop),
                Dzialanie("Zastępstwo na czas urlopu, żeby sprawy nie czekały na powrót.", _ORGANIZACJA),
                Dzialanie("Lista spraw do zamknięcia i do przekazania przed urlopem.", _ORGANIZACJA),
            ), kody(wypoczynek)))

    if zakres:
        wynik.append(Sygnal(
            "SZERSZY_ZAKRES_ZADAN", DOBROSTAN, "Zakres zadań szerszy niż stałe obowiązki",
            f"Obserwujemy, że w ostatnich 12 miesiącach zakres zadań był szerszy niż stałe obowiązki ({_lista(zakres)}). "
            "Jeżeli dodatkowe zadania zostają na dłużej, warto to uporządkować.",
            "Które z przejętych zadań chciałaby Pani/chciałby Pan zatrzymać, a które powinny wrócić do poprzedniego podziału?",
            (
                Dzialanie("Przegląd dodatkowych zadań: które zostają, które wracają do poprzedniego podziału, a które wymagają wsparcia zespołu.", _ORGANIZACJA),
                Dzialanie("Wniosek o dodatek zadaniowy na okres wykonywania dodatkowych zadań - jeżeli te zadania trwają.",
                          "art. 88 u.s.c.; Standardy ZZL, cz. IV pkt 3 (dodatki zadaniowe)"),
                Dzialanie("Włączenie zadań do opisu stanowiska pracy - jeżeli zostają na stałe.",
                          "Standardy ZZL, cz. IV pkt 3 (zmiana zadań dodatkowych na stałe)"),
            ), kody(zakres)))

    if (obciazenie or wypoczynek) and docenienie:
        okolicznosci = " oraz ".join(
            f"{nazwa} ({_lista(wybor)})" for nazwa, wybor in (("podwyższone obciążenie", obciazenie), ("odkładany wypoczynek", wypoczynek)) if wybor)
        wynik.append(Sygnal(
            "DOBRE_WYNIKI_PRZY_OBCIAZENIU", DOBROSTAN, "Powody do docenienia i sygnały obciążenia jednocześnie",
            f"Obserwujemy powody do docenienia ({_lista(docenienie)}) i jednocześnie {okolicznosci}. "
            "Taki układ utrzymany przez dłuższy czas sprzyja wypaleniu zawodowemu - warto działać, zanim pojawią się trudności.",
            "Co w obecnej pracy daje Pani/Panu satysfakcję, a co warto byłoby oddać albo ograniczyć?",
            (
                Dzialanie("Docenienie i odciążenie jednocześnie: podziękowanie za wyniki i przekazanie części zadań innym osobom.", _ORGANIZACJA),
                Dzialanie("Zadanie rozwojowe zamiast kolejnego rutynowego: udział w zespole projektowym, "
                          "poprowadzenie szkolenia wewnętrznego albo rola mentora.",
                          "Standardy ZZL, cz. IV pkt 4 (nowe i interesujące zadania) i pkt 5 (zespoły projektowe)"),
                Dzialanie("Wpisanie uzgodnionego działania rozwojowego do wniosków do IPRZ.", _IPRZ),
                Dzialanie("Stały rytm krótkich rozmów z powrotem do wcześniejszych ustaleń.", _INFORMACJA_ZWROTNA),
            ), kody(obciazenie + wypoczynek + docenienie)))

    if docenienie:
        dzialania = [Dzialanie(
            "Podziękowanie osobiste i konkretne: z nazwaniem faktu z karty i tego, co dał sprawie albo zespołowi.",
            "Standardy ZZL, cz. IV pkt 4 (pochwały) i pkt 6 (informacja bieżąca)")]
        if wybrane(_WYNIKI):
            dzialania.append(Dzialanie(
                "Podziękowanie na odprawie zespołu i zaproszenie do podzielenia się sposobem pracy - w krótkim szkoleniu wewnętrznym albo w roli mentora.",
                "Standardy ZZL, cz. IV pkt 2 (szkolenia wewnętrzne i mentoring wśród kryteriów nagród)"))
        if zakres:
            dzialania.append(Dzialanie(
                "Wniosek o nagrodę z funduszu nagród z opisem konkretnych osiągnięć w uzasadnieniu.",
                "art. 93 ust. 1 u.s.c.; Standardy ZZL, cz. IV pkt 2 (nagrody)"))
        dzialania.append(Dzialanie(
            "Pisemna pochwała albo wyróżnienie - według zasad przyjętych w urzędzie.",
            "Standardy ZZL, cz. IV pkt 4 (pochwały, wyróżnienia)"))
        wynik.append(Sygnal(
            "MOMENT_NA_DOCENIENIE", DOCENIENIE, "Moment na docenienie",
            f"Obserwujemy konkretne powody do podziękowania: {_lista(docenienie)}. Docenienie działa najlepiej od razu "
            "i z podaniem faktu.",
            "Co pomogło Pani/Panu osiągnąć taki wynik i czym warto podzielić się z zespołem?",
            tuple(dzialania), kody(docenienie)))
    return tuple(wynik)
