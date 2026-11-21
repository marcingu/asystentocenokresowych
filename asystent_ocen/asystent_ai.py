"""Asystent AI - wyłącznie funkcje dopuszczone w rejestrze `zgodnosc.toml`.

- PYTANIA_O_PROCEDURE: odpowiedź na pytanie o procedurę oceny okresowej, oparta wyłącznie na fragmentach
  przepisów z `baza_wiedzy.json` dobranych do pytania,
- KOREKTA_JEZYKOWA_UZASADNIENIA: propozycja poprawek językowych tekstu napisanego przez oceniającego;
  propozycję przyjmuje albo odrzuca człowiek,
- REDAKCJA_NOTATEK_OCENIAJACEGO: projekt tekstu uzasadnienia ułożony z notatek napisanych przez oceniającego;
  model nie dostaje ocen cząstkowych, wyniku oceny ani danych z EZD RP, a projekt przyjmuje, zmienia albo
  odrzuca człowiek.

Model językowy nie ocenia pracownika i nie proponuje ocen, a treść uzasadnienia pochodzi od oceniającego
(załącznik III pkt 4 lit. b rozporządzenia (UE) 2024/1689 - klasyfikacja i podstawy są w rejestrze funkcji AI).
Każde wywołanie przechodzi przez bramkę `wymagaj_dozwolonej_funkcji_ai`. Do modelu nie trafiają numery PESEL,
adresy e-mail, numery telefonów ani wskazane imiona i nazwiska (moduł `anonimizacja`).

Odpowiedź modelu nie jest źródłem prawa: wynik zawsze wskazuje przepisy przekazane modelowi, a ostrzeżenia
sygnalizują oznaki zmyślenia (przepis albo liczba spoza podanych fragmentów, brak podstawy prawnej).

Moduł nie zależy od konkretnego modelu: model to dowolna funkcja `wiadomości -> tekst`, na przykład
`KlientOllama` dla modelu uruchomionego lokalnie w urzędzie.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .anonimizacja import anonimizuj, przywroc
from .konfiguracja import wczytaj_przepisy
from .zgodnosc import Wymogi, rejestr_funkcji_ai, wymagaj_dozwolonej_funkcji_ai

FUNKCJA_PYTANIA = "PYTANIA_O_PROCEDURE"
FUNKCJA_KOREKTY = "KOREKTA_JEZYKOWA_UZASADNIENIA"
FUNKCJA_PROPOZYCJI_OCENY = "PROPOZYCJA_OCENY"
ODMOWA_OCENA_OSOBY = "ocena_osoby"
ODMOWA_BRAK_PRZEPISU = "brak_przepisu"
DOMYSLNA_BAZA = Path(__file__).with_name("baza_wiedzy.json")

Model = Callable[[list[dict]], str]

ZASADY_ODPOWIEDZI = (
    "Wyjaśniasz procedurę ocen okresowych w służbie cywilnej. Odpowiadasz po polsku, krótko i rzeczowo, "
    "wyłącznie na podstawie przepisów podanych w wiadomości użytkownika. Warunki, terminy i liczby podawaj dosłownie "
    "tak, jak brzmią w przepisie - nie dodawaj warunków ani terminów, których w przepisach nie ma. Wykorzystaj każdy "
    "podany przepis, który odpowiada na pytanie, także przepisy o terminach. Po każdej "
    "informacji podaj podstawę prawną w nawiasie, przepisując oznaczenie z nawiasu kwadratowego przed przepisem, "
    "na przykład (art. 83 ust. 1 u.s.c.). Jeżeli podane przepisy nie pozwalają odpowiedzieć, napisz to wprost "
    "i niczego nie dopowiadaj. Nie oceniaj pracowników, nie proponuj ocen ani punktów, nie doradzaj decyzji "
    "kadrowych i nie pisz uzasadnień ocen - to zadania oceniającego."
)

ZASADY_KOREKTY = (
    "Poprawiasz wyłącznie język tekstu urzędowego: ortografię, interpunkcję, gramatykę i styl. Nie zmieniaj treści: "
    "faktów, liczb, dat, ocen ani wniosków. Nie dodawaj i nie usuwaj informacji. Znaczniki w nawiasach kwadratowych, "
    "na przykład [OSOBA_1], przepisz bez zmian. Zwróć sam poprawiony tekst, bez komentarza."
)

_BRAK_PRZEPISU = (
    "W przepisach o ocenach okresowych, którymi dysponuję, nie znalazłem podstawy do odpowiedzi na to pytanie."
)
# Dopuszczalna zmiana długości tekstu po korekcie językowej (propozycja / oryginał).
_MIN_STOSUNEK_DLUGOSCI = 0.6
_MAX_STOSUNEK_DLUGOSCI = 1.5


class BladModelu(Exception):
    """Model językowy jest niedostępny albo zwrócił odpowiedź, której nie da się użyć."""


@dataclass(frozen=True)
class Fragment:
    """Fragment przepisu z bazy wiedzy.

    `zrodlo` to oznaczenie do cytowania, np. „art. 83 ust. 1 u.s.c.”. `hasla` to słowa pomocnicze do
    wyszukiwania (potoczne sformułowania pytań) - nie są treścią przepisu i nie trafiają do modelu.
    """

    id: str
    zrodlo: str
    tytul: str
    tresc: str
    hasla: str = ""


@dataclass(frozen=True)
class OdpowiedzAI:
    tekst: str
    zrodla: tuple[str, ...] = ()  # przepisy przekazane modelowi jako podstawa odpowiedzi
    odmowa: bool = False
    powod: str = ""  # przy odmowie: ODMOWA_OCENA_OSOBY albo ODMOWA_BRAK_PRZEPISU
    ostrzezenia: tuple[str, ...] = ()
    powolane: tuple[str, ...] = ()  # te z przekazanych przepisów, które odpowiedź wskazuje jako podstawę


@dataclass(frozen=True)
class KorektaAI:
    oryginal: str
    propozycja: str  # do przyjęcia albo odrzucenia przez autora tekstu
    ostrzezenia: tuple[str, ...] = ()


# --- baza wiedzy i wyszukiwanie przepisów ---

@lru_cache(maxsize=4)
def _wczytaj_fragmenty(sciezka: str) -> tuple[Fragment, ...]:
    dane = json.loads(Path(sciezka).read_text(encoding="utf-8"))
    fragmenty = tuple(
        Fragment(
            id=pozycja["id"],
            zrodlo=pozycja["zrodlo"],
            tytul=pozycja.get("tytul", ""),
            tresc=pozycja["tresc"],
            hasla=pozycja.get("hasla", ""),
        )
        for pozycja in dane["fragmenty"]
    )
    if not fragmenty:
        raise ValueError(f"Baza wiedzy {sciezka} nie zawiera żadnego fragmentu przepisów.")
    for fragment in fragmenty:
        if not fragment.zrodlo.strip() or not fragment.tresc.strip():
            raise ValueError(f"Fragment {fragment.id!r} w bazie wiedzy nie ma źródła albo treści.")
    return fragmenty


def wczytaj_fragmenty(sciezka: Path | str | None = None) -> tuple[Fragment, ...]:
    """Fragmenty przepisów z pliku JSON (domyślnie `baza_wiedzy.json` obok modułu)."""
    return _wczytaj_fragmenty(str(sciezka or DOMYSLNA_BAZA))


_SLOWO = re.compile(r"[a-z0-9]+")
_DLUGOSC_RDZENIA = 4  # przybliżenie odmiany: „sprzeciwu” i „sprzeciw”, „stopnia” i „stopień” mają wspólny początek
_WAGA_TYTULU = 2
_WAGA_HASEL = 2
_BM25_K1 = 1.2
_BM25_B = 0.75
_POMIJANE = frozenset(
    "ale albo bedzie byc czy dla gdy gdzie ich ile jak jaka jaki jakie jakiej jakim jego jej jest kiedy kto ktora "
    "ktore ktorego ktorej ktory ktorym lub mam moge moze mozna nad nie oraz pod przez przy sie tak tego tej ten tym".split()
)


def _normalizuj(tekst: str) -> str:
    """Małe litery bez znaków diakrytycznych."""
    rozlozony = unicodedata.normalize("NFKD", str(tekst).lower().replace("ł", "l"))
    return "".join(znak for znak in rozlozony if not unicodedata.combining(znak))


def _rdzenie(tekst: str) -> list[str]:
    return [
        slowo[:_DLUGOSC_RDZENIA]
        for slowo in _SLOWO.findall(_normalizuj(tekst))
        if len(slowo) >= 3 and slowo not in _POMIJANE
    ]


@dataclass(frozen=True)
class _Indeks:
    liczniki: tuple[Counter, ...]
    dlugosci: tuple[int, ...]
    srednia_dlugosc: float
    idf: dict[str, float]


@lru_cache(maxsize=4)
def _indeks(fragmenty: tuple[Fragment, ...]) -> _Indeks:
    liczniki = []
    for fragment in fragmenty:
        licznik = Counter(_rdzenie(fragment.tresc))
        for rdzen in _rdzenie(fragment.tytul):
            licznik[rdzen] += _WAGA_TYTULU
        for rdzen in set(_rdzenie(fragment.hasla)):
            licznik[rdzen] += _WAGA_HASEL
        liczniki.append(licznik)
    dlugosci = tuple(sum(licznik.values()) for licznik in liczniki)
    wystapienia = Counter(rdzen for licznik in liczniki for rdzen in licznik)
    idf = {
        rdzen: math.log(1 + (len(fragmenty) - ile + 0.5) / (ile + 0.5)) for rdzen, ile in wystapienia.items()
    }
    return _Indeks(tuple(liczniki), dlugosci, sum(dlugosci) / len(dlugosci), idf)


def znajdz_fragmenty(
    pytanie: str, fragmenty: Iterable[Fragment] | None = None, limit: int = 4
) -> list[Fragment]:
    """Fragmenty przepisów najlepiej pasujące do pytania (ranking BM25 po początkach wyrazów treści, tytułu
    i słów pomocniczych).

    Pytanie bez żadnego wspólnego wyrazu z bazą daje pustą listę - wtedy model nie jest pytany.
    """
    fragmenty = wczytaj_fragmenty() if fragmenty is None else tuple(fragmenty)
    if not fragmenty:
        return []
    indeks = _indeks(fragmenty)
    szukane = set(_rdzenie(pytanie))
    wyniki = []
    for numer, licznik in enumerate(indeks.liczniki):
        wynik = 0.0
        for rdzen in szukane:
            ile = licznik.get(rdzen, 0)
            if ile:
                normalizacja = 1 - _BM25_B + _BM25_B * indeks.dlugosci[numer] / indeks.srednia_dlugosc
                wynik += indeks.idf[rdzen] * ile * (_BM25_K1 + 1) / (ile + _BM25_K1 * normalizacja)
        if wynik > 0:
            wyniki.append((wynik, numer))
    wyniki.sort(key=lambda para: (-para[0], para[1]))
    return [fragmenty[numer] for _, numer in wyniki[:limit]]


_ZRODLO_PARAGRAFU = re.compile(r"§ (\d+) rozp\.")
_ZRODLO_USTEPU = re.compile(r"art\. (\d+) ust\. (\d+) u\.s\.c\.")


def _czy_powoluje(inny: Fragment, znaleziony: Fragment) -> bool:
    """Czy treść fragmentu `inny` odsyła numerem do fragmentu `znaleziony`."""
    paragraf = _ZRODLO_PARAGRAFU.fullmatch(znaleziony.zrodlo)
    if paragraf:
        return inny.id.startswith("rozp-par-") and bool(re.search(rf"§ {paragraf.group(1)}(?!\d)", inny.tresc))
    ustep = _ZRODLO_USTEPU.fullmatch(znaleziony.zrodlo)
    if ustep:
        artykul, numer = ustep.groups()
        if re.search(rf"art\. {artykul} ust\. {numer}(?!\d)", inny.tresc):
            return True
        # W obrębie tego samego artykułu ustawa odsyła samym numerem ustępu („termin, o którym mowa w ust. 4”).
        return inny.id.startswith(f"usc-art-{artykul}-ust-") and bool(re.search(rf"ust\. {numer}(?!\d)", inny.tresc))
    return False


def dolacz_odeslania(
    znalezione: Sequence[Fragment], fragmenty: Iterable[Fragment] | None = None, limit: int = 2
) -> list[Fragment]:
    """Dołącza przepisy, które numerem odsyłają do znalezionych (najwyżej `limit`, w kolejności bazy).

    Przykład: pytanie o kryteria znajduje § 5, a termin tej czynności jest w § 7 („Czynności, o których mowa
    w § 5 i § 6, dokonuje się w terminie…”), który nie ma z pytaniem wspólnych wyrazów.
    """
    fragmenty = wczytaj_fragmenty() if fragmenty is None else tuple(fragmenty)
    wynik = list(znalezione)
    obecne = {fragment.id for fragment in wynik}
    dodane = 0
    for inny in fragmenty:
        if dodane >= limit:
            break
        if inny.id not in obecne and any(_czy_powoluje(inny, znaleziony) for znaleziony in znalezione):
            wynik.append(inny)
            obecne.add(inny.id)
            dodane += 1
    return wynik


# --- granica: model nie ocenia ---

# Heurystyka na tekście bez znaków diakrytycznych. Nie zastępuje bramki rejestru ani zasad w poleceniu dla
# modelu - odsiewa najczęstsze prośby, zanim cokolwiek trafi do modelu.
_WZORCE_PROSBY_O_OCENE = tuple(
    re.compile(wzorzec)
    for wzorzec in (
        r"\b(jaka|jakie|ktora|ile) (ocene|oceny|punktow|punkty)\b.{0,40}\b(wystawic|dac|przyznac|postawic|wpisac|zaproponowac)\b",
        r"\b(zaproponuj|zasugeruj|podpowiedz|wybierz|wskaz)\b.{0,30}\b(ocen|punkt|poziom)",
        r"\b(ocen|podsumuj|porownaj)\b.{0,15}\b(prac|pracownik|podwladn|pan|urzednik|osob)",
        r"\bczy\b.{0,30}\b(zwolnic|awansowac|ukarac|nagrodzic|zdegradowac|rozwiazac umowe|przedluzyc umowe)",
        r"\b(napisz|przygotuj|wygeneruj|sporzadz|uloz|stworz|zredaguj)\b.{0,30}\b(uzasadnieni|ocen|wniosk)",
    )
)


def czy_prosba_o_ocene_osoby(pytanie: str) -> bool:
    """Czy pytanie prosi o ocenę pracownika, propozycję oceny, decyzję kadrową albo napisanie uzasadnienia."""
    tekst = _normalizuj(pytanie)
    return any(wzorzec.search(tekst) for wzorzec in _WZORCE_PROSBY_O_OCENE)


def _tresc_odmowy(wymogi: Wymogi | None) -> str:
    podstawa = next(
        (funkcja.podstawa for funkcja in rejestr_funkcji_ai(wymogi) if funkcja.kod == FUNKCJA_PROPOZYCJI_OCENY), ""
    )
    tresc = (
        "Na to pytanie nie odpowiem: asystent AI nie ocenia pracowników, nie proponuje ocen ani decyzji kadrowych "
        "i nie pisze uzasadnień za oceniającego. Ocena należy do oceniającego."
    )
    if podstawa:
        tresc += f" Podstawa: {podstawa}"
    return tresc + " Mogę wyjaśnić procedurę, terminy, skalę ocen i znaczenie kryteriów."


# --- wywołanie modelu i kontrola odpowiedzi ---

def _zapytaj(model: Model, wiadomosci: list[dict], schemat: dict | None = None) -> str:
    """Odpowiedź modelu. `schemat` (JSON Schema) wymusza postać odpowiedzi - przekazywany tylko, gdy jest potrzebny."""
    odpowiedz = model(wiadomosci) if schemat is None else model(wiadomosci, schemat=schemat)
    if not isinstance(odpowiedz, str) or not odpowiedz.strip():
        raise BladModelu("Model językowy zwrócił pustą odpowiedź.")
    return odpowiedz.strip()


_POWOLANIE = re.compile(r"(art\.|§)\s*(\d+)", re.IGNORECASE)
_KRYTERIUM_W_ZRODLE = re.compile(r"kryterium „(.+)”")


def _powolania(tekst: str) -> list[tuple[str, str]]:
    return [(znak.lower(), numer) for znak, numer in _POWOLANIE.findall(tekst)]


def _liczby(tekst: str) -> list[str]:
    return sorted(re.findall(r"\d+", tekst))


def _czy_powolany(fragment: Fragment, odpowiedz: str) -> bool:
    """Czy odpowiedź wskazuje ten fragment jako podstawę (oznaczenie bez skrótu aktu albo nazwa kryterium)."""
    kryterium = _KRYTERIUM_W_ZRODLE.search(fragment.zrodlo)
    if kryterium:
        return kryterium.group(1).lower() in odpowiedz.lower() and "załącznik" in odpowiedz.lower()
    oznaczenie = re.sub(r" (u\.s\.c\.|rozp\.)$", "", fragment.zrodlo)
    return bool(re.search(rf"{re.escape(oznaczenie)}(?!\d)", odpowiedz, re.IGNORECASE))


def _ostrzezenia_do_odpowiedzi(
    odpowiedz: str, pytanie: str, fragmenty: Sequence[Fragment], powolane: Sequence[str]
) -> tuple[str, ...]:
    """Oznaki, że model wyszedł poza podane przepisy. Brak ostrzeżeń nie dowodzi poprawności odpowiedzi."""
    ostrzezenia = []
    podane = " ".join(f"{fragment.zrodlo} {fragment.tresc}" for fragment in fragmenty)
    znane_przepisy = set(_powolania(podane))
    obce = []
    for powolanie in _powolania(odpowiedz):
        if powolanie not in znane_przepisy and powolanie not in obce:
            obce.append(powolanie)
    if obce:
        lista = ", ".join(f"{znak} {numer}" for znak, numer in obce)
        ostrzezenia.append(
            f"Odpowiedź powołuje przepis, którego nie było wśród podanych modelowi ({lista}) - sprawdź go w źródle."
        )
    if not powolane:
        ostrzezenia.append(
            "Odpowiedź nie wskazuje podstawy prawnej spośród podanych przepisów - potraktuj ją ostrożnie."
        )
    znane_liczby = set(_liczby(f"{podane} {pytanie}"))
    obce_liczby = [liczba for liczba in dict.fromkeys(re.findall(r"\d+", odpowiedz)) if liczba not in znane_liczby]
    if obce_liczby:
        ostrzezenia.append(
            f"Odpowiedź zawiera liczbę, której nie ma w podanych przepisach ({', '.join(obce_liczby)}) - "
            "porównaj z brzmieniem przepisu."
        )
    return tuple(ostrzezenia)


@lru_cache(maxsize=4)
def _wzor_odpowiedzi(fragmenty: tuple[Fragment, ...]) -> tuple[dict, ...]:
    """Przykładowa wymiana pokazująca modelowi, jak wskazywać podstawę prawną.

    Powstaje z dwóch najkrótszych fragmentów bazy wiedzy, więc po zmianie przepisów nie podaje modelowi
    nieaktualnej treści. Baza z jednym fragmentem nie daje wzoru.
    """
    najkrotsze = sorted(fragmenty, key=lambda fragment: len(fragment.tresc))[:2]
    if len(najkrotsze) < 2:
        return ()
    przepisy = "\n".join(f"[{fragment.zrodlo}] {fragment.tresc}" for fragment in najkrotsze)
    odpowiedz = " ".join(f"{fragment.tresc.rstrip('.')} ({fragment.zrodlo})." for fragment in najkrotsze)
    return (
        {"role": "user", "content": f"Przepisy:\n{przepisy}\n\nPytanie: Co wynika z tych przepisów?"},
        {"role": "assistant", "content": odpowiedz},
    )


def odpowiedz_na_pytanie(
    pytanie: str,
    *,
    model: Model,
    wymogi: Wymogi | None = None,
    fragmenty: Iterable[Fragment] | None = None,
    limit: int = 4,
) -> OdpowiedzAI:
    """Odpowiedź na pytanie o procedurę oceny okresowej, oparta na przepisach z bazy wiedzy.

    Model nie jest wywoływany, gdy pytanie prosi o ocenę osoby albo gdy żaden przepis do niego nie pasuje.
    Funkcja wyłączona w rejestrze -> BladZgodnosci. Puste pytanie -> ValueError. Niedostępny model -> BladModelu.
    """
    wymagaj_dozwolonej_funkcji_ai(FUNKCJA_PYTANIA, wymogi)
    pytanie = str(pytanie or "").strip()
    if not pytanie:
        raise ValueError("Pytanie nie może być puste.")
    if czy_prosba_o_ocene_osoby(pytanie):
        return OdpowiedzAI(tekst=_tresc_odmowy(wymogi), odmowa=True, powod=ODMOWA_OCENA_OSOBY)
    fragmenty = wczytaj_fragmenty() if fragmenty is None else tuple(fragmenty)
    zanonimizowane = anonimizuj(pytanie)
    znalezione = znajdz_fragmenty(zanonimizowane.tekst, fragmenty, limit)
    if not znalezione:
        return OdpowiedzAI(tekst=_BRAK_PRZEPISU, odmowa=True, powod=ODMOWA_BRAK_PRZEPISU)
    podane = dolacz_odeslania(znalezione, fragmenty)
    przepisy = "\n".join(f"[{fragment.zrodlo}] {fragment.tresc}" for fragment in podane)
    wiadomosci = [
        {"role": "system", "content": ZASADY_ODPOWIEDZI},
        *_wzor_odpowiedzi(fragmenty),
        {"role": "user", "content": f"Przepisy:\n{przepisy}\n\nPytanie: {zanonimizowane.tekst}"},
    ]
    tekst = przywroc(_zapytaj(model, wiadomosci), zanonimizowane.mapa)
    powolane = tuple(fragment.zrodlo for fragment in podane if _czy_powolany(fragment, tekst))
    return OdpowiedzAI(
        tekst=tekst,
        zrodla=tuple(fragment.zrodlo for fragment in podane),
        ostrzezenia=_ostrzezenia_do_odpowiedzi(tekst, pytanie, podane, powolane),
        powolane=powolane,
    )


def popraw_jezyk(
    tekst: str, *, model: Model, wymogi: Wymogi | None = None, osoby: Sequence[str] = ()
) -> KorektaAI:
    """Propozycja poprawek językowych tekstu napisanego przez człowieka (np. uzasadnienia oceny).

    Model dostaje tekst bez danych osobowych; `osoby` to imiona i nazwiska do ukrycia. Ostrzeżenia wskazują
    oznaki zmiany treści: inne liczby, wyraźnie inna długość, zgubiony znacznik danych osobowych.
    Funkcja wyłączona w rejestrze -> BladZgodnosci. Pusty tekst -> ValueError. Niedostępny model -> BladModelu.
    """
    wymagaj_dozwolonej_funkcji_ai(FUNKCJA_KOREKTY, wymogi)
    oryginal = str(tekst or "")
    if not oryginal.strip():
        raise ValueError("Tekst do korekty nie może być pusty.")
    zanonimizowany = anonimizuj(oryginal, osoby)
    wiadomosci = [
        {"role": "system", "content": ZASADY_KOREKTY},
        {"role": "user", "content": zanonimizowany.tekst},
    ]
    surowa = _zapytaj(model, wiadomosci)
    ostrzezenia = []
    zgubione = [znacznik for znacznik in zanonimizowany.mapa if znacznik not in surowa]
    if zgubione:
        ostrzezenia.append(
            f"Model pominął znacznik danych osobowych ({', '.join(zgubione)}) - w propozycji może brakować tych danych."
        )
    propozycja = przywroc(surowa, zanonimizowany.mapa)
    if _liczby(propozycja) != _liczby(oryginal):
        ostrzezenia.append("Model zmienił liczby lub daty - porównaj propozycję z oryginałem.")
    stosunek = len(propozycja) / len(oryginal.strip())
    if not _MIN_STOSUNEK_DLUGOSCI <= stosunek <= _MAX_STOSUNEK_DLUGOSCI:
        ostrzezenia.append(
            "Propozycja ma wyraźnie inną długość niż oryginał - model mógł dodać albo usunąć treść."
        )
    return KorektaAI(oryginal=oryginal, propozycja=propozycja, ostrzezenia=tuple(ostrzezenia))


# --- redakcja notatek oceniającego ---

FUNKCJA_REDAKCJI = "REDAKCJA_NOTATEK_OCENIAJACEGO"
ODMOWA_BRAK_NOTATEK = "brak_notatek"

ZASADY_REDAKCJI = (
    "Układasz notatki przełożonego w projekt uzasadnienia oceny okresowej. Każdą notatkę zamień na pełne zdanie "
    "w stylu urzędowym, w tej samej kolejności. Korzystaj wyłącznie z informacji z notatek: nie dodawaj faktów, "
    "liczb, dat, określeń, przykładów, wniosków ani zapowiedzi dalszych działań, których w notatkach nie ma. "
    "Liczby i daty przepisz cyframi. Jeżeli notatka nie wskazuje, czy chodzi o kobietę, czy o mężczyznę, pisz "
    "bezosobowo. Nie proponuj ocen, punktów ani poziomu spełniania kryteriów i nie oceniaj pracownika własnymi "
    "słowami - ocenę ustala wyłącznie oceniający. Nie pisz nagłówka, wstępu ani podsumowania i nie zostawiaj pól "
    "do uzupełnienia. Zwróć sam tekst projektu."
)
# O znacznikach model dowiaduje się tylko wtedy, gdy notatki je zawierają - inaczej wymyśla własne pola.
_O_ZNACZNIKACH = "Znaczniki w nawiasach kwadratowych oznaczają ukryte dane osobowe - przepisz je bez zmian."

# Przykłady oczekiwanej postaci projektu: zdanie za notatkę, bez nagłówka i bez dopowiedzeń. Dane są zmyślone.
_WZOR_REDAKCJI = (
    {
        "role": "user",
        "content": "Notatki:\n- prowadzi rejestr umów na bieżąco, bez zaległości\n- marzec 2025: nowy wzór "
        "zestawienia kwartalnego, używa go cały wydział\n- 2 razy sprawozdanie po terminie (3 i 5 dni)",
    },
    {
        "role": "assistant",
        "content": "Prowadzi rejestr umów na bieżąco, bez zaległości. W marcu 2025 r. opracowano nowy wzór "
        "zestawienia kwartalnego, z którego korzysta cały wydział. Sprawozdanie przekazano po terminie 2 razy, "
        "z opóźnieniem 3 i 5 dni.",
    },
)
_WZOR_REDAKCJI_ZE_ZNACZNIKIEM = (
    {
        "role": "user",
        "content": "Notatki:\n- [OSOBA_1] zastępował kierownika referatu przez 6 tygodni\n- terminowość ok\n"
        f"- kontakt z klientami: 1 skarga, niezasadna\n\n{_O_ZNACZNIKACH}",
    },
    {
        "role": "assistant",
        "content": "[OSOBA_1] zastępował kierownika referatu przez 6 tygodni. Zadania wykonuje terminowo. "
        "W kontaktach z klientami odnotowano 1 skargę, która okazała się niezasadna.",
    },
)
# Projekt dłuższy niż dwukrotność notatek (z zapasem na bardzo krótkie notatki) to oznaka dopisanej treści.
_MAX_STOSUNEK_REDAKCJI = 2.0
_ZAPAS_ZNAKOW_REDAKCJI = 100
_POLE_W_NAWIASIE = re.compile(r"\[[^\[\]\n]{1,60}\]")
_DATA_DZIENNA = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")

# Wzorce na tekście bez znaków diakrytycznych. Nazwy poziomów oceny dochodzą z konfiguracji przepisów.
_WZORCE_OCENY_W_PROJEKCIE = tuple(
    re.compile(wzorzec)
    for wzorzec in (
        r"\bocen\w*\s+(?:pozytywn|negatywn)\w*",
        r"\bzasluguj\w*\s+na\s+(?:\w+\s+)?ocen\w*",
        r"\b(?:proponuj|rekomenduj|sugeruj|wnioskuj)\w*\s+(?:o\s+)?(?:\w+\s+)?ocen\w*",
        r"\b\d+\s*(?:punkt\w*|pkt)\b",
    )
)


@dataclass(frozen=True)
class RedakcjaAI:
    """Projekt tekstu ułożony z notatek oceniającego - do przyjęcia, zmiany albo odrzucenia przez człowieka."""

    propozycja: str
    odmowa: bool = False
    powod: str = ""  # przy odmowie: ODMOWA_BRAK_NOTATEK
    ostrzezenia: tuple[str, ...] = ()


def _sformulowania_o_ocenie(projekt: str, notatki: str) -> list[str]:
    """Fragmenty projektu, które brzmią jak ocena albo poziom spełniania kryteriów, a nie pochodzą z notatek."""
    tekst = _normalizuj(projekt)
    znane = _normalizuj(notatki)
    zakresy = [dopasowanie.span() for wzorzec in _WZORCE_OCENY_W_PROJEKCIE for dopasowanie in wzorzec.finditer(tekst)]
    # Nazwy poziomów są w konfiguracji przepisów (§ 11 ust. 1 pkt 1 rozp.) - zmiana skali nie wymaga zmiany kodu.
    for poziom in wczytaj_przepisy().poziomy:
        zakresy.extend(dopasowanie.span() for dopasowanie in re.finditer(re.escape(_normalizuj(poziom.nazwa)), tekst))
    fragmenty: list[str] = []
    przyjete: list[tuple[int, int]] = []
    # Dłuższe dopasowanie od tego samego miejsca najpierw: „znacznie poniżej oczekiwań” przed „poniżej oczekiwań”.
    for poczatek, koniec in sorted(set(zakresy), key=lambda zakres: (zakres[0], -zakres[1])):
        if any(p <= poczatek and koniec <= k for p, k in przyjete):
            continue
        przyjete.append((poczatek, koniec))
        if tekst[poczatek:koniec] in znane:
            continue  # to słowa oceniającego, nie modelu
        # Cytat z oryginału, o ile normalizacja nie zmieniła długości tekstu (np. wielokropek jako jeden znak).
        fragment = projekt[poczatek:koniec] if len(projekt) == len(tekst) else tekst[poczatek:koniec]
        if fragment not in fragmenty:
            fragmenty.append(fragment)
    return fragmenty


def _ostrzezenia_do_redakcji(projekt: str, notatki: str, notatki_bez_danych: str) -> tuple[str, ...]:
    """Oznaki, że projekt wychodzi poza notatki albo je gubi. Brak ostrzeżeń nie dowodzi wierności projektu.

    `notatki_bez_danych` to notatki po anonimizacji: numer PESEL albo telefonu z notatek nie musi być w projekcie.
    """
    ostrzezenia = []
    pola = [pole for pole in dict.fromkeys(_POLE_W_NAWIASIE.findall(projekt)) if pole not in notatki]
    if pola:
        ostrzezenia.append(
            f"Projekt zawiera pole w nawiasie kwadratowym, którego nie ma w notatkach ({', '.join(pola)}) - "
            "model zostawił miejsce do uzupełnienia zamiast treści."
        )
    w_projekcie = list(dict.fromkeys(re.findall(r"\d+", _POLE_W_NAWIASIE.sub(" ", projekt))))
    znane_liczby = set(_liczby(notatki))
    obce_liczby = [liczba for liczba in w_projekcie if liczba not in znane_liczby]
    if obce_liczby:
        ostrzezenia.append(
            f"Projekt zawiera liczbę, której nie ma w notatkach ({', '.join(obce_liczby)}) - sprawdź, skąd pochodzi."
        )
    # Liczby wielocyfrowe z notatek powinny zostać w projekcie. Jednocyfrową model może zapisać słownie,
    # a numer miesiąca w dacie dziennej - nazwą miesiąca.
    wymagane = re.findall(r"\d+", _DATA_DZIENNA.sub(r"\1 \3", _POLE_W_NAWIASIE.sub(" ", notatki_bez_danych)))
    pominiete = [liczba for liczba in dict.fromkeys(wymagane) if len(liczba) > 1 and liczba not in w_projekcie]
    if pominiete:
        ostrzezenia.append(
            f"W projekcie brakuje liczby z notatek ({', '.join(pominiete)}) - sprawdź, czy model nie pominął "
            "albo nie zmienił faktu."
        )
    o_ocenie = _sformulowania_o_ocenie(projekt, notatki)
    if o_ocenie:
        cytaty = ", ".join(f"„{fragment}”" for fragment in o_ocenie)
        ostrzezenia.append(
            f"Projekt zawiera sformułowanie o ocenie albo poziomie spełniania kryteriów ({cytaty}), którego nie ma "
            "w notatkach - ocenę i poziom ustala wyłącznie oceniający."
        )
    if len(projekt) > _MAX_STOSUNEK_REDAKCJI * len(notatki) + _ZAPAS_ZNAKOW_REDAKCJI:
        ostrzezenia.append(
            "Projekt jest wyraźnie dłuższy niż notatki - model mógł dopisać treść, której w nich nie ma."
        )
    return tuple(ostrzezenia)


def zredaguj_notatki(
    notatki: Iterable[str], *, model: Model, wymogi: Wymogi | None = None, osoby: Sequence[str] = ()
) -> RedakcjaAI:
    """Projekt tekstu uzasadnienia ułożony z notatek napisanych przez oceniającego.

    Funkcja nie przyjmuje ocen cząstkowych, wyniku oceny ani danych o pracy z EZD RP: model dostaje wyłącznie
    notatki, bez danych osobowych (`osoby` to imiona i nazwiska do ukrycia). Projekt przyjmuje, zmienia albo
    odrzuca oceniający. Ostrzeżenia wskazują oznaki wyjścia poza notatki albo zgubienia ich treści: pole do
    uzupełnienia, liczbę spoza notatek, pominiętą liczbę z notatek, sformułowanie o ocenie albo poziomie, tekst
    wyraźnie dłuższy niż notatki.
    Brak notatek -> odmowa bez wywołania modelu. Funkcja wyłączona w rejestrze -> BladZgodnosci.
    Niedostępny model -> BladModelu.
    """
    wymagaj_dozwolonej_funkcji_ai(FUNKCJA_REDAKCJI, wymogi)
    if isinstance(notatki, str):
        notatki = [notatki]
    tresci = [str(notatka).strip() for notatka in notatki if str(notatka or "").strip()]
    if not tresci:
        return RedakcjaAI(propozycja="", odmowa=True, powod=ODMOWA_BRAK_NOTATEK)
    zrodlo = "\n".join(f"- {tresc}" for tresc in tresci)
    zanonimizowane = anonimizuj(zrodlo, osoby)
    ze_znacznikami = bool(zanonimizowane.mapa)
    polecenie = f"Notatki:\n{zanonimizowane.tekst}"
    if ze_znacznikami:
        polecenie += f"\n\n{_O_ZNACZNIKACH}"
    wiadomosci = [
        {"role": "system", "content": ZASADY_REDAKCJI},
        *(_WZOR_REDAKCJI_ZE_ZNACZNIKIEM if ze_znacznikami else ()),
        *_WZOR_REDAKCJI,
        {"role": "user", "content": polecenie},
    ]
    projekt = przywroc(_zapytaj(model, wiadomosci), zanonimizowane.mapa)
    return RedakcjaAI(
        propozycja=projekt, ostrzezenia=_ostrzezenia_do_redakcji(projekt, zrodlo, zanonimizowane.tekst)
    )


# --- sugestia ocen cząstkowych (funkcja wysokiego ryzyka: PROPOZYCJA_OCENY) ---

ZASADY_SUGESTII = (
    "Pomagasz przełożonemu przygotować się do wystawienia oceny okresowej. Dla każdego kryterium z listy podaj "
    "sugerowaną ocenę cząstkową ze skali, opierając się wyłącznie na notatkach przełożonego. Jeżeli żadna notatka "
    "nie dotyczy kryterium, wpisz ocenę 0 i napisz, że notatki nie dają podstaw - nie zgaduj i nie zakładaj, że "
    "brak uwag oznacza dobrą albo złą pracę. W uzasadnieniu wskaż w jednym lub dwóch zdaniach, które notatki "
    "przemawiają za oceną; nie dodawaj faktów, liczb ani dat, których w notatkach nie ma, i nie powtarzaj w nim "
    "samej oceny. To tylko podpowiedź: ocenę wystawia przełożony, który zna także to, czego nie zapisał."
)
ODMOWA_ZA_MALO_NOTATEK = "za_malo_notatek"
# Decyzja zespołu, nie przepis: jedna albo dwie notatki nie pokazują pracy z całego okresu oceny, a model potrafi
# wyprowadzić z nich ocenę skrajną (próba na PLLuM-12B z 21.11.2026).
MIN_NOTATEK_DO_SUGESTII = 3
# Wartość w odpowiedzi modelu oznaczająca „notatki nie dają podstaw” - nie jest oceną i nie trafia do oceniającego.
_BRAK_PODSTAW = 0


@dataclass(frozen=True)
class SugestiaKryterium:
    kryterium: str
    ocena: int | None  # None = notatki nie dają podstaw do sugestii
    uzasadnienie: str = ""


@dataclass(frozen=True)
class SugestiaOcen:
    """Podpowiedź modelu dla oceniającego. Oceny wpisuje i za ocenę odpowiada człowiek."""

    sugestie: tuple[SugestiaKryterium, ...] = ()
    odmowa: bool = False
    powod: str = ""  # przy odmowie: ODMOWA_BRAK_NOTATEK albo ODMOWA_ZA_MALO_NOTATEK
    ostrzezenia: tuple[str, ...] = ()


def opisy_kryteriow() -> dict[str, str]:
    """Opisy kryteriów z załącznika nr 1 do rozporządzenia (z bazy wiedzy asystenta), według nazw kryteriów."""
    opisy = {}
    for fragment in wczytaj_fragmenty():
        dopasowanie = _KRYTERIUM_W_ZRODLE.search(fragment.zrodlo)
        if dopasowanie:
            opisy[dopasowanie.group(1)] = fragment.tresc
    return opisy


def _schemat_sugestii(kryteria: Sequence[str], skala: Sequence[int]) -> dict:
    """Schemat odpowiedzi: wpis dla każdego kryterium, najpierw uzasadnienie, potem ocena ze skali albo 0."""
    wpis = {
        "type": "object",
        "properties": {
            "uzasadnienie": {"type": "string"},
            "ocena": {"type": "integer", "enum": [_BRAK_PODSTAW, *sorted(skala)]},
        },
        "required": ["uzasadnienie", "ocena"],
    }
    return {"type": "object", "properties": {kryterium: wpis for kryterium in kryteria}, "required": list(kryteria)}


def zasugeruj_oceny(
    notatki: Iterable[str],
    kryteria: Sequence[str],
    *,
    model: Model,
    wymogi: Wymogi | None = None,
    osoby: Sequence[str] = (),
) -> SugestiaOcen:
    """Sugestia ocen cząstkowych dla oceniającego - funkcja wysokiego ryzyka (zał. III pkt 4 lit. b AI Act).

    Model dostaje wyłącznie notatki oceniającego (obserwacje, dodatkowe osiągnięcia, wynik egzaminu), bez danych
    osobowych, oraz nazwy i opisy kryteriów ze skalą ocen. Funkcja nie przyjmuje danych z EZD RP, szkicu ani
    wyniku oceny. Odpowiedź sprawdzają reguły: ocena spoza skali i kryterium pominięte przez model zostają bez
    sugestii, a liczba spoza notatek w uzasadnieniu daje ostrzeżenie. Sugestia nie jest oceną - oceny wpisuje
    oceniający.
    Brak notatek albo mniej niż `MIN_NOTATEK_DO_SUGESTII` -> odmowa bez wywołania modelu; ocena z krańca skali
    -> ostrzeżenie. Funkcja niewłączona decyzją urzędu -> BladZgodnosci.
    Niedostępny model albo odpowiedź w nieznanej postaci -> BladModelu.
    """
    wymagaj_dozwolonej_funkcji_ai(FUNKCJA_PROPOZYCJI_OCENY, wymogi)
    if isinstance(notatki, str):
        notatki = [notatki]
    tresci = [str(notatka).strip() for notatka in notatki if str(notatka or "").strip()]
    if not tresci:
        return SugestiaOcen(odmowa=True, powod=ODMOWA_BRAK_NOTATEK)
    if len(tresci) < MIN_NOTATEK_DO_SUGESTII:
        return SugestiaOcen(odmowa=True, powod=ODMOWA_ZA_MALO_NOTATEK)
    przepisy = wczytaj_przepisy()
    zrodlo = "\n".join(f"- {tresc}" for tresc in tresci)
    zanonimizowane = anonimizuj(zrodlo, osoby)
    opisy = opisy_kryteriow()
    # Nazwy ocen cząstkowych: skala punktów i nazwy poziomów mają w rozporządzeniu tę samą kolejność.
    skala = "; ".join(f"{punkty} - {poziom.nazwa}" for punkty, poziom in zip(sorted(przepisy.skala), przepisy.poziomy))
    skrajne = (min(przepisy.skala), max(przepisy.skala))
    lista = "\n".join(f"- {kryterium}: {opisy.get(kryterium, 'brak opisu')}" for kryterium in kryteria)
    polecenie = (
        f"Skala ocen cząstkowych: {skala}; {_BRAK_PODSTAW} - notatki nie dają podstaw.\n\n"
        f"Kryteria:\n{lista}\n\nNotatki przełożonego:\n{zanonimizowane.tekst}"
    )
    if zanonimizowane.mapa:
        polecenie += f"\n\n{_O_ZNACZNIKACH}"
    wiadomosci = [{"role": "system", "content": ZASADY_SUGESTII}, {"role": "user", "content": polecenie}]
    surowa = _zapytaj(model, wiadomosci, _schemat_sugestii(kryteria, przepisy.skala))
    try:
        odpowiedz = json.loads(surowa)
    except ValueError as blad:
        raise BladModelu("Model językowy zwrócił sugestię w nieznanej postaci.") from blad
    if not isinstance(odpowiedz, dict):
        raise BladModelu("Model językowy zwrócił sugestię w nieznanej postaci.")

    sugestie: list[SugestiaKryterium] = []
    ostrzezenia: list[str] = []
    znane_liczby = set(_liczby(zrodlo))
    for kryterium in kryteria:
        wpis = odpowiedz.get(kryterium)
        ocena = wpis.get("ocena") if isinstance(wpis, dict) else None
        if not isinstance(wpis, dict) or type(ocena) is not int:
            ostrzezenia.append(f"Model nie odniósł się do kryterium „{kryterium}” - sugestii brak.")
            sugestie.append(SugestiaKryterium(kryterium, None))
            continue
        uzasadnienie = przywroc(str(wpis.get("uzasadnienie") or "").strip(), zanonimizowane.mapa)
        if ocena != _BRAK_PODSTAW and ocena not in przepisy.skala:
            ostrzezenia.append(f"Model podał dla kryterium „{kryterium}” ocenę spoza skali ({ocena}) - pominięto ją.")
            ocena = _BRAK_PODSTAW
        obce = [liczba for liczba in dict.fromkeys(_liczby(uzasadnienie)) if len(liczba) > 1 and liczba not in znane_liczby]
        if obce:
            ostrzezenia.append(
                f"Uzasadnienie dla kryterium „{kryterium}” zawiera liczbę, której nie ma w notatkach "
                f"({', '.join(obce)}) - sprawdź, skąd pochodzi."
            )
        if ocena in skrajne:
            ostrzezenia.append(
                f"Model zasugerował dla kryterium „{kryterium}” ocenę skrajną ({ocena}) - sprawdź, czy notatki "
                "rzeczywiście ją uzasadniają."
            )
        sugestie.append(SugestiaKryterium(kryterium, None if ocena == _BRAK_PODSTAW else ocena, uzasadnienie))
    return SugestiaOcen(sugestie=tuple(sugestie), ostrzezenia=tuple(ostrzezenia))


class KlientOllama:
    """Model uruchomiony lokalnie przez Ollamę (np. PLLuM): `POST /api/chat` bez strumieniowania.

    Obiekt jest funkcją `wiadomości -> tekst`. Błąd połączenia, przekroczenie czasu i nieczytelna odpowiedź
    są zgłaszane jako BladModelu - aplikacja pokazuje wtedy, że asystent jest niedostępny, i działa dalej.
    Temperatura domyślnie 0: odpowiedzi o prawie mają być powtarzalne.
    """

    def __init__(
        self,
        adres: str,
        model: str,
        *,
        limit_czasu: float = 120,
        temperatura: float = 0,
        otworz: Callable | None = None,
    ) -> None:
        czesci = urllib.parse.urlsplit(str(adres or ""))
        if czesci.scheme not in ("http", "https") or not czesci.netloc:
            raise ValueError(f"Adres modelu musi zaczynać się od http:// albo https:// (podano: {adres!r}).")
        if not str(model or "").strip():
            raise ValueError("Podaj nazwę modelu językowego.")
        self.adres = str(adres).rstrip("/")
        self.model = model
        self.limit_czasu = limit_czasu
        self.temperatura = temperatura
        self._otworz = otworz or urllib.request.urlopen

    def __call__(self, wiadomosci: list[dict], schemat: dict | None = None) -> str:
        zapytanie = {
            "model": self.model,
            "messages": list(wiadomosci),
            "stream": False,
            "options": {"temperature": self.temperatura},
        }
        if schemat is not None:
            # JSON Schema w polu `format`: Ollama ogranicza odpowiedź modelu do tej postaci.
            zapytanie["format"] = schemat
        dane = json.dumps(zapytanie).encode("utf-8")
        zadanie = urllib.request.Request(
            f"{self.adres}/api/chat", data=dane, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with self._otworz(zadanie, timeout=self.limit_czasu) as odpowiedz:
                wynik = json.loads(odpowiedz.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as blad:
            raise BladModelu(f"Model językowy jest niedostępny ({self.adres}): {blad}") from blad
        if not isinstance(wynik, dict):
            raise BladModelu("Model językowy zwrócił odpowiedź w nieznanej postaci.")
        if wynik.get("error"):
            raise BladModelu(f"Model językowy zgłosił błąd: {wynik['error']}")
        komunikat = wynik.get("message")
        tresc = komunikat.get("content") if isinstance(komunikat, dict) else None
        if not isinstance(tresc, str) or not tresc.strip():
            raise BladModelu("Model językowy zwrócił pustą odpowiedź.")
        return tresc.strip()
