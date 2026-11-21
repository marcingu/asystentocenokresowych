"""Przebieg procesu oceny - etapy, role i blokady pól (przypadki użycia i model BPMN KPRM).

Role odpowiadają torom modelu BPMN: ZARZĄDZAJĄCY (kadry / dyrektor generalny), OCENIAJĄCY,
OCENIANY, ADMIN. Harmonogram (SCHEDULER) jest realizowany przez moduł `przypomnienia`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum

from .bledy import Blad, BladWalidacji
from .konfiguracja import Przepisy, _ustal_przepisy
from .kryteria import _klucz, bledy_kryteriow_dodatkowych
from .terminy import czy_dopuszczalna_zmiana_terminu
from .walidacja import NIE, Formularz, bledy_przed_zatwierdzeniem, domyslna_odpowiedz_o_wniosek
from .wynik import WynikOceny, bledy_ocen_czastkowych, oblicz_wynik


class Rola(str, Enum):
    ZARZADZAJACY = "zarządzający"
    OCENIAJACY = "oceniający"
    OCENIANY = "oceniany"
    ADMIN = "admin"


class Etap(str, Enum):
    KRYTERIA_DO_WYZNACZENIA = "kryteria do wyznaczenia"
    KRYTERIA_DO_POTWIERDZENIA = "kryteria do potwierdzenia przez ocenianego"
    OCENIANIE = "rozmowa oceniająca i dokonanie oceny"
    OCENA_DO_ZAPOZNANIA = "ocena do zapoznania"
    ZAKONCZONA = "zakończona"


class BladUprawnien(Exception):
    """Rola nie może wykonać tej czynności."""


class BladEtapu(Exception):
    """Czynność niedozwolona na obecnym etapie procesu."""


@dataclass
class Notatka:
    data: date
    tresc: str


@dataclass
class Dokument:
    rodzaj: str  # np. "zawiadomienie o nowym terminie oceny"
    data: date
    adresat: Rola
    opis: str = ""  # np. przyczyna zmiany terminu


@dataclass
class ProcesOceny:
    arkusz: str
    urzednik: bool
    poczatek_cyklu: date
    etap: Etap | None = None  # stan początkowy ustala implementacja (test: nowy proces = KRYTERIA_DO_WYZNACZENIA)
    kryteria_dodatkowe: list[str] = field(default_factory=list)
    termin: date | None = None
    data_zapoznania_z_kryteriami: date | None = None
    wynik: WynikOceny | None = None
    oceny: dict[str, int] = field(default_factory=dict)
    data_zapoznania_z_ocena: date | None = None
    zapoznanie_fikcyjne: bool = False
    fikcje_stwierdzil: Rola | None = None
    oceny_anulowane: list[WynikOceny] = field(default_factory=list)
    notatki: list[Notatka] = field(default_factory=list)
    dokumenty: list[Dokument] = field(default_factory=list)
    # Pola dodane w implementacji (opcjonalne) - dane czynności, które inaczej by przepadały:
    data_wyznaczenia_kryteriow: date | None = None  # rozmowa i wpisanie kryteriów przez oceniającego (§ 5 rozp.)
    data_rozmowy_oceniajacej: date | None = None  # § 10 rozp.
    data_sporzadzenia: date | None = None  # dzień sporządzenia oceny na piśmie (§ 11 rozp.)
    daty_zmiany_oceniajacego: list[date] = field(default_factory=list)  # art. 81 ust. 8 pkt 1 u.s.c.
    formularz: Formularz | None = None  # zatwierdzona treść części II i III arkusza
    przepisy: Przepisy | None = field(default=None, repr=False, compare=False)  # None = przepisy domyślne

    def __post_init__(self) -> None:
        if self.etap is None:
            self.etap = Etap.KRYTERIA_DO_WYZNACZENIA

    # --- kontrola ról i etapów ---

    def _wymagaj_roli(self, rola: Rola, *dozwolone: Rola, czynnosc: str) -> None:
        if rola not in dozwolone:
            uprawnieni = ", ".join(dozwolona.value for dozwolona in dozwolone)
            raise BladUprawnien(
                f"Rola „{getattr(rola, 'value', rola)}” nie może wykonać czynności: {czynnosc} "
                f"(uprawnieni: {uprawnieni})"
            )

    def _wymagaj_etapu(self, *dozwolone: Etap, czynnosc: str) -> None:
        if self.etap not in dozwolone:
            raise BladEtapu(
                f"Czynność „{czynnosc}” jest niedozwolona na etapie „{getattr(self.etap, 'value', self.etap)}”"
            )

    def _sprawdzone_kryteria(self, kryteria_dodatkowe: list[str]) -> list[str]:
        """Waliduje wybór kryteriów dodatkowych (§ 5 ust. 2 rozp.) i zwraca nazwy w pisowni z wykazu."""
        przepisy = _ustal_przepisy(self.przepisy)
        bledy = bledy_kryteriow_dodatkowych(self.arkusz, kryteria_dodatkowe, przepisy)
        if bledy:
            raise BladWalidacji(bledy)
        z_wykazu = {_klucz(nazwa): nazwa for nazwa in przepisy.katalog_kryteriow}
        return [z_wykazu[_klucz(nazwa)] for nazwa in kryteria_dodatkowe if _klucz(nazwa)]

    def _sprawdz_dopuszczalnosc_zmiany_terminu(self, dzien: date, data_ostatniej_oceny: date | None) -> list[Blad]:
        """Art. 81 ust. 8 in fine u.s.c. - warunek wspólny dla wszystkich przypadków zmiany terminu."""
        przepisy = _ustal_przepisy(self.przepisy)
        dopuszczalna = czy_dopuszczalna_zmiana_terminu(
            dzien,
            data_ostatniej_oceny=data_ostatniej_oceny,
            data_nawiazania_stosunku_pracy=self.poczatek_cyklu,
            data_zapoznania_z_kryteriami=self.data_zapoznania_z_kryteriami,
            przepisy=przepisy,
        )
        if dopuszczalna:
            return []
        return [Blad(
            "ZMIANA_TERMINU_ZBYT_WCZESNIE",
            f"Termin oceny można zmienić dopiero, gdy upłynie więcej niż {przepisy.min_miesiecy_do_zmiany_terminu} "
            "mies. od ostatniej oceny, a przy pierwszej ocenie - od początku okresu podlegającego ocenie.",
            "art. 81 ust. 8 in fine u.s.c.",
        )]

    # --- etap I: kryteria ---

    def wyznacz_kryteria(self, rola: Rola, kryteria_dodatkowe: list[str], termin: date, data: date) -> None:
        """§ 5 i § 6 ust. 1 rozp.: oceniający wpisuje kryteria dodatkowe i termin sporządzenia oceny,
        po czym przekazuje je ocenianemu do potwierdzenia. Do potwierdzenia wpis można poprawiać."""
        self._wymagaj_roli(rola, Rola.OCENIAJACY, czynnosc="wyznaczenie kryteriów oceny")
        self._wymagaj_etapu(
            Etap.KRYTERIA_DO_WYZNACZENIA, Etap.KRYTERIA_DO_POTWIERDZENIA, czynnosc="wyznaczenie kryteriów oceny"
        )
        self.kryteria_dodatkowe = self._sprawdzone_kryteria(kryteria_dodatkowe)
        self.termin = termin
        self.data_wyznaczenia_kryteriow = data
        self.etap = Etap.KRYTERIA_DO_POTWIERDZENIA

    def potwierdz_kryteria(self, rola: Rola, data: date) -> None:
        """§ 6 ust. 2 rozp.: oceniany potwierdza rozmowę oraz zapoznanie z kryteriami i terminem oceny."""
        self._wymagaj_roli(rola, Rola.OCENIANY, czynnosc="potwierdzenie rozmowy i zapoznania z kryteriami")
        self._wymagaj_etapu(Etap.KRYTERIA_DO_POTWIERDZENIA, czynnosc="potwierdzenie zapoznania z kryteriami")
        self.data_zapoznania_z_kryteriami = data
        self.etap = Etap.OCENIANIE

    def zmien_kryteria(self, rola: Rola, kryteria_dodatkowe: list[str], *, tryb_korekty: bool = False) -> None:
        """Zmiana kryteriów dodatkowych: przez oceniającego do potwierdzenia przez ocenianego, później
        wyłącznie przez administratora w trybie korekty błędów (schematy pól formularza KPRM)."""
        if tryb_korekty:
            self._wymagaj_roli(rola, Rola.ADMIN, czynnosc="korekta błędów w kryteriach oceny")
        else:
            self._wymagaj_roli(rola, Rola.OCENIAJACY, czynnosc="zmiana kryteriów oceny")
            self._wymagaj_etapu(
                Etap.KRYTERIA_DO_WYZNACZENIA, Etap.KRYTERIA_DO_POTWIERDZENIA, czynnosc="zmiana kryteriów oceny"
            )
        nowe_kryteria = self._sprawdzone_kryteria(kryteria_dodatkowe)
        if self.oceny:
            # Korekta po sporządzeniu oceny nie może rozspójnić kryteriów i ocen cząstkowych.
            bledy = bledy_ocen_czastkowych(self.arkusz, nowe_kryteria, self.oceny, _ustal_przepisy(self.przepisy))
            if bledy:
                raise BladWalidacji(bledy)
        self.kryteria_dodatkowe = nowe_kryteria

    # --- sytuacje kadrowe w trakcie okresu oceny ---

    def zmien_termin(
        self, rola: Rola, nowy_termin: date, data: date, przyczyna: str, data_ostatniej_oceny: date | None = None
    ) -> None:
        """Art. 81 ust. 8 u.s.c. i § 8 rozp.: oceniający zmienia termin oceny i pisemnie zawiadamia ocenianego
        (dokument „zawiadomienie o nowym terminie oceny”). Warunek upływu ponad 6 miesięcy sprawdza się jak
        w `zloz_wniosek_o_zmiane_terminu`."""
        self._wymagaj_roli(rola, Rola.OCENIAJACY, czynnosc="zmiana terminu oceny")
        self._wymagaj_etapu(Etap.OCENIANIE, czynnosc="zmiana terminu oceny")
        bledy = self._sprawdz_dopuszczalnosc_zmiany_terminu(data, data_ostatniej_oceny)
        if not str(przyczyna or "").strip():
            bledy.append(Blad(
                "BRAK_PRZYCZYNY_ZMIANY_TERMINU",
                "Podaj przyczynę zmiany terminu oceny - ustawa dopuszcza zmianę tylko w wymienionych przypadkach.",
                "art. 81 ust. 8 u.s.c.",
            ))
        if bledy:
            raise BladWalidacji(bledy)
        self.termin = nowy_termin
        self.dokumenty.append(
            Dokument("zawiadomienie o nowym terminie oceny", data, Rola.OCENIANY, opis=str(przyczyna).strip())
        )

    def zloz_wniosek_o_zmiane_terminu(
        self, rola: Rola, data: date, data_ostatniej_oceny: date | None = None
    ) -> None:
        """Art. 81 ust. 8 pkt 4 u.s.c.: wniosek składa oceniany, rozpatruje oceniający. Przy pierwszej ocenie
        (`data_ostatniej_oceny=None`) 6 miesięcy liczy się wg przełącznika `pierwsza_ocena_6_miesiecy_od`
        (domyślnie od początku cyklu, czyli nawiązania stosunku pracy na czas nieokreślony).
        Dopuszczalny wniosek trafia do oceniającego jako dokument „wniosek o zmianę terminu oceny”."""
        self._wymagaj_roli(rola, Rola.OCENIANY, czynnosc="złożenie wniosku o zmianę terminu oceny")
        self._wymagaj_etapu(Etap.OCENIANIE, czynnosc="złożenie wniosku o zmianę terminu oceny")
        bledy = self._sprawdz_dopuszczalnosc_zmiany_terminu(data, data_ostatniej_oceny)
        if bledy:
            raise BladWalidacji(bledy)
        self.dokumenty.append(Dokument("wniosek o zmianę terminu oceny", data, Rola.OCENIAJACY))

    def zmien_oceniajacego(self, rola: Rola, data: date) -> None:
        """Zmiana na stanowisku oceniającego w trakcie okresu oceny: kryteria i termin pozostają bez zmian
        (§ 9 ust. 3 rozp.); zmiana jest odnotowywana, bo uprawnia do zmiany terminu (art. 81 ust. 8 pkt 1)."""
        self._wymagaj_roli(rola, Rola.ZARZADZAJACY, czynnosc="zmiana oceniającego")
        self._wymagaj_etapu(
            Etap.KRYTERIA_DO_WYZNACZENIA,
            Etap.KRYTERIA_DO_POTWIERDZENIA,
            Etap.OCENIANIE,
            Etap.OCENA_DO_ZAPOZNANIA,
            czynnosc="zmiana oceniającego",
        )
        self.daty_zmiany_oceniajacego.append(data)

    # --- notatki z obserwacji ---

    def dodaj_notatke(self, rola: Rola, tresc: str, data: date) -> None:
        """Robocza notatka oceniającego z obserwacji pracy ocenianego (nie jest częścią arkusza)."""
        self._wymagaj_roli(rola, Rola.OCENIAJACY, czynnosc="dodanie notatki z obserwacji")
        self._wymagaj_etapu(
            Etap.KRYTERIA_DO_WYZNACZENIA,
            Etap.KRYTERIA_DO_POTWIERDZENIA,
            Etap.OCENIANIE,
            Etap.OCENA_DO_ZAPOZNANIA,
            czynnosc="dodanie notatki z obserwacji",
        )
        if not str(tresc or "").strip():
            raise BladWalidacji([Blad("PUSTA_NOTATKA", "Notatka nie może być pusta.")])
        self.notatki.append(Notatka(data=data, tresc=tresc))

    def notatki_z_okresu(self, rola: Rola, od: date, do: date) -> list[Notatka]:
        """Notatki oceniającego z okresu od-do (włącznie), chronologicznie. Oceniany nie ma do nich wglądu
        (decyzja zespołu z 21.11.2026)."""
        self._wymagaj_roli(rola, Rola.OCENIAJACY, czynnosc="wgląd w notatki oceniającego")
        return sorted((notatka for notatka in self.notatki if od <= notatka.data <= do), key=lambda n: n.data)

    # --- etap II: ocena ---

    def sporzadz_ocene(
        self,
        rola: Rola,
        *,
        data: date,
        data_rozmowy: date,
        oceny: dict[str, int],
        wnioski_iprz: str,
        uzasadnienie: str = "",
        wniosek_o_stopien: str | None = None,
        umotywowanie_wniosku: str = "",
        posiadany_stopien: int | None = None,
    ) -> WynikOceny:
        """§ 10-11 rozp.: po rozmowie oceniającej oceniający sporządza ocenę; formularz przechodzi pełną
        walidację, wynik jest wyliczany, a ocena trafia do ocenianego do zapoznania."""
        self._wymagaj_roli(rola, Rola.OCENIAJACY, czynnosc="sporządzenie oceny")
        self._wymagaj_etapu(Etap.OCENIANIE, czynnosc="sporządzenie oceny")
        przepisy = _ustal_przepisy(self.przepisy)
        formularz = Formularz(
            arkusz=self.arkusz,
            urzednik=self.urzednik,
            oceny=dict(oceny),
            kryteria_dodatkowe=list(self.kryteria_dodatkowe),
            uzasadnienie=uzasadnienie,
            wnioski_iprz=wnioski_iprz,
            wniosek_o_stopien=wniosek_o_stopien,
            umotywowanie_wniosku=umotywowanie_wniosku,
            posiadany_stopien=posiadany_stopien,
        )
        bledy = bledy_przed_zatwierdzeniem(formularz, przepisy)
        if data_rozmowy > data:
            bledy.append(Blad(
                "ROZMOWA_PO_SPORZADZENIU_OCENY",
                "Rozmowę oceniającą przeprowadza się przed sporządzeniem oceny na piśmie.",
                "§ 10 rozp.",
            ))
        if bledy:
            raise BladWalidacji(bledy)
        wynik = oblicz_wynik(formularz.oceny, przepisy)
        if formularz.wniosek_o_stopien is None:
            # Brak odpowiedzi = brak wniosku (wartości domyślne ze schematu pól formularza KPRM).
            formularz.wniosek_o_stopien = (
                domyslna_odpowiedz_o_wniosek(urzednik=self.urzednik, ocena=wynik.ocena) or NIE
            )
        self.oceny = dict(oceny)
        self.wynik = wynik
        self.formularz = formularz
        self.data_rozmowy_oceniajacej = data_rozmowy
        self.data_sporzadzenia = data
        self.etap = Etap.OCENA_DO_ZAPOZNANIA
        return wynik

    def _zamknij_zapoznaniem(self, data: date) -> None:
        if self.data_sporzadzenia is not None and data < self.data_sporzadzenia:
            raise BladWalidacji([Blad(
                "ZAPOZNANIE_PRZED_SPORZADZENIEM_OCENY",
                "Zapoznanie z oceną nie może nastąpić przed dniem jej sporządzenia.",
                "§ 12 ust. 1 rozp.",
            )])
        self.data_zapoznania_z_ocena = data
        self.etap = Etap.ZAKONCZONA

    def potwierdz_zapoznanie(self, rola: Rola, data: date) -> None:
        """§ 12 ust. 1 rozp.: oceniany potwierdza zapoznanie się z oceną - koniec procesu."""
        self._wymagaj_roli(rola, Rola.OCENIANY, czynnosc="potwierdzenie zapoznania z oceną")
        self._wymagaj_etapu(Etap.OCENA_DO_ZAPOZNANIA, czynnosc="potwierdzenie zapoznania z oceną")
        self._zamknij_zapoznaniem(data)

    def stwierdz_fikcje_zapoznania(self, rola: Rola, data: date) -> None:
        """Przypadek użycia „stwierdzenie fikcji zapoznania z oceną”. Stwierdzić może każda ze stron procesu:
        oceniający, oceniany (odmowa potwierdzenia) i zarządzający; administrator nie jest stroną (decyzja
        zespołu z 21.11.2026). Data stwierdzenia staje się datą zapoznania z oceną."""
        self._wymagaj_roli(
            rola, Rola.OCENIAJACY, Rola.OCENIANY, Rola.ZARZADZAJACY, czynnosc="stwierdzenie fikcji zapoznania z oceną"
        )
        self._wymagaj_etapu(Etap.OCENA_DO_ZAPOZNANIA, czynnosc="stwierdzenie fikcji zapoznania z oceną")
        self._zamknij_zapoznaniem(data)
        self.zapoznanie_fikcyjne = True
        self.fikcje_stwierdzil = Rola(rola)

    # --- sprzeciw (art. 83 ust. 4 u.s.c.) ---

    def uwzglednij_sprzeciw(
        self, rola: Rola, *, tryb: str, data: date, nowe_oceny: dict[str, int] | None = None
    ) -> None:
        """tryb: "zmiana" albo "ponowne_sporzadzenie" (art. 83 ust. 4 u.s.c.).

        Uwzględnienie sprzeciwu wprowadza zarządzający w imieniu dyrektora generalnego (model BPMN).
        „zmiana” zastępuje oceny cząstkowe nowymi - żadna nie może być niższa niż dotychczas (Poradnik KPRM
        s. 32); „ponowne_sporzadzenie” anuluje ocenę i cofa proces do etapu rozmowy i dokonania oceny.
        """
        self._wymagaj_roli(rola, Rola.ZARZADZAJACY, czynnosc="uwzględnienie sprzeciwu od oceny")
        self._wymagaj_etapu(Etap.ZAKONCZONA, czynnosc="uwzględnienie sprzeciwu od oceny")
        if self.wynik is None:
            raise BladEtapu("Nie ma oceny, od której można uwzględnić sprzeciw")
        if tryb == "ponowne_sporzadzenie":
            self._anuluj_ocene(data)
        elif tryb == "zmiana":
            self._zmien_ocene_po_sprzeciwie(nowe_oceny, data)
        else:
            raise ValueError(f"Nieznany tryb uwzględnienia sprzeciwu: {tryb!r}")

    def _anuluj_ocene(self, data: date) -> None:
        self.oceny_anulowane.append(self.wynik)
        self.wynik = None
        self.oceny = {}
        self.formularz = None
        self.data_rozmowy_oceniajacej = None
        self.data_sporzadzenia = None
        self.data_zapoznania_z_ocena = None
        self.zapoznanie_fikcyjne = False
        self.fikcje_stwierdzil = None
        self.etap = Etap.OCENIANIE
        self.dokumenty.append(Dokument("polecenie ponownego sporządzenia oceny", data, Rola.OCENIAJACY))
        self.dokumenty.append(Dokument("powiadomienie o ponownym sporządzeniu oceny", data, Rola.OCENIANY))

    def _zmien_ocene_po_sprzeciwie(self, nowe_oceny: dict[str, int] | None, data: date) -> None:
        przepisy = _ustal_przepisy(self.przepisy)
        if not nowe_oceny:
            raise BladWalidacji([Blad(
                "BRAK_NOWYCH_OCEN", "Zmiana oceny po sprzeciwie wymaga podania ocen cząstkowych.",
                "art. 83 ust. 4 u.s.c.",
            )])
        bledy = bledy_ocen_czastkowych(self.arkusz, self.kryteria_dodatkowe, nowe_oceny, przepisy)
        if not bledy:
            dotychczasowe = {_klucz(nazwa): wartosc for nazwa, wartosc in self.oceny.items()}
            for nazwa, wartosc in nowe_oceny.items():
                poprzednia = dotychczasowe.get(_klucz(nazwa))
                if poprzednia is not None and wartosc < poprzednia:
                    bledy.append(Blad(
                        "OBNIZENIE_OCENY_PO_SPRZECIWIE",
                        f"Uwzględnienie sprzeciwu nie może obniżyć oceny cząstkowej kryterium „{nazwa}” "
                        f"(było {poprzednia}, jest {wartosc}).",
                        "art. 83 ust. 4 u.s.c.; Poradnik KPRM s. 32",
                    ))
        zmieniony_formularz = None
        if not bledy and self.formularz is not None:
            zmieniony_formularz = replace(self.formularz, oceny=dict(nowe_oceny))
            bledy = bledy_przed_zatwierdzeniem(zmieniony_formularz, przepisy)
        if bledy:
            raise BladWalidacji(bledy)
        self.oceny = dict(nowe_oceny)
        self.wynik = oblicz_wynik(self.oceny, przepisy)
        self.formularz = zmieniony_formularz
        for adresat in (Rola.OCENIAJACY, Rola.OCENIANY):
            self.dokumenty.append(Dokument("powiadomienie o zmianie oceny po uwzględnieniu sprzeciwu", data, adresat))
