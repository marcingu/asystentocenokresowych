"""Dobre praktyki zarządcze: krótkie podpowiedzi dla przełożonego przy polach formularzy.

To stałe teksty, nie odpowiedzi modelu językowego. Opierają się na Poradniku KPRM „Oceny okresowe w służbie
cywilnej” - punkt Poradnika jest w polu `zrodlo` - i odpowiadają na trzy potrzeby z opisu wyzwania: jak formułować
konstruktywną informację zwrotną, jak opisywać mocne strony i obszary do rozwoju oraz jak przekładać wyniki oceny
na codzienne zarządzanie zespołem. Przykłady są zmyślone i nie dotyczą żadnej osoby.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Praktyka:
    tytul: str                  # ciąg dalszy nagłówka „Dobre praktyki: ...”
    wskazowki: tuple[str, ...]
    zamiast: str                # sformułowanie, którego lepiej unikać
    napisz: str                 # to samo powiedziane faktami
    zrodlo: str = ""


PRAKTYKI = {
    "informacja_zwrotna": Praktyka(
        "jak formułować konstruktywną informację zwrotną",
        (
            "Zacznij od faktu, który da się sprawdzić: co się wydarzyło, kiedy i w jakiej sprawie.",
            "Powiedz, jaki był skutek - dla sprawy, zespołu albo obywatela.",
            "Nazwij oczekiwanie na przyszłość i zapytaj, czego pracownik potrzebuje, żeby je spełnić.",
            "Opisuj zachowanie, nie osobę. Unikaj słów „zawsze”, „nigdy” i etykiet w rodzaju „niesumienny”.",
            "Uzasadnij także ocenę pozytywną - pracownik dowie się, co robi dobrze i co warto powtarzać.",
        ),
        "Jest Pan niesystematyczny.",
        "W marcu i kwietniu trzy odpowiedzi na skargi wyszły po terminie. Wnioskodawcy czekali dłużej, a wydział "
        "tłumaczył się z opóźnień. Ustalmy, co pomoże pilnować terminów - np. cotygodniowy przegląd spraw w toku.",
        "Poradnik KPRM, pkt 6.2.5.3: uzasadnienie ma mieć formę konstruktywnej informacji zwrotnej, która pozwoli "
        "ocenianemu zmienić sposób wykonywania obowiązków.",
    ),
    "mocne_strony": Praktyka(
        "jak opisywać mocne strony i obszary do rozwoju",
        (
            "Mocną stronę pokaż na przykładzie i podaj jego skutek - samo „dobrze pracuje” niczego nie uczy.",
            "Obszar do rozwoju opisz jako umiejętność do zdobycia: co ma być inaczej i po czym to poznacie.",
            "Odnoś się do kryteriów oceny i zadań z opisu stanowiska, nie do cech charakteru.",
            "Kryterium ocenione poniżej oczekiwań to obszar rozwojowy - wskaż, o które zachowanie w nim chodzi.",
            "Każdy obszar do rozwoju połącz z formą wsparcia: szkoleniem, nowym zadaniem, mentoringiem albo pracą w parze.",
        ),
        "Słaba komunikacja.",
        "Projekty pism są poprawne merytorycznie; dwa z pięciu wymagały uproszczenia języka. Proponuję szkolenie "
        "z prostego języka i wzajemne czytanie projektów w zespole przed wysłaniem.",
        "Poradnik KPRM, pkt 6.2.5.4: wnioski do IPRZ zawierają obszary wiedzy i umiejętności wymagające doskonalenia "
        "oraz optymalne formy i metody ich realizacji.",
    ),
    "zarzadzanie": Praktyka(
        "jak przełożyć wynik oceny na codzienne zarządzanie zespołem",
        (
            "Zapisz we wnioskach do IPRZ dwa albo trzy konkretne działania z terminem, a nie listę życzeń.",
            "Przełóż mocne strony na podział zadań: powierz to, w czym pracownik jest dobry, i jedno zadanie, które go rozwija.",
            "Umów stały rytm krótkich rozmów - co miesiąc albo co kwartał - i wracaj w nich do ustaleń.",
            "Doceniaj na bieżąco i konkretnie: za co, przy jakiej sprawie i co to dało zespołowi.",
            "Notuj fakty przez cały okres oceny. Następna ocena oprze się wtedy na całej pracy, a nie na ostatnich tygodniach.",
        ),
        "Proszę się bardziej starać.",
        "Do końca kwartału prowadzi Pani szkolenie wewnętrzne z obiegu korespondencji i przejmuje jedną sprawę "
        "z zamówień publicznych z opiekunem. Wracamy do tego na rozmowie w pierwszy poniedziałek miesiąca.",
        "Poradnik KPRM, pkt 6.2.3: ocenianie jest działaniem ciągłym - pomagają comiesięczne albo cokwartalne rozmowy "
        "i decyzje oparte na faktach, a nie na opiniach.",
    ),
    "rozmowa": Praktyka(
        "jak prowadzić rozmowę z pracownikiem",
        (
            "Uprzedź, o czym będzie rozmowa, i zarezerwuj czas bez telefonów i poczty.",
            "Najpierw zapytaj pracownika, jak sam widzi miniony okres. Słuchaj więcej, niż mówisz.",
            "Zadawaj pytania otwarte: „Co Pani/Panu pomaga...?”, „Czego Pani/Pan potrzebuje, żeby...?”.",
            "Pytaj o organizację pracy i wsparcie. Nie pytaj o zdrowie ani o sprawy prywatne.",
            "Zakończ ustaleniem: kto, co i do kiedy zrobi. Zapisz je w notatce.",
        ),
        "Musimy porozmawiać o Pani wynikach.",
        "W czwartek o 10.00 chciałbym omówić z Panią ostatnie pół roku: co się udało, co było trudne i czego "
        "potrzebuje Pani ode mnie. Proszę przemyśleć dwa tematy, które są dla Pani ważne.",
        "Poradnik KPRM, pkt 6.2.4: rozmowa oceniająca ma być dialogiem oceniającego z ocenianym, a nie monologiem.",
    ),
    "notatka": Praktyka(
        "jak pisać notatkę",
        (
            "Zapisuj fakt, datę i skutek - nie ocenę osoby.",
            "Notuj także to, co poszło dobrze. Z samych potknięć nie powstanie uczciwa ocena.",
            "Pisz tak, żeby notatkę dało się bez wstydu pokazać pracownikowi.",
        ),
        "Znowu zawaliła termin.",
        "12.05 odpowiedź na interpelację wyszła 2 dni po terminie; przyczyną było oczekiwanie na opinię prawną.",
        "Poradnik KPRM, pkt 6.2.3: informacje do oceny gromadzi się przez cały okres, który jej podlega.",
    ),
}
