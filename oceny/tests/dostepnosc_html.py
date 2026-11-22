"""Kontrola dostępności cyfrowej w samym HTML strony - bez przeglądarki.

Sprawdza te wymagania z załącznika do ustawy o dostępności cyfrowej (WCAG 2.1, poziomy A i AA), które da się
rozstrzygnąć na podstawie znaczników: język, tytuł, nagłówki, etykiety pól, nazwy przycisków i linków, tabele,
unikalne identyfikatory, pominięcie bloków, komunikaty o stanie i stan terminu podany tekstem. Każdy komunikat zaczyna się od numeru kryterium.

Kontrastu, układu przy powiększeniu i obsługi z klawiatury w znacznikach nie widać: kontrast liczy
`test_dostepnosc.py` z arkusza stylów, a pomiary w przeglądarce opisuje `dokumentacja/dostepnosc.md`.
"""

from __future__ import annotations

from collections.abc import Iterator
from html.parser import HTMLParser

_BEZ_ZAMKNIECIA = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_NAGLOWKI = ("h1", "h2", "h3", "h4", "h5", "h6")
_POLA = ("input", "select", "textarea")
_TYPY_BEZ_ETYKIETY = {"hidden", "submit", "button", "reset", "image"}
_ODWOLANIA = ("for", "aria-labelledby", "aria-describedby", "aria-controls")
_ZAKRESY_NAGLOWKA = {"col", "row", "colgroup", "rowgroup"}
CEL_POMINIECIA = "tresc"
KLASA_PRZEWIJANIA = "przewijana"
KLASA_CZEKANIA = "czekanie"
KLASA_STANU = "stan"
PRZEDROSTEK_TERMINU = "termin-"
_KLASY_TERMINU_BEZ_STANU = {"termin-data", "termin-nazwa", "termin-informacja"}  # części wiersza i termin bez stanu


class Element:
    """Węzeł uproszczonego drzewa strony."""

    def __init__(self, znacznik: str, atrybuty: dict[str, str], rodzic: Element | None) -> None:
        self.znacznik, self.atrybuty, self.rodzic = znacznik, atrybuty, rodzic
        self.dzieci: list[Element | str] = []

    def tekst(self) -> str:
        czesci = [dziecko if isinstance(dziecko, str) else dziecko.tekst() for dziecko in self.dzieci]
        return " ".join(" ".join(czesci).split())

    def potomkowie(self) -> Iterator[Element]:
        for dziecko in self.dzieci:
            if isinstance(dziecko, Element):
                yield dziecko
                yield from dziecko.potomkowie()

    def przodkowie(self) -> Iterator[Element]:
        wezel = self.rodzic
        while wezel is not None:
            yield wezel
            wezel = wezel.rodzic

    def klasy(self) -> list[str]:
        return self.atrybuty.get("class", "").split()

    def __str__(self) -> str:
        atrybuty = "".join(f' {nazwa}="{self.atrybuty[nazwa]}"' for nazwa in ("id", "name", "class", "href") if nazwa in self.atrybuty)
        return f"<{self.znacznik}{atrybuty}>"


class _Drzewo(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.korzen = Element("#dokument", {}, None)
        self._biezacy = self.korzen

    def _dodaj(self, znacznik: str, atrybuty: list[tuple[str, str | None]]) -> Element:
        element = Element(znacznik, {nazwa: wartosc or "" for nazwa, wartosc in atrybuty}, self._biezacy)
        self._biezacy.dzieci.append(element)
        return element

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = self._dodaj(tag, attrs)
        if tag not in _BEZ_ZAMKNIECIA:
            self._biezacy = element

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._dodaj(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        wezel = self._biezacy
        while wezel is not self.korzen and wezel.znacznik != tag:
            wezel = wezel.rodzic
        if wezel is not self.korzen:
            self._biezacy = wezel.rodzic

    def handle_data(self, data: str) -> None:
        self._biezacy.dzieci.append(data)


def tytul_strony(html: str) -> str:
    drzewo = _Drzewo()
    drzewo.feed(html)
    return next((element.tekst() for element in drzewo.korzen.potomkowie() if element.znacznik == "title"), "")


def bledy_dostepnosci(html: str) -> list[str]:
    """Lista naruszeń wymagań dostępności widocznych w znacznikach strony; pusta, gdy żadnego nie ma."""
    drzewo = _Drzewo()
    drzewo.feed(html)
    drzewo.close()
    elementy = list(drzewo.korzen.potomkowie())
    wg_id: dict[str, list[Element]] = {}
    for element in elementy:
        if "id" in element.atrybuty:
            wg_id.setdefault(element.atrybuty["id"], []).append(element)

    def nazwa_z_aria(element: Element) -> str:
        if element.atrybuty.get("aria-label", "").strip():
            return element.atrybuty["aria-label"].strip()
        wskazane = [wg_id[i][0].tekst() for i in element.atrybuty.get("aria-labelledby", "").split() if i in wg_id]
        return " ".join(wskazane).strip()

    def znaczniki(*nazwy: str) -> list[Element]:
        return [element for element in elementy if element.znacznik in nazwy]

    bledy: list[str] = []

    # 3.1.1 Język strony; 2.4.2 Tytuł strony
    if not any(element.atrybuty.get("lang") == "pl" for element in znaczniki("html")):
        bledy.append('3.1.1 strona nie ma języka: brak <html lang="pl">')
    if not any(element.tekst() for element in znaczniki("title")):
        bledy.append("2.4.2 strona nie ma tytułu")

    # 1.3.1 Informacje i relacje, 2.4.6 Nagłówki i etykiety: jeden nagłówek główny, bez przeskakiwania poziomów
    poziomy = [(int(element.znacznik[1]), element) for element in znaczniki(*_NAGLOWKI)]
    if sum(1 for poziom, _ in poziomy if poziom == 1) != 1:
        bledy.append(f"1.3.1 strona ma mieć dokładnie jeden nagłówek h1, a ma {sum(1 for p, _ in poziomy if p == 1)}")
    for (wyzszy, _), (nizszy, element) in zip(poziomy, poziomy[1:]):
        if nizszy - wyzszy > 1:
            bledy.append(f"1.3.1 nagłówek przeskakuje poziom (h{wyzszy} -> h{nizszy}): „{element.tekst()}”")
    for _, element in poziomy:
        if not element.tekst():
            bledy.append(f"2.4.6 pusty nagłówek {element}")

    # 4.1.1 Poprawność kodu: identyfikatory bez powtórzeń i odwołania do istniejących elementów
    for identyfikator, wystapienia in wg_id.items():
        if len(wystapienia) > 1:
            bledy.append(f'4.1.1 identyfikator id="{identyfikator}" powtarza się {len(wystapienia)} razy')
    for element in elementy:
        for atrybut in _ODWOLANIA:
            for identyfikator in element.atrybuty.get(atrybut, "").split():
                if identyfikator not in wg_id:
                    bledy.append(f'4.1.1 {element} wskazuje nieistniejący element ({atrybut}="{identyfikator}")')
        cel = element.atrybuty.get("href", "")
        if element.znacznik == "a" and cel.startswith("#") and cel[1:] not in wg_id:
            bledy.append(f"4.1.1 link {element} prowadzi do nieistniejącego miejsca na stronie")

    # 1.3.1, 3.3.2 Etykiety lub instrukcje, 4.1.2 Nazwa, rola, wartość: każde pole ma etykietę
    etykiety = {element.atrybuty["for"] for element in znaczniki("label") if element.atrybuty.get("for") and element.tekst()}
    for pole in znaczniki(*_POLA):
        if pole.znacznik == "input" and pole.atrybuty.get("type", "text") in _TYPY_BEZ_ETYKIETY:
            continue
        w_etykiecie = any(przodek.znacznik == "label" and przodek.tekst() for przodek in pole.przodkowie())
        if not (pole.atrybuty.get("id") in etykiety or w_etykiecie or nazwa_z_aria(pole)):
            bledy.append(f"3.3.2 pole formularza bez etykiety: {pole}")

    # 4.1.2, 2.4.4 Cel linku: przyciski i linki mają nazwę; 1.1.1 Treść nietekstowa: obrazy mają opis
    for element in znaczniki("button", "a", "summary"):
        if element.znacznik == "a" and "href" not in element.atrybuty:
            continue
        if not (element.tekst() or nazwa_z_aria(element)):
            bledy.append(f"4.1.2 {'link' if element.znacznik == 'a' else 'przycisk'} bez nazwy: {element}")
    for element in znaczniki("img"):
        if "alt" not in element.atrybuty:
            bledy.append(f"1.1.1 obraz bez opisu (atrybut alt): {element}")

    # 1.3.1: tabela ma nazwę i nagłówki z zakresem; 1.4.10 Dopasowanie do ekranu i 2.1.1 Klawiatura: szeroka tabela
    # przewija się we własnym obszarze, do którego da się wejść klawiaturą i który ma nazwę
    for tabela in znaczniki("table"):
        naglowki = [element for element in tabela.potomkowie() if element.znacznik == "th"]
        podpis = any(element.znacznik == "caption" and element.tekst() for element in tabela.potomkowie())
        if not (podpis or nazwa_z_aria(tabela)):
            bledy.append(f"1.3.1 tabela bez nazwy (caption): {tabela}")
        if not naglowki:
            bledy.append(f"1.3.1 tabela bez komórek nagłówkowych: {tabela}")
        for naglowek in naglowki:
            if naglowek.atrybuty.get("scope") not in _ZAKRESY_NAGLOWKA:
                bledy.append(f"1.3.1 komórka nagłówkowa bez zakresu (scope): „{naglowek.tekst()}”")
        obszar = next((przodek for przodek in tabela.przodkowie() if KLASA_PRZEWIJANIA in przodek.klasy()), None)
        if obszar is None:
            bledy.append(f"1.4.10 tabela poza obszarem przewijania (klasa {KLASA_PRZEWIJANIA}): {tabela}")
        elif obszar.atrybuty.get("tabindex") != "0" or obszar.atrybuty.get("role") != "region" or not nazwa_z_aria(obszar):
            bledy.append(f'2.1.1 obszar przewijania tabeli bez tabindex="0", role="region" albo nazwy: {obszar}')

    # 2.4.1 Możliwość pominięcia bloków: pierwszy link strony prowadzi do treści
    linki = [element for element in znaczniki("a") if "href" in element.atrybuty]
    if not linki or linki[0].atrybuty["href"] != f"#{CEL_POMINIECIA}":
        bledy.append(f"2.4.1 pierwszy link strony nie prowadzi do treści (#{CEL_POMINIECIA})")

    # 1.4.1 Użycie koloru: stan terminu pokazuje kolor obramowania wiersza - ten sam stan musi być podany tekstem
    for element in elementy:
        stany = [k for k in element.klasy() if k.startswith(PRZEDROSTEK_TERMINU) and k not in _KLASY_TERMINU_BEZ_STANU]
        if stany and not any(KLASA_STANU in potomek.klasy() and potomek.tekst() for potomek in element.potomkowie()):
            bledy.append(f"1.4.1 stan terminu podany samym kolorem, bez tekstu: {element}")

    # 4.1.3 Komunikaty o stanie: miejsce na komunikat istnieje od początku i jest puste - tekst wpisany później
    # czytnik ekranu ogłasza; elementu odkrytego razem z treścią zwykle nie ogłasza
    for element in elementy:
        if KLASA_CZEKANIA not in element.klasy():
            continue
        if element.atrybuty.get("role") != "status" or "hidden" in element.atrybuty:
            bledy.append(f'4.1.3 komunikat o stanie ma być widocznym od początku elementem role="status": {element}')
        elif element.tekst() or not element.atrybuty.get("data-komunikat", "").strip():
            bledy.append(f"4.1.3 komunikat o stanie ma być pusty i mieć treść w atrybucie data-komunikat: {element}")
    # Każdy test, który sprawdza stronę tym kontrolerem, sprawdza przy okazji, czy nie zostały na niej ślady warsztatu.
    bledy += [f"pozostałość - {uwaga}" for uwaga in pozostalosci(html)]
    return bledy


_BEZ_KONTROLI_TEKSTU = {"script", "style", "textarea", "pre", "code", "title"}
_WZORCE_POZOSTALOSCI = (
    ("komentarz szablonu", r"\{#|#\}"),
    ("znacznik szablonu", r"\{%|%\}|\{\{|\}\}"),
    ("znacznik HTML pokazany jako tekst", r"</?[a-zA-Z][a-zA-Z0-9]*(\s[^<>]*)?/?>"),
    ("podwójnie zakodowany znak", r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]{2,8});"),
)


def pozostalosci(html: str) -> list[str]:
    """Ślady warsztatu w tekście widocznym na stronie: komentarze i znaczniki szablonu, znaczniki HTML pokazane
    jako tekst oraz podwójnie zakodowane znaki. Treści pól do edycji i kodu się nie sprawdza."""
    import re

    drzewo = _Drzewo()
    drzewo.feed(html)
    uwagi = []
    for element in [drzewo.korzen, *drzewo.korzen.potomkowie()]:
        if element.znacznik in _BEZ_KONTROLI_TEKSTU or any(p.znacznik in _BEZ_KONTROLI_TEKSTU for p in element.przodkowie()):
            continue
        for tekst in (dziecko for dziecko in element.dzieci if isinstance(dziecko, str)):
            for nazwa, wzor in _WZORCE_POZOSTALOSCI:
                trafienie = re.search(wzor, tekst)
                if trafienie:
                    poczatek = max(0, trafienie.start() - 30)
                    uwagi.append(f"{nazwa}: „{' '.join(tekst[poczatek:trafienie.end() + 30].split())}” w {element}")
                    break
    return uwagi
