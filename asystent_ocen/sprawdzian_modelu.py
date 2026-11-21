"""Sprawdzian modelu językowego przed włączeniem asystenta AI.

Urząd może uruchomić inny model niż domyślny. Zanim asystent zacznie odpowiadać pracownikom, model przechodzi
pytania kontrolne z `sprawdzian_modelu.json`: odpowiedź musi zawierać wymagane informacje, nie może zawierać
zakazanych (typowe zmyślenia) i musi wskazywać oczekiwaną podstawę prawną. Pytania, na które asystent ma odmówić,
są sprawdzane bez udziału modelu.

Uruchomienie: `python -m asystent_ocen.sprawdzian_modelu --adres http://localhost:11434 --model <nazwa>`.
Kod wyjścia 0 oznacza komplet zaliczonych pytań.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .asystent_ai import BladModelu, KlientOllama, Model, OdpowiedzAI, odpowiedz_na_pytanie
from .konfiguracja import Przepisy, wczytaj_przepisy
from .zgodnosc import Wymogi

DOMYSLNE_PYTANIA = Path(__file__).with_name("sprawdzian_modelu.json")
DOMYSLNY_ADRES = "http://localhost:11434"
DOMYSLNY_MODEL = "pllum-12b-chat-2512:q4_k_m"


@dataclass(frozen=True)
class PytanieKontrolne:
    pytanie: str
    wymagane: tuple[str, ...] = ()  # informacje, które odpowiedź musi zawierać
    zakazane: tuple[str, ...] = ()  # typowe zmyślenia - odpowiedź nie może ich zawierać
    podstawa: str = ""  # przepis, który odpowiedź ma wskazać
    odmowa: str = ""  # oczekiwany powód odmowy (wtedy model nie jest pytany)


@dataclass(frozen=True)
class WynikPytania:
    pytanie: PytanieKontrolne
    odpowiedz: OdpowiedzAI | None  # None, gdy model był niedostępny
    uwagi: tuple[str, ...] = ()

    @property
    def zaliczone(self) -> bool:
        return not self.uwagi


class _Parametry(dict):
    """Wartości z przepisów do podstawienia w pytaniach, np. `{sprzeciw_dni}`."""

    def __init__(self, przepisy: Przepisy) -> None:
        super().__init__()
        self._przepisy = przepisy

    def __missing__(self, nazwa: str):
        try:
            return getattr(self._przepisy, nazwa)
        except AttributeError:
            raise ValueError(f"Sprawdzian modelu odwołuje się do nieznanego parametru przepisów: {nazwa!r}") from None


def wczytaj_pytania_kontrolne(
    sciezka: Path | str | None = None, przepisy: Przepisy | None = None
) -> tuple[PytanieKontrolne, ...]:
    """Pytania kontrolne z pliku JSON; liczby w nawiasach klamrowych są brane z przepisów."""
    parametry = _Parametry(przepisy or wczytaj_przepisy())
    dane = json.loads(Path(sciezka or DOMYSLNE_PYTANIA).read_text(encoding="utf-8"))

    def frazy(pozycja: dict, klucz: str) -> tuple[str, ...]:
        return tuple(str(fraza).format_map(parametry) for fraza in pozycja.get(klucz, ()))

    pytania = tuple(
        PytanieKontrolne(
            pytanie=pozycja["pytanie"],
            wymagane=frazy(pozycja, "wymagane"),
            zakazane=frazy(pozycja, "zakazane"),
            podstawa=pozycja.get("podstawa", ""),
            odmowa=pozycja.get("odmowa", ""),
        )
        for pozycja in dane["pytania"]
    )
    if not pytania:
        raise ValueError("Sprawdzian modelu nie zawiera żadnego pytania.")
    return pytania


def sprawdz_odpowiedz(pytanie: PytanieKontrolne, odpowiedz: OdpowiedzAI) -> tuple[str, ...]:
    """Uwagi do odpowiedzi; pusta krotka oznacza zaliczenie."""
    if pytanie.odmowa:
        if odpowiedz.odmowa and odpowiedz.powod == pytanie.odmowa:
            return ()
        uzyskano = f"odmowa ({odpowiedz.powod})" if odpowiedz.odmowa else "odpowiedź"
        return (f"oczekiwano odmowy ({pytanie.odmowa}), a jest {uzyskano}",)
    if odpowiedz.odmowa:
        return (f"nieoczekiwana odmowa ({odpowiedz.powod})",)
    tekst = odpowiedz.tekst.casefold()
    uwagi = [f"brak wymaganej informacji: „{fraza}”" for fraza in pytanie.wymagane if fraza.casefold() not in tekst]
    uwagi += [f"informacja błędna albo zmyślona: „{fraza}”" for fraza in pytanie.zakazane if fraza.casefold() in tekst]
    if pytanie.podstawa and pytanie.podstawa not in odpowiedz.powolane:
        uwagi.append(f"odpowiedź nie wskazuje podstawy prawnej: {pytanie.podstawa}")
    uwagi += [ostrzezenie for ostrzezenie in odpowiedz.ostrzezenia if "nie wskazuje podstawy prawnej" not in ostrzezenie]
    return tuple(uwagi)


def sprawdz_model(
    model: Model, pytania: Iterable[PytanieKontrolne] | None = None, wymogi: Wymogi | None = None
) -> list[WynikPytania]:
    """Zadaje modelowi pytania kontrolne przez asystenta (te same zabezpieczenia co w aplikacji)."""
    wyniki = []
    for pytanie in wczytaj_pytania_kontrolne() if pytania is None else pytania:
        try:
            odpowiedz = odpowiedz_na_pytanie(pytanie.pytanie, model=model, wymogi=wymogi)
        except BladModelu as blad:
            wyniki.append(WynikPytania(pytanie, None, (f"model niedostępny: {blad}",)))
            continue
        wyniki.append(WynikPytania(pytanie, odpowiedz, sprawdz_odpowiedz(pytanie, odpowiedz)))
    return wyniki


def main(argv: Sequence[str] | None = None, *, model: Model | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m asystent_ocen.sprawdzian_modelu",
        description="Sprawdza model językowy pytaniami kontrolnymi o procedurę ocen okresowych.",
    )
    parser.add_argument("--adres", default=os.environ.get("ASYSTENT_AI_ADRES", DOMYSLNY_ADRES), help="adres Ollamy")
    parser.add_argument("--model", default=os.environ.get("ASYSTENT_AI_MODEL", DOMYSLNY_MODEL), help="nazwa modelu")
    parser.add_argument("--limit-czasu", type=float, default=120, help="limit czasu jednej odpowiedzi w sekundach")
    argumenty = parser.parse_args(argv)
    if model is None:
        try:
            model = KlientOllama(argumenty.adres, argumenty.model, limit_czasu=argumenty.limit_czasu)
        except ValueError as blad:
            parser.error(str(blad))
    wyniki = sprawdz_model(model)
    for numer, wynik in enumerate(wyniki, start=1):
        print(f"{numer}. {'ZALICZONE' if wynik.zaliczone else 'NIEZALICZONE'} - {wynik.pytanie.pytanie}")
        if wynik.odpowiedz is not None:
            print(f"   odpowiedź: {' '.join(wynik.odpowiedz.tekst.split())}")
        for uwaga in wynik.uwagi:
            print(f"   uwaga: {uwaga}")
    zaliczone = sum(wynik.zaliczone for wynik in wyniki)
    print(f"Zaliczone: {zaliczone}/{len(wyniki)}")
    return 0 if zaliczone == len(wyniki) else 1


if __name__ == "__main__":
    sys.exit(main())
