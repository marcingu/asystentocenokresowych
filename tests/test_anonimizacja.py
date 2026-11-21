"""Wymaganie: anonimizacja danych osobowych przed przetwarzaniem poza infrastrukturą urzędu.

Źródło: treść wyzwania KPRM, pkt 5 („bezpieczne pod względem danych - z mechanizmami kontroli dostępu,
ochroną danych osobowych, anonimizacją w razie przetwarzania danych poza infrastrukturą użytkownika”).
Moduł HR partnera może korzystać z zewnętrznego modelu AI wyłącznie na tekście zanonimizowanym.
"""

import re

from asystent_ocen.anonimizacja import anonimizuj, przywroc

TEKST = (
    "Adam Kowalik (PESEL 90010112345, adam.kowalik@urzad.gov.pl, tel. 501 234 567) "
    "w ocenie Mirandy Wąsik przygotował raport. Adam Kowalik prosi o kontakt: +48 22 597 09 27."
)


def test_pesel_nie_trafia_poza_urzad():
    wynik = anonimizuj(TEKST, osoby=["Adam Kowalik"])
    assert "90010112345" not in wynik.tekst
    assert not re.search(r"\d{11}", wynik.tekst)


def test_adres_email_nie_trafia_poza_urzad():
    assert "adam.kowalik@urzad.gov.pl" not in anonimizuj(TEKST, osoby=["Adam Kowalik"]).tekst


def test_numery_telefonow_nie_trafiaja_poza_urzad():
    tekst = anonimizuj(TEKST, osoby=["Adam Kowalik"]).tekst
    assert "501 234 567" not in tekst
    assert "597 09 27" not in tekst


def test_wskazane_osoby_sa_zastepowane_tym_samym_znacznikiem_przy_kazdym_wystapieniu():
    wynik = anonimizuj(TEKST, osoby=["Adam Kowalik"])
    assert "Adam Kowalik" not in wynik.tekst
    znaczniki = [z for z, oryginal in wynik.mapa.items() if oryginal == "Adam Kowalik"]
    assert len(znaczniki) == 1
    assert wynik.tekst.count(znaczniki[0]) == 2


def test_anonimizacja_jest_odwracalna_po_stronie_urzedu():
    wynik = anonimizuj(TEKST, osoby=["Adam Kowalik"])
    assert przywroc(wynik.tekst, wynik.mapa) == TEKST


def test_tekst_bez_danych_osobowych_pozostaje_bez_zmian():
    tekst = "Proponowane szkolenie: zarządzanie czasem i priorytetami."
    wynik = anonimizuj(tekst)
    assert wynik.tekst == tekst
    assert wynik.mapa == {}
