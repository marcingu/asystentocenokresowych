"""Wymaganie: oceniający zapisuje o pracowniku nie tylko obserwacje, ale też dodatkowe osiągnięcia, a przy
pierwszej ocenie - wynik egzaminu ze służby przygotowawczej (punkty, ewentualny egzamin poprawkowy).

Źródła: decyzja zespołu z 21.11.2026; art. 36 ust. 5 u.s.c. („Służba przygotowawcza kończy się egzaminem. Zakres,
sposób przeprowadzenia oraz warunki zaliczenia egzaminu określa dyrektor generalny urzędu.”) - dlatego rdzeń nie
zna skali punktów ani progu zaliczenia i wynik tylko zapisuje. Wynik egzaminu jest przesłanką pierwszej oceny
w służbie cywilnej (art. 38 ust. 2 pkt 2 u.s.c.); w ocenie okresowej jest informacją pomocniczą oceniającego.
"""

import pytest

from asystent_ocen.bledy import BladWalidacji
from asystent_ocen.przebieg import DOBROSTAN, EGZAMIN, OBSERWACJA, OSIAGNIECIE, BladUprawnien, ProcesOceny, Rola
from asystent_ocen.zapis import proces_do_slownika, proces_ze_slownika
from stale import d

DZIEN = d(2026, 6, 30)


def proces():
    p = ProcesOceny(arkusz="C", urzednik=False, poczatek_cyklu=d(2026, 1, 12))
    p.wyznacz_kryteria(Rola.OCENIAJACY, [], termin=d(2028, 1, 12), data=d(2026, 1, 20))
    p.potwierdz_kryteria(Rola.OCENIANY, data=d(2026, 1, 21))
    return p


def egzamin(p, **zmiany):
    dane = {"punkty": "42", "punkty_max": "50", "poprawkowy": False, "data_egzaminu": d(2026, 5, 20), "data": DZIEN}
    dane.update(zmiany)
    p.zapisz_egzamin(Rola.OCENIAJACY, **dane)
    return [notatka for notatka in p.notatki if notatka.rodzaj == EGZAMIN]


# --- rodzaje notatek ---

def test_notatka_bez_podanego_rodzaju_jest_obserwacja():
    p = proces()
    p.dodaj_notatke(Rola.OCENIAJACY, "Terminowo przygotował raport roczny.", data=DZIEN)
    assert p.notatki[0].rodzaj == OBSERWACJA


def test_oceniajacy_zapisuje_dodatkowe_osiagniecie_pracownika():
    p = proces()
    p.dodaj_notatke(Rola.OCENIAJACY, "Opracował wzór decyzji przyjęty w całym urzędzie.", data=DZIEN, rodzaj=OSIAGNIECIE)
    assert [(n.rodzaj, n.tresc) for n in p.notatki] == [(OSIAGNIECIE, "Opracował wzór decyzji przyjęty w całym urzędzie.")]


def test_oceniajacy_zapisuje_notatke_o_dobrostanie_i_zapis_ja_zachowuje():
    """Decyzja prowadzącego projekt z 22.11.2026: notatki łączą się z Radarem Dobrostanu przez rodzaj wpisu -
    ten sam kod co rodzaj karty obserwacji w `asystent_ocen.radar`."""
    from asystent_ocen import radar

    p = proces()
    p.dodaj_notatke(Rola.OCENIAJACY, "Ustalony urlop 14 dni w lipcu.", data=DZIEN, rodzaj=DOBROSTAN)
    assert [(n.rodzaj, n.tresc) for n in p.notatki] == [(DOBROSTAN, "Ustalony urlop 14 dni w lipcu.")]
    assert proces_ze_slownika(proces_do_slownika(p)).notatki == p.notatki
    assert DOBROSTAN == radar.DOBROSTAN


@pytest.mark.parametrize("rodzaj", ["pochwała", "", EGZAMIN], ids=["nieznany", "pusty", "egzamin poza formularzem"])
def test_notatki_o_innym_rodzaju_nie_da_sie_dodac(rodzaj):
    """Wynik egzaminu ma własną czynność z kontrolą punktów - nie da się go wpisać jako dowolnego tekstu."""
    p = proces()
    with pytest.raises(BladWalidacji) as blad:
        p.dodaj_notatke(Rola.OCENIAJACY, "Treść.", data=DZIEN, rodzaj=rodzaj)
    assert blad.value.kody == {"NIEZNANY_RODZAJ_NOTATKI"}
    assert p.notatki == []


# --- egzamin ze służby przygotowawczej ---

def test_wynik_egzaminu_trafia_do_notatek_z_data_i_punktami():
    zapisane = egzamin(proces())
    assert [n.tresc for n in zapisane] == [
        "Egzamin ze służby przygotowawczej: zdany 20.05.2026, 42 z 50 pkt, w pierwszym terminie."
    ]
    assert zapisane[0].data == DZIEN


def test_egzamin_poprawkowy_jest_odnotowany():
    zapisane = egzamin(proces(), punkty="31", poprawkowy=True, uwagi="W pierwszym terminie 21 pkt.")
    assert zapisane[0].tresc == (
        "Egzamin ze służby przygotowawczej: zdany 20.05.2026, 31 z 50 pkt, po egzaminie poprawkowym. "
        "W pierwszym terminie 21 pkt."
    )


def test_egzamin_bez_daty_i_bez_maksymalnej_liczby_punktow():
    zapisane = egzamin(proces(), punkty_max="", data_egzaminu=None)
    assert zapisane[0].tresc == "Egzamin ze służby przygotowawczej: zdany, 42 pkt, w pierwszym terminie."


def test_punkty_moga_miec_czesc_ulamkowa():
    zapisane = egzamin(proces(), punkty="42.5", punkty_max="50")
    assert "42,5 z 50 pkt" in zapisane[0].tresc


def test_ponowny_zapis_egzaminu_zastepuje_poprzedni_wpis():
    p = proces()
    p.dodaj_notatke(Rola.OCENIAJACY, "Obserwacja.", data=DZIEN)
    egzamin(p)
    zapisane = egzamin(p, punkty="45")
    assert len(zapisane) == 1 and "45 z 50 pkt" in zapisane[0].tresc
    assert len(p.notatki) == 2


@pytest.mark.parametrize(
    ("punkty", "punkty_max", "kod"),
    [
        ("", "50", "BRAK_PUNKTOW_EGZAMINU"),
        ("dużo", "50", "NIEPOPRAWNE_PUNKTY_EGZAMINU"),
        ("-3", "50", "NIEPOPRAWNE_PUNKTY_EGZAMINU"),
        ("42", "zero", "NIEPOPRAWNE_PUNKTY_EGZAMINU"),
        ("42", "0", "NIEPOPRAWNE_PUNKTY_EGZAMINU"),
        ("51", "50", "PUNKTY_EGZAMINU_PONAD_MAKSIMUM"),
    ],
    ids=["brak", "tekst", "ujemne", "maksimum tekstem", "maksimum zero", "ponad maksimum"],
)
def test_niepoprawne_punkty_egzaminu_sa_odrzucane(punkty, punkty_max, kod):
    p = proces()
    with pytest.raises(BladWalidacji) as blad:
        egzamin(p, punkty=punkty, punkty_max=punkty_max)
    assert blad.value.kody == {kod}
    assert p.notatki == []


def test_data_egzaminu_nie_moze_byc_pozniejsza_niz_dzien_wpisu():
    with pytest.raises(BladWalidacji) as blad:
        egzamin(proces(), data_egzaminu=d(2026, 7, 1))
    assert blad.value.kody == {"DATA_EGZAMINU_Z_PRZYSZLOSCI"}


def test_wynik_egzaminu_wpisuje_wylacznie_oceniajacy():
    p = proces()
    with pytest.raises(BladUprawnien):
        p.zapisz_egzamin(Rola.OCENIANY, punkty="42", data=DZIEN)


# --- zapis stanu ---

def test_rodzaj_notatki_przechodzi_przez_zapis_i_odczyt():
    p = proces()
    p.dodaj_notatke(Rola.OCENIAJACY, "Osiągnięcie.", data=DZIEN, rodzaj=OSIAGNIECIE)
    egzamin(p)
    odtworzony = proces_ze_slownika(proces_do_slownika(p))
    assert [n.rodzaj for n in odtworzony.notatki] == [OSIAGNIECIE, EGZAMIN]


def test_zapis_sprzed_wprowadzenia_rodzajow_jest_czytany_jako_obserwacje():
    """Oceny zapisane wcześniej nie mają pola `rodzaj` - po odczycie ich notatki są obserwacjami."""
    p = proces()
    p.dodaj_notatke(Rola.OCENIAJACY, "Dawna notatka.", data=DZIEN)
    dane = proces_do_slownika(p)
    del dane["notatki"][0]["rodzaj"]
    assert proces_ze_slownika(dane).notatki[0].rodzaj == OBSERWACJA
