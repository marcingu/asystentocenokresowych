"""Wymaganie: terminy sprzeciwu i odwołania od oceny okresowej.

Źródła: art. 83 u.s.c.; pouczenie w arkuszach B i C; Poradnik KPRM s. 32-33.
"""

from asystent_ocen.terminy import termin_odwolania_do_sadu, termin_rozpatrzenia_sprzeciwu, termin_sprzeciwu
from stale import d


def test_sprzeciw_wnosi_sie_w_7_dni_od_zapoznania_z_ocena():
    """art. 83 ust. 1 u.s.c.: zapoznanie 12.10.2026 -> sprzeciw do 19.10.2026."""
    assert termin_sprzeciwu(d(2026, 10, 12)) == d(2026, 10, 19)


def test_termin_sprzeciwu_przypadajacy_w_swieto_przesuwa_sie():
    """art. 115 KC: zapoznanie 4.11.2026 + 7 dni = 11.11.2026 (święto) -> 12.11.2026."""
    assert termin_sprzeciwu(d(2026, 11, 4)) == d(2026, 11, 12)


def test_sprzeciw_rozpatruje_sie_w_14_dni_od_wniesienia():
    """art. 83 ust. 3 u.s.c."""
    assert termin_rozpatrzenia_sprzeciwu(d(2026, 11, 12)) == d(2026, 11, 26)


def test_odwolanie_do_sadu_pracy_przysluguje_w_14_dni_od_doreczenia_decyzji():
    """art. 83 ust. 5 u.s.c."""
    assert termin_odwolania_do_sadu(data_doreczenia_decyzji=d(2026, 11, 25)) == d(2026, 12, 9)


def test_przy_nierozpatrzeniu_sprzeciwu_14_dni_liczy_sie_od_uplywu_terminu_na_rozpatrzenie():
    """art. 83 ust. 5 u.s.c.: wniesienie 12.11.2026 -> rozpatrzenie do 26.11.2026 -> odwołanie do 10.12.2026."""
    assert termin_odwolania_do_sadu(data_wniesienia_sprzeciwu=d(2026, 11, 12)) == d(2026, 12, 10)


# --- status sprawy po sprzeciwie (art. 83 ust. 3-5 u.s.c.) ---
# Ocena pozostaje zakończona, a status mówi, co dzieje się ze sprzeciwem i czy przysługuje odwołanie do sądu pracy.

from asystent_ocen import po_sprzeciwie as ps  # noqa: E402

WNIESIONY = d(2026, 11, 12)          # rozpatrzenie do 26.11.2026, a bez rozpatrzenia odwołanie do 10.12.2026
ROZSTRZYGNIETY = d(2026, 11, 20)
DORECZONY = d(2026, 11, 25)          # odwołanie do 9.12.2026


def status(dzien, **pola):
    return ps.status_po_sprzeciwie(data_wniesienia=WNIESIONY, dzien=dzien, **pola)


def test_sprzeciw_w_terminie_na_rozpatrzenie_jest_w_toku_i_nie_ma_jeszcze_drogi_sadowej():
    wynik = status(d(2026, 11, 26))

    assert (wynik.kod, wynik.termin, wynik.termin_rozpatrzenia) == (ps.W_TOKU, None, d(2026, 11, 26))
    assert "sąd" not in wynik.opis


def test_sprzeciw_uwzgledniony_nie_otwiera_drogi_sadowej_takze_po_terminie():
    for dzien, rozstrzygniety in ((ROZSTRZYGNIETY, ROZSTRZYGNIETY), (d(2026, 12, 2), d(2026, 12, 1))):
        wynik = status(dzien, rozstrzygniecie=ps.UWZGLEDNIONO, data_rozstrzygniecia=rozstrzygniety)

        assert (wynik.kod, wynik.termin) == (ps.UWZGLEDNIONY, None)
        assert "sąd" not in wynik.opis + wynik.wyjasnienie


def test_po_nieuwzglednieniu_termin_nie_biegnie_dopoki_rozstrzygniecia_nie_doreczono():
    """Art. 83 ust. 5: 14 dni liczy się od dnia doręczenia decyzji - sam wpis rozstrzygnięcia to nie doręczenie."""
    wynik = status(d(2026, 12, 20), rozstrzygniecie=ps.NIE_UWZGLEDNIONO, data_rozstrzygniecia=ROZSTRZYGNIETY)

    assert (wynik.kod, wynik.termin) == (ps.DO_DORECZENIA, None)
    assert wynik.opis == "nieuwzględniony - rozstrzygnięcie czeka na doręczenie"
    assert "od dnia doręczenia" in wynik.wyjasnienie and "art. 83 ust. 5 u.s.c." in wynik.wyjasnienie


def test_po_doreczeniu_odmowy_status_podaje_dzien_do_ktorego_przysluguje_odwolanie():
    pola = {"rozstrzygniecie": ps.NIE_UWZGLEDNIONO, "data_rozstrzygniecia": ROZSTRZYGNIETY, "data_doreczenia": DORECZONY}

    for dzien in (DORECZONY, d(2026, 12, 9)):
        wynik = status(dzien, **pola)

        assert (wynik.kod, wynik.termin, wynik.od_uplywu_terminu) == (ps.ODWOLANIE_PRZYSLUGUJE, d(2026, 12, 9), False)
        assert wynik.opis == "przysługuje odwołanie do sądu pracy - do 09.12.2026"
        assert "doręczono 25.11.2026" in wynik.wyjasnienie and "14 dni od doręczenia" in wynik.wyjasnienie


def test_po_uplywie_14_dni_status_mowi_tylko_ze_termin_uplynal():
    """System nie rejestruje odwołań, więc nie twierdzi, że odwołania nie wniesiono."""
    wynik = status(
        d(2026, 12, 10), rozstrzygniecie=ps.NIE_UWZGLEDNIONO, data_rozstrzygniecia=ROZSTRZYGNIETY, data_doreczenia=DORECZONY
    )

    assert (wynik.kod, wynik.termin) == (ps.TERMIN_ODWOLANIA_UPLYNAL, d(2026, 12, 9))
    assert wynik.opis == "termin na odwołanie do sądu pracy upłynął 09.12.2026"
    assert "nie wniesiono" not in wynik.opis + wynik.wyjasnienie


def test_sprzeciw_nierozpatrzony_w_terminie_otwiera_droge_sadowa_od_uplywu_terminu():
    """Art. 83 ust. 5: przy nierozpatrzeniu sprzeciwu 14 dni liczy się od upływu terminu z ust. 3."""
    dzien_po_terminie = status(d(2026, 11, 27))
    ostatni_dzien = status(d(2026, 12, 10))
    po_wszystkim = status(d(2026, 12, 11))

    for wynik in (dzien_po_terminie, ostatni_dzien):
        assert (wynik.kod, wynik.termin, wynik.od_uplywu_terminu) == (ps.ODWOLANIE_PRZYSLUGUJE, d(2026, 12, 10), True)
        assert wynik.opis == "przysługuje odwołanie do sądu pracy - do 10.12.2026"
        assert "nie rozpatrzono w terminie (do 26.11.2026)" in wynik.wyjasnienie
    assert po_wszystkim.kod == ps.TERMIN_ODWOLANIA_UPLYNAL


def test_odmowa_wydana_po_terminie_nie_przesuwa_daty_liczonej_od_uplywu_terminu():
    """Reguła ostrożna systemu: przy rozstrzygnięciu po terminie pokazywana jest wcześniejsza z możliwych dat,
    także po doręczeniu - odwołanie wniesione do tego dnia jest w terminie przy każdym odczytaniu ust. 5."""
    pola = {"rozstrzygniecie": ps.NIE_UWZGLEDNIONO, "data_rozstrzygniecia": d(2026, 11, 30)}

    for doreczenie in (None, d(2026, 12, 1)):
        wynik = status(d(2026, 12, 2), data_doreczenia=doreczenie, **pola)

        assert (wynik.kod, wynik.termin, wynik.od_uplywu_terminu) == (ps.ODWOLANIE_PRZYSLUGUJE, d(2026, 12, 10), True)
        assert "wcześniejszy" in wynik.wyjasnienie


def test_liczba_dni_w_objasnieniu_pochodzi_z_przepisow():
    from dataclasses import replace

    from asystent_ocen.konfiguracja import wczytaj_przepisy

    przepisy = replace(wczytaj_przepisy(), odwolanie_do_sadu_dni=21)
    wynik = ps.status_po_sprzeciwie(
        data_wniesienia=WNIESIONY, dzien=DORECZONY, rozstrzygniecie=ps.NIE_UWZGLEDNIONO,
        data_rozstrzygniecia=ROZSTRZYGNIETY, data_doreczenia=DORECZONY, przepisy=przepisy,
    )

    assert wynik.termin == d(2026, 12, 16)
    assert "21 dni od doręczenia" in wynik.wyjasnienie
