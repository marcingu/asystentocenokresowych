"""Walidacja formularza przed zatwierdzeniem oceny (schematy pól arkuszy A/B/C KPRM, rozp. § 11)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .bledy import Blad
from .konfiguracja import Przepisy, _ustal_przepisy
from .kryteria import _klucz, _symbol_arkusza, bledy_kryteriow_dodatkowych
from .stopnie import komunikat_dla_stopnia
from .wynik import NEGATYWNA, bledy_ocen_czastkowych, oblicz_wynik

TAK = "TAK"
NIE = "NIE"
NIE_DOTYCZY = "NIE DOTYCZY"

# Arkusz, w którym adresata sprzeciwu wpisuje oceniający (wzór arkusza A - zał. nr 2 do rozp.).
_ARKUSZ_Z_WPISYWANYM_ADRESATEM = "A"
_MIEJSCE_NA_ADRESATA = "................................"


@dataclass
class Formularz:
    arkusz: str
    urzednik: bool
    oceny: dict[str, int]
    kryteria_dodatkowe: list[str] = field(default_factory=list)
    uzasadnienie: str = ""
    wnioski_iprz: str = ""
    wniosek_o_stopien: str | None = None  # TAK / NIE / NIE DOTYCZY
    umotywowanie_wniosku: str = ""
    posiadany_stopien: int | None = None


def _puste(tekst: str | None) -> bool:
    return not str(tekst or "").strip()


def _czy_tak(odpowiedz: str | None) -> bool:
    return _klucz(odpowiedz or "") == _klucz(TAK)


def bledy_przed_zatwierdzeniem(formularz: Formularz, przepisy: Przepisy | None = None) -> list[Blad]:
    """Kody: BRAK_UZASADNIENIA_NEGATYWNEJ, BRAK_WNIOSKOW_IPRZ, WNIOSEK_O_STOPIEN_NIE_DLA_PRACOWNIKA,
    WNIOSEK_O_STOPIEN_PRZY_NEGATYWNEJ, BRAK_UMOTYWOWANIA_WNIOSKU, NAJWYZSZY_STOPIEN oraz kody
    z walidacji kryteriów i ocen cząstkowych."""
    przepisy = _ustal_przepisy(przepisy)
    bledy = bledy_kryteriow_dodatkowych(formularz.arkusz, formularz.kryteria_dodatkowe, przepisy)
    bledy_ocen = bledy_ocen_czastkowych(formularz.arkusz, formularz.kryteria_dodatkowe, formularz.oceny, przepisy)
    bledy.extend(bledy_ocen)
    # Wynik oceny (pozytywna/negatywna) jest określony dopiero dla kompletu poprawnych ocen cząstkowych.
    ocena = None if bledy_ocen or not formularz.oceny else oblicz_wynik(formularz.oceny, przepisy).ocena

    if ocena == NEGATYWNA and _puste(formularz.uzasadnienie):
        bledy.append(Blad(
            "BRAK_UZASADNIENIA_NEGATYWNEJ",
            "Ocena negatywna wymaga uzasadnienia - uzupełnij pole „Uzasadnienie przyznanej oceny”.",
            "§ 11 ust. 3 rozp.",
        ))
    if _puste(formularz.wnioski_iprz):
        bledy.append(Blad(
            "BRAK_WNIOSKOW_IPRZ",
            "Uzupełnij wnioski dotyczące indywidualnego programu rozwoju zawodowego.",
            "art. 81 ust. 5 u.s.c.; § 11 ust. 1 pkt 5 rozp.",
        ))
    if _czy_tak(formularz.wniosek_o_stopien):
        if not formularz.urzednik:
            bledy.append(Blad(
                "WNIOSEK_O_STOPIEN_NIE_DLA_PRACOWNIKA",
                "Wniosek o przyznanie kolejnego stopnia służbowego dotyczy wyłącznie urzędnika służby cywilnej.",
                "art. 89 ust. 1 u.s.c.; § 11 ust. 5 rozp.",
            ))
        if ocena == NEGATYWNA:
            bledy.append(Blad(
                "WNIOSEK_O_STOPIEN_PRZY_NEGATYWNEJ",
                "Wniosek o przyznanie kolejnego stopnia służbowego można złożyć tylko przy ocenie pozytywnej.",
                "art. 89 ust. 1 u.s.c.; § 11 ust. 5 rozp.",
            ))
        if _puste(formularz.umotywowanie_wniosku):
            bledy.append(Blad(
                "BRAK_UMOTYWOWANIA_WNIOSKU",
                "Wniosek o przyznanie kolejnego stopnia służbowego wymaga umotywowania.",
                "art. 89 ust. 1 u.s.c.; § 11 ust. 5 rozp.",
            ))
        if formularz.posiadany_stopien is not None:
            komunikat = komunikat_dla_stopnia(formularz.posiadany_stopien, przepisy)
            if komunikat is not None:
                bledy.append(Blad("NAJWYZSZY_STOPIEN", komunikat, "art. 86 ust. 1 u.s.c."))
    return bledy


def domyslna_odpowiedz_o_wniosek(*, urzednik: bool, ocena: str) -> str | None:
    """Pole „Czy dołączono wniosek o przyznanie kolejnego stopnia”: NIE DOTYCZY dla pracownika,
    NIE dla urzędnika z oceną negatywną, None (wybór oceniającego) dla urzędnika z oceną pozytywną."""
    if not urzednik:
        return NIE_DOTYCZY
    if ocena == NEGATYWNA:
        return NIE
    return None


def czy_drukowac_czesc_III(*, urzednik: bool, wniosek_o_stopien: str | None) -> bool:
    """Przypis do części III: nie drukuje się jej dla pracownika SC ani gdy nie składa się wniosku."""
    return bool(urzednik) and _czy_tak(wniosek_o_stopien)


def czy_aktywna_sekcja_poprzedniej_oceny(*, urzednik: bool) -> bool:
    """„Dane dotyczące poprzedniej oceny okresowej urzędnika” - nieaktywne, gdy oceniany nie jest urzędnikiem."""
    return bool(urzednik)


def pouczenie_o_sprzeciwie(
    arkusz: str,
    *,
    urzad_ma_dyrektora_generalnego: bool = True,
    adresat: str | None = None,
    przepisy: Przepisy | None = None,
) -> str:
    """Treść pouczenia (art. 83 ust. 1 u.s.c.). Arkusz A: adresat sprzeciwu wpisywany w formularzu.

    W arkuszach B i C adresat wynika z wzoru arkusza (dyrektor generalny urzędu, a w urzędzie bez tego
    stanowiska - kierownik urzędu, przypis 17), więc parametr `adresat` nie jest tam używany. W arkuszu A
    brak adresata daje miejsce do wypełnienia.
    """
    przepisy = _ustal_przepisy(przepisy)
    termin = "1 dnia" if przepisy.sprzeciw_dni == 1 else f"{przepisy.sprzeciw_dni} dni"
    tresc = (
        "art. 83 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej od oceny okresowej służy, "
        f"w terminie {termin} od dnia zapoznania się z oceną, sprzeciw do"
    )
    if _symbol_arkusza(arkusz, przepisy) == _ARKUSZ_Z_WPISYWANYM_ADRESATEM:
        if _puste(adresat):
            return f"Na podstawie {tresc}: {_MIEJSCE_NA_ADRESATA}"
        return f"Na podstawie {tresc} {str(adresat).strip()}."
    if urzad_ma_dyrektora_generalnego:
        return f"Zgodnie z {tresc} dyrektora generalnego urzędu."
    return f"Zgodnie z {tresc} kierownika urzędu."
