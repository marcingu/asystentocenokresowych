"""Wymaganie: przypomnienia o terminach w kalendarzu - eksport terminów procesu oceny do pliku iCalendar (.ics).

Źródła:
- treść wyzwania KPRM (`../tekst/KPRM - Szegółowy Opis Wyzwania.pdf.txt`, wiersz 174: asystent ma „przypominać
  o terminach”); przypadki użycia KPRM - przypomnienia harmonogramu (`use cases - opis.docx.md`);
- RFC 5545 (iCalendar): pkt 3.1 - wiersze zakończone CRLF i łamanie wierszy dłuższych niż 75 oktetów, pkt 3.3.11 -
  znaki ucieczki w wartościach TEXT, pkt 3.4 i 3.6 - obiekt VCALENDAR z co najmniej jednym składnikiem, pkt 3.6.1 -
  VEVENT (UID, DTSTAMP, DTSTART, DTEND), pkt 3.3.4 i 3.8.2.2 - wydarzenie całodniowe (DTEND = dzień następny),
  pkt 3.6.6 - VALARM;
- terminy: § 7 rozp. (kryteria), art. 81 ust. 4 i 7 u.s.c. (termin oceny), art. 83 ust. 1 u.s.c. (sprzeciw),
  art. 81 ust. 9 u.s.c. (ponowna ocena po negatywnej) - liczone funkcjami rdzenia (`terminy.py`).

Daty oczekiwane w testach sprawdzono niezależnie skryptem z `dateutil` (21.11.2026): początek cyklu 12.01.2026
(poniedziałek) + 30 dni = 11.02.2026 (środa), + 7 dni = 19.01.2026 (poniedziałek), + 24 miesiące = 12.01.2028
(środa); zapoznanie 11.01.2028 (wtorek) + 7 dni = 18.01.2028 (wtorek), + 6 miesięcy i 1 dzień = 12.07.2028 (środa);
zapoznanie 15.01.2028 (sobota) + 7 dni = 22.01.2028 (sobota) -> 24.01.2028 (poniedziałek, art. 115 KC).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from asystent_ocen.ics import Wydarzenie, kalendarz_ics, wydarzenia_procesu
from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.przebieg import ProcesOceny, Rola
from stale import OBOWIAZKOWE_C, d

WYTWORZONO = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
TERMIN = Wydarzenie(
    uid="ocena-7-termin-oceny@asystent-ocen",
    data=d(2028, 1, 12),
    tytul="Termin sporządzenia oceny okresowej - Żaneta Źdźbło",
    opis="Podstawa prawna: art. 81 ust. 4 ustawy o służbie cywilnej.",
)
DLUGI_OPIS = (
    "Zażółć gęślą jaźń; pamiętaj o rozmowie oceniającej, kryteriach obowiązkowych i dodatkowych, "
    "wnioskach dotyczących indywidualnego programu rozwoju zawodowego oraz o terminie sprzeciwu.\n"
    "Druga linia: ścieżka C:\\oceny\\2028 - źródło danych."
)


def wiersze(ics: str) -> list[str]:
    """Wiersze logiczne: po rozdzieleniu na CRLF i cofnięciu łamania (CRLF + spacja)."""
    assert ics.endswith("\r\n")
    return ics.replace("\r\n ", "").split("\r\n")[:-1]


def wlasciwosci(ics: str, nazwa: str) -> list[str]:
    """Wartości właściwości o podanej nazwie (z parametrami), w kolejności wystąpienia."""
    return [w.split(":", 1)[1] for w in wiersze(ics) if w.split(":", 1)[0] == nazwa]


def proces_C(etap: str, *, oceny=(5, 7, 5, 5, 5), zapoznanie=d(2028, 1, 11), przepisy=None) -> ProcesOceny:
    """Proces prowadzony metodami rdzenia: „nowy”, „kryteria”, „potwierdzone”, „ocena” albo „zapoznanie”."""
    krok = ("nowy", "kryteria", "potwierdzone", "ocena", "zapoznanie").index(etap)
    proces = ProcesOceny(arkusz="C", urzednik=False, poczatek_cyklu=d(2026, 1, 12), przepisy=przepisy)
    if krok >= 1:
        proces.wyznacz_kryteria(Rola.OCENIAJACY, [], termin=d(2028, 1, 12), data=d(2026, 1, 20))
    if krok >= 2:
        proces.potwierdz_kryteria(Rola.OCENIANY, data=d(2026, 1, 21))
        proces.dodaj_notatke(Rola.OCENIAJACY, "TAJNA-NOTATKA o spóźnieniach", data=d(2026, 6, 30))
    if krok >= 3:
        proces.sporzadz_ocene(
            Rola.OCENIAJACY, data=d(2028, 1, 10), data_rozmowy=d(2028, 1, 5), oceny=dict(zip(OBOWIAZKOWE_C, oceny)),
            wnioski_iprz="TAJNE-WNIOSKI", uzasadnienie="TAJNE-UZASADNIENIE",
        )
    if krok >= 4:
        proces.potwierdz_zapoznanie(Rola.OCENIANY, data=zapoznanie)
    return proces


def terminy(proces, **parametry) -> dict[str, object]:
    """Kod wydarzenia (końcówka UID przed „@”) -> data."""
    wydarzenia = wydarzenia_procesu(proces, kto="pracownik nr 7", identyfikator="ocena-7", **parametry)
    return {w.uid.split("@")[0].removeprefix("ocena-7-"): w.data for w in wydarzenia}


# === Składnia iCalendar ===

def test_kalendarz_ma_naglowek_vcalendar_i_wiersze_zakonczone_crlf():
    """RFC 5545 pkt 3.1 (CRLF), pkt 3.4 (BEGIN/END:VCALENDAR), pkt 3.7.3 i 3.7.4 (PRODID, VERSION:2.0)."""
    ics = kalendarz_ics([TERMIN], wytworzono=WYTWORZONO)
    assert "\n" not in ics.replace("\r\n", "") and "\r" not in ics.replace("\r\n", "")
    logiczne = wiersze(ics)
    assert logiczne[0] == "BEGIN:VCALENDAR" and logiczne[-1] == "END:VCALENDAR"
    assert wlasciwosci(ics, "VERSION") == ["2.0"]
    assert len(wlasciwosci(ics, "PRODID")) == 1 and wlasciwosci(ics, "PRODID")[0].startswith("-//")
    assert logiczne.count("BEGIN:VEVENT") == logiczne.count("END:VEVENT") == 1


def test_wydarzenie_jest_calodniowe_a_koniec_to_dzien_nastepny():
    """RFC 5545 pkt 3.6.1 i 3.8.2.2: przy DTSTART typu DATE koniec (DTEND) nie wlicza się do wydarzenia."""
    ics = kalendarz_ics([TERMIN], wytworzono=WYTWORZONO)
    assert wlasciwosci(ics, "DTSTART;VALUE=DATE") == ["20280112"]
    assert wlasciwosci(ics, "DTEND;VALUE=DATE") == ["20280113"]


@pytest.mark.parametrize("dzien, koniec", [(d(2027, 12, 31), "20280101"), (d(2028, 2, 29), "20280301")])
def test_koniec_wydarzenia_przechodzi_przez_granice_miesiaca_i_roku(dzien, koniec):
    ics = kalendarz_ics([replace(TERMIN, data=dzien)], wytworzono=WYTWORZONO)
    assert wlasciwosci(ics, "DTEND;VALUE=DATE") == [koniec]


def test_uid_tytul_i_znacznik_czasu_pochodza_z_parametrow():
    """RFC 5545 pkt 3.8.4.7 (UID) i 3.8.7.2 (DTSTAMP w czasie UTC)."""
    ics = kalendarz_ics([TERMIN], wytworzono=WYTWORZONO)
    assert wlasciwosci(ics, "UID") == ["ocena-7-termin-oceny@asystent-ocen"]
    assert wlasciwosci(ics, "DTSTAMP") == ["20261121T120000Z"]
    assert wlasciwosci(ics, "SUMMARY") == ["Termin sporządzenia oceny okresowej - Żaneta Źdźbło"]
    assert wlasciwosci(ics, "DESCRIPTION")[0] == "Podstawa prawna: art. 81 ust. 4 ustawy o służbie cywilnej."


def test_znacznik_czasu_jest_przeliczany_na_utc():
    warszawa_zima = timezone(timedelta(hours=1))
    ics = kalendarz_ics([TERMIN], wytworzono=datetime(2026, 11, 21, 13, 0, 0, tzinfo=warszawa_zima))
    assert wlasciwosci(ics, "DTSTAMP") == ["20261121T120000Z"]


def test_wynik_jest_deterministyczny():
    pierwszy = kalendarz_ics([TERMIN, replace(TERMIN, uid="inne@asystent-ocen")], wytworzono=WYTWORZONO)
    drugi = kalendarz_ics([TERMIN, replace(TERMIN, uid="inne@asystent-ocen")], wytworzono=WYTWORZONO)
    assert pierwszy == drugi


def test_znaki_specjalne_w_tekscie_sa_poprzedzane_ukosnikiem():
    """RFC 5545 pkt 3.3.11: w wartości TEXT ukośnik wsteczny, średnik i przecinek dostają ukośnik, a nowa linia
    to „\\n”."""
    wydarzenie = replace(TERMIN, tytul="Ocena; etap II, rozmowa", opis="Linia 1\nC:\\oceny; a, b\r\nLinia 3")
    ics = kalendarz_ics([wydarzenie], wytworzono=WYTWORZONO)
    assert wlasciwosci(ics, "SUMMARY") == ["Ocena\\; etap II\\, rozmowa"]
    assert wlasciwosci(ics, "DESCRIPTION")[0] == "Linia 1\\nC:\\\\oceny\\; a\\, b\\nLinia 3"


def test_dlugie_wiersze_sa_lamane_po_75_oktetach_bez_rozcinania_znakow():
    """RFC 5545 pkt 3.1: wiersz ma najwyżej 75 oktetów (bez CRLF), dalszy ciąg zaczyna się od spacji; polskie
    znaki zajmują w UTF-8 po dwa oktety i nie mogą zostać rozcięte."""
    ics = kalendarz_ics([replace(TERMIN, opis=DLUGI_OPIS)], wytworzono=WYTWORZONO)
    fizyczne = ics.encode("utf-8").split(b"\r\n")
    assert max(len(wiersz) for wiersz in fizyczne) <= 75
    for wiersz in fizyczne:
        wiersz.decode("utf-8")  # każdy wiersz fizyczny jest poprawnym UTF-8 (żaden znak nie jest rozcięty)
    opis = next(w for w in wiersze(ics) if w.startswith("DESCRIPTION:"))
    assert len(opis.encode("utf-8")) > 150  # wiersz logiczny wymagał co najmniej dwóch złamań
    oczekiwany = DLUGI_OPIS.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    assert opis == "DESCRIPTION:" + oczekiwany
    kontynuacje = [w for w in ics.split("\r\n") if w.startswith(" ")]
    assert kontynuacje and all(len(w.encode("utf-8")) <= 75 for w in kontynuacje)


def test_wiersz_o_dlugosci_dokladnie_75_oktetow_nie_jest_lamany():
    tytul = "ą" * 33 + "b"  # „SUMMARY:” to 8 oktetów + 33 x 2 + 1 = 75
    ics = kalendarz_ics([replace(TERMIN, tytul=tytul, opis="")], wytworzono=WYTWORZONO)
    assert f"SUMMARY:{tytul}\r\n" in ics
    dluzszy = kalendarz_ics([replace(TERMIN, tytul=tytul + "c", opis="")], wytworzono=WYTWORZONO)
    assert f"SUMMARY:{tytul}\r\n c\r\n" in dluzszy


def test_wydarzenie_bez_opisu_nie_ma_wlasciwosci_description_poza_alarmami():
    ics = kalendarz_ics([replace(TERMIN, opis="")], wytworzono=WYTWORZONO)
    poza_alarmami, w_alarmie = [], False
    for wiersz in wiersze(ics):
        w_alarmie = (w_alarmie or wiersz == "BEGIN:VALARM") and wiersz != "END:VALARM"
        if not w_alarmie:
            poza_alarmami.append(wiersz)
    assert not any(wiersz.startswith("DESCRIPTION") for wiersz in poza_alarmami)


def test_pusty_kalendarz_i_powtorzony_identyfikator_sa_odrzucane():
    """RFC 5545 pkt 3.6: obiekt iCalendar zawiera co najmniej jeden składnik; pkt 3.8.4.7: UID jest unikalny."""
    with pytest.raises(ValueError):
        kalendarz_ics([], wytworzono=WYTWORZONO)
    with pytest.raises(ValueError):
        kalendarz_ics([TERMIN, TERMIN], wytworzono=WYTWORZONO)
    with pytest.raises(ValueError):
        kalendarz_ics([replace(TERMIN, uid="  ")], wytworzono=WYTWORZONO)


# === Przypomnienia (VALARM) ===

def test_przypomnienia_maja_wyprzedzenia_z_konfiguracji():
    """`przepisy.toml`: przypomnienia_dni_przed = [30, 14, 3] (decyzja projektowa); RFC 5545 pkt 3.6.6 - alarm
    typu DISPLAY wymaga ACTION, DESCRIPTION i TRIGGER."""
    ics = kalendarz_ics([TERMIN], wytworzono=WYTWORZONO)
    assert wlasciwosci(ics, "TRIGGER") == ["-P30D", "-P14D", "-P3D"]
    logiczne = wiersze(ics)
    assert logiczne.count("BEGIN:VALARM") == logiczne.count("END:VALARM") == 3
    assert wlasciwosci(ics, "ACTION") == ["DISPLAY"] * 3
    assert logiczne.index("BEGIN:VEVENT") < logiczne.index("BEGIN:VALARM") < logiczne.index("END:VEVENT")


def test_zmiana_wyprzedzen_w_konfiguracji_zmienia_przypomnienia():
    przepisy = replace(wczytaj_przepisy(), przypomnienia_dni_przed=(7, 0))
    ics = kalendarz_ics([TERMIN], wytworzono=WYTWORZONO, przepisy=przepisy)
    assert wlasciwosci(ics, "TRIGGER") == ["-P7D", "PT0S"]


@pytest.mark.decyzja_projektowa
def test_przypomnienia_ktorych_dzien_minal_przed_wytworzeniem_kalendarza_sa_pomijane():
    """Termin sprzeciwu biegnie 7 dni - przypomnienia na 30 i 14 dni przed nim wypadłyby w przeszłości."""
    sprzeciw = replace(TERMIN, data=d(2028, 1, 18))
    ics = kalendarz_ics([sprzeciw], wytworzono=datetime(2028, 1, 11, 9, 0, tzinfo=timezone.utc))
    assert wlasciwosci(ics, "TRIGGER") == ["-P3D"]
    po_terminie = kalendarz_ics([sprzeciw], wytworzono=datetime(2028, 2, 1, 9, 0, tzinfo=timezone.utc))
    assert wlasciwosci(po_terminie, "TRIGGER") == []


# === Terminy procesu ===

def test_nowy_proces_ma_termin_wyznaczenia_kryteriow_i_termin_oceny():
    """§ 7 pkt 1 rozp.: 30 dni od początku cyklu (12.01.2026 -> 11.02.2026); art. 81 ust. 4 u.s.c.: 24 miesiące
    (-> 12.01.2028)."""
    assert terminy(proces_C("nowy")) == {"kryteria": d(2026, 2, 11), "termin-oceny": d(2028, 1, 12)}


def test_po_ocenie_negatywnej_kryteria_wyznacza_sie_w_7_dni():
    """§ 7 pkt 2 rozp.: 7 dni od sporządzenia negatywnej oceny (12.01.2026 -> 19.01.2026)."""
    assert terminy(proces_C("nowy"), po_negatywnej=True)["kryteria"] == d(2026, 1, 19)


def test_termin_kryteriow_zostaje_w_kalendarzu_do_potwierdzenia_przez_ocenianego():
    """§ 6 ust. 2 rozp.: czynności kończy potwierdzenie ocenianego - do tego czasu termin z § 7 biegnie."""
    assert "kryteria" in terminy(proces_C("kryteria"))
    assert terminy(proces_C("potwierdzone")) == {"termin-oceny": d(2028, 1, 12)}


def test_termin_oceny_to_termin_wpisany_w_czesci_I_arkusza_gdy_oceniajacy_go_ustalil():
    """§ 5 ust. 3 i § 8 rozp.: termin sporządzenia oceny wpisuje i zmienia oceniający."""
    proces = proces_C("potwierdzone")
    proces.zmien_termin(Rola.OCENIAJACY, nowy_termin=d(2027, 9, 1), data=d(2027, 3, 1), przyczyna="NIEOBECNOSC_OCENIAJACEGO")
    assert terminy(proces) == {"termin-oceny": d(2027, 9, 1)}


def test_po_sporzadzeniu_oceny_a_przed_zapoznaniem_nie_ma_terminow_do_przypomnienia():
    """§ 12 ust. 1 rozp.: z oceną zapoznaje się „niezwłocznie” - przepis nie wyznacza terminu w dniach."""
    assert terminy(proces_C("ocena")) == {}


def test_po_zapoznaniu_z_ocena_pozytywna_jest_termin_sprzeciwu():
    """Art. 83 ust. 1 u.s.c.: 7 dni od zapoznania (11.01.2028 -> 18.01.2028)."""
    assert terminy(proces_C("zapoznanie")) == {"sprzeciw": d(2028, 1, 18)}


def test_po_zapoznaniu_z_ocena_negatywna_jest_tez_ponowna_ocena():
    """Art. 81 ust. 9 u.s.c.: po upływie 6 miesięcy od zapoznania (11.01.2028 -> 12.07.2028)."""
    proces = proces_C("zapoznanie", oceny=(5, 1, 5, 5, 5))
    assert terminy(proces) == {"sprzeciw": d(2028, 1, 18), "ponowna-ocena": d(2028, 7, 12)}


def test_termin_sprzeciwu_konczacy_sie_w_sobote_przechodzi_na_poniedzialek():
    """Art. 115 KC: zapoznanie w sobotę 15.01.2028 + 7 dni = sobota 22.01.2028 -> poniedziałek 24.01.2028."""
    assert terminy(proces_C("zapoznanie", zapoznanie=d(2028, 1, 15)))["sprzeciw"] == d(2028, 1, 24)


def test_zmiana_przepisow_zmienia_terminy_w_kalendarzu():
    """11.01.2028 + 14 dni = 25.01.2028 (wtorek)."""
    przepisy = replace(wczytaj_przepisy(), sprzeciw_dni=14)
    assert terminy(proces_C("zapoznanie"), przepisy=przepisy) == {"sprzeciw": d(2028, 1, 25)}
    assert terminy(proces_C("zapoznanie", przepisy=przepisy)) == {"sprzeciw": d(2028, 1, 25)}


def test_opisy_wydarzen_podaja_podstawe_prawna():
    podstawy = {}
    for proces in (proces_C("nowy"), proces_C("zapoznanie", oceny=(5, 1, 5, 5, 5))):
        for wydarzenie in wydarzenia_procesu(proces, kto="pracownik nr 7", identyfikator="ocena-7"):
            podstawy[wydarzenie.uid.split("@")[0].removeprefix("ocena-7-")] = wydarzenie.opis
    assert "§ 7 pkt 1" in podstawy["kryteria"] and "Dz. U. poz. 470" in podstawy["kryteria"]
    assert "art. 81 ust. 4" in podstawy["termin-oceny"]
    assert "art. 83 ust. 1" in podstawy["sprzeciw"]
    assert "art. 81 ust. 9" in podstawy["ponowna-ocena"]
    assert all("Podstawa prawna" in opis for opis in podstawy.values())


def test_wydarzenia_nie_zawieraja_danych_spoza_parametru_kto():
    """Minimalizacja danych: w kalendarzu jest tylko oznaczenie osoby przekazane w `kto` - bez ocen, uzasadnień,
    notatek ani informacji, że ocena była negatywna."""
    proces = proces_C("zapoznanie", oceny=(5, 1, 5, 5, 5))
    wydarzenia = wydarzenia_procesu(proces, kto="pracownik nr 7", identyfikator="ocena-7")
    ics = kalendarz_ics(wydarzenia, wytworzono=WYTWORZONO)
    assert all(wydarzenie.tytul.endswith(" - pracownik nr 7") for wydarzenie in wydarzenia)
    for zakazane in ("TAJN", "negatywn", "NEGATYWN", "Rzetelność", "oceniający"):
        assert zakazane not in ics


def test_identyfikatory_wydarzen_sa_stale_i_rozne():
    """Ponowny eksport ma aktualizować wpisy w kalendarzu, a nie je dublować (RFC 5545 pkt 3.8.4.7)."""
    proces = proces_C("zapoznanie", oceny=(5, 1, 5, 5, 5))
    pierwsze = [w.uid for w in wydarzenia_procesu(proces, kto="A", identyfikator="ocena-7")]
    drugie = [w.uid for w in wydarzenia_procesu(proces, kto="B", identyfikator="ocena-7")]
    assert pierwsze == drugie and len(set(pierwsze)) == 2
    inne = [w.uid for w in wydarzenia_procesu(proces, kto="A", identyfikator="ocena-8")]
    assert not set(pierwsze) & set(inne)
    with pytest.raises(ValueError):
        wydarzenia_procesu(proces, kto="A", identyfikator=" ")


def test_wydarzenia_procesu_daja_poprawny_kalendarz():
    wydarzenia = wydarzenia_procesu(proces_C("nowy"), kto="Żaneta Źdźbło", identyfikator="ocena-7")
    ics = kalendarz_ics(wydarzenia, wytworzono=datetime(2026, 1, 12, 8, 0, tzinfo=timezone.utc))
    assert wlasciwosci(ics, "DTSTART;VALUE=DATE") == ["20260211", "20280112"]  # kolejność chronologiczna
    assert max(len(wiersz) for wiersz in ics.encode("utf-8").split(b"\r\n")) <= 75
    # 11.02.2026 jest 30 dni po 12.01.2026 - przypomnienie na 30 dni przed terminem wypada w dniu wytworzenia.
    assert wlasciwosci(ics, "TRIGGER") == ["-P30D", "-P14D", "-P3D"] * 2
