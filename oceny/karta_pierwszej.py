"""Dane karty pierwszej oceny do wyświetlenia - w układzie karty oceny okresowej: oś etapów, zadania,
terminy, wynik i historia czynności.

Moduł niczego nie zapisuje i niczego nie rozstrzyga: formularze, uprawnienia i reguły są w `pierwsza.py`.
Podstawy: art. 36 i 38 u.s.c. oraz rozporządzenie Prezesa Rady Ministrów z dnia 23 lipca 2015 r. (Dz. U. poz. 1144).
"""

from __future__ import annotations

from datetime import date

from .karta import opis_stanu_terminu, stan_terminu  # te same stany i opisy terminów co na karcie oceny okresowej
from .pierwsza import CZESCI_RAPORTU, ELEMENTY, OPISY_EGZAMINU, SKALA, WNIOSKI
from .umowy import koniec_okresu
from .zadania import opis_dni_do_terminu

ETAPY = ("rozmowa wstępna", "sprawozdanie ocenianego", "rozmowa oceniająca i pierwsza ocena", "wniosek do dyrektora generalnego")
ZASTEPSTWO = "zastepstwo_ocena"


def _dzien(zapis: str) -> date:
    """Daty czynności są w zapisie arkusza w postaci RRRR-MM-DD; karta pokazuje je jak inne daty - dd.mm.rrrr."""
    return date.fromisoformat(zapis)


def numer_etapu(dane: dict, dzien: date) -> int:
    """Bieżący krok osi etapów (0-3); 4 oznacza, że wniosek do dyrektora generalnego został złożony.

    Rozmowa oceniająca staje się bieżącym krokiem po złożeniu sprawozdania albo po upływie terminu na jego
    złożenie (§ 8 ust. 1 rozp.)."""
    if "wniosek" in dane:
        return 4
    if "ocena" in dane:
        return 3
    if "wstepna" not in dane:
        return 0
    return 2 if "raport" in dane or dzien.isoformat() > dane["wstepna"]["do"] else 1


def os_etapow(numer: int) -> list[dict]:
    return [
        {"nazwa": nazwa, "stan": "zrobiony" if krok < numer else "biezacy" if krok == numer else "przyszly"}
        for krok, nazwa in enumerate(ETAPY)
    ]


def _zlozone_na_czas(dane: dict) -> bool:
    """Czy sprawozdanie złożono w wyznaczonym terminie - ten sam warunek, którego używa zapis oceny."""
    raport = dane.get("raport", {}).get("data", "")
    return bool(raport) and dane["wstepna"]["od"] <= raport <= dane["wstepna"]["do"]


def wiersze_terminow(ocena, dzien: date, od: date, do: date, termin_wstepnej: date) -> list[dict]:
    dane, umowa = ocena.dane, ocena.umowa
    wstepna, raport, wynik, egzamin = (dane.get(klucz) for klucz in ("wstepna", "raport", "ocena", "egzamin"))
    wiersze: list[dict] = []

    def dodaj(nazwa: str, data: date, podstawa: str = "", uwaga: str = "", stan: str = "informacja") -> None:
        wiersze.append({
            "nazwa": nazwa, "data": data, "podstawa": podstawa, "uwaga": uwaga, "stan": stan,
            "stan_opis": opis_stanu_terminu(stan, data, dzien),
        })

    if wstepna:
        rozmowa = _dzien(wstepna["rozmowa"])
        uwaga = f"Termin upłynął {termin_wstepnej:%d.%m.%Y}." if rozmowa > termin_wstepnej else ""
        dodaj("Rozmowa wstępna", rozmowa, "§ 3 rozp.", uwaga, "wykonane")
    else:
        dodaj("Rozmowa wstępna - najpóźniej", termin_wstepnej, "§ 3 rozp.", stan=stan_terminu(termin_wstepnej, dzien))
    if umowa.kwalifikacja != ZASTEPSTWO:
        if egzamin:
            dodaj(
                f"Egzamin ze służby przygotowawczej: {OPISY_EGZAMINU[egzamin['wynik']]}", _dzien(egzamin["dzien_egzaminu"]),
                "art. 36 ust. 5 u.s.c.", stan="wykonane",
            )
        elif not wynik:
            dodaj(
                "Służba przygotowawcza - koniec najpóźniej", koniec_okresu(umowa.poczatek, 8), "art. 36 ust. 4 u.s.c.",
                "Jeżeli jest wymagana, trwa nie dłużej niż 4 miesiące i kończy się egzaminem.",
            )
    if raport:
        uwaga = "" if _zlozone_na_czas(dane) else "Po wyznaczonym terminie."
        dodaj("Złożenie sprawozdania", _dzien(raport["data"]), "§ 6 rozp.", uwaga, "wykonane")
    elif wstepna and wynik:
        dodaj("Sprawozdanie - termin", _dzien(wstepna["do"]), "§ 4 ust. 1 rozp.", "Nie złożono przed dokonaniem oceny.")
    elif wstepna:
        termin = _dzien(wstepna["do"])
        dodaj("Sprawozdanie - najwcześniej", _dzien(wstepna["od"]), "§ 4 ust. 1 rozp.")
        dodaj("Sprawozdanie - najpóźniej", termin, "§ 4 ust. 1 rozp.", stan=stan_terminu(termin, dzien))
    if wynik:
        dodaj("Dokonanie pierwszej oceny", _dzien(wynik["data"]), "art. 38 ust. 1 u.s.c.", stan="wykonane")
    else:
        dodaj("Pierwsza ocena - najwcześniej", od, "art. 38 ust. 1 u.s.c.")
        dodaj("Pierwsza ocena - najpóźniej", do, "art. 38 ust. 1 u.s.c.", stan=stan_terminu(do, dzien))
    if "wniosek" in dane:
        dodaj("Wniosek do dyrektora generalnego", _dzien(dane["wniosek"]["data"]), "art. 38 ust. 3 u.s.c.", stan="wykonane")
    dodaj("Ostatni dzień umowy na czas określony", umowa.koniec)
    # Kolejność kalendarzowa; sortowanie stabilne zostawia w jednym dniu kolejność czynności w procesie.
    return sorted(wiersze, key=lambda wiersz: wiersz["data"])


def zadania_karty(dane: dict, etap: int, dzien: date, do: date, termin_wstepnej: date, *, oceniany: bool, szef: bool,
                  kierujacy: bool) -> list[dict]:
    """Co zalogowana osoba ma teraz do zrobienia w tej sprawie - z terminem i podstawą, jak na karcie okresowej."""
    zadania: list[dict] = []

    def dodaj(tytul: str, termin: date | None, podstawa: str, bez_terminu: str = "") -> None:
        zadania.append({
            "tytul": tytul, "termin": termin, "podstawa": podstawa,
            "stan": stan_terminu(termin, dzien) if termin else "bez_terminu",
            "stan_opis": opis_dni_do_terminu((termin - dzien).days) if termin else bez_terminu,
        })

    if szef and etap == 0:
        dodaj("Przeprowadź rozmowę wstępną i wyznacz termin sprawozdania", termin_wstepnej, "§ 3 i § 4 rozp.")
    if oceniany and etap in (1, 2) and "raport" not in dane and dzien <= do:  # po okresie oceny sprawozdania już się nie składa
        dodaj("Złóż sprawozdanie", _dzien(dane["wstepna"]["do"]), "§ 4 ust. 1 i § 6 rozp.")
    if szef and etap == 2:
        dodaj("Przeprowadź rozmowę oceniającą i dokonaj pierwszej oceny", do, "art. 38 ust. 1 i 2 u.s.c.; § 8 ust. 1 rozp.")
    if kierujacy and etap == 3:
        dodaj("Złóż wniosek do dyrektora generalnego", None, "art. 38 ust. 3 u.s.c.", "po dokonaniu oceny")
    return zadania


def historia(ocena) -> list[dict]:
    """Czynności formalne z datą i wykonawcą. Prywatnych szkiców i notatek tu nie ma - inni uczestnicy
    nie dowiadują się nawet, że powstają."""
    dane, umowa = ocena.dane, ocena.umowa
    przelozony = f"{ocena.szef}, bezpośredni przełożony" if ocena.szef_id else "bezpośredni przełożony"
    kierujacy = f"{ocena.kierujacy}, kierujący komórką" if ocena.kierujacy_id else "kierujący komórką"
    wpisy: list[dict] = []

    def dodaj(klucz: str, czynnosc: str, podpis: str, opis: str = "") -> None:
        zapis = dane.get(klucz)
        if zapis and zapis.get("data"):
            wpisy.append({"data": _dzien(zapis["data"]), "czynnosc": czynnosc, "opis": opis, "podpis": podpis})

    dodaj("wstepna", "zapisanie rozmowy wstępnej i terminu sprawozdania", przelozony)
    dodaj("termin", "wyznaczenie nowego terminu sprawozdania", przelozony)
    dodaj("egzamin", "zapisanie wyniku egzaminu ze służby przygotowawczej", przelozony)
    dodaj("raport", "złożenie sprawozdania", f"{umowa.osoba}, oceniany")
    dodaj("ocena", "dokonanie pierwszej oceny", przelozony, dane.get("ocena", {}).get("wynik", "").lower())
    dodaj("wniosek", "złożenie wniosku do dyrektora generalnego", kierujacy)
    return sorted(wpisy, key=lambda wpis: wpis["data"])  # sortowanie stabilne: w jednym dniu kolejność procesu


def wynik_do_pokazania(dane: dict) -> dict | None:
    zapis = dane.get("ocena")
    if not zapis:
        return None
    nazwy = dict(SKALA)
    return {
        "ocena": zapis["wynik"].upper(),
        "klasa": zapis["wynik"].lower(),
        "srednia": f"{zapis['srednia']:.1f}".replace(".", ","),
        "rozmowa": _dzien(zapis["rozmowa"]),
        "data": _dzien(zapis["data"]),
        "wiersze": [
            {"nazwa": nazwa, "punkty": zapis[f"pkt{numer}"], "opis": nazwy.get(zapis[f"pkt{numer}"], "")}
            for numer, nazwa in enumerate(ELEMENTY)
        ],
        "egzamin": OPISY_EGZAMINU.get(zapis["egzamin"], zapis["egzamin"]),
        "na_czas": zapis["na_czas"],
        "uzasadnienie": zapis.get("uzasadnienie", ""),
        "rozwoj": zapis.get("rozwoj", ""),
    }


def kontekst_karty(ocena, osoba, dzien: date, *, od: date, do: date, termin_wstepnej: date, formularze: dict, edytor,
                   mozna_zlozyc: bool, jest_szefem: bool) -> dict:
    dane, umowa = ocena.dane, ocena.umowa
    etap = numer_etapu(dane, dzien)
    wstepna, raport, egzamin = dane.get("wstepna"), dane.get("raport"), dane.get("egzamin")
    jest_ocenianym = osoba == umowa.osoba
    jest_kierujacym = osoba is not None and osoba == ocena.kierujacy
    role = [nazwa for nazwa, pelni in (
        ("oceniany", jest_ocenianym), ("bezpośredni przełożony", osoba is not None and osoba == ocena.szef),
        ("kierujący komórką", jest_kierujacym), ("dyrektor generalny", bool(osoba and osoba.rola_dyrektor)),
    ) if pelni]
    kontekst = {
        "ocena": ocena, "oceniany": umowa.osoba, "od": od, "do": do, "termin_wstepnej": termin_wstepnej,
        "formularze": formularze, "edytor": edytor, "mozna_zlozyc": mozna_zlozyc, "jest_szefem": jest_szefem,
        "role_opis": ", ".join(role),
        "os_etapow": os_etapow(etap),
        "zadania": zadania_karty(dane, etap, dzien, do, termin_wstepnej, oceniany=jest_ocenianym, szef=jest_szefem,
                                 kierujacy=jest_kierujacym),
        "terminy": wiersze_terminow(ocena, dzien, od, do, termin_wstepnej),
        "zdarzenia": historia(ocena),
        "wynik": wynik_do_pokazania(dane),
        "skala": SKALA,
        "spozniona_wstepna": not wstepna and dzien > termin_wstepnej,
        "po_terminie_raportu": bool(wstepna and dzien.isoformat() > wstepna["do"]),
        "zastepstwo": umowa.kwalifikacja == ZASTEPSTWO,
        # Przełożony widzi, dlaczego nie ma formularza oceny, zamiast pustego miejsca.
        "okno_minelo": jest_szefem and etap == 2 and dzien > do,
        "brak_kierujacego": jest_szefem and etap == 2 and dzien <= do and not ocena.kierujacy_id,
    }
    if wstepna:
        kontekst["wstepna"] = {
            "rozmowa": _dzien(wstepna["rozmowa"]), "od": _dzien(wstepna["od"]), "do": _dzien(wstepna["do"]),
            "data": _dzien(wstepna["data"]),
            "poprzednie": [{"od": _dzien(stary["od"]), "do": _dzien(stary["do"])} for stary in dane.get("historia_terminow", [])],
        }
    if raport:
        czesci = [{"nazwa": nazwa, "tresc": raport[kod]} for kod, nazwa in CZESCI_RAPORTU.items() if raport.get(kod)]
        kontekst["raport"] = {
            "data": _dzien(raport["data"]), "na_czas": _zlozone_na_czas(dane),
            "czesci": czesci or [{"nazwa": "Treść sprawozdania", "tresc": raport.get("tresc", "")}],
        }
    if egzamin:
        kontekst["egzamin"] = {"dzien": _dzien(egzamin["dzien_egzaminu"]), "opis": OPISY_EGZAMINU[egzamin["wynik"]]}
    if "wniosek" in dane:
        kontekst["wniosek"] = {"tresc": WNIOSKI[dane["wniosek"]["wybor"]], "data": _dzien(dane["wniosek"]["data"])}
    if jest_szefem:
        # Notatki widzi wyłącznie bezpośredni przełożony - tak jak notatki oceniającego na karcie okresowej.
        notatki = [{"data": _dzien(wpis["data"]), "element": wpis["element"], "opis": wpis["opis"]} for wpis in dane.get("obserwacje", [])]
        kontekst["notatki"] = sorted(notatki, key=lambda wpis: wpis["data"], reverse=True)
    if "ocena" in formularze:
        pola = formularze["ocena"]
        kontekst["wiersze_ocen"] = [
            {"numer": numer, "nazwa": nazwa, "wartosc": int(wartosc) if str(wartosc or "").isdigit() else None}
            for numer, nazwa in enumerate(ELEMENTY) for wartosc in [pola[f"pkt{numer}"].value()]
        ]
        kontekst["sprawozdanie_na_czas"] = _zlozone_na_czas(dane)
    return kontekst
