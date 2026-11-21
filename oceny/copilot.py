"""HR Copilot - spięcie modułu AI rdzenia (`asystent_ocen.asystent_ai`) z lokalnym modelem językowym.

Model działa lokalnie (Ollama). Każde wywołanie przechodzi w rdzeniu przez rejestr funkcji AI i anonimizację.
Model odpowiada na pytania o procedurę, poprawia język tekstu napisanego przez człowieka i układa notatki
oceniającego w projekt uzasadnienia, o którego losie decyduje oceniający.

Sugestia ocen cząstkowych to funkcja wysokiego ryzyka (zał. III pkt 4 lit. b AI Act): działa tylko wtedy, gdy
urząd włączył ją własną decyzją (`rejestr_ai`), a oceny i tak wpisuje oceniający.

Wirtualny HR partner przygotowuje rozmowę oceniającą: układa z notatek pytania do rozmowy, a po decyzji urzędu
proponuje też kierunki do IPRZ (funkcja wysokiego ryzyka). Pytania zadaje i wnioski wpisuje oceniający.
"""

from __future__ import annotations

from django.conf import settings

from asystent_ocen.asystent_ai import (
    FUNKCJA_PROPOZYCJI_OCENY,
    FUNKCJA_PYTANIA,
    FUNKCJA_REDAKCJI,
    MIN_NOTATEK_DO_SUGESTII,
    ODMOWA_ZA_MALO_NOTATEK,
    BladModelu,
    KlientOllama,
    odpowiedz_na_pytanie,
    popraw_jezyk,
    zasugeruj_oceny,
    zredaguj_notatki,
)
from asystent_ocen.przygotowanie_rozmowy import (
    FUNKCJA_KIERUNKOW_IPRZ,
    FUNKCJA_PYTAN_DO_ROZMOWY,
    przygotuj_rozmowe,
)
from asystent_ocen.zgodnosc import (
    POZA_ZALACZNIKIEM_III,
    WYJATEK_ART_6_UST_3,
    WYSOKIE_RYZYKO,
    ZAKAZANA,
    BladZgodnosci,
    wymagaj_dozwolonej_funkcji_ai,
)

from . import rejestr_ai

PRZYKLADOWE_PYTANIA = (
    "Co ile sporządza się ocenę okresową?",
    "Ile mam czasu na sprzeciw od oceny?",
    "Kiedy oceniający musi napisać uzasadnienie oceny?",
    "Ile kryteriów dodatkowych może wybrać oceniający?",
    "Co się dzieje po ocenie negatywnej?",
)

MODEL_NIEDOSTEPNY = (
    "Lokalny model językowy jest teraz niedostępny. Proces oceny działa bez niego - asystent jest dodatkiem."
)
FUNKCJA_WYLACZONA = "Ta funkcja asystenta jest wyłączona w rejestrze funkcji AI urzędu."
SUGESTIA_NIEWLACZONA = (
    "Sugestia ocen cząstkowych to funkcja wysokiego ryzyka. Nie włączyła jej decyzja urzędu, więc system jej "
    "nie uruchamia."
)
BRAK_NOTATEK_DO_ROZMOWY = (
    "Nie ma jeszcze notatek z okresu oceny, więc model nie ma z czego ułożyć pytań. Dodaj notatki w panelu "
    "„Moje notatki z okresu oceny” albo przygotuj pytania samodzielnie."
)
BRAK_NOTATEK_DO_SUGESTII = (
    "Nie ma jeszcze notatek z okresu oceny, więc model nie ma na czym oprzeć sugestii. Dodaj notatki w panelu "
    "„Moje notatki z okresu oceny”."
)


# Klasyfikacje z rejestru funkcji AI w postaci dla czytelnika - do informacji przy treściach wygenerowanych przez model.
KLASYFIKACJE = {
    POZA_ZALACZNIKIEM_III: "poza katalogiem systemów wysokiego ryzyka z załącznika III AI Act",
    WYJATEK_ART_6_UST_3: "poza wysokim ryzykiem na podstawie wyjątku z art. 6 ust. 3 AI Act",
    WYSOKIE_RYZYKO: "wysokie ryzyko według AI Act",
    ZAKAZANA: "praktyka zakazana według AI Act",
}


def nota_ai(kod: str) -> dict:
    """Informacja pokazywana przy funkcji modelu i przy treści, którą wygenerował: klasyfikacja według AI Act
    z rejestru urzędu, a dla funkcji wysokiego ryzyka także decyzja urzędu o włączeniu i analizy, które ją
    poprzedziły. W pokazie zamiast decyzji jest lista analiz, które urząd wykonuje przed włączeniem.
    Pusty słownik, gdy funkcji nie ma w rejestrze."""
    wymogi = rejestr_ai.wymogi()
    funkcja = next((wpis for wpis in wymogi.funkcje_ai if wpis.kod == kod), None)
    if funkcja is None:
        return {}
    return {
        "klasyfikacja": KLASYFIKACJE.get(funkcja.klasyfikacja, funkcja.klasyfikacja),
        "podstawa": funkcja.podstawa,
        "wysokie_ryzyko": funkcja.klasyfikacja == WYSOKIE_RYZYKO,
        "pokaz": funkcja.decyzja_pokazowa,
        "organ": funkcja.decyzja_organ,
        "data": funkcja.decyzja_data,
        "decyzja": funkcja.decyzja_wlaczenia,
        "dokumenty": funkcja.decyzja_dokumenty,
        "wymagane": wymogi.warunki_wlaczenia,
    }


def model() -> KlientOllama:
    return KlientOllama(
        adres=settings.ASYSTENT_OLLAMA_ADRES,
        model=settings.ASYSTENT_MODEL,
        limit_czasu=settings.ASYSTENT_MODEL_LIMIT_CZASU,
    )


def funkcja_wlaczona(kod: str) -> bool:
    """Czy rejestr funkcji AI urzędu (rejestr z pakietu i decyzje urzędu) dopuszcza funkcję o tym kodzie."""
    try:
        wymagaj_dozwolonej_funkcji_ai(kod, rejestr_ai.wymogi())
    except BladZgodnosci:
        return False
    return True


def redakcja_notatek_dostepna() -> bool:
    return funkcja_wlaczona(FUNKCJA_REDAKCJI)


def sugestie_ocen_dostepne() -> bool:
    """Funkcja wysokiego ryzyka: dostępna tylko wtedy, gdy włączyła ją decyzja urzędu."""
    return funkcja_wlaczona(FUNKCJA_PROPOZYCJI_OCENY)


def pytania_do_rozmowy_dostepne() -> bool:
    return funkcja_wlaczona(FUNKCJA_PYTAN_DO_ROZMOWY)


def kierunki_iprz_dostepne() -> bool:
    """Funkcja wysokiego ryzyka: dostępna tylko wtedy, gdy włączyła ją decyzja urzędu."""
    return funkcja_wlaczona(FUNKCJA_KIERUNKOW_IPRZ)


def odpowiedz(pytanie: str) -> dict:
    """Odpowiedź na pytanie o procedurę: tekst, przepisy podane modelowi i ostrzeżenia kontroli odpowiedzi."""
    try:
        wynik = odpowiedz_na_pytanie(pytanie, model=model())
    except BladModelu:
        return {"blad": MODEL_NIEDOSTEPNY}
    return {"odpowiedz": wynik}


def korekta(tekst: str, osoby: list[str]) -> dict:
    """Propozycja poprawek językowych tekstu oceniającego. Treść merytoryczna zostaje jego."""
    try:
        wynik = popraw_jezyk(tekst, model=model(), osoby=osoby)
    except BladModelu:
        return {"blad": MODEL_NIEDOSTEPNY}
    return {"korekta": wynik}


def projekt_uzasadnienia(notatki: list[str], osoby: list[str]) -> dict:
    """Projekt uzasadnienia ułożony z notatek oceniającego - bez ocen cząstkowych i bez danych z EZD RP.

    Zwraca słownik z kluczem „projekt” (wynik rdzenia, także odmowa przy braku notatek) albo „blad” (komunikat).
    """
    try:
        wynik = zredaguj_notatki(notatki, model=model(), osoby=osoby)
    except BladZgodnosci:
        return {"blad": FUNKCJA_WYLACZONA}
    except BladModelu:
        return {"blad": MODEL_NIEDOSTEPNY}
    return {"projekt": wynik}


def sugestia_ocen(notatki: list[str], kryteria: list[str], osoby: list[str]) -> dict:
    """Sugestia ocen cząstkowych z notatek oceniającego - bez danych z EZD RP i bez szkicu oceny.

    Zwraca słownik z kluczem „sugestia” (wynik rdzenia, także odmowa przy zbyt małej liczbie notatek) albo „blad”
    (komunikat). Rejestr jest czytany przy każdym wywołaniu, więc wycofanie decyzji urzędu działa od razu.
    """
    try:
        wynik = zasugeruj_oceny(notatki, kryteria, model=model(), wymogi=rejestr_ai.wymogi(), osoby=osoby)
    except BladZgodnosci:
        return {"blad": SUGESTIA_NIEWLACZONA}
    except BladModelu:
        return {"blad": MODEL_NIEDOSTEPNY}
    return {"sugestia": wynik}


def sugestia_do_pokazania(wynik: dict, liczba_notatek: int) -> dict:
    """Wynik usługi `sugestia_ocen` w postaci dla karty oceny: „blad”, „odmowa” albo „wiersze” i „ostrzezenia”."""
    from .karta import skala_ocen  # import przy użyciu - karta sięga po ten moduł tylko wtedy, gdy potrzebuje AI

    if "blad" in wynik:
        return {"blad": wynik["blad"]}
    sugestia = wynik["sugestia"]
    if sugestia.odmowa:
        if sugestia.powod == ODMOWA_ZA_MALO_NOTATEK:
            return {"odmowa": (
                f"Notatek z okresu oceny jest za mało, żeby model mógł cokolwiek zasugerować (są: {liczba_notatek}, "
                f"minimalna liczba: {MIN_NOTATEK_DO_SUGESTII}). Jedna albo dwie notatki nie pokazują pracy z całego "
                "okresu oceny."
            )}
        return {"odmowa": BRAK_NOTATEK_DO_SUGESTII}
    nazwy = {pozycja["punkty"]: pozycja["nazwa"] for pozycja in skala_ocen()}
    return {
        "wiersze": [
            {
                "kryterium": pozycja.kryterium,
                "ocena": pozycja.ocena,
                "poziom": nazwy.get(pozycja.ocena, ""),
                "uzasadnienie": pozycja.uzasadnienie,
            }
            for pozycja in sugestia.sugestie
        ],
        "ostrzezenia": list(sugestia.ostrzezenia),
    }


def przygotowanie_rozmowy(notatki: list[str], osoby: list[str]) -> dict:
    """Pytania do rozmowy oceniającej i - gdy urząd włączył tę funkcję - propozycja kierunków do IPRZ.

    Zwraca słownik z kluczem „rozmowa” (wynik rdzenia, także odmowa przy braku notatek) albo „blad” (komunikat).
    Rejestr jest czytany przy każdym wywołaniu, więc wycofanie decyzji urzędu działa od razu.
    """
    try:
        wynik = przygotuj_rozmowe(notatki, model=model(), wymogi=rejestr_ai.wymogi(), osoby=osoby)
    except BladZgodnosci:
        return {"blad": FUNKCJA_WYLACZONA}
    except BladModelu:
        return {"blad": MODEL_NIEDOSTEPNY}
    return {"rozmowa": wynik}


def rozmowa_do_pokazania(wynik: dict, liczba_notatek: int) -> dict:
    """Wynik usługi `przygotowanie_rozmowy` w postaci dla karty oceny: „blad”, „odmowa” albo pytania, kierunki
    do IPRZ i ostrzeżenia."""
    if "blad" in wynik:
        return {"blad": wynik["blad"]}
    rozmowa = wynik["rozmowa"]
    if rozmowa.odmowa:
        return {"odmowa": BRAK_NOTATEK_DO_ROZMOWY}
    return {
        "pytania": list(rozmowa.pytania),
        "z_kierunkami": rozmowa.z_kierunkami,
        "kierunki": [{"kierunek": pozycja.kierunek, "podstawa": pozycja.podstawa} for pozycja in rozmowa.kierunki_iprz],
        # Funkcja kierunków jest włączona, ale notatek jest za mało, żeby model cokolwiek proponował.
        "za_malo_notatek": not rozmowa.z_kierunkami and kierunki_iprz_dostepne(),
        "min_notatek": MIN_NOTATEK_DO_SUGESTII,
        "liczba_notatek": liczba_notatek,
        "ostrzezenia": list(rozmowa.ostrzezenia),
    }
