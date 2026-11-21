"""Asystent AI - wyłącznie dwie funkcje dopuszczone w rejestrze `zgodnosc.toml`.

- PYTANIA_O_PROCEDURE: odpowiedź na pytanie o procedurę oceny okresowej, oparta wyłącznie na fragmentach
  przepisów z `baza_wiedzy.json` dobranych do pytania,
- KOREKTA_JEZYKOWA_UZASADNIENIA: propozycja poprawek językowych tekstu napisanego przez oceniającego;
  propozycję przyjmuje albo odrzuca człowiek.

Model językowy nie ocenia pracownika, nie proponuje ocen i nie pisze uzasadnień (załącznik III pkt 4 lit. b
rozporządzenia (UE) 2024/1689 - klasyfikacja i podstawy są w rejestrze funkcji AI). Każde wywołanie przechodzi
przez bramkę `wymagaj_dozwolonej_funkcji_ai`. Do modelu nie trafiają numery PESEL, adresy e-mail, numery
telefonów ani wskazane imiona i nazwiska (moduł `anonimizacja`).

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
        "i nie pisze uzasadnień. Ocena należy do oceniającego."
    )
    if podstawa:
        tresc += f" Podstawa: {podstawa}"
    return tresc + " Mogę wyjaśnić procedurę, terminy, skalę ocen i znaczenie kryteriów."


# --- wywołanie modelu i kontrola odpowiedzi ---

def _zapytaj(model: Model, wiadomosci: list[dict]) -> str:
    odpowiedz = model(wiadomosci)
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

    def __call__(self, wiadomosci: list[dict]) -> str:
        dane = json.dumps(
            {
                "model": self.model,
                "messages": list(wiadomosci),
                "stream": False,
                "options": {"temperature": self.temperatura},
            }
        ).encode("utf-8")
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
