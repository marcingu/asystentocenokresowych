"""Dane demonstracyjne - fikcyjny urząd. Wszystkie osoby, sprawy i zdarzenia są zmyślone.

Dane powstają tymi samymi usługami, których używa aplikacja, więc przechodzą przez wszystkie reguły rdzenia.
Daty są liczone względem podanego dnia - pokaz wygląda tak samo niezależnie od tego, kiedy się go uruchamia.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction

from asystent_ocen import terminy
from asystent_ocen.kalendarz import czy_dzien_ustawowo_wolny, dodaj_miesiace
from asystent_ocen.kryteria import kryteria_obowiazkowe

from . import uslugi
from .models import Pracownik, UstaleniaMonitoringu

WYDZIAL = "Wydział Organizacyjny"
KADRY = "Biuro Kadr i Szkoleń"


def _roboczy(dzien: date) -> date:
    """Najbliższy dzień roboczy nie późniejszy niż podany (czynności w pokazie nie wypadają w dni wolne)."""
    while dzien.weekday() >= 5 or czy_dzien_ustawowo_wolny(dzien):
        dzien -= timedelta(days=1)
    return dzien


def _dni(dzien: date, ile: int) -> date:
    return _roboczy(dzien + timedelta(days=ile))


def _osoba(login: str, imie: str, nazwisko: str, stanowisko: str, komorka: str, opis: str, **pola) -> Pracownik:
    # Konto bez hasła: wejście jest możliwe wyłącznie w trybie demonstracyjnym.
    konto = get_user_model().objects.create_user(username=login)
    dane = {
        "rodzaj_zatrudnienia": "umowa_na_czas_nieokreslony",
        "identyfikator_ezd": f"stanowisko-{login}",
        "klauzula_ezd_potwierdzona": True,
    }
    dane.update(pola)
    return Pracownik.objects.create(
        uzytkownik=konto, imie=imie, nazwisko=nazwisko, stanowisko=stanowisko, komorka=komorka,
        opis_stanowiska=opis, **dane,
    )


def _oceny(arkusz: str, dodatkowe: list[str], punkty: int | dict[str, int], domyslnie: int = 5) -> dict[str, int]:
    nazwy = kryteria_obowiazkowe(arkusz) + dodatkowe
    if isinstance(punkty, int):
        return {nazwa: punkty for nazwa in nazwy}
    return {nazwa: punkty.get(nazwa, domyslnie) for nazwa in nazwy}


def _do_oceniania(osoba, kadry, oceniajacy, *, poczatek: date, dodatkowe: list[str], termin: date | None = None):
    """Cykl z potwierdzonymi kryteriami - etap rozmowy oceniającej i dokonania oceny."""
    ocena = uslugi.rozpocznij_cykl(osoba, kadry.uzytkownik, poczatek_cyklu=poczatek, data=poczatek)
    uslugi.wyznacz_kryteria(
        ocena, oceniajacy.uzytkownik, kryteria_dodatkowe=dodatkowe,
        termin=termin or terminy.termin_oceny(poczatek), data=_dni(poczatek, 9),
    )
    uslugi.potwierdz_kryteria(ocena, osoba.uzytkownik, data=_dni(poczatek, 10))
    return ocena


@transaction.atomic
def zaladuj(dzien: date) -> dict[str, Pracownik]:
    """Buduje fikcyjny urząd z ocenami na każdym etapie procesu. Zwraca osoby według loginów."""
    dwa_lata_temu = dodaj_miesiace(dzien, -24)

    dyrektor = _osoba(
        "dyrektor", "Helena", "Dąbrowska", "dyrektor generalny urzędu", "Kierownictwo urzędu",
        "Zapewnienie funkcjonowania i ciągłości pracy urzędu; dokonywanie czynności z zakresu prawa pracy.",
        rodzaj_zatrudnienia="wyzsze_stanowisko", rola_dyrektor=True, kieruje_pracownikami=True,
        data_zatrudnienia=dodaj_miesiace(dzien, -80),
    )
    kadry = _osoba(
        "kadry", "Barbara", "Kowalczyk", "główny specjalista do spraw kadr", KADRY,
        "Prowadzenie spraw kadrowych pracowników urzędu, w tym obsługa procesu ocen okresowych.",
        rola_kadry=True, przelozony=dyrektor, data_zatrudnienia=dodaj_miesiace(dzien, -60),
    )
    naczelnik = _osoba(
        "naczelnik", "Tomasz", "Wiśniewski", "naczelnik wydziału", WYDZIAL,
        "Kierowanie pracą wydziału, nadzór nad terminowością i jakością załatwianych spraw.",
        rodzaj_zatrudnienia="mianowanie", kieruje_pracownikami=True, przelozony=dyrektor,
        data_zatrudnienia=dodaj_miesiace(dzien, -120), rok_mianowania=dzien.year - 9, stopien_sluzbowy=5,
        data_stopnia=dodaj_miesiace(dzien, -40),
    )

    def podwladny(login, imie, nazwisko, stanowisko, opis, **pola) -> Pracownik:
        return _osoba(login, imie, nazwisko, stanowisko, WYDZIAL, opis, przelozony=naczelnik, **pola)

    # --- Anna: ocena do sporządzenia za kilka dni; poprzednia ocena na poziomie „powyżej oczekiwań” ---
    sporzadzenie_poprzedniej = _roboczy(dwa_lata_temu + timedelta(days=5))
    poczatek_poprzedniej = _roboczy(dodaj_miesiace(sporzadzenie_poprzedniej, -24))
    anna = podwladny(
        "anna", "Anna", "Nowak", "starszy specjalista",
        "Prowadzenie spraw z zakresu skarg i wniosków oraz organizacji pracy wydziału.",
        rodzaj_zatrudnienia="mianowanie", data_zatrudnienia=dodaj_miesiace(poczatek_poprzedniej, -30),
        rok_mianowania=poczatek_poprzedniej.year - 1, stopien_sluzbowy=2,
        data_stopnia=dodaj_miesiace(poczatek_poprzedniej, -6),
    )
    dodatkowe_anny = ["Orientacja na klienta/interesanta", "Myślenie analityczne"]
    poprzednia = _do_oceniania(
        anna, kadry, naczelnik, poczatek=poczatek_poprzedniej, dodatkowe=dodatkowe_anny,
        termin=sporzadzenie_poprzedniej,
    )
    uslugi.sporzadz_ocene(
        poprzednia, naczelnik.uzytkownik, data_rozmowy=_dni(sporzadzenie_poprzedniej, -2),
        oceny=_oceny("C", dodatkowe_anny, 7),
        wnioski_iprz="Szkolenie z prowadzenia postępowań skargowych; udział w zespole wdrażającym EZD RP.",
        uzasadnienie="Sprawy prowadzone terminowo i samodzielnie; projekty pism nie wymagały poprawek merytorycznych.",
        wniosek_o_stopien="NIE", data=sporzadzenie_poprzedniej,
    )
    uslugi.potwierdz_zapoznanie(poprzednia, anna.uzytkownik, data=sporzadzenie_poprzedniej)
    biezaca = uslugi.rozpocznij_kolejny_cykl(poprzednia, kadry.uzytkownik, data=sporzadzenie_poprzedniej)
    uslugi.wyznacz_kryteria(
        biezaca, naczelnik.uzytkownik, kryteria_dodatkowe=dodatkowe_anny,
        termin=terminy.termin_oceny(sporzadzenie_poprzedniej), data=_dni(sporzadzenie_poprzedniej, 8),
    )
    uslugi.potwierdz_kryteria(biezaca, anna.uzytkownik, data=_dni(sporzadzenie_poprzedniej, 9))
    notatki = [
        (4, "obserwacja", "Przygotowała projekt procedury obiegu korespondencji; wdrożony bez poprawek merytorycznych."),
        (9, "obserwacja", "Sprawy z zakresu skarg i wniosków załatwia przed terminem; w drugim kwartale żadna nie przekroczyła terminu."),
        (15, "osiagniecie", "Przeprowadziła szkolenie dla nowych pracowników wydziału z obsługi EZD RP."),
        (21, "obserwacja", "Dwa projekty pism do ministerstwa wymagały poprawek stylistycznych; merytorycznie bez uwag."),
    ]
    for miesiac, rodzaj, tresc in notatki:
        uslugi.dodaj_notatke(
            biezaca, naczelnik.uzytkownik, tresc=tresc, rodzaj=rodzaj,
            data=_roboczy(dodaj_miesiace(sporzadzenie_poprzedniej, miesiac)),
        )

    # --- Piotr: nowy pracownik na czas nieokreślony - kryteria do wyznaczenia w 30 dni ---
    zatrudnienie_piotra = _dni(dzien, -12)
    piotr = podwladny(
        "piotr", "Piotr", "Zieliński", "specjalista",
        "Obsługa zamówień i umów wydziału oraz prowadzenie rejestru umów.",
        data_zatrudnienia=zatrudnienie_piotra,
    )
    ocena_piotra = uslugi.rozpocznij_cykl(piotr, kadry.uzytkownik, data=zatrudnienie_piotra)
    # Egzamin ze służby przygotowawczej zdawał jeszcze na umowie na czas określony (art. 36 ust. 4 i 5 u.s.c.).
    uslugi.zapisz_egzamin(
        ocena_piotra, naczelnik.uzytkownik, punkty="31", punkty_max="50", poprawkowy=True,
        data_egzaminu=_roboczy(dodaj_miesiace(zatrudnienie_piotra, -5)), uwagi="W pierwszym terminie 24 pkt.",
        data=_dni(dzien, -10),
    )

    # --- Katarzyna: kryteria wyznaczone, czekają na jej potwierdzenie ---
    zatrudnienie_katarzyny = _dni(dzien, -21)
    katarzyna = podwladny(
        "katarzyna", "Katarzyna", "Lewandowska", "inspektor",
        "Obsługa kancelaryjna wydziału i archiwizacja dokumentacji.",
        data_zatrudnienia=zatrudnienie_katarzyny,
    )
    ocena_katarzyny = uslugi.rozpocznij_cykl(katarzyna, kadry.uzytkownik, data=zatrudnienie_katarzyny)
    uslugi.zapisz_egzamin(
        ocena_katarzyny, naczelnik.uzytkownik, punkty="44", punkty_max="50",
        data_egzaminu=_roboczy(dodaj_miesiace(zatrudnienie_katarzyny, -6)), data=_dni(dzien, -2),
    )
    uslugi.wyznacz_kryteria(
        ocena_katarzyny, naczelnik.uzytkownik, kryteria_dodatkowe=["Orientacja na klienta/interesanta", "Kreatywność"],
        termin=terminy.termin_oceny(zatrudnienie_katarzyny), data=_dni(dzien, -1),
    )

    # --- Marek: ocena negatywna sporządzona, do zapoznania (potem można wnieść sprzeciw) ---
    poczatek_marka = _roboczy(dwa_lata_temu + timedelta(days=12))
    marek = podwladny(
        "marek", "Marek", "Kamiński", "starszy inspektor",
        "Prowadzenie postępowań administracyjnych i przygotowywanie projektów decyzji.",
        rodzaj_zatrudnienia="mianowanie", data_zatrudnienia=dodaj_miesiace(poczatek_marka, -40),
        rok_mianowania=poczatek_marka.year - 1, stopien_sluzbowy=1, data_stopnia=dodaj_miesiace(poczatek_marka, -8),
    )
    dodatkowe_marka = ["Podejmowanie decyzji i odpowiedzialność"]
    ocena_marka = _do_oceniania(marek, kadry, naczelnik, poczatek=poczatek_marka, dodatkowe=dodatkowe_marka)
    uslugi.sporzadz_ocene(
        ocena_marka, naczelnik.uzytkownik, data_rozmowy=_dni(dzien, -3),
        oceny=_oceny("C", dodatkowe_marka, {"Rzetelność": 1, "Współpraca": 5}, domyslnie=3),
        wnioski_iprz=(
            "Szkolenie z Kodeksu postępowania administracyjnego; praca z opiekunem merytorycznym przez trzy miesiące; "
            "cotygodniowy przegląd terminów spraw z przełożonym."
        ),
        uzasadnienie=(
            "W okresie oceny 11 z 34 spraw zostało załatwionych po terminie. Trzy projekty decyzji wymagały "
            "sprostowania z powodu błędnie wskazanej podstawy prawnej. Ustalenia z rozmów w sprawie terminowości "
            "nie zostały wykonane."
        ),
        poprzednia_reczna={"ocena": "POZYTYWNA", "poziom": "na poziomie oczekiwań", "data": poczatek_marka.isoformat()},
        data=_dni(dzien, -2),
    )

    # --- Ewa: termin z arkusza minął, ale długa nieobecność przedłużyła termin ustawowy (art. 81 ust. 7) ---
    poczatek_ewy = _roboczy(dwa_lata_temu - timedelta(days=8))
    ewa = podwladny(
        "ewa", "Ewa", "Szymańska", "główny specjalista",
        "Koordynacja kontroli zarządczej i sprawozdawczości wydziału.",
        data_zatrudnienia=poczatek_ewy,
    )
    _do_oceniania(ewa, kadry, naczelnik, poczatek=poczatek_ewy, dodatkowe=["Myślenie analityczne", "Negocjowanie"])
    poczatek_nieobecnosci = dodaj_miesiace(poczatek_ewy, 10)
    uslugi.dodaj_nieobecnosc(
        ewa, kadry.uzytkownik, od=poczatek_nieobecnosci, do=poczatek_nieobecnosci + timedelta(days=94)
    )

    # --- Robert: ocena negatywna, sprzeciw wniesiony w terminie - czeka na rozstrzygnięcie ---
    poczatek_roberta = _roboczy(dwa_lata_temu - timedelta(days=4))
    robert = podwladny(
        "robert", "Robert", "Kaczmarek", "inspektor",
        "Obsługa interesantów i prowadzenie rejestru skarg.",
        data_zatrudnienia=poczatek_roberta,
    )
    dodatkowe_roberta = ["Orientacja na klienta/interesanta"]
    ocena_roberta = _do_oceniania(
        robert, kadry, naczelnik, poczatek=poczatek_roberta, dodatkowe=dodatkowe_roberta, termin=_dni(dzien, -12)
    )
    uslugi.sporzadz_ocene(
        ocena_roberta, naczelnik.uzytkownik, data_rozmowy=_dni(dzien, -13),
        oceny=_oceny("C", dodatkowe_roberta, {"Komunikacja": 1}, domyslnie=3),
        wnioski_iprz="Szkolenie z obsługi trudnego interesanta; warsztaty z komunikacji pisemnej.",
        uzasadnienie=(
            "W okresie oceny wpłynęło siedem uzasadnionych skarg interesantów na sposób udzielania informacji. "
            "Odpowiedzi na skargi były przekazywane po terminie."
        ),
        data=_dni(dzien, -12),
    )
    uslugi.potwierdz_zapoznanie(ocena_roberta, robert.uzytkownik, data=_dni(dzien, -12))
    uslugi.wnies_sprzeciw(
        ocena_roberta, robert.uzytkownik,
        tresc=(
            "Nie zgadzam się z oceną kryterium „Komunikacja”. Cztery z siedmiu skarg dotyczyły okresu, w którym "
            "zastępowałem nieobecnego pracownika i obsługiwałem dwa stanowiska. Wnoszę o zmianę oceny."
        ),
        data=_dni(dzien, -12) + timedelta(days=6),
    )

    # --- osoby bez oceny: nowa pracownica i umowa na czas określony ---
    podwladny(
        "zofia", "Zofia", "Mazur", "specjalista",
        "Prowadzenie spraw z zakresu dostępu do informacji publicznej.",
        data_zatrudnienia=_dni(dzien, -3),
    )
    podwladny(
        "jan", "Jan", "Wójcik", "referent",
        "Wsparcie obsługi kancelaryjnej wydziału.",
        rodzaj_zatrudnienia="umowa_na_czas_okreslony", data_zatrudnienia=dodaj_miesiace(dzien, -5),
    )

    # --- oceny prowadzone przez dyrektor generalną: naczelnik (arkusz B) i kadry ---
    _do_oceniania(
        naczelnik, kadry, dyrektor, poczatek=_roboczy(dodaj_miesiace(dzien, -20)),
        dodatkowe=["Zarządzanie strategiczne", "Rzetelność"],
    )
    sporzadzenie_kadr = _roboczy(dodaj_miesiace(dzien, -12))
    ocena_kadr = _do_oceniania(
        kadry, kadry, dyrektor, poczatek=_roboczy(dodaj_miesiace(dzien, -36)), dodatkowe=["Myślenie analityczne"],
        termin=sporzadzenie_kadr,
    )
    uslugi.sporzadz_ocene(
        ocena_kadr, dyrektor.uzytkownik, data_rozmowy=_dni(sporzadzenie_kadr, -1),
        oceny=_oceny("C", ["Myślenie analityczne"], 5),
        wnioski_iprz="Szkolenie z nowelizacji przepisów o służbie cywilnej.", data=sporzadzenie_kadr,
    )
    uslugi.potwierdz_zapoznanie(ocena_kadr, kadry.uzytkownik, data=sporzadzenie_kadr)
    kolejna_kadr = uslugi.rozpocznij_kolejny_cykl(ocena_kadr, kadry.uzytkownik, data=sporzadzenie_kadr)
    uslugi.wyznacz_kryteria(
        kolejna_kadr, dyrektor.uzytkownik, kryteria_dodatkowe=["Myślenie analityczne"],
        termin=terminy.termin_oceny(sporzadzenie_kadr), data=_dni(sporzadzenie_kadr, 12),
    )
    uslugi.potwierdz_kryteria(kolejna_kadr, kadry.uzytkownik, data=_dni(sporzadzenie_kadr, 13))

    # --- ustalenia wymagane przed korzystaniem z danych EZD RP (art. 22[2] § 6-7 w zw. z art. 22[3] KP) ---
    UstaleniaMonitoringu.objects.create(
        integracja_wlaczona=True,
        podstawa="Regulamin pracy urzędu, § 27a (obwieszczenie dyrektora generalnego).",
        cele="Zapewnienie organizacji pracy umożliwiającej pełne wykorzystanie czasu pracy.",
        zakres="Liczba i terminowość spraw prowadzonych w EZD RP oraz wyniki akceptacji projektów pism.",
        sposob="Zestawienie zbiorcze za okres oceny, bez punktacji i rankingów; jawne dla ocenianego.",
        data_poinformowania=dzien - timedelta(days=60),
    )
    _konta_do_pokazu_zaplecza()
    return {
        osoba.uzytkownik.username: osoba
        for osoba in Pracownik.objects.select_related("uzytkownik") if osoba.uzytkownik_id
    }


def _konta_do_pokazu_zaplecza() -> None:
    """Administrator pokazu (bez hasła i bez dostępu do panelu Django) oraz konto zawieszone za brak aktywności:
    Ewa jest od dawna nieobecna, więc na jej koncie nikt się nie logował ponad miesiąc."""
    from django.utils import timezone

    from . import bezpieczenstwo

    konta = get_user_model().objects
    konta.create_user(username="administrator", first_name="Administrator", last_name="systemu", is_superuser=True)
    teraz = timezone.now()
    konta.filter(username="ewa").update(last_login=teraz - timedelta(days=45), date_joined=teraz - timedelta(days=400))
    bezpieczenstwo.zawies_nieaktywne()
