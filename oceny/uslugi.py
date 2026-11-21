"""Usługi - jedna funkcja na czynność procesu oceny.

Każda czynność działa w transakcji: wczytuje proces z bazy, sprawdza rolę użytkownika w tej ocenie, wywołuje
metodę rdzenia, zapisuje stan i dopisuje wpis w dzienniku zdarzeń. Wyjątki rdzenia (`BladWalidacji`,
`BladUprawnien`, `BladEtapu`) nie są połykane - widok pokazuje komunikat i podstawę prawną.

Reguły prawne są w rdzeniu (`asystent_ocen`). Tutaj są tylko warunki porządkowe aplikacji: kto może wykonać
czynność i czy rekordy w bazie na nią pozwalają.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from django.db import transaction

from asystent_ocen import terminy
from asystent_ocen.bledy import Blad, BladWalidacji
from asystent_ocen.przebieg import OBSERWACJA, OSIAGNIECIE, BladEtapu, BladUprawnien, Etap, Rola
from asystent_ocen.zgodnosc import UstaleniaMonitoringu as UstaleniaRdzenia
from asystent_ocen.zgodnosc import bledy_uruchomienia_monitoringu

from .czas import dzis
from .formularze import nazwy_kryteriow
from .models import Nieobecnosc, Ocena, Pracownik, Sprzeciw, UstaleniaMonitoringu, WniosekOTermin, Zdarzenie
from .uprawnienia import czy_kadry, pracownik_uzytkownika, role_uzytkownika

UWZGLEDNIENIA_SPRZECIWU = (Sprzeciw.ZMIANA, Sprzeciw.PONOWNE_SPORZADZENIE)
CZYNNOSC_NOTATKA = "notatka"
CZYNNOSC_PROJEKT_AI = "projekt uzasadnienia ułożony przez model językowy"
CZYNNOSC_SUGESTIA_AI = "sugestia ocen cząstkowych przygotowana przez model językowy"
# Ślady użycia modelu językowego przy pracy nad oceną - oceniany widzi je po sporządzeniu oceny.
CZYNNOSCI_AI = (CZYNNOSC_PROJEKT_AI, CZYNNOSC_SUGESTIA_AI)


# --- narzędzia wspólne ---

def _podpis(uzytkownik) -> str:
    pracownik = pracownik_uzytkownika(uzytkownik)
    if pracownik is not None:
        return f"{pracownik.imie_i_nazwisko}, {pracownik.stanowisko}"
    return uzytkownik.get_username()


def _zapisz_zdarzenie(ocena: Ocena, uzytkownik, czynnosc: str, data: date, opis: str = "") -> None:
    Zdarzenie.objects.create(
        ocena=ocena, uzytkownik=uzytkownik, podpis=_podpis(uzytkownik), czynnosc=czynnosc, data=data, opis=opis
    )


def _wymagaj_roli(uzytkownik, ocena: Ocena, rola: Rola) -> None:
    if rola not in role_uzytkownika(uzytkownik, ocena):
        raise BladUprawnien(f"Użytkownik nie występuje w tej ocenie w roli „{Rola(rola).value}”.")


def _wymagaj_kadr(uzytkownik, czynnosc: str) -> None:
    if not czy_kadry(uzytkownik):
        raise BladUprawnien(f"Czynność „{czynnosc}” wykonuje komórka kadr.")


def _data_ostatniej_oceny(ocena: Ocena) -> date | None:
    """Dzień sporządzenia poprzedniej oceny (art. 81 ust. 8 in fine u.s.c.); None przy pierwszej ocenie."""
    if ocena.poprzednia_id is None:
        return None
    return ocena.poprzednia.proces().data_sporzadzenia


@contextmanager
def _czynnosc(ocena: Ocena, uzytkownik, rola: Rola, nazwa: str, data: date, opis: str = ""):
    """Czynność na procesie w jednej transakcji. Wyjątek w bloku wycofuje wszystko."""
    with transaction.atomic():
        biezaca = Ocena.objects.select_for_update().select_related("oceniany", "poprzednia").get(pk=ocena.pk)
        _wymagaj_roli(uzytkownik, biezaca, rola)
        proces = biezaca.proces()
        yield biezaca, proces
        biezaca.zapisz_proces(proces)
        _zapisz_zdarzenie(biezaca, uzytkownik, nazwa, data, opis)
    ocena.refresh_from_db()


# --- rozpoczęcie cyklu ---

def rozpocznij_cykl(
    pracownik: Pracownik, uzytkownik, *, poczatek_cyklu: date | None = None, data: date | None = None
) -> Ocena:
    """Pierwszy cykl oceny pracownika. Oceniającym jest bezpośredni przełożony (art. 81 ust. 1 u.s.c.).

    Początek cyklu to domyślnie dzień zatrudnienia na czas nieokreślony albo mianowania; kadry mogą podać inny
    dzień, np. sporządzenia ostatniej oceny prowadzonej na papierze.
    """
    _wymagaj_kadr(uzytkownik, "rozpoczęcie cyklu oceny")
    data = data or dzis()
    if not pracownik.podlega_ocenie:
        raise BladWalidacji([Blad(
            "NIE_PODLEGA_OCENIE",
            f"{pracownik.imie_i_nazwisko} nie podlega ocenie okresowej ({pracownik.rodzaj_zatrudnienia_opis}).",
            "art. 81 ust. 1 u.s.c.",
        )])
    bledy = []
    if pracownik.przelozony_id is None:
        bledy.append(Blad(
            "BRAK_PRZELOZONEGO", "Wskaż bezpośredniego przełożonego - to on dokonuje oceny.",
            "art. 81 ust. 1 u.s.c.; § 2 ust. 1 rozp.",
        ))
    if not pracownik.opis_stanowiska.strip():
        bledy.append(Blad(
            "BRAK_OPISU_STANOWISKA",
            "Uzupełnij opis stanowiska pracy - ocena dotyczy obowiązków wynikających z tego opisu.",
            "art. 81 ust. 3 u.s.c.",
        ))
    with transaction.atomic():
        if pracownik.oceny.exclude(etap=Etap.ZAKONCZONA.name).exists():
            bledy.append(Blad("OCENA_W_TOKU", "Ta osoba ma już ocenę w toku."))
        elif pracownik.oceny.exists():
            bledy.append(Blad(
                "KOLEJNY_CYKL", "Ta osoba ma zakończoną ocenę - rozpocznij kolejny cykl z poziomu tej oceny."
            ))
        if bledy:
            raise BladWalidacji(bledy)
        ocena = Ocena.utworz(
            oceniany=pracownik, oceniajacy=pracownik.przelozony,
            poczatek_cyklu=poczatek_cyklu or pracownik.data_zatrudnienia,
        )
        _zapisz_zdarzenie(ocena, uzytkownik, "rozpoczęcie cyklu oceny", data)
    return ocena


def rozpocznij_kolejny_cykl(ocena: Ocena, uzytkownik, *, data: date | None = None) -> Ocena:
    """Kolejny cykl po zakończonej ocenie. Początkiem jest dzień sporządzenia tej oceny (§ 7 rozp.)."""
    data = data or dzis()
    with transaction.atomic():
        biezaca = Ocena.objects.select_for_update().select_related("oceniany").get(pk=ocena.pk)
        _wymagaj_roli(uzytkownik, biezaca, Rola.ZARZADZAJACY)
        proces = biezaca.proces()
        if proces.etap != Etap.ZAKONCZONA or proces.data_sporzadzenia is None:
            raise BladEtapu("Kolejny cykl można rozpocząć po zakończeniu bieżącej oceny.")
        if Ocena.objects.filter(poprzednia=biezaca).exists():
            raise BladWalidacji([Blad("KOLEJNY_CYKL_ISTNIEJE", "Kolejny cykl po tej ocenie został już rozpoczęty.")])
        if biezaca.sprzeciwy.filter(rozstrzygniecie="").exists():
            raise BladWalidacji([Blad(
                "SPRZECIW_W_TOKU", "Najpierw trzeba rozpatrzyć sprzeciw od tej oceny.", "art. 83 ust. 3 u.s.c."
            )])
        nowa = Ocena.utworz(
            oceniany=biezaca.oceniany,
            oceniajacy=biezaca.oceniany.przelozony or biezaca.oceniajacy,
            poczatek_cyklu=proces.data_sporzadzenia,
            poprzednia=biezaca,
        )
        _zapisz_zdarzenie(biezaca, uzytkownik, "rozpoczęcie kolejnego cyklu", data)
        _zapisz_zdarzenie(nowa, uzytkownik, "rozpoczęcie cyklu oceny", data)
    return nowa


# --- część I: kryteria ---

def wyznacz_kryteria(ocena: Ocena, uzytkownik, *, kryteria_dodatkowe, termin: date, data: date | None = None) -> None:
    data = data or dzis()
    with _czynnosc(ocena, uzytkownik, Rola.OCENIAJACY, "wyznaczenie kryteriów", data) as (_, proces):
        proces.wyznacz_kryteria(Rola.OCENIAJACY, list(kryteria_dodatkowe), termin, data)


def potwierdz_kryteria(ocena: Ocena, uzytkownik, *, data: date | None = None) -> None:
    data = data or dzis()
    with _czynnosc(ocena, uzytkownik, Rola.OCENIANY, "potwierdzenie kryteriów", data) as (_, proces):
        proces.potwierdz_kryteria(Rola.OCENIANY, data)


# --- okres oceny: notatki, terminy, nieobecności ---

def dodaj_notatke(
    ocena: Ocena, uzytkownik, *, tresc: str, rodzaj: str = OBSERWACJA, data: date | None = None
) -> None:
    """Notatka oceniającego: obserwacja albo dodatkowe osiągnięcie pracownika. Treść nie trafia do dziennika."""
    data = data or dzis()
    with _czynnosc(ocena, uzytkownik, Rola.OCENIAJACY, CZYNNOSC_NOTATKA, data) as (_, proces):
        proces.dodaj_notatke(Rola.OCENIAJACY, tresc, data, rodzaj=rodzaj)


def zapisz_egzamin(
    ocena: Ocena,
    uzytkownik,
    *,
    punkty: str,
    punkty_max: str = "",
    poprawkowy: bool = False,
    data_egzaminu: date | None = None,
    uwagi: str = "",
    data: date | None = None,
) -> None:
    """Wynik egzaminu ze służby przygotowawczej w notatkach oceniającego - tylko przy pierwszej ocenie pracownika.

    Egzamin kończy służbę przygotowawczą na początku pracy w służbie cywilnej (art. 36 ust. 5 u.s.c.), więc przy
    kolejnych ocenach nie ma czego wpisywać. Wynik nie trafia do dziennika ani do arkusza.
    """
    data = data or dzis()
    with _czynnosc(ocena, uzytkownik, Rola.OCENIAJACY, CZYNNOSC_NOTATKA, data) as (biezaca, proces):
        if not biezaca.pierwsza:
            raise BladWalidacji([Blad(
                "EGZAMIN_TYLKO_PRZY_PIERWSZEJ_OCENIE",
                "Wynik egzaminu ze służby przygotowawczej zapisuje się przy pierwszej ocenie pracownika.",
                "art. 36 ust. 5 u.s.c.",
            )])
        proces.zapisz_egzamin(
            Rola.OCENIAJACY, punkty=punkty, punkty_max=punkty_max, poprawkowy=poprawkowy,
            data_egzaminu=data_egzaminu, uwagi=uwagi, data=data,
        )


def zmien_termin(ocena: Ocena, uzytkownik, *, nowy_termin: date, przyczyna: str, data: date | None = None) -> None:
    data = data or dzis()
    opis = f"nowy termin: {nowy_termin:%d.%m.%Y}"
    with _czynnosc(ocena, uzytkownik, Rola.OCENIAJACY, "zmiana terminu oceny", data, opis) as (biezaca, proces):
        proces.zmien_termin(Rola.OCENIAJACY, nowy_termin, data, przyczyna, _data_ostatniej_oceny(biezaca))


def zloz_wniosek_o_zmiane_terminu(
    ocena: Ocena, uzytkownik, *, uzasadnienie: str = "", data: date | None = None
) -> WniosekOTermin:
    data = data or dzis()
    with _czynnosc(ocena, uzytkownik, Rola.OCENIANY, "wniosek o zmianę terminu oceny", data) as (biezaca, proces):
        if biezaca.wnioski_o_termin.filter(status=WniosekOTermin.OCZEKUJE).exists():
            raise BladWalidacji([Blad("WNIOSEK_W_TOKU", "Poprzedni wniosek o zmianę terminu czeka na rozpatrzenie.")])
        proces.zloz_wniosek_o_zmiane_terminu(Rola.OCENIANY, data, _data_ostatniej_oceny(biezaca))
        wniosek = WniosekOTermin.objects.create(ocena=biezaca, data=data, uzasadnienie=uzasadnienie.strip())
    return wniosek


def rozpatrz_wniosek_o_zmiane_terminu(
    ocena: Ocena, uzytkownik, *, uwzglednic: bool, nowy_termin: date | None = None, data: date | None = None
) -> None:
    data = data or dzis()
    nazwa = "rozpatrzenie wniosku o zmianę terminu"
    opis = "uwzględniony" if uwzglednic else "odrzucony"
    with _czynnosc(ocena, uzytkownik, Rola.OCENIAJACY, nazwa, data, opis) as (biezaca, proces):
        wniosek = biezaca.wnioski_o_termin.filter(status=WniosekOTermin.OCZEKUJE).order_by("pk").first()
        if wniosek is None:
            raise BladWalidacji([Blad("BRAK_WNIOSKU", "Nie ma wniosku o zmianę terminu do rozpatrzenia.")])
        if uwzglednic:
            if nowy_termin is None:
                raise BladWalidacji([Blad("BRAK_NOWEGO_TERMINU", "Podaj nowy termin sporządzenia oceny.", "§ 8 rozp.")])
            proces.zmien_termin(
                Rola.OCENIAJACY, nowy_termin, data, "wniosek ocenianego o zmianę terminu przeprowadzenia oceny",
                _data_ostatniej_oceny(biezaca),
            )
        wniosek.status = WniosekOTermin.UWZGLEDNIONY if uwzglednic else WniosekOTermin.ODRZUCONY
        wniosek.data_rozpatrzenia = data
        wniosek.save()


def zmien_oceniajacego(ocena: Ocena, uzytkownik, *, nowy_oceniajacy: Pracownik, data: date | None = None) -> None:
    """Zmiana na stanowisku oceniającego: kryteria i termin zostają bez zmian (§ 9 ust. 3 rozp.)."""
    data = data or dzis()
    opis = f"nowy oceniający: {nowy_oceniajacy.imie_i_nazwisko}"
    with _czynnosc(ocena, uzytkownik, Rola.ZARZADZAJACY, "zmiana oceniającego", data, opis) as (biezaca, proces):
        if nowy_oceniajacy.pk == biezaca.oceniany_id:
            raise BladWalidacji([Blad("OCENIAJACY_TO_OCENIANY", "Oceniany nie może oceniać sam siebie.")])
        proces.zmien_oceniajacego(Rola.ZARZADZAJACY, data)
        biezaca.oceniajacy = nowy_oceniajacy


def dodaj_nieobecnosc(
    pracownik: Pracownik, uzytkownik, *, od: date, do: date, usprawiedliwiona: bool = True
) -> Nieobecnosc:
    """Nieobecność wprowadza komórka kadr. Termin oceny przelicza rdzeń przy każdym wyświetleniu (art. 81 ust. 7)."""
    _wymagaj_kadr(uzytkownik, "wprowadzenie nieobecności")
    if do < od:
        raise BladWalidacji([Blad(
            "BLEDNY_OKRES_NIEOBECNOSCI", "Koniec nieobecności nie może być wcześniejszy niż jej początek."
        )])
    return Nieobecnosc.objects.create(pracownik=pracownik, od=od, do=do, usprawiedliwiona=usprawiedliwiona)


def zapisz_ustalenia_monitoringu(
    uzytkownik,
    *,
    podstawa: str,
    cele: str,
    zakres: str,
    sposob: str,
    data_poinformowania: date | None,
    wlaczona: bool,
    data: date | None = None,
) -> UstaleniaMonitoringu:
    """Ustalenia pracodawcy dotyczące danych z EZD RP. Integrację da się włączyć dopiero wtedy, gdy rdzeń nie
    widzi przeszkód z Kodeksu pracy (art. 22[2] § 6-7 w zw. z art. 22[3] § 3-4); robocze ustalenia można
    zapisywać przy wyłączonej integracji."""
    _wymagaj_kadr(uzytkownik, "ustalenia dotyczące danych z EZD RP")
    data = data or dzis()
    dane = {
        "podstawa": str(podstawa or "").strip(), "cele": str(cele or "").strip(),
        "zakres": str(zakres or "").strip(), "sposob": str(sposob or "").strip(),
        "data_poinformowania": data_poinformowania,
    }
    if wlaczona:
        przeszkody = bledy_uruchomienia_monitoringu(UstaleniaRdzenia(**dane), data)
        if przeszkody:
            raise BladWalidacji(przeszkody)
    with transaction.atomic():
        zapis = UstaleniaMonitoringu.objects.select_for_update().order_by("pk").first() or UstaleniaMonitoringu()
        for pole, wartosc in dane.items():
            setattr(zapis, pole, wartosc)
        zapis.integracja_wlaczona = bool(wlaczona)
        zapis.save()
    return zapis


# --- część II i III: ocena ---

def sporzadz_ocene(
    ocena: Ocena,
    uzytkownik,
    *,
    data_rozmowy: date,
    oceny: dict[str, int],
    wnioski_iprz: str,
    uzasadnienie: str = "",
    wniosek_o_stopien: str | None = None,
    umotywowanie_wniosku: str = "",
    posiadany_stopien: int | None = None,
    poprzednia_reczna: dict | None = None,
    data: date | None = None,
) -> None:
    """Sporządzenie oceny. Posiadany stopień służbowy, jeśli go nie podano, pochodzi z danych kadrowych."""
    data = data or dzis()
    with _czynnosc(ocena, uzytkownik, Rola.OCENIAJACY, "sporządzenie oceny", data) as (biezaca, proces):
        if posiadany_stopien is None and proces.urzednik:
            posiadany_stopien = biezaca.oceniany.stopien_sluzbowy
        proces.sporzadz_ocene(
            Rola.OCENIAJACY,
            data=data,
            data_rozmowy=data_rozmowy,
            oceny=dict(oceny),
            wnioski_iprz=wnioski_iprz,
            uzasadnienie=uzasadnienie,
            wniosek_o_stopien=wniosek_o_stopien,
            umotywowanie_wniosku=umotywowanie_wniosku,
            posiadany_stopien=posiadany_stopien,
        )
        biezaca.szkic = None
        if poprzednia_reczna is not None:
            biezaca.poprzednia_reczna = poprzednia_reczna


def zapisz_szkic(ocena: Ocena, uzytkownik, szkic: dict) -> None:
    """Roboczy zapis części II. Nie zmienia procesu i nie trafia do dziennika - szkic widzi tylko oceniający."""
    with transaction.atomic():
        biezaca = Ocena.objects.select_for_update().get(pk=ocena.pk)
        _wymagaj_roli(uzytkownik, biezaca, Rola.OCENIAJACY)
        if biezaca.etap != Etap.OCENIANIE.name:
            raise BladEtapu("Szkic oceny można zapisać tylko na etapie dokonywania oceny.")
        biezaca.szkic = szkic
        biezaca.save(update_fields=["szkic", "zmieniono"])
    ocena.refresh_from_db()


def projekt_uzasadnienia(ocena: Ocena, uzytkownik, *, redaktor, data: date | None = None) -> dict:
    """Projekt uzasadnienia ułożony przez model językowy z notatek oceniającego (HR Copilot).

    `redaktor(notatki, osoby)` zwraca słownik z kluczem „projekt” (wynik rdzenia) albo „blad” (komunikat) -
    w aplikacji jest nim `copilot.projekt_uzasadnienia`. Model dostaje wyłącznie notatki: bez ocen cząstkowych,
    szkicu, wyniku i danych z EZD RP. Projekt nie jest zapisywany - do formularza przenosi go oceniający.
    W dzienniku zostaje ślad użycia funkcji, bez treści. Model pracuje kilka-kilkanaście sekund, dlatego
    wywołanie nie jest objęte transakcją.
    """
    data = data or dzis()
    biezaca = Ocena.objects.select_related("oceniany").get(pk=ocena.pk)
    _wymagaj_roli(uzytkownik, biezaca, Rola.OCENIAJACY)
    if biezaca.etap != Etap.OCENIANIE.name:
        raise BladEtapu("Projekt uzasadnienia można przygotować tylko na etapie dokonywania oceny.")
    notatki = [notatka.tresc for notatka in sorted(biezaca.proces().notatki, key=lambda notatka: notatka.data)]
    oceniany = biezaca.oceniany
    wynik = redaktor(notatki, [oceniany.imie_i_nazwisko, oceniany.imie, oceniany.nazwisko])
    projekt = wynik.get("projekt")
    if projekt is not None and not projekt.odmowa:
        _zapisz_zdarzenie(
            biezaca, uzytkownik, CZYNNOSC_PROJEKT_AI, data, "tekst do decyzji oceniającego - nie jest zapisywany"
        )
    return wynik


def sugestia_ocen(ocena: Ocena, uzytkownik, *, doradca, data: date | None = None) -> dict:
    """Sugestia ocen cząstkowych przygotowana przez model językowy - funkcja wysokiego ryzyka (zał. III pkt 4
    lit. b AI Act), którą włącza tylko decyzja urzędu.

    `doradca(notatki, kryteria, osoby)` zwraca słownik z kluczem „sugestia” (wynik rdzenia) albo „blad”
    (komunikat) - w aplikacji jest nim `copilot.sugestia_ocen`. Model dostaje wyłącznie to, co oceniający sam
    zapisał: obserwacje, dodatkowe osiągnięcia i wynik egzaminu - oraz nazwy kryteriów arkusza. Nie dostaje
    danych z EZD RP ani szkicu oceny. Sugestia nie jest zapisywana i nie zmienia formularza: oceny wpisuje
    oceniający. W dzienniku zostaje ślad użycia funkcji, bez treści. Model pracuje kilkanaście sekund,
    dlatego wywołanie nie jest objęte transakcją.
    """
    data = data or dzis()
    biezaca = Ocena.objects.select_related("oceniany").get(pk=ocena.pk)
    _wymagaj_roli(uzytkownik, biezaca, Rola.OCENIAJACY)
    if biezaca.etap != Etap.OCENIANIE.name:
        raise BladEtapu("Sugestię ocen cząstkowych można przygotować tylko na etapie dokonywania oceny.")
    proces = biezaca.proces()
    notatki = [
        f"Dodatkowe osiągnięcie: {notatka.tresc}" if notatka.rodzaj == OSIAGNIECIE else notatka.tresc
        for notatka in sorted(proces.notatki, key=lambda notatka: notatka.data)
    ]
    oceniany = biezaca.oceniany
    wynik = doradca(notatki, nazwy_kryteriow(proces), [oceniany.imie_i_nazwisko, oceniany.imie, oceniany.nazwisko])
    sugestia = wynik.get("sugestia")
    if sugestia is not None and not sugestia.odmowa:
        _zapisz_zdarzenie(
            biezaca, uzytkownik, CZYNNOSC_SUGESTIA_AI, data,
            "podpowiedź dla oceniającego - nie jest zapisywana; oceny wpisuje oceniający",
        )
    return wynik


def potwierdz_zapoznanie(ocena: Ocena, uzytkownik, *, data: date | None = None) -> None:
    data = data or dzis()
    with _czynnosc(ocena, uzytkownik, Rola.OCENIANY, "potwierdzenie zapoznania z oceną", data) as (_, proces):
        proces.potwierdz_zapoznanie(Rola.OCENIANY, data)


def stwierdz_fikcje_zapoznania(ocena: Ocena, uzytkownik, *, rola: Rola, data: date | None = None) -> None:
    """Fikcję stwierdza strona procesu działająca we wskazanej roli (oceniający, oceniany albo kadry)."""
    data = data or dzis()
    opis = f"stwierdził: {Rola(rola).value}"
    with _czynnosc(ocena, uzytkownik, rola, "stwierdzenie fikcji zapoznania z oceną", data, opis) as (_, proces):
        proces.stwierdz_fikcje_zapoznania(rola, data)


# --- sprzeciw (art. 83 u.s.c.) ---

def wnies_sprzeciw(ocena: Ocena, uzytkownik, *, tresc: str, data: date | None = None) -> Sprzeciw:
    """Rejestruje sprzeciw ocenianego. Sprzeciw wniesiony po terminie jest przyjmowany z oznaczeniem -
    o skutkach uchybienia terminu rozstrzyga dyrektor generalny, nie system."""
    data = data or dzis()
    with transaction.atomic():
        biezaca = Ocena.objects.select_for_update().get(pk=ocena.pk)
        _wymagaj_roli(uzytkownik, biezaca, Rola.OCENIANY)
        proces = biezaca.proces()
        if proces.etap != Etap.ZAKONCZONA or proces.data_zapoznania_z_ocena is None:
            raise BladEtapu("Sprzeciw można wnieść po zapoznaniu się z oceną.")
        if not str(tresc or "").strip():
            raise BladWalidacji([Blad("PUSTY_SPRZECIW", "Wpisz treść sprzeciwu.", "art. 83 ust. 1 u.s.c.")])
        if biezaca.sprzeciwy.filter(rozstrzygniecie="").exists():
            raise BladWalidacji([Blad(
                "SPRZECIW_W_TOKU", "Sprzeciw od tej oceny został już wniesiony i czeka na rozpatrzenie.",
                "art. 83 ust. 3 u.s.c.",
            )])
        if biezaca.sprzeciwy.filter(data_wniesienia__gte=proces.data_zapoznania_z_ocena).exists():
            raise BladWalidacji([Blad(
                "SPRZECIW_ROZPATRZONY",
                "Sprzeciw od tej oceny został już rozpatrzony. Ponowny sprzeciw przysługuje od oceny sporządzonej "
                "po raz drugi.",
                "art. 83 ust. 4 u.s.c.",
            )])
        termin = terminy.termin_sprzeciwu(proces.data_zapoznania_z_ocena)
        sprzeciw = Sprzeciw.objects.create(
            ocena=biezaca, data_wniesienia=data, tresc=str(tresc).strip(), po_terminie=data > termin
        )
        opis = "po terminie" if sprzeciw.po_terminie else ""
        _zapisz_zdarzenie(biezaca, uzytkownik, "wniesienie sprzeciwu", data, opis)
    return sprzeciw


def rozpatrz_sprzeciw(
    ocena: Ocena,
    uzytkownik,
    *,
    rozstrzygniecie: str,
    uzasadnienie: str = "",
    nowe_oceny: dict[str, int] | None = None,
    data: date | None = None,
) -> None:
    """Rozstrzygnięcie dyrektora generalnego wprowadza komórka kadr (model BPMN KPRM)."""
    if rozstrzygniecie not in Sprzeciw.NAZWY_ROZSTRZYGNIEC:
        raise ValueError(f"Nieznane rozstrzygnięcie sprzeciwu: {rozstrzygniecie!r}")
    data = data or dzis()
    with transaction.atomic():
        biezaca = Ocena.objects.select_for_update().get(pk=ocena.pk)
        _wymagaj_roli(uzytkownik, biezaca, Rola.ZARZADZAJACY)
        sprzeciw = biezaca.sprzeciwy.filter(rozstrzygniecie="").order_by("pk").first()
        if sprzeciw is None:
            raise BladWalidacji([Blad("BRAK_SPRZECIWU", "Nie ma sprzeciwu do rozpatrzenia.")])
        if rozstrzygniecie in UWZGLEDNIENIA_SPRZECIWU:
            proces = biezaca.proces()
            proces.uwzglednij_sprzeciw(Rola.ZARZADZAJACY, tryb=rozstrzygniecie, data=data, nowe_oceny=nowe_oceny)
            biezaca.zapisz_proces(proces)
        sprzeciw.rozstrzygniecie = rozstrzygniecie
        sprzeciw.data_rozstrzygniecia = data
        sprzeciw.uzasadnienie = str(uzasadnienie or "").strip()
        sprzeciw.save()
        _zapisz_zdarzenie(biezaca, uzytkownik, "rozpatrzenie sprzeciwu", data, sprzeciw.rozstrzygniecie_opis)
    ocena.refresh_from_db()
