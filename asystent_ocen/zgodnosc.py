"""Bramki zgodności: monitoring pracy (Kodeks pracy) i rejestr funkcji AI (AI Act).

Parametry i klasyfikacje są w `zgodnosc.toml`. Uzasadnienie: dokumentacja/analiza-prawna-ai-act-kp-rodo.md.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from .bledy import Blad

POZA_ZALACZNIKIEM_III = "poza_zalacznikiem_III"
WYJATEK_ART_6_UST_3 = "wyjatek_art_6_ust_3"
WYSOKIE_RYZYKO = "wysokie_ryzyko"
ZAKAZANA = "zakazana"

_KLASYFIKACJE = (POZA_ZALACZNIKIEM_III, WYJATEK_ART_6_UST_3, WYSOKIE_RYZYKO, ZAKAZANA)
# Funkcji zakazanej (art. 5 AI Act) nie da się włączyć żadną konfiguracją.
_KLASYFIKACJE_NIEWLACZALNE = (ZAKAZANA,)
_KLASYFIKACJE_DOZWOLONE = (POZA_ZALACZNIKIEM_III, WYJATEK_ART_6_UST_3)
# Funkcję wysokiego ryzyka włącza wyłącznie decyzja urzędu zapisana w osobnym pliku wdrożenia (parametr `decyzje`
# w `wczytaj_wymogi`); rejestr z pakietu ma takie funkcje wyłączone. Włączenie nie zmienia klasyfikacji ani
# obowiązków urzędu z AI Act i RODO.

_DOMYSLNY_PLIK = Path(__file__).with_name("zgodnosc.toml")

# podstawy prawne przeszkód uruchomienia monitoringu (indeks górny artykułu zapisany w nawiasie kwadratowym)
_PODSTAWA_USTALEN = "art. 22[2] § 6 KP"
_PODSTAWA_INFORMACJI = "art. 22[2] § 7 w zw. z art. 22[3] § 3 i 4 KP"

# (pole ustaleń, kod błędu, komunikat) - w kolejności zgłaszania
_WYMAGANE_USTALENIA = (
    (
        "podstawa",
        "BRAK_PODSTAWY_MONITORINGU",
        "Nie wskazano układu zbiorowego pracy, regulaminu pracy ani obwieszczenia, w którym ustalono cele, zakres "
        "i sposób zastosowania monitoringu.",
    ),
    (
        "cele",
        "BRAK_CELOW_MONITORINGU",
        "Nie podano celów monitoringu ustalonych w układzie zbiorowym pracy, regulaminie pracy albo obwieszczeniu.",
    ),
    (
        "zakres",
        "BRAK_ZAKRESU_MONITORINGU",
        "Nie podano zakresu monitoringu ustalonego w układzie zbiorowym pracy, regulaminie pracy albo obwieszczeniu.",
    ),
    (
        "sposob",
        "BRAK_SPOSOBU_MONITORINGU",
        "Nie podano sposobu zastosowania monitoringu ustalonego w układzie zbiorowym pracy, regulaminie pracy "
        "albo obwieszczeniu.",
    ),
)


class BladZgodnosci(Exception):
    """Operacja niedopuszczalna ze względu na wymogi KP, RODO albo AI Act."""


@dataclass(frozen=True)
class WarunekWlaczenia:
    """Analiza albo czynność, którą urząd wykonuje przed włączeniem funkcji wysokiego ryzyka (`zgodnosc.toml`)."""

    kod: str
    nazwa: str
    podstawa: str


@dataclass(frozen=True)
class DokumentWarunku:
    """Dokument, którym urząd wykazał w decyzji wykonanie analizy albo czynności."""

    kod: str
    nazwa: str
    podstawa: str
    dokument: str


@dataclass(frozen=True)
class FunkcjaAI:
    kod: str
    opis: str
    klasyfikacja: str  # jedna ze stałych powyżej
    podstawa: str
    wlaczona: bool
    # Pola decyzji wypełnia tylko plik decyzji urzędu o funkcji wysokiego ryzyka. Puste = brak decyzji.
    decyzja_wlaczenia: str = ""  # zakres i warunki włączenia
    decyzja_organ: str = ""  # kto zdecydował
    decyzja_data: date | None = None  # kiedy
    decyzja_dokumenty: tuple[DokumentWarunku, ...] = ()  # analizy i czynności wykonane przed włączeniem
    # Pokaz na danych fikcyjnych: bez organu, daty i analiz; działa tylko w trybie demonstracyjnym.
    decyzja_pokazowa: bool = False


@dataclass(frozen=True)
class Wymogi:
    """Zawartość `zgodnosc.toml`."""

    monitoring_wyprzedzenie_informacji_dni: int
    min_licznosc_wskaznika: int
    ezdrp_prefiks: str
    ezdrp_rozmiar_strony: int
    ezdrp_pierwsza_strona: int
    ezdrp_status_sprawy_zakonczona: int
    ezdrp_statusy_sprawy: dict[int, str]
    ezdrp_wyniki_akceptacji: dict[int, str]
    funkcje_ai: tuple[FunkcjaAI, ...]
    zrodla: dict[str, str]
    # Analizy i czynności wymagane przed włączeniem funkcji wysokiego ryzyka.
    warunki_wlaczenia: tuple[WarunekWlaczenia, ...] = ()


def wczytaj_wymogi(
    sciezka: str | None = None, decyzje: str | Path | None = None, tryb_pokazu: bool = False
) -> Wymogi:
    """Wczytuje `zgodnosc.toml` (domyślnie plik z pakietu). Klucze słowników statusów zamienia na int.
    Rejestr funkcji AI przechodzi przez `sprawdz_rejestr_funkcji_ai` - błędna konfiguracja nie da się wczytać.

    `decyzje` to plik urzędu z decyzjami o włączeniu funkcji wysokiego ryzyka (wzór: `decyzje-ai-wzor.toml`).
    Jest czytany przy każdym wywołaniu, więc usunięcie wpisu wyłącza funkcję bez ponownego uruchamiania systemu.
    Decyzja podaje organ, datę i dokument każdej analizy i czynności z listy `warunki_wlaczenia`. Brak pliku, błąd
    w jego budowie, nieznany kod, decyzja niepełna albo decyzja o funkcji innej niż wysokiego ryzyka ->
    BladZgodnosci. Wynik z decyzjami jest nowym obiektem - rejestr z pakietu się nie zmienia.

    `tryb_pokazu` dopuszcza decyzję pokazową (`pokaz = true`, bez organu, daty i analiz) - tylko dla pokazu na
    danych fikcyjnych. Poza tym trybem plik z taką decyzją jest odrzucany.

    Plik domyślny jest czytany raz, a wynik zapamiętywany (kolejne wywołania zwracają ten sam obiekt - zmiany
    wprowadza się przez `dataclasses.replace`). Plik wskazany w `sciezka` jest czytany przy każdym wywołaniu.
    Brak klucza, zły typ albo wartość poniżej dopuszczalnego minimum -> BladZgodnosci."""
    wymogi = _wymogi_domyslne() if sciezka is None else _wczytaj_plik(Path(sciezka))
    return wymogi if decyzje is None else _z_decyzjami_urzedu(wymogi, Path(decyzje), tryb_pokazu)


@lru_cache(maxsize=1)
def _wymogi_domyslne() -> Wymogi:
    return _wczytaj_plik(_DOMYSLNY_PLIK)


def _wczytaj_plik(plik: Path) -> Wymogi:
    with plik.open("rb") as strumien:
        dane = tomllib.load(strumien)
    funkcje = tuple(_funkcja_ai(wpis, nr) for nr, wpis in enumerate(_wartosc(dane, "funkcje_ai", list), start=1))
    sprawdz_rejestr_funkcji_ai(funkcje)
    warunki = tuple(
        _warunek_wlaczenia(wpis, nr)
        for nr, wpis in enumerate(_wartosc(dane, "warunki_wlaczenia_wysokiego_ryzyka", list), start=1)
    )
    kody_warunkow = [warunek.kod for warunek in warunki]
    if not warunki or len(set(kody_warunkow)) != len(kody_warunkow):
        raise BladZgodnosci(
            "Konfiguracja zgodności: lista `warunki_wlaczenia_wysokiego_ryzyka` (analizy i czynności przed "
            "włączeniem funkcji wysokiego ryzyka) nie może być pusta ani zawierać powtórzonych kodów."
        )
    return Wymogi(
        monitoring_wyprzedzenie_informacji_dni=_liczba(dane, "monitoring.wyprzedzenie_informacji_dni", minimum=0),
        min_licznosc_wskaznika=_liczba(dane, "wiedza_o_pracy.min_licznosc_wskaznika", minimum=1),
        ezdrp_prefiks=_wartosc(dane, "ezdrp.prefiks", str),
        ezdrp_rozmiar_strony=_liczba(dane, "ezdrp.rozmiar_strony", minimum=1),
        ezdrp_pierwsza_strona=_liczba(dane, "ezdrp.pierwsza_strona", minimum=0),
        ezdrp_status_sprawy_zakonczona=_liczba(dane, "ezdrp.status_sprawy_zakonczona", minimum=0),
        ezdrp_statusy_sprawy=_slownik_kodow(dane, "ezdrp.statusy_sprawy"),
        ezdrp_wyniki_akceptacji=_slownik_kodow(dane, "ezdrp.wyniki_akceptacji"),
        funkcje_ai=funkcje,
        zrodla=dict(_wartosc(dane, "zrodla", dict)),
        warunki_wlaczenia=warunki,
    )


def _z_decyzjami_urzedu(wymogi: Wymogi, plik: Path, tryb_pokazu: bool = False) -> Wymogi:
    """Wymogi z funkcjami wysokiego ryzyka włączonymi decyzjami urzędu z pliku `plik`."""
    try:
        with plik.open("rb") as strumien:
            dane = tomllib.load(strumien)
    except (OSError, tomllib.TOMLDecodeError) as blad:
        # Sama nazwa pliku i przyczyna - komunikat trafia na ekran, więc nie może ujawniać ścieżek serwera.
        if isinstance(blad, FileNotFoundError):
            powod = "pliku nie ma"
        elif isinstance(blad, OSError):
            powod = "pliku nie można otworzyć"
        else:
            powod = f"błąd składni TOML ({blad})"
        raise BladZgodnosci(f"Nie można odczytać pliku decyzji urzędu o funkcjach AI „{plik.name}”: {powod}.") from blad
    znane = {funkcja.kod: funkcja for funkcja in wymogi.funkcje_ai}
    decyzje: dict[str, dict] = {}
    for nr, wpis in enumerate(_wartosc(dane, "decyzje", list), start=1):
        gdzie = f"decyzje[{nr}]."
        kod = _wartosc(wpis, "kod", str, gdzie)
        opis = _wartosc(wpis, "decyzja_wlaczenia", str, gdzie).strip()
        if kod in decyzje:
            raise BladZgodnosci(f"Plik decyzji urzędu: funkcja „{kod}” występuje więcej niż raz.")
        if kod not in znane:
            raise BladZgodnosci(f"Plik decyzji urzędu: funkcji „{kod}” nie ma w rejestrze funkcji AI.")
        # Funkcja zakazana przechodzi dalej - odrzuci ją kontrola rejestru, z właściwym komunikatem.
        if znane[kod].klasyfikacja not in (WYSOKIE_RYZYKO, *_KLASYFIKACJE_NIEWLACZALNE):
            raise BladZgodnosci(
                f"Plik decyzji urzędu dotyczy tylko funkcji wysokiego ryzyka, a funkcja „{kod}” ma klasyfikację "
                f"„{znane[kod].klasyfikacja}” - włącza się ją i wyłącza w rejestrze funkcji AI."
            )
        pokazowa = _wartosc(wpis, "pokaz", bool, gdzie) if "pokaz" in wpis else False
        if pokazowa and not tryb_pokazu:
            raise BladZgodnosci(
                f"Plik decyzji urzędu: wpis o funkcji „{kod}” jest decyzją pokazową (pokaz = true). Taka decyzja "
                "działa tylko w trybie demonstracyjnym, na danych fikcyjnych. Urząd włącza funkcję wysokiego "
                "ryzyka własną decyzją, która podaje organ, datę i dokument każdej analizy."
            )
        pola = {"wlaczona": True, "decyzja_wlaczenia": opis, "decyzja_pokazowa": pokazowa}
        if not pokazowa:
            pola.update(_pola_decyzji_urzedu(wpis, kod, wymogi.warunki_wlaczenia))
        decyzje[kod] = pola
    funkcje = tuple(
        replace(funkcja, **decyzje[funkcja.kod]) if funkcja.kod in decyzje else funkcja
        for funkcja in wymogi.funkcje_ai
    )
    sprawdz_rejestr_funkcji_ai(funkcje)
    return replace(wymogi, funkcje_ai=funkcje)


def _pola_decyzji_urzedu(wpis: dict, kod: str, warunki: tuple[WarunekWlaczenia, ...]) -> dict:
    """Organ, data i dokumenty analiz z wpisu decyzji urzędu. Brak albo błąd któregokolwiek -> BladZgodnosci."""
    organ = wpis.get("organ")
    if not isinstance(organ, str) or not organ.strip():
        raise BladZgodnosci(
            f"Plik decyzji urzędu: decyzja o funkcji „{kod}” nie podaje organu, który ją podjął (pole organ)."
        )
    data = wpis.get("data")
    if type(data) is not date:  # data z godziną (datetime) jest podtypem date - też jej nie przyjmujemy
        raise BladZgodnosci(
            f"Plik decyzji urzędu: decyzja o funkcji „{kod}” nie podaje daty (pole data w zapisie RRRR-MM-DD, "
            "bez cudzysłowu i godziny, np. data = 2027-12-06)."
        )
    wskazane = wpis.get("dokumenty")
    if not isinstance(wskazane, dict):
        wskazane = {}
    nieznane = sorted(set(wskazane) - {warunek.kod for warunek in warunki})
    if nieznane:
        raise BladZgodnosci(
            f"Plik decyzji urzędu: decyzja o funkcji „{kod}” wskazuje pozycje spoza listy analiz i czynności "
            f"z rejestru: {', '.join(nieznane)}."
        )
    dokumenty = []
    for warunek in warunki:
        dokument = wskazane.get(warunek.kod)
        if isinstance(dokument, str) and dokument.strip():
            dokumenty.append(DokumentWarunku(warunek.kod, warunek.nazwa, warunek.podstawa, dokument.strip()))
    brakujace = _warunki_bez_dokumentu(dokumenty, warunki)
    if brakujace:
        raise BladZgodnosci(
            f"Plik decyzji urzędu: decyzja o funkcji „{kod}” nie wskazuje dokumentu dla: {'; '.join(brakujace)}. "
            "Urząd wykonuje te analizy i czynności, zanim włączy funkcję wysokiego ryzyka."
        )
    return {"decyzja_organ": organ.strip(), "decyzja_data": data, "decyzja_dokumenty": tuple(dokumenty)}


def _warunki_bez_dokumentu(dokumenty, warunki: tuple[WarunekWlaczenia, ...]) -> list[str]:
    """Analizy i czynności z rejestru, dla których decyzja nie wskazuje dokumentu - z podstawą prawną."""
    wskazane = {dokument.kod for dokument in dokumenty if (dokument.dokument or "").strip()}
    return [f"{warunek.nazwa} ({warunek.podstawa})" for warunek in warunki if warunek.kod not in wskazane]


def _warunek_wlaczenia(wpis: object, nr: int) -> WarunekWlaczenia:
    gdzie = f"warunki_wlaczenia_wysokiego_ryzyka[{nr}]."
    pola = {klucz: _wartosc(wpis, klucz, str, gdzie).strip() for klucz in ("kod", "nazwa", "podstawa")}
    if not all(pola.values()):
        raise BladZgodnosci(f"Konfiguracja zgodności: wpis `{gdzie[:-1]}` wymaga kodu, nazwy i podstawy prawnej.")
    return WarunekWlaczenia(**pola)


def _wartosc(dane: object, klucz: str, typ: type, gdzie: str = ""):
    """Wartość spod klucza z kropkami (np. `ezdrp.prefiks`). Brak klucza albo zły typ -> BladZgodnosci."""
    wartosc = dane
    for czesc in klucz.split("."):
        if not isinstance(wartosc, dict) or czesc not in wartosc:
            raise BladZgodnosci(f"Konfiguracja zgodności: brak klucza `{gdzie}{klucz}`.")
        wartosc = wartosc[czesc]
    # bool jest w Pythonie podtypem int - `true` w miejscu liczby to błąd konfiguracji, a nie 1
    if not isinstance(wartosc, typ) or (typ is int and isinstance(wartosc, bool)):
        raise BladZgodnosci(
            f"Konfiguracja zgodności: klucz `{gdzie}{klucz}` ma typ {type(wartosc).__name__}, "
            f"wymagany {typ.__name__}."
        )
    return wartosc


def _liczba(dane: dict, klucz: str, *, minimum: int) -> int:
    wartosc = _wartosc(dane, klucz, int)
    if wartosc < minimum:
        raise BladZgodnosci(f"Konfiguracja zgodności: `{klucz}` = {wartosc}, wymagane co najmniej {minimum}.")
    return wartosc


def _slownik_kodow(dane: dict, klucz: str) -> dict[int, str]:
    """Słownik statusów z TOML (klucze są tam napisami) -> {kod liczbowy: nazwa}."""
    slownik: dict[int, str] = {}
    for kod, nazwa in _wartosc(dane, klucz, dict).items():
        try:
            numer = int(kod)
        except ValueError:
            numer = None
        if numer is None or not isinstance(nazwa, str) or not nazwa.strip():
            raise BladZgodnosci(
                f"Konfiguracja zgodności: `{klucz}` - wpis {kod!r} = {nazwa!r} nie jest parą: kod liczbowy, nazwa."
            )
        slownik[numer] = nazwa
    return slownik


def _funkcja_ai(wpis: object, nr: int) -> FunkcjaAI:
    # Opisu decyzji o włączeniu nie czyta się z rejestru: funkcja wysokiego ryzyka z `wlaczona = true` nie przejdzie
    # kontroli, więc w tym pliku nie da się jej włączyć. Decyzje urzędu są w osobnym pliku (`_z_decyzjami_urzedu`).
    gdzie = f"funkcje_ai[{nr}]."
    return FunkcjaAI(
        kod=_wartosc(wpis, "kod", str, gdzie),
        opis=_wartosc(wpis, "opis", str, gdzie),
        klasyfikacja=_wartosc(wpis, "klasyfikacja", str, gdzie),
        podstawa=_wartosc(wpis, "podstawa", str, gdzie),
        wlaczona=_wartosc(wpis, "wlaczona", bool, gdzie),
    )


def _wymogi(wymogi: Wymogi | None) -> Wymogi:
    """Przekazane wymogi mają pierwszeństwo; bez nich obowiązuje plik z pakietu."""
    return wczytaj_wymogi() if wymogi is None else wymogi


@dataclass(frozen=True)
class UstaleniaMonitoringu:
    """Ustalenia pracodawcy wymagane przed uruchomieniem „innej formy monitoringu” (art. 22[3] § 4 KP).

    podstawa - wskazanie układu zbiorowego pracy, regulaminu pracy albo obwieszczenia (art. 22[2] § 6 KP);
    cele, zakres, sposob - treść ustaleń z art. 22[2] § 6 KP;
    data_poinformowania - dzień poinformowania pracowników (art. 22[2] § 7 KP)."""

    podstawa: str
    cele: str
    zakres: str
    sposob: str
    data_poinformowania: date | None


def najwczesniejsze_uruchomienie_monitoringu(data_poinformowania: date, wymogi: Wymogi | None = None) -> date:
    """Art. 22[2] § 7 w zw. z art. 22[3] § 3-4 KP: informacja „nie później niż 2 tygodnie przed uruchomieniem”,
    czyli uruchomienie najwcześniej w dniu: data poinformowania + `monitoring_wyprzedzenie_informacji_dni`."""
    return data_poinformowania + timedelta(days=_wymogi(wymogi).monitoring_wyprzedzenie_informacji_dni)


def bledy_uruchomienia_monitoringu(
    ustalenia: UstaleniaMonitoringu, dzien: date, wymogi: Wymogi | None = None
) -> list[Blad]:
    """Lista przeszkód uruchomienia integracji z EZD RP w dniu `dzien` (pusta = można uruchomić).

    Kody (każdy błąd ma podstawę prawną z KP):
    BRAK_PODSTAWY_MONITORINGU, BRAK_CELOW_MONITORINGU, BRAK_ZAKRESU_MONITORINGU, BRAK_SPOSOBU_MONITORINGU
    (art. 22[2] § 6; pusty napis albo same odstępy = brak), BRAK_POINFORMOWANIA_PRACOWNIKOW (art. 22[2] § 7),
    MONITORING_ZA_WCZESNIE (art. 22[2] § 7 - przed upływem 2 tygodni od poinformowania)."""
    wymogi = _wymogi(wymogi)
    bledy = [
        Blad(kod=kod, komunikat=komunikat, podstawa=_PODSTAWA_USTALEN)
        for pole, kod, komunikat in _WYMAGANE_USTALENIA
        if not (getattr(ustalenia, pole) or "").strip()
    ]
    dni = wymogi.monitoring_wyprzedzenie_informacji_dni
    poinformowano = ustalenia.data_poinformowania
    if poinformowano is None:
        bledy.append(
            Blad(
                kod="BRAK_POINFORMOWANIA_PRACOWNIKOW",
                komunikat="Nie podano dnia poinformowania pracowników o wprowadzeniu monitoringu. Integrację można "
                f"uruchomić najwcześniej {dni} dni po poinformowaniu.",
                podstawa=_PODSTAWA_INFORMACJI,
            )
        )
        return bledy
    najwczesniej = najwczesniejsze_uruchomienie_monitoringu(poinformowano, wymogi)
    if dzien < najwczesniej:
        bledy.append(
            Blad(
                kod="MONITORING_ZA_WCZESNIE",
                komunikat=f"Pracowników poinformowano o monitoringu {poinformowano:%d.%m.%Y}, więc integrację można "
                f"uruchomić najwcześniej {najwczesniej:%d.%m.%Y} ({dni} dni po poinformowaniu), "
                f"a nie {dzien:%d.%m.%Y}.",
                podstawa=_PODSTAWA_INFORMACJI,
            )
        )
    return bledy


def sprawdz_rejestr_funkcji_ai(funkcje: Iterable[FunkcjaAI]) -> None:
    """Rzuca BladZgodnosci, gdy: klasyfikacja spoza czterech stałych, brak podstawy klasyfikacji, powtórzony kod,
    funkcja zakazana ma `wlaczona = True` albo funkcja wysokiego ryzyka jest włączona bez decyzji urzędu:
    opisu, organu i daty (decyzja pokazowa wymaga tylko opisu). Kompletność dokumentów analiz sprawdza
    wczytanie pliku decyzji i `wymagaj_dozwolonej_funkcji_ai` - do tego potrzebna jest lista z rejestru."""
    problemy: list[str] = []
    kody: set[str] = set()
    for funkcja in funkcje:
        if funkcja.kod in kody:
            problemy.append(f"kod „{funkcja.kod}” występuje więcej niż raz")
        kody.add(funkcja.kod)
        if funkcja.klasyfikacja not in _KLASYFIKACJE:
            problemy.append(
                f"funkcja „{funkcja.kod}” ma klasyfikację „{funkcja.klasyfikacja}” spoza dozwolonych "
                f"({', '.join(_KLASYFIKACJE)})"
            )
        if not (funkcja.podstawa or "").strip():
            problemy.append(f"funkcja „{funkcja.kod}” nie ma podstawy klasyfikacji")
        # bezpieczny kierunek: wszystko poza jawnym False liczy się jako próba włączenia
        if funkcja.klasyfikacja in _KLASYFIKACJE_NIEWLACZALNE and funkcja.wlaczona is not False:
            problemy.append(
                f"funkcja „{funkcja.kod}” o klasyfikacji „{funkcja.klasyfikacja}” nie może być włączona"
            )
        if (
            funkcja.klasyfikacja == WYSOKIE_RYZYKO
            and funkcja.wlaczona is not False
            and not (funkcja.decyzja_wlaczenia or "").strip()
        ):
            problemy.append(
                f"funkcja „{funkcja.kod}” wysokiego ryzyka może być włączona tylko z opisaną decyzją urzędu "
                "(pole decyzja_wlaczenia)"
            )
        if (
            funkcja.klasyfikacja == WYSOKIE_RYZYKO
            and funkcja.wlaczona is not False
            and funkcja.decyzja_pokazowa is not True
            and not ((funkcja.decyzja_organ or "").strip() and type(funkcja.decyzja_data) is date)
        ):
            problemy.append(
                f"funkcja „{funkcja.kod}” wysokiego ryzyka może być włączona tylko decyzją urzędu, która podaje "
                "organ i datę (pola organ i data)"
            )
    if problemy:
        raise BladZgodnosci("Rejestr funkcji AI jest niezgodny z wymogami: " + "; ".join(problemy) + ".")


def rejestr_funkcji_ai(wymogi: Wymogi | None = None) -> tuple[FunkcjaAI, ...]:
    """Wszystkie funkcje AI z konfiguracji, w kolejności z pliku - także wyłączone, wysokiego ryzyka i zakazane."""
    return tuple(_wymogi(wymogi).funkcje_ai)


def wymagaj_dozwolonej_funkcji_ai(kod: str, wymogi: Wymogi | None = None) -> FunkcjaAI:
    """Zwraca funkcję, gdy istnieje w rejestrze, jest włączona i nie jest zakazana; funkcja wysokiego ryzyka
    musi mieć dodatkowo decyzję urzędu: opis, organ, datę i dokument każdej analizy z rejestru (albo decyzję
    pokazową - tę dopuszcza tylko wczytanie w trybie pokazu).
    W przeciwnym razie (także dla nieznanego kodu) rzuca BladZgodnosci z podstawą klasyfikacji w komunikacie."""
    wpisy = [funkcja for funkcja in rejestr_funkcji_ai(wymogi) if funkcja.kod == kod]
    if not wpisy:
        raise BladZgodnosci(
            f"Funkcja AI „{kod}” nie jest wpisana do rejestru funkcji AI, więc nie ma klasyfikacji według AI Act "
            "ani jej podstawy - nie można jej użyć."
        )
    # rejestr mógł zostać zbudowany z pominięciem `wczytaj_wymogi`, dlatego każdy wpis o tym kodzie musi być dozwolony
    for funkcja in wpisy:
        if funkcja.klasyfikacja == WYSOKIE_RYZYKO:
            if funkcja.wlaczona is True and not (funkcja.decyzja_wlaczenia or "").strip():
                raise BladZgodnosci(
                    f"Funkcja AI „{kod}” jest funkcją wysokiego ryzyka i nie ma opisanej decyzji o włączeniu, "
                    f"więc nie można jej użyć. Podstawa klasyfikacji: {funkcja.podstawa}"
                )
            if funkcja.wlaczona is True and funkcja.decyzja_pokazowa is not True:
                braki = [
                    *([] if (funkcja.decyzja_organ or "").strip() else ["organ, który podjął decyzję"]),
                    *([] if type(funkcja.decyzja_data) is date else ["data decyzji"]),
                    *_warunki_bez_dokumentu(funkcja.decyzja_dokumenty, _wymogi(wymogi).warunki_wlaczenia),
                ]
                if braki:
                    raise BladZgodnosci(
                        f"Funkcja AI „{kod}” jest funkcją wysokiego ryzyka, a decyzja urzędu o jej włączeniu jest "
                        f"niepełna - brakuje: {'; '.join(braki)}. Podstawa klasyfikacji: {funkcja.podstawa}"
                    )
        elif funkcja.klasyfikacja not in _KLASYFIKACJE_DOZWOLONE:
            raise BladZgodnosci(
                f"Funkcja AI „{kod}” ma klasyfikację „{funkcja.klasyfikacja}” i nie może być użyta w tej wersji "
                f"systemu. Podstawa klasyfikacji: {funkcja.podstawa}"
            )
        if funkcja.wlaczona is not True:
            raise BladZgodnosci(
                f"Funkcja AI „{kod}” jest wyłączona w konfiguracji (klasyfikacja „{funkcja.klasyfikacja}”). "
                f"Podstawa klasyfikacji: {funkcja.podstawa}"
            )
    return wpisy[0]
