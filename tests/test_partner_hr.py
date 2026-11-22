"""Partner HR: z kart obserwacji Radaru powstaje obraz sytuacji i lista działań możliwych do ustalenia w rozmowie.

Wymaganie (prowadzący projekt, 22.11.2026; opis wyzwania KPRM, moduł „HR Asystent”): moduł ma wspierać przełożonego
w zarządzaniu ludźmi - analizować dane o zadaniach i ich realizacji (charakter zadań, zmiany zakresu obowiązków),
wskazywać sygnały przeciążenia i okoliczności sprzyjające wypaleniu, podpowiadać działania wspierające dobrostan,
rozwiązania organizacyjne i działania prewencyjne oraz wskazywać momenty na docenienie z konkretną formą uznania.

Zasady podane przez prowadzącego projekt: (1) nie oceniaj pracownika - opisuj obserwację („Obserwujemy spiętrzenie
zadań..., co może rodzić ryzyko przemęczenia”); (2) rekomendacje prowadzą do rozmowy, nie do kar i poleceń;
(3) działania realne w ustawie o służbie cywilnej i Kodeksie pracy; (4) przy okazji do wzmocnienia motywacji -
konkretna forma podziękowania; (5) ton doradczy, bez żargonu.

Decyzje projektowe: sygnały liczy zwykły kod z kart (to nie jest system AI i nie wnioskuje o emocjach ani zdrowiu);
każde działanie ma podstawę - przepis albo punkt Standardów zarządzania zasobami ludzkimi w służbie cywilnej
(zarządzenie nr 6 Szefa Służby Cywilnej z 2020 r.); karty Radaru pozostają samymi faktami.
"""

import itertools
import re

import pytest

from asystent_ocen import partner_hr
from asystent_ocen.partner_hr import sygnaly
from asystent_ocen.radar import DOBROSTAN, DOCENIENIE, EZD, KADRY, ZASADY_RADARU, KartaObserwacji

TYTULY = {
    "URLOP_ZALEGLY": (DOBROSTAN, "Urlop zaległy"), "DLUGI_WYPOCZYNEK": (DOBROSTAN, "Dłuższy wypoczynek"),
    "NADGODZINY": (DOBROSTAN, "Godziny nadliczbowe"), "SPRAWY_W_TOKU": (DOBROSTAN, "Sprawy w toku"),
    "PRACA_POZA_GODZINAMI": (DOBROSTAN, "Praca poza godzinami urzędu"),
    "TERMINOWOSC": (DOCENIENIE, "Terminowość"), "PRZEJETE_SPRAWY": (DOCENIENIE, "Sprawy przejęte po nieobecnych"),
    "PISMA_BEZ_POPRAWEK": (DOCENIENIE, "Pisma bez poprawek"), "ZASTEPSTWA": (DOCENIENIE, "Zastępstwa"),
}
# Zasada 1 i 2: żadnych ocen osoby, diagnoz, kar ani jednostronnych poleceń. Wzorce na tekście małymi literami.
NIEDOZWOLONE = (
    r"pracownik (pracuje|jest|nie )", r"pracuje (źle|dobrze|słabo)", r"wypalon", r"zestresowan", r"zdemotywowan",
    r"nie radzi", r"leniw", r"\bkar[ayę]\b", r"nagan", r"upomn", r"polecenie służbowe", r"depres", r"chorob", r"zdrowi",
    r"emocj", r" – ",
)


def karty(*kody):
    return tuple(KartaObserwacji(kod, TYTULY[kod][0], TYTULY[kod][1], f"Fakt karty {kod}: 24.", EZD if "SPRAW" in kod else KADRY,
                                 "ustawienie urzędu", "Do omówienia.") for kod in kody)


def kody(wynik):
    return [sygnal.kod for sygnal in wynik]


def teksty(sygnal):
    return [sygnal.tytul, sygnal.obserwacja, sygnal.rozmowa, *(dzialanie.tekst for dzialanie in sygnal.dzialania)]


def podstawy(sygnal):
    return " | ".join(dzialanie.podstawa for dzialanie in sygnal.dzialania)


def test_spietrzenie_pracy_w_kilku_obszarach_jest_opisane_jako_obserwacja_a_nie_ocena():
    (sygnal,) = sygnaly(karty("NADGODZINY", "SPRAWY_W_TOKU"))

    assert sygnal.kod == "SPIETRZENIE_PRACY" and sygnal.rodzaj == DOBROSTAN
    assert sygnal.karty == ("NADGODZINY", "SPRAWY_W_TOKU")
    assert sygnal.obserwacja == ("Obserwujemy spiętrzenie pracy w 2 obszarach jednocześnie: godziny nadliczbowe, sprawy w toku. "
                                 "Taki układ może rodzić ryzyko przemęczenia.")
    assert sygnal.rozmowa.endswith("?") and "Pani/Panu" in sygnal.rozmowa
    # działania realne w służbie cywilnej: priorytety, podział czynności, odbiór czasu wolnego
    assert "art. 97 ust. 6, 7 i 9 u.s.c." in podstawy(sygnal)
    assert any("podział" in dzialanie.tekst for dzialanie in sygnal.dzialania)
    assert any("priorytet" in dzialanie.tekst.lower() for dzialanie in sygnal.dzialania)


def test_jedna_karta_obciazenia_daje_lzejszy_sygnal_a_czas_wolny_tylko_przy_nadgodzinach():
    (sygnal,) = sygnaly(karty("SPRAWY_W_TOKU"))

    assert sygnal.kod == "SPIETRZENIE_PRACY"
    assert sygnal.obserwacja.startswith("Obserwujemy podwyższone obciążenie w obszarze: sprawy w toku.")
    assert "art. 97" not in podstawy(sygnal)


def test_odkladany_wypoczynek_prowadzi_do_planu_urlopu():
    (sygnal,) = sygnaly(karty("URLOP_ZALEGLY", "DLUGI_WYPOCZYNEK"))

    assert sygnal.kod == "ODKLADANY_WYPOCZYNEK"
    assert sygnal.obserwacja.startswith("Obserwujemy odkładany wypoczynek")
    assert "art. 162 i 163 KP" in podstawy(sygnal) and "art. 168 KP" in podstawy(sygnal)
    # art. 163 § 1[1] KP: urząd bez planu urlopów ustala termin po porozumieniu z pracownikiem
    assert "w planie urlopów albo ustalony po porozumieniu" in sygnal.dzialania[0].tekst
    assert "art. 168 KP" not in podstawy(sygnaly(karty("DLUGI_WYPOCZYNEK"))[0])  # bez urlopu zaległego nie ma jego podstawy


def test_przejete_sprawy_i_zastepstwa_to_szerszy_zakres_zadan_i_powod_do_nagrody():
    wynik = sygnaly(karty("PRZEJETE_SPRAWY", "ZASTEPSTWA"))

    assert kody(wynik) == ["SZERSZY_ZAKRES_ZADAN", "MOMENT_NA_DOCENIENIE"]
    zakres, docenienie = wynik
    assert "zakres zadań był szerszy niż stałe obowiązki" in zakres.obserwacja
    assert "art. 88 u.s.c." in podstawy(zakres)            # dodatek zadaniowy na okres dodatkowych zadań
    assert "opis" in " ".join(teksty(zakres))               # zadania stałe - do opisu stanowiska pracy
    assert docenienie.rodzaj == DOCENIENIE
    assert "art. 93 ust. 1 u.s.c." in podstawy(docenienie)  # nagroda z funduszu nagród


def test_kazda_karta_docenienia_daje_konkretna_forme_podziekowania():
    for kod in ("TERMINOWOSC", "PISMA_BEZ_POPRAWEK", "PRZEJETE_SPRAWY", "ZASTEPSTWA"):
        docenienie = [sygnal for sygnal in sygnaly(karty(kod)) if sygnal.kod == "MOMENT_NA_DOCENIENIE"]
        assert len(docenienie) == 1, kod
        assert TYTULY[kod][1].lower() in docenienie[0].obserwacja
        assert any(dzialanie.tekst.startswith("Podziękowanie") for dzialanie in docenienie[0].dzialania)
    mentor = sygnaly(karty("PISMA_BEZ_POPRAWEK"))[-1]
    assert any("mentor" in dzialanie.tekst for dzialanie in mentor.dzialania)
    assert "art. 93" not in podstawy(sygnaly(karty("TERMINOWOSC"))[-1])  # nagroda - przy dodatkowym wysiłku, nie za każdą kartę


def test_dobre_wyniki_przy_obciazeniu_to_sygnal_prewencyjny_z_dzialaniem_rozwojowym():
    wynik = sygnaly(karty("NADGODZINY", "SPRAWY_W_TOKU", "TERMINOWOSC"))

    assert kody(wynik) == ["SPIETRZENIE_PRACY", "DOBRE_WYNIKI_PRZY_OBCIAZENIU", "MOMENT_NA_DOCENIENIE"]
    prewencja = wynik[1]
    assert "sprzyja wypaleniu zawodowemu" in prewencja.obserwacja and "zanim pojawią się trudności" in prewencja.obserwacja
    assert "art. 108 u.s.c." in podstawy(prewencja)  # działanie rozwojowe trafia do IPRZ
    assert "podwyższone obciążenie (godziny nadliczbowe, sprawy w toku)" in prewencja.obserwacja
    # sam odkładany wypoczynek nie jest nazywany obciążeniem
    bez_urlopu = sygnaly(karty("URLOP_ZALEGLY", "TERMINOWOSC"))[1]
    assert "odkładany wypoczynek (urlop zaległy)" in bez_urlopu.obserwacja and "podwyższone obciążenie" not in bez_urlopu.obserwacja
    oba = sygnaly(karty("URLOP_ZALEGLY", "NADGODZINY", "TERMINOWOSC"))[2]
    assert "podwyższone obciążenie (godziny nadliczbowe) oraz odkładany wypoczynek (urlop zaległy)" in oba.obserwacja
    assert "DOBRE_WYNIKI_PRZY_OBCIAZENIU" not in kody(sygnaly(karty("TERMINOWOSC")))
    assert "DOBRE_WYNIKI_PRZY_OBCIAZENIU" not in kody(sygnaly(karty("NADGODZINY")))


def test_bez_kart_partner_podpowiada_dzialania_prewencyjne():
    (sygnal,) = sygnaly(())

    assert sygnal.kod == "BEZ_SYGNALOW" and sygnal.karty == ()
    assert "zanim pojawią się trudności" in sygnal.obserwacja
    assert "art. 108 u.s.c." in podstawy(sygnal)


def test_zadna_kombinacja_kart_nie_daje_oceny_osoby_diagnozy_kary_ani_dzialania_bez_podstawy():
    wszystkie = list(TYTULY)
    for ile in range(len(wszystkie) + 1):
        for zestaw in itertools.combinations(wszystkie, ile):
            wynik = sygnaly(karty(*zestaw))
            assert wynik, zestaw
            assert len(set(kody(wynik))) == len(wynik)
            assert [sygnal.rodzaj for sygnal in wynik] == sorted((sygnal.rodzaj for sygnal in wynik), key=[DOBROSTAN, DOCENIENIE].index)
            for sygnal in wynik:
                assert sygnal.obserwacja.startswith(("Obserwujemy", "W danych nie ma")), sygnal.obserwacja
                assert sygnal.rozmowa.endswith("?")
                assert 2 <= len(sygnal.dzialania) <= 5
                assert set(sygnal.karty) <= set(zestaw)
                for dzialanie in sygnal.dzialania:
                    assert dzialanie.podstawa.strip(), dzialanie.tekst
                    # działanie czytają obie strony - to równoważnik zdania, nie polecenie dla przełożonego
                    assert not re.match(r"(Ustal|Wystąp|Złóż|Zaproponuj|Podziękuj|Wpisz|Umów|Przekaż|Rozważ|Zapytaj|Doceń)\b", dzialanie.tekst), dzialanie.tekst
                for tekst in teksty(sygnal):
                    for wzorzec in NIEDOZWOLONE:
                        assert not re.search(wzorzec, tekst.lower()), (wzorzec, tekst)


def test_zasady_partnera_sa_jawne_i_trafiaja_do_modelu_jezykowego():
    assert partner_hr.CEL.startswith("Wspierać bezpośredniego przełożonego w mądrym, pełnym szacunku i efektywnym zarządzaniu ludźmi")
    assert [zasada.split(":")[0] for zasada in partner_hr.ZASADY] == [
        "Nie oceniaj pracownika", "Promuj dialog", "Bądź pragmatyczny w realiach administracji publicznej",
        "Dbaj o kulturę doceniania", "Utrzymuj ton",
    ]
    for fragment in ("Nie oceniaj pracownika", "partnerskiej rozmowy", "służbie cywilnej", "żargonu"):
        assert fragment in ZASADY_RADARU
    # pytania zadaje się pracownikowi - model nadal nie pyta o zdrowie ani emocje
    assert "Nie pytaj o zdrowie, emocje" in ZASADY_RADARU


@pytest.mark.parametrize("kod", sorted(TYTULY))
def test_sygnal_wskazuje_karty_z_ktorych_wynika(kod):
    for sygnal in sygnaly(karty(kod)):
        assert sygnal.karty in ((kod,), ())
