"""Arkusze A/B/C i kryteria oceny (rozp. § 2-5, załącznik nr 1)."""

from __future__ import annotations

from collections.abc import Sequence

from .bledy import Blad
from .konfiguracja import Przepisy, _ustal_przepisy


def _klucz(nazwa: object) -> str:
    """Postać nazwy do porównań: bez rozróżniania wielkości liter i nadmiarowych odstępów."""
    return " ".join(str(nazwa).split()).casefold()


def _symbol_arkusza(arkusz: str, przepisy: Przepisy) -> str:
    """Symbol arkusza w postaci użytej w przepisach; nieznany arkusz -> ValueError."""
    symbole = {_klucz(symbol): symbol for symbol in przepisy.arkusze}
    try:
        return symbole[_klucz(arkusz)]
    except KeyError:
        raise ValueError(f"Nieznany arkusz oceny: {arkusz!r} (dostępne: {', '.join(przepisy.arkusze)})") from None


def czy_podlega_ocenie(*, rodzaj_zatrudnienia: str, przepisy: Przepisy | None = None) -> bool:
    """Art. 81 ust. 1 u.s.c.: ocenie podlega urzędnik SC ("mianowanie") i pracownik SC zatrudniony
    na czas nieokreślony ("umowa_na_czas_nieokreslony"); nie podlegają: "umowa_na_czas_okreslony",
    "wyzsze_stanowisko" (Poradnik KPRM s. 7).

    Wykazy rodzajów zatrudnienia są w przepisach; nieznany rodzaj -> ValueError (literówka nie może po cichu
    wyłączyć nikogo z oceny).
    """
    przepisy = _ustal_przepisy(przepisy)
    if rodzaj_zatrudnienia in przepisy.rodzaje_zatrudnienia_podlegajace_ocenie:
        return True
    if rodzaj_zatrudnienia in przepisy.rodzaje_zatrudnienia_niepodlegajace_ocenie:
        return False
    znane = przepisy.rodzaje_zatrudnienia_podlegajace_ocenie + przepisy.rodzaje_zatrudnienia_niepodlegajace_ocenie
    raise ValueError(f"Nieznany rodzaj zatrudnienia: {rodzaj_zatrudnienia!r} (znane: {', '.join(znane)})")


def wybierz_arkusz(*, kierownik_urzedu: bool, kieruje_bezposrednio_pracownikami: bool) -> str:
    """§ 3 rozp.: A - kierownik urzędu, B - bezpośrednie kierowanie pracownikami, C - pozostali."""
    if kierownik_urzedu:
        return "A"  # § 3 ust. 2 - pierwszeństwo przed arkuszem B
    if kieruje_bezposrednio_pracownikami:
        return "B"  # § 3 ust. 3
    return "C"  # § 3 ust. 4


def kryteria_obowiazkowe(arkusz: str, przepisy: Przepisy | None = None) -> list[str]:
    """§ 4 rozp. - kryteria obowiązkowe przypisane na stałe do arkusza."""
    przepisy = _ustal_przepisy(przepisy)
    return list(przepisy.arkusze[_symbol_arkusza(arkusz, przepisy)])


def kryteria_dodatkowe_do_wyboru(
    arkusz: str, wybrane: Sequence[str] = (), przepisy: Przepisy | None = None
) -> list[str]:
    """Lista rozwijana kryteriów dodatkowych: wykaz (zał. nr 1) bez kryteriów obowiązkowych arkusza
    i bez kryteriów już wybranych w pozostałych polach (schemat pól formularza KPRM)."""
    przepisy = _ustal_przepisy(przepisy)
    niedostepne = {_klucz(nazwa) for nazwa in kryteria_obowiazkowe(arkusz, przepisy)}
    niedostepne.update(_klucz(nazwa) for nazwa in wybrane if _klucz(nazwa))
    return [nazwa for nazwa in przepisy.katalog_kryteriow if _klucz(nazwa) not in niedostepne]


def bledy_kryteriow_dodatkowych(
    arkusz: str, wybrane: Sequence[str], przepisy: Przepisy | None = None
) -> list[Blad]:
    """Kody: ZA_DUZO_KRYTERIOW_DODATKOWYCH, POWTORZONE_KRYTERIUM, KRYTERIUM_SPOZA_WYKAZU,
    KRYTERIUM_OBOWIAZKOWE_JAKO_DODATKOWE. Porównanie nazw bez rozróżniania wielkości liter.

    Puste pozycje (pole bez wyboru na formularzu) są pomijane.
    """
    przepisy = _ustal_przepisy(przepisy)
    obowiazkowe = {_klucz(nazwa) for nazwa in kryteria_obowiazkowe(arkusz, przepisy)}
    wykaz = {_klucz(nazwa) for nazwa in przepisy.katalog_kryteriow}
    wybrane = [nazwa for nazwa in wybrane if _klucz(nazwa)]

    bledy: list[Blad] = []
    if len(wybrane) > przepisy.max_kryteriow_dodatkowych:
        bledy.append(Blad(
            "ZA_DUZO_KRYTERIOW_DODATKOWYCH",
            f"Wybrano {len(wybrane)} kryteriów dodatkowych - można wybrać nie więcej niż "
            f"{przepisy.max_kryteriow_dodatkowych}.",
            "§ 5 ust. 2 rozp.",
        ))
    widziane: set[str] = set()
    zgloszone_powtorzenia: set[str] = set()
    for nazwa in wybrane:
        klucz = _klucz(nazwa)
        if klucz in widziane:
            if klucz not in zgloszone_powtorzenia:
                zgloszone_powtorzenia.add(klucz)
                bledy.append(Blad(
                    "POWTORZONE_KRYTERIUM",
                    f"Kryterium „{nazwa}” wybrano więcej niż raz.",
                    "§ 5 ust. 2 rozp.; schemat pól formularza KPRM",
                ))
            continue
        widziane.add(klucz)
        if klucz not in wykaz:
            bledy.append(Blad(
                "KRYTERIUM_SPOZA_WYKAZU",
                f"Kryterium „{nazwa}” nie występuje w wykazie kryteriów oceny.",
                "§ 2 ust. 3 i § 5 ust. 2 rozp., załącznik nr 1",
            ))
        elif klucz in obowiazkowe:
            bledy.append(Blad(
                "KRYTERIUM_OBOWIAZKOWE_JAKO_DODATKOWE",
                f"Kryterium „{nazwa}” jest kryterium obowiązkowym tego arkusza - nie można go wybrać "
                "jako dodatkowego.",
                "§ 4 rozp.",
            ))
    return bledy
