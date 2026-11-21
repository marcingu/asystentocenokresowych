"""Terminy procesu oceny okresowej (u.s.c. art. 81, 83, 89; rozp. § 7-9)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from .kalendarz import (
    dodaj_miesiace,
    koniec_terminu_dni,
    przesun_na_dzien_roboczy,
    uplynelo_wiecej_niz_miesiecy,
)
from .konfiguracja import (
    OD_NAWIAZANIA_STOSUNKU_PRACY,
    OD_ZAPOZNANIA_Z_KRYTERIAMI,
    Przepisy,
    _ustal_przepisy,
)
from .nieobecnosci import Nieobecnosc, dni_przedluzenia_terminu


def termin_oceny(
    poczatek_cyklu: date, nieobecnosci: Iterable[Nieobecnosc] = (), przepisy: Przepisy | None = None
) -> date:
    """Termin sporządzenia oceny: początek cyklu + 24 miesiące (art. 81 ust. 4),
    przedłużony o nieobecności ciągłe dłuższe niż miesiąc (art. 81 ust. 7), z art. 115 KC.
    Początek cyklu = dzień sporządzenia poprzedniej oceny albo zatrudnienia na czas nieokreślony."""
    przepisy = _ustal_przepisy(przepisy)
    nieobecnosci = tuple(nieobecnosci)
    podstawowy = dodaj_miesiace(poczatek_cyklu, przepisy.cykl_oceny_miesiace)
    termin = przesun_na_dzien_roboczy(podstawowy, przepisy)
    # Przedłużenie może objąć kolejną długą nieobecność zaczętą przed nowym terminem - liczymy do skutku.
    while True:
        dni = dni_przedluzenia_terminu(nieobecnosci, poczatek_cyklu, termin, przepisy)
        przedluzony = przesun_na_dzien_roboczy(podstawowy + timedelta(days=dni), przepisy)
        if przedluzony <= termin:
            return termin
        termin = przedluzony


def data_ponownej_oceny_po_negatywnej(
    data_zapoznania_z_negatywna: date,
    nieobecnosci: Iterable[Nieobecnosc] = (),
    przepisy: Przepisy | None = None,
) -> date:
    """Art. 81 ust. 9: ponowna ocena po upływie 6 miesięcy od zapoznania z oceną negatywną, czyli pierwszego
    dnia po upływie tego okresu. Gdy `ponowna_ocena_w_dniu_roboczym` (domyślnie tak - decyzja zespołu
    z 21.11.2026), data jest przesuwana na najbliższy dzień roboczy. Nie przedłuża się o nieobecności
    (Poradnik s. 14)."""
    przepisy = _ustal_przepisy(przepisy)
    # `nieobecnosci` celowo nie wpływają na wynik: art. 81 ust. 7 dotyczy tylko terminu z ust. 4.
    uplyw_okresu = dodaj_miesiace(data_zapoznania_z_negatywna, przepisy.ponowna_ocena_po_negatywnej_miesiace)
    pierwszy_dzien_po_uplywie = uplyw_okresu + timedelta(days=1)
    if przepisy.ponowna_ocena_w_dniu_roboczym:
        return przesun_na_dzien_roboczy(pierwszy_dzien_po_uplywie, przepisy)
    return pierwszy_dzien_po_uplywie


def termin_wyznaczenia_kryteriow(
    poczatek_cyklu: date, po_negatywnej: bool = False, przepisy: Przepisy | None = None
) -> date:
    """§ 7 rozp.: rozmowa i zapoznanie z kryteriami w 30 dni (albo 7 dni po ocenie negatywnej)."""
    przepisy = _ustal_przepisy(przepisy)
    dni = przepisy.termin_kryteriow_po_negatywnej_dni if po_negatywnej else przepisy.termin_kryteriow_dni
    return koniec_terminu_dni(poczatek_cyklu, dni, przepisy)


def okres_podlegania_ocenie(
    data_zapoznania_z_kryteriami: date,
    data_sporzadzenia: date,
    ostatni_dzien_na_stanowisku: date | None = None,
) -> tuple[date, date]:
    """Okres oceny „od-do” (przypisy do części II arkusza): od zapoznania z kryteriami do
    sporządzenia oceny; przy art. 81 ust. 6 bez oceny przed zmianą - do ostatniego dnia na stanowisku.

    Ostatni dzień na stanowisku kończy okres tylko wtedy, gdy oceny nie sporządzono przed zmianą stanowiska
    (przypis 7 do części II arkusza B); ocena sporządzona wcześniej kończy okres w dniu jej sporządzenia.
    """
    koniec = data_sporzadzenia
    if ostatni_dzien_na_stanowisku is not None and ostatni_dzien_na_stanowisku < data_sporzadzenia:
        koniec = ostatni_dzien_na_stanowisku
    if koniec < data_zapoznania_z_kryteriami:
        raise ValueError(
            f"Okres podlegania ocenie kończy się ({koniec}) przed zapoznaniem z kryteriami "
            f"({data_zapoznania_z_kryteriami})"
        )
    return data_zapoznania_z_kryteriami, koniec


def _poczatek_okresu_do_zmiany(
    data_ostatniej_oceny: date | None,
    data_nawiazania_stosunku_pracy: date | None,
    data_zapoznania_z_kryteriami: date | None,
    przepisy: Przepisy,
) -> date:
    """Dzień, od którego liczy się okres z art. 81 ust. 6 i ust. 8 in fine u.s.c. (domyślnie 6 miesięcy)."""
    if data_ostatniej_oceny is not None:
        return data_ostatniej_oceny
    przelacznik = przepisy.pierwsza_ocena_6_miesiecy_od
    if przelacznik == OD_NAWIAZANIA_STOSUNKU_PRACY:
        poczatek, nazwa = data_nawiazania_stosunku_pracy, "daty nawiązania stosunku pracy"
    elif przelacznik == OD_ZAPOZNANIA_Z_KRYTERIAMI:
        poczatek, nazwa = data_zapoznania_z_kryteriami, "daty zapoznania z kryteriami"
    else:
        raise ValueError(f"Nieznana wartość przełącznika pierwsza_ocena_6_miesiecy_od: {przelacznik!r}")
    if poczatek is None:
        raise ValueError(f"Przy pierwszej ocenie (brak daty ostatniej oceny) potrzeba {nazwa}")
    return poczatek


def czy_dopuszczalna_zmiana_terminu(
    dzien: date,
    *,
    data_ostatniej_oceny: date | None = None,
    data_nawiazania_stosunku_pracy: date | None = None,
    data_zapoznania_z_kryteriami: date | None = None,
    przepisy: Przepisy | None = None,
) -> bool:
    """Art. 81 ust. 8 in fine: zmiana terminu (w tym na wniosek ocenianego) możliwa, gdy od ostatniej oceny
    upłynęło więcej niż 6 miesięcy. Przy pierwszej ocenie (brak `data_ostatniej_oceny`) 6 miesięcy liczy się
    od daty wskazanej przełącznikiem `pierwsza_ocena_6_miesiecy_od` (domyślnie od nawiązania stosunku pracy
    na czas nieokreślony). Brak potrzebnej daty -> ValueError."""
    przepisy = _ustal_przepisy(przepisy)
    poczatek = _poczatek_okresu_do_zmiany(
        data_ostatniej_oceny, data_nawiazania_stosunku_pracy, data_zapoznania_z_kryteriami, przepisy
    )
    return uplynelo_wiecej_niz_miesiecy(poczatek, dzien, przepisy.min_miesiecy_do_zmiany_terminu)


@dataclass(frozen=True)
class SkutekZmianyStanowiska:
    wymagana_ocena: bool
    ocena_najwczesniej: date | None
    ocena_najpozniej: date | None
    ponowne_kryteria_do: date | None
    termin_oceny_bez_zmian: bool


def skutek_zmiany_stanowiska(
    data_zmiany: date,
    *,
    istotna_zmiana_zakresu: bool,
    data_ostatniej_oceny: date | None = None,
    data_nawiazania_stosunku_pracy: date | None = None,
    data_zapoznania_z_kryteriami: date | None = None,
    przepisy: Przepisy | None = None,
) -> SkutekZmianyStanowiska:
    """Art. 81 ust. 6 u.s.c. i § 9 ust. 1-2 rozp. Początek 6 miesięcy ustala się tak samo jak
    w `czy_dopuszczalna_zmiana_terminu` (ten sam przełącznik), żeby obie ścieżki były spójne."""
    przepisy = _ustal_przepisy(przepisy)
    if not istotna_zmiana_zakresu:
        # Przepisy dotyczą wyłącznie zmiany stanowiska wiążącej się z istotną zmianą zakresu obowiązków.
        return SkutekZmianyStanowiska(
            wymagana_ocena=False,
            ocena_najwczesniej=None,
            ocena_najpozniej=None,
            ponowne_kryteria_do=None,
            termin_oceny_bez_zmian=True,
        )
    poczatek = _poczatek_okresu_do_zmiany(
        data_ostatniej_oceny, data_nawiazania_stosunku_pracy, data_zapoznania_z_kryteriami, przepisy
    )
    termin_po_zmianie = koniec_terminu_dni(data_zmiany, przepisy.zmiana_stanowiska_najpozniej_dni_po, przepisy)
    if uplynelo_wiecej_niz_miesiecy(poczatek, data_zmiany, przepisy.min_miesiecy_do_zmiany_terminu):
        # Art. 81 ust. 6 u.s.c. i § 9 ust. 2 rozp.: ocena w oknie wokół dnia zmiany stanowiska. Granicę
        # „nie wcześniej niż ... dni przed zmianą” liczy się wstecz od dnia zmiany (KC nie ma na to reguły).
        return SkutekZmianyStanowiska(
            wymagana_ocena=True,
            ocena_najwczesniej=data_zmiany - timedelta(days=przepisy.zmiana_stanowiska_najwczesniej_dni_przed),
            ocena_najpozniej=termin_po_zmianie,
            ponowne_kryteria_do=None,
            termin_oceny_bez_zmian=False,
        )
    # § 9 ust. 1 rozp.: ponowna rozmowa i zapoznanie z kryteriami, termin sporządzenia oceny bez zmian.
    return SkutekZmianyStanowiska(
        wymagana_ocena=False,
        ocena_najwczesniej=None,
        ocena_najpozniej=None,
        ponowne_kryteria_do=termin_po_zmianie,
        termin_oceny_bez_zmian=True,
    )


def termin_sprzeciwu(data_zapoznania: date, przepisy: Przepisy | None = None) -> date:
    """Art. 83 ust. 1: sprzeciw do dyrektora generalnego w terminie 7 dni od zapoznania z oceną."""
    przepisy = _ustal_przepisy(przepisy)
    return koniec_terminu_dni(data_zapoznania, przepisy.sprzeciw_dni, przepisy)


def termin_rozpatrzenia_sprzeciwu(data_wniesienia: date, przepisy: Przepisy | None = None) -> date:
    """Art. 83 ust. 3: sprzeciw rozpatruje się w terminie 14 dni od wniesienia."""
    przepisy = _ustal_przepisy(przepisy)
    return koniec_terminu_dni(data_wniesienia, przepisy.rozpatrzenie_sprzeciwu_dni, przepisy)


def termin_odwolania_do_sadu(
    *,
    data_doreczenia_decyzji: date | None = None,
    data_wniesienia_sprzeciwu: date | None = None,
    przepisy: Przepisy | None = None,
) -> date:
    """Art. 83 ust. 5: 14 dni od doręczenia decyzji albo od upływu terminu na rozpatrzenie sprzeciwu.

    Gdy podano datę doręczenia decyzji, termin liczy się od niej; w przeciwnym razie od upływu terminu
    na rozpatrzenie sprzeciwu wniesionego w dniu `data_wniesienia_sprzeciwu`. Brak obu dat -> ValueError.
    """
    przepisy = _ustal_przepisy(przepisy)
    if data_doreczenia_decyzji is not None:
        poczatek = data_doreczenia_decyzji
    elif data_wniesienia_sprzeciwu is not None:
        poczatek = termin_rozpatrzenia_sprzeciwu(data_wniesienia_sprzeciwu, przepisy)
    else:
        raise ValueError("Potrzebna jest data doręczenia decyzji albo data wniesienia sprzeciwu")
    return koniec_terminu_dni(poczatek, przepisy.odwolanie_do_sadu_dni, przepisy)


def termin_przyznania_stopnia_obligatoryjnego(data_zapoznania: date, przepisy: Przepisy | None = None) -> date:
    """Art. 89 ust. 2: kolejny stopień w terminie 30 dni od zapoznania z oceną."""
    przepisy = _ustal_przepisy(przepisy)
    return koniec_terminu_dni(data_zapoznania, przepisy.stopien_obligatoryjny_dni, przepisy)
