"""Zapis i odczyt stanu procesu oceny (`ProcesOceny`) w postaci słownika zgodnego z JSON.

Stan oceny jest jednym źródłem prawdy o procesie: aplikacja zapisuje go w bazie jako JSON, a przed każdą
czynnością odtwarza z niego obiekt rdzenia. Postać zapisu (dokumentacja/architektura.md, pkt 4):
- daty jako napis RRRR-MM-DD, brak daty jako null,
- wyliczenia (`Rola`, `Etap`) jako ich wartości,
- średnia (`Fraction`) jako napis „licznik/mianownik” - bez utraty dokładności na granicach przedziałów,
- pole `przepisy` nie jest zapisywane: po odczycie obowiązują przepisy domyślne (zmiana prawa nie wymaga
  przepisywania zapisanych procesów).
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

from .przebieg import OBSERWACJA, Dokument, Etap, Notatka, ProcesOceny, Rola
from .walidacja import Formularz
from .wynik import WynikOceny

WERSJA_ZAPISU = 1


# --- zapis ---

def _data_do_napisu(dzien: date | None) -> str | None:
    return None if dzien is None else dzien.isoformat()


def _wynik_do_slownika(wynik: WynikOceny | None) -> dict | None:
    if wynik is None:
        return None
    return {
        "srednia": f"{wynik.srednia.numerator}/{wynik.srednia.denominator}",
        "poziom": wynik.poziom,
        "ocena": wynik.ocena,
    }


def _formularz_do_slownika(formularz: Formularz | None) -> dict | None:
    if formularz is None:
        return None
    return {
        "arkusz": formularz.arkusz,
        "urzednik": formularz.urzednik,
        "oceny": dict(formularz.oceny),
        "kryteria_dodatkowe": list(formularz.kryteria_dodatkowe),
        "uzasadnienie": formularz.uzasadnienie,
        "wnioski_iprz": formularz.wnioski_iprz,
        "wniosek_o_stopien": formularz.wniosek_o_stopien,
        "umotywowanie_wniosku": formularz.umotywowanie_wniosku,
        "posiadany_stopien": formularz.posiadany_stopien,
    }


def proces_do_slownika(proces: ProcesOceny) -> dict:
    """Słownik gotowy do `json.dumps` (bez dodatkowych koderów); nie współdzieli list ani słowników z procesem."""
    return {
        "wersja": WERSJA_ZAPISU,
        "arkusz": proces.arkusz,
        "urzednik": proces.urzednik,
        "poczatek_cyklu": _data_do_napisu(proces.poczatek_cyklu),
        "etap": Etap(proces.etap).value,
        "kryteria_dodatkowe": list(proces.kryteria_dodatkowe),
        "termin": _data_do_napisu(proces.termin),
        "data_zapoznania_z_kryteriami": _data_do_napisu(proces.data_zapoznania_z_kryteriami),
        "wynik": _wynik_do_slownika(proces.wynik),
        "oceny": dict(proces.oceny),
        "data_zapoznania_z_ocena": _data_do_napisu(proces.data_zapoznania_z_ocena),
        "zapoznanie_fikcyjne": proces.zapoznanie_fikcyjne,
        "fikcje_stwierdzil": None if proces.fikcje_stwierdzil is None else Rola(proces.fikcje_stwierdzil).value,
        "oceny_anulowane": [_wynik_do_slownika(wynik) for wynik in proces.oceny_anulowane],
        "notatki": [
            {"data": _data_do_napisu(notatka.data), "tresc": notatka.tresc, "rodzaj": notatka.rodzaj}
            for notatka in proces.notatki
        ],
        "dokumenty": [
            {
                "rodzaj": dokument.rodzaj,
                "data": _data_do_napisu(dokument.data),
                "adresat": Rola(dokument.adresat).value,
                "opis": dokument.opis,
            }
            for dokument in proces.dokumenty
        ],
        "data_wyznaczenia_kryteriow": _data_do_napisu(proces.data_wyznaczenia_kryteriow),
        "data_rozmowy_oceniajacej": _data_do_napisu(proces.data_rozmowy_oceniajacej),
        "data_sporzadzenia": _data_do_napisu(proces.data_sporzadzenia),
        "daty_zmiany_oceniajacego": [_data_do_napisu(dzien) for dzien in proces.daty_zmiany_oceniajacego],
        "formularz": _formularz_do_slownika(proces.formularz),
        "zmiana_stanowiska": _data_do_napisu(proces.zmiana_stanowiska),
        "ocena_najwczesniej": _data_do_napisu(proces.ocena_najwczesniej),
        "ponowne_kryteria_do": _data_do_napisu(proces.ponowne_kryteria_do),
        "stanowisko_przed_zmiana": proces.stanowisko_przed_zmiana,
    }


# --- odczyt ---

def _napis_do_daty(napis: str | None) -> date | None:
    return None if napis is None else date.fromisoformat(napis)


def _wynik_ze_slownika(dane: dict | None) -> WynikOceny | None:
    if dane is None:
        return None
    return WynikOceny(srednia=Fraction(dane["srednia"]), poziom=dane["poziom"], ocena=dane["ocena"])


def _formularz_ze_slownika(dane: dict | None) -> Formularz | None:
    if dane is None:
        return None
    return Formularz(
        arkusz=dane["arkusz"],
        urzednik=dane["urzednik"],
        oceny=dict(dane["oceny"]),
        kryteria_dodatkowe=list(dane["kryteria_dodatkowe"]),
        uzasadnienie=dane["uzasadnienie"],
        wnioski_iprz=dane["wnioski_iprz"],
        wniosek_o_stopien=dane["wniosek_o_stopien"],
        umotywowanie_wniosku=dane["umotywowanie_wniosku"],
        posiadany_stopien=dane["posiadany_stopien"],
    )


def proces_ze_slownika(dane: dict) -> ProcesOceny:
    """Odtwarza proces ze słownika utworzonego przez `proces_do_slownika`. Nieznana wersja zapisu -> ValueError
    (odczyt zapisu w nieznanej postaci mógłby po cichu zgubić albo przekręcić dane oceny)."""
    wersja = dane.get("wersja") if isinstance(dane, dict) else None
    # `type(...) is int` odrzuca też wartości logiczne i napisy („1”), które przypadkiem są równe wersji.
    if type(wersja) is not int or wersja != WERSJA_ZAPISU:
        raise ValueError(f"Nieznana wersja zapisu procesu oceny: {wersja!r} (obsługiwana: {WERSJA_ZAPISU})")
    return ProcesOceny(
        arkusz=dane["arkusz"],
        urzednik=dane["urzednik"],
        poczatek_cyklu=_napis_do_daty(dane["poczatek_cyklu"]),
        etap=Etap(dane["etap"]),
        kryteria_dodatkowe=list(dane["kryteria_dodatkowe"]),
        termin=_napis_do_daty(dane["termin"]),
        data_zapoznania_z_kryteriami=_napis_do_daty(dane["data_zapoznania_z_kryteriami"]),
        wynik=_wynik_ze_slownika(dane["wynik"]),
        oceny=dict(dane["oceny"]),
        data_zapoznania_z_ocena=_napis_do_daty(dane["data_zapoznania_z_ocena"]),
        zapoznanie_fikcyjne=dane["zapoznanie_fikcyjne"],
        fikcje_stwierdzil=None if dane["fikcje_stwierdzil"] is None else Rola(dane["fikcje_stwierdzil"]),
        oceny_anulowane=[_wynik_ze_slownika(wynik) for wynik in dane["oceny_anulowane"]],
        # Zapisy sprzed wprowadzenia rodzajów notatek nie mają pola `rodzaj` - ich notatki są obserwacjami.
        notatki=[
            Notatka(
                data=_napis_do_daty(notatka["data"]), tresc=notatka["tresc"], rodzaj=notatka.get("rodzaj", OBSERWACJA)
            )
            for notatka in dane["notatki"]
        ],
        dokumenty=[
            Dokument(
                rodzaj=dokument["rodzaj"],
                data=_napis_do_daty(dokument["data"]),
                adresat=Rola(dokument["adresat"]),
                opis=dokument["opis"],
            )
            for dokument in dane["dokumenty"]
        ],
        data_wyznaczenia_kryteriow=_napis_do_daty(dane["data_wyznaczenia_kryteriow"]),
        data_rozmowy_oceniajacej=_napis_do_daty(dane["data_rozmowy_oceniajacej"]),
        data_sporzadzenia=_napis_do_daty(dane["data_sporzadzenia"]),
        daty_zmiany_oceniajacego=[_napis_do_daty(dzien) for dzien in dane["daty_zmiany_oceniajacego"]],
        formularz=_formularz_ze_slownika(dane["formularz"]),
        # Zapisy sprzed obsługi zmiany stanowiska nie mają tych pól.
        zmiana_stanowiska=_napis_do_daty(dane.get("zmiana_stanowiska")),
        ocena_najwczesniej=_napis_do_daty(dane.get("ocena_najwczesniej")),
        ponowne_kryteria_do=_napis_do_daty(dane.get("ponowne_kryteria_do")),
        stanowisko_przed_zmiana=dane.get("stanowisko_przed_zmiana", ""),
    )
