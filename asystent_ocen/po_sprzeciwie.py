"""Status sprawy po sprzeciwie od oceny okresowej (art. 83 ust. 3-5 u.s.c.).

Ocena pozostaje zakończona. Status mówi, co dzieje się ze sprzeciwem i czy ocenianemu przysługuje odwołanie
do sądu pracy. Art. 83 ust. 5 u.s.c.: „W razie nierozpatrzenia sprzeciwu w terminie albo nieuwzględnienia
sprzeciwu od oceny okresowej, oceniany może, w terminie 14 dni od dnia doręczenia decyzji albo od dnia upływu
terminu, o którym mowa w ust. 3, odwołać się do sądu pracy.”

System nie rejestruje odwołań - wnosi się je do sądu pracy. Dlatego po upływie terminu status mówi tylko,
że termin upłynął.

Reguła ostrożna systemu (nie wynika wprost z przepisu): gdy rozstrzygnięcie zapadło po terminie z ust. 3,
status pokazuje datę liczoną od upływu tego terminu, czyli wcześniejszą z możliwych - także po doręczeniu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .konfiguracja import Przepisy, _ustal_przepisy
from .terminy import termin_odwolania_do_sadu, termin_rozpatrzenia_sprzeciwu

# Rozstrzygnięcie sprzeciwu przekazywane do funkcji (pusty tekst = sprzeciw nierozpatrzony).
UWZGLEDNIONO = "uwzgledniony"
NIE_UWZGLEDNIONO = "nieuwzgledniony"

# Kody statusu.
W_TOKU = "W_TOKU"
UWZGLEDNIONY = "UWZGLEDNIONY"
DO_DORECZENIA = "DO_DORECZENIA"
ODWOLANIE_PRZYSLUGUJE = "ODWOLANIE_PRZYSLUGUJE"
TERMIN_ODWOLANIA_UPLYNAL = "TERMIN_ODWOLANIA_UPLYNAL"

PODSTAWA = "art. 83 ust. 5 u.s.c."
_BEZ_REJESTRU = "Odwołanie wnosi się do sądu pracy - system go nie rejestruje."


@dataclass(frozen=True)
class StatusPoSprzeciwie:
    kod: str
    opis: str                           # krótka etykieta statusu
    wyjasnienie: str = ""               # zdanie z datami i podstawą prawną
    termin_rozpatrzenia: date | None = None
    termin: date | None = None          # dzień, do którego przysługuje odwołanie do sądu pracy
    od_uplywu_terminu: bool = False     # termin liczony od upływu terminu na rozpatrzenie, a nie od doręczenia

    @property
    def droga_sadowa(self) -> bool:
        return self.kod in (ODWOLANIE_PRZYSLUGUJE, TERMIN_ODWOLANIA_UPLYNAL)


def _dni(liczba: int) -> str:
    return "1 dzień" if liczba == 1 else f"{liczba} dni"


def status_po_sprzeciwie(
    *,
    data_wniesienia: date,
    dzien: date,
    rozstrzygniecie: str = "",
    data_rozstrzygniecia: date | None = None,
    data_doreczenia: date | None = None,
    przepisy: Przepisy | None = None,
) -> StatusPoSprzeciwie:
    """Status sprzeciwu w dniu `dzien`. `rozstrzygniecie`: pusty tekst, UWZGLEDNIONO albo NIE_UWZGLEDNIONO."""
    if rozstrzygniecie not in ("", UWZGLEDNIONO, NIE_UWZGLEDNIONO):
        raise ValueError(f"Nieznane rozstrzygnięcie sprzeciwu: {rozstrzygniecie!r}")
    przepisy = _ustal_przepisy(przepisy)
    rozpatrzenie = termin_rozpatrzenia_sprzeciwu(data_wniesienia, przepisy)
    ile = _dni(przepisy.odwolanie_do_sadu_dni)

    if rozstrzygniecie == UWZGLEDNIONO:
        return StatusPoSprzeciwie(UWZGLEDNIONY, "uwzględniony", termin_rozpatrzenia=rozpatrzenie)
    if not rozstrzygniecie and dzien <= rozpatrzenie:
        return StatusPoSprzeciwie(
            W_TOKU, "w toku", f"Sprzeciw rozpatruje się do {rozpatrzenie:%d.%m.%Y} (art. 83 ust. 3 u.s.c.).",
            termin_rozpatrzenia=rozpatrzenie,
        )

    w_terminie = bool(rozstrzygniecie) and data_rozstrzygniecia is not None and data_rozstrzygniecia <= rozpatrzenie
    if w_terminie:
        if data_doreczenia is None:
            return StatusPoSprzeciwie(
                DO_DORECZENIA, "nieuwzględniony - rozstrzygnięcie czeka na doręczenie",
                f"Termin na odwołanie do sądu pracy - {ile} - biegnie od dnia doręczenia rozstrzygnięcia ({PODSTAWA}).",
                termin_rozpatrzenia=rozpatrzenie,
            )
        termin = termin_odwolania_do_sadu(data_doreczenia_decyzji=data_doreczenia, przepisy=przepisy)
        powod = f"Rozstrzygnięcie doręczono {data_doreczenia:%d.%m.%Y}."
        liczenie = f"{ile} od doręczenia"
    else:
        termin = termin_odwolania_do_sadu(data_wniesienia_sprzeciwu=data_wniesienia, przepisy=przepisy)
        powod = f"Sprzeciwu nie rozpatrzono w terminie (do {rozpatrzenie:%d.%m.%Y})."
        liczenie = f"{ile} od upływu terminu na rozpatrzenie sprzeciwu"
        if rozstrzygniecie:
            powod += (
                f" Rozstrzygnięcie zapadło później, {data_rozstrzygniecia:%d.%m.%Y}, dlatego system pokazuje termin"
                " wcześniejszy z możliwych."
            )

    if dzien <= termin:
        return StatusPoSprzeciwie(
            ODWOLANIE_PRZYSLUGUJE, f"przysługuje odwołanie do sądu pracy - do {termin:%d.%m.%Y}",
            f"{powod} Odwołanie do sądu pracy można wnieść do {termin:%d.%m.%Y} - {liczenie} ({PODSTAWA}). {_BEZ_REJESTRU}",
            termin_rozpatrzenia=rozpatrzenie, termin=termin, od_uplywu_terminu=not w_terminie,
        )
    return StatusPoSprzeciwie(
        TERMIN_ODWOLANIA_UPLYNAL, f"termin na odwołanie do sądu pracy upłynął {termin:%d.%m.%Y}",
        f"{powod} Termin na odwołanie do sądu pracy - {liczenie} - upłynął {termin:%d.%m.%Y} ({PODSTAWA}). {_BEZ_REJESTRU}",
        termin_rozpatrzenia=rozpatrzenie, termin=termin, od_uplywu_terminu=not w_terminie,
    )
