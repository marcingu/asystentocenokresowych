"""Dane karty oceny do wyświetlenia: etapy, terminy, formularze i podgląd wyniku.

Wszystko, co jest tu liczone (terminy, średnia, poziom, braki formularza), pochodzi z funkcji rdzenia.
"""

from __future__ import annotations

from datetime import date

from django.conf import settings

from asystent_ocen import terminy
from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.kryteria import kryteria_dodatkowe_do_wyboru, kryteria_obowiazkowe
from asystent_ocen.przebieg import EGZAMIN, OBSERWACJA, OSIAGNIECIE, Etap, ProcesOceny, Rola
from asystent_ocen.stopnie import kolejny_stopien_slownie, komunikat_dla_stopnia
from asystent_ocen.walidacja import Formularz, bledy_przed_zatwierdzeniem, pouczenie_o_sprzeciwie
from asystent_ocen.wynik import NEGATYWNA, bledy_ocen_czastkowych, formatuj_srednia, oblicz_wynik

from . import drukowanie
from .formularze import nazwy_kryteriow
from .kontekst_ezd import karta_kontekstu
from .radar import radar_oceny
from .models import Ocena, WniosekOTermin
from .uprawnienia import role_uzytkownika
from .uslugi import CZYNNOSC_NOTATKA, CZYNNOSCI_AI, CZYNNOSCI_AI_WYSOKIEGO_RYZYKA
from .zadania import opis_dni_do_terminu, opisy_skutkow, zadania_oceny


def _stan_terminu(termin: date, dzien: date) -> str:
    dni = (termin - dzien).days
    if dni < 0:
        return "po_terminie"
    return "pilne" if dni <= settings.ASYSTENT_DNI_PILNE else "w_terminie"


def _opis_stanu_terminu(stan: str, termin: date | None, dzien: date) -> str:
    """Stan terminu słowami. Wiersz terminu ma kolorowe obramowanie, a kolor nie może być jedynym nośnikiem
    informacji (WCAG 2.1, kryterium 1.4.1). Termin czysto informacyjny nie ma stanu."""
    if stan == "wykonane":
        return "wykonano"
    if stan == "informacja" or termin is None:
        return ""
    return opis_dni_do_terminu((termin - dzien).days)


def os_etapow(etap: Etap) -> list[dict]:
    etapy = list(Etap)
    biezacy = etapy.index(etap)
    return [
        {
            "nazwa": krok.value,
            "stan": "zrobiony" if numer < biezacy or etap == Etap.ZAKONCZONA else "biezacy" if numer == biezacy else "przyszly",
        }
        for numer, krok in enumerate(etapy)
    ]


def termin_ustawowy(ocena: Ocena, proces: ProcesOceny, nieobecnosci: list) -> dict:
    """Termin, w którym ocena ma być sporządzona z mocy ustawy - z przedłużeniem o długie nieobecności."""
    if ocena.po_negatywnej and ocena.poprzednia.data_zapoznania:
        zapoznanie = ocena.poprzednia.data_zapoznania
        termin = terminy.data_ponownej_oceny_po_negatywnej(zapoznanie, nieobecnosci)
        bez_nieobecnosci = terminy.data_ponownej_oceny_po_negatywnej(zapoznanie)
        podstawa = "art. 81 ust. 9 u.s.c."
        nazwa = "Ponowna ocena po ocenie negatywnej - termin ustawowy"
    else:
        termin = terminy.termin_oceny(proces.poczatek_cyklu, nieobecnosci)
        bez_nieobecnosci = terminy.termin_oceny(proces.poczatek_cyklu)
        podstawa = "art. 81 ust. 4 u.s.c."
        nazwa = "Sporządzenie oceny - termin ustawowy"
    uwaga = ""
    if termin > bez_nieobecnosci:
        podstawa += "; art. 81 ust. 7 u.s.c."
        uwaga = (
            f"Termin przedłużony z {bez_nieobecnosci:%d.%m.%Y} o usprawiedliwioną nieobecność ocenianego "
            "trwającą dłużej niż miesiąc."
        )
    return {"nazwa": nazwa, "data": termin, "podstawa": podstawa, "uwaga": uwaga, "stan": "informacja"}


def wiersze_terminow(ocena: Ocena, proces: ProcesOceny, nieobecnosci: list, dzien: date) -> list[dict]:
    wiersze: list[dict] = []

    def dodaj(nazwa: str, data: date | None, podstawa: str = "", uwaga: str = "", stan: str = "informacja") -> None:
        wiersze.append({
            "nazwa": nazwa, "data": data, "podstawa": podstawa, "uwaga": uwaga, "stan": stan,
            "stan_opis": _opis_stanu_terminu(stan, data, dzien),
        })

    po_negatywnej = ocena.po_negatywnej
    if proces.data_zapoznania_z_kryteriami:
        dodaj("Zapoznanie z kryteriami oceny", proces.data_zapoznania_z_kryteriami, "§ 6 ust. 2 rozp.", stan="wykonane")
    else:
        termin = terminy.termin_wyznaczenia_kryteriow(proces.poczatek_cyklu, po_negatywnej)
        dodaj(
            "Rozmowa i zapoznanie z kryteriami - najpóźniej", termin, f"§ 7 pkt {2 if po_negatywnej else 1} rozp.",
            stan=_stan_terminu(termin, dzien),
        )
    if proces.data_sporzadzenia:
        dodaj("Sporządzenie oceny", proces.data_sporzadzenia, "§ 11 rozp.", stan="wykonane")
    else:
        ustawowy = termin_ustawowy(ocena, proces, nieobecnosci)
        if proces.termin:
            uwaga = ""
            if ustawowy["data"] > proces.termin and ustawowy["uwaga"]:
                uwaga = "Termin ustawowy jest późniejszy - oceniający może zmienić termin (art. 81 ust. 8 u.s.c.)."
            dodaj(
                "Sporządzenie oceny - termin z części I arkusza", proces.termin, "§ 5 ust. 3 rozp.", uwaga,
                _stan_terminu(proces.termin, dzien),
            )
        wiersze.append(ustawowy)
    if proces.data_zapoznania_z_ocena:
        uwaga = ""
        if proces.zapoznanie_fikcyjne:
            uwaga = f"Stwierdzono fikcję zapoznania z oceną (stwierdził: {Rola(proces.fikcje_stwierdzil).value})."
        dodaj("Zapoznanie z oceną", proces.data_zapoznania_z_ocena, "§ 12 ust. 1 rozp.", uwaga, "wykonane")
        sprzeciwy = list(ocena.sprzeciwy.all())
        w_toku = [sprzeciw for sprzeciw in sprzeciwy if not sprzeciw.rozpatrzony]
        if w_toku:
            termin = terminy.termin_rozpatrzenia_sprzeciwu(w_toku[0].data_wniesienia)
            dodaj("Rozpatrzenie sprzeciwu - najpóźniej", termin, "art. 83 ust. 3 u.s.c.", stan=_stan_terminu(termin, dzien))
        elif not sprzeciwy:
            termin = terminy.termin_sprzeciwu(proces.data_zapoznania_z_ocena)
            minal = termin < dzien
            dodaj(
                "Sprzeciw od oceny - najpóźniej", termin, "art. 83 ust. 1 u.s.c.",
                "Termin upłynął." if minal else "", "informacja" if minal else _stan_terminu(termin, dzien),
            )
    return wiersze


def formularz_kryteriow(proces: ProcesOceny, ustawowy: date) -> dict:
    przepisy = wczytaj_przepisy()
    limit = przepisy.max_kryteriow_dodatkowych
    wybrane = (list(proces.kryteria_dodatkowe) + [""] * limit)[:limit]
    opcje = kryteria_dodatkowe_do_wyboru(proces.arkusz)
    return {
        "pola": [{"numer": numer + 1, "wybrane": nazwa, "opcje": opcje} for numer, nazwa in enumerate(wybrane)],
        "limit": limit,
        "termin": (proces.termin or ustawowy).isoformat(),
        "termin_ustawowy": ustawowy,
    }


def skala_ocen() -> list[dict]:
    """Skala ocen cząstkowych z nazwami poziomów (§ 11 ust. 1 pkt 1 rozp.) - pozycjami, jak na arkuszu."""
    przepisy = wczytaj_przepisy()
    return [{"punkty": punkty, "nazwa": poziom.nazwa} for punkty, poziom in zip(przepisy.skala, przepisy.poziomy)]


def podglad_wyniku(proces: ProcesOceny, oceny: dict[str, int]) -> dict | None:
    """Wynik wyliczony przez rdzeń dla kompletu poprawnych ocen cząstkowych; inaczej None."""
    if not oceny or bledy_ocen_czastkowych(proces.arkusz, proces.kryteria_dodatkowe, oceny):
        return None
    wynik = oblicz_wynik(oceny)
    return {"srednia": formatuj_srednia(wynik.srednia), "poziom": wynik.poziom, "ocena": wynik.ocena}


def formularz_oceny(ocena: Ocena, proces: ProcesOceny, dzien: date) -> dict:
    """Formularz części II i III wypełniony szkicem oceniającego, z podglądem wyniku i listą braków."""
    szkic = ocena.szkic or {}
    oceny = {nazwa: wartosc for nazwa, wartosc in (szkic.get("oceny") or {}).items() if isinstance(wartosc, int)}
    obowiazkowe = set(kryteria_obowiazkowe(proces.arkusz))
    stopien = ocena.oceniany.stopien_sluzbowy if proces.urzednik else None
    podglad = podglad_wyniku(proces, oceny)
    braki = []
    if szkic:
        braki = bledy_przed_zatwierdzeniem(Formularz(
            arkusz=proces.arkusz,
            urzednik=proces.urzednik,
            oceny=oceny,
            kryteria_dodatkowe=list(proces.kryteria_dodatkowe),
            uzasadnienie=szkic.get("uzasadnienie", ""),
            wnioski_iprz=szkic.get("wnioski_iprz", ""),
            wniosek_o_stopien=szkic.get("wniosek_o_stopien"),
            umotywowanie_wniosku=szkic.get("umotywowanie_wniosku", ""),
            posiadany_stopien=stopien,
        ))
    z_systemu = drukowanie.poprzednia_ocena(ocena) if ocena.poprzednia_id else None
    komunikat_stopnia = komunikat_dla_stopnia(stopien) if stopien else None
    return {
        "skala": skala_ocen(),
        "wiersze": [
            {"numer": numer, "nazwa": nazwa, "obowiazkowe": nazwa in obowiazkowe, "wartosc": oceny.get(nazwa)}
            for numer, nazwa in enumerate(nazwy_kryteriow(proces))
        ],
        "data_rozmowy": szkic.get("data_rozmowy") or "",
        "uzasadnienie": szkic.get("uzasadnienie", ""),
        "wnioski_iprz": szkic.get("wnioski_iprz", ""),
        "wniosek_o_stopien": szkic.get("wniosek_o_stopien") or "",
        "umotywowanie_wniosku": szkic.get("umotywowanie_wniosku", ""),
        "urzednik": proces.urzednik,
        "posiadany_stopien": stopien,
        "komunikat_stopnia": komunikat_stopnia,
        "kolejny_stopien": kolejny_stopien_slownie(stopien) if stopien and not komunikat_stopnia else "",
        "wniosek_zablokowany": bool(komunikat_stopnia) or bool(podglad and podglad["ocena"] == NEGATYWNA),
        "poprzednia_z_systemu": z_systemu,
        "poprzednia_reczna": szkic.get("poprzednia") or ocena.poprzednia_reczna or {},
        "poziomy": [poziom.nazwa for poziom in wczytaj_przepisy().poziomy],
        "podglad": podglad,
        "braki": braki,
        "ma_szkic": bool(szkic),
        "dzis": dzien.isoformat(),
    }


def wynik_do_pokazania(proces: ProcesOceny) -> dict | None:
    if proces.wynik is None:
        return None
    formularz = proces.formularz
    obowiazkowe = set(kryteria_obowiazkowe(proces.arkusz))
    nazwy_skali = {pozycja["punkty"]: pozycja["nazwa"] for pozycja in skala_ocen()}
    return {
        "srednia": formatuj_srednia(proces.wynik.srednia),
        "poziom": proces.wynik.poziom,
        "ocena": proces.wynik.ocena,
        "negatywna": proces.wynik.ocena == NEGATYWNA,
        "wiersze": [
            {
                "nazwa": nazwa, "obowiazkowe": nazwa in obowiazkowe, "punkty": proces.oceny.get(nazwa),
                "opis": nazwy_skali.get(proces.oceny.get(nazwa), ""),
            }
            for nazwa in nazwy_kryteriow(proces)
        ],
        "uzasadnienie": formularz.uzasadnienie if formularz else "",
        "wnioski_iprz": formularz.wnioski_iprz if formularz else "",
        "wniosek_o_stopien": formularz.wniosek_o_stopien if formularz else "",
        "umotywowanie_wniosku": formularz.umotywowanie_wniosku if formularz else "",
    }


def uzycie_ai(ocena: Ocena) -> dict | None:
    """Zestawienie użycia modelu językowego przy pracy nad oceną - informacja dla stron po sporządzeniu oceny
    (art. 26 ust. 11 AI Act: osobę, wobec której wykorzystano system wysokiego ryzyka, informuje się o tym).

    None, gdy modelu nie użyto. Przy funkcji wysokiego ryzyka (sugestia ocen cząstkowych, propozycja kierunków
    do IPRZ) dołącza informację o decyzji urzędu według obecnego stanu rejestru funkcji AI.
    """
    wpisy: dict[str, dict] = {}
    for zdarzenie in ocena.zdarzenia.all():
        if zdarzenie.czynnosc not in CZYNNOSCI_AI:
            continue
        wpis = wpisy.setdefault(zdarzenie.czynnosc, {
            "czynnosc": zdarzenie.czynnosc,
            "liczba": 0,
            "ostatnio": zdarzenie.data,
            "wysokie_ryzyko": zdarzenie.czynnosc in CZYNNOSCI_AI_WYSOKIEGO_RYZYKA,
        })
        wpis["liczba"] += 1
        wpis["ostatnio"] = max(wpis["ostatnio"], zdarzenie.data)
    if not wpisy:
        return None
    for czynnosc, kod in CZYNNOSCI_AI_WYSOKIEGO_RYZYKA.items():
        if czynnosc in wpisy:
            from . import copilot  # import przy użyciu - moduł AI nie jest potrzebny do pracy reszty systemu

            wpisy[czynnosc]["nota"] = copilot.nota_ai(kod)
    return {"wpisy": list(wpisy.values())}


def kontekst_karty(ocena: Ocena, uzytkownik, dzien: date) -> dict:
    proces = ocena.proces()
    role = role_uzytkownika(uzytkownik, ocena)
    nieobecnosci = [nieobecnosc.do_rdzenia() for nieobecnosc in ocena.oceniany.nieobecnosci.all()]
    oceniajacy = Rola.OCENIAJACY in role
    oceniany = Rola.OCENIANY in role
    kadry = Rola.ZARZADZAJACY in role
    etap = proces.etap
    sprzeciwy = list(ocena.sprzeciwy.all())
    sprzeciw_w_toku = next((sprzeciw for sprzeciw in sprzeciwy if not sprzeciw.rozpatrzony), None)
    wnioski = list(ocena.wnioski_o_termin.all())
    nastepna = Ocena.objects.filter(poprzednia=ocena).first()
    ustawowy = termin_ustawowy(ocena, proces, nieobecnosci)
    zakonczona = etap == Etap.ZAKONCZONA

    kontekst = {
        "ocena": ocena,
        "proces": proces,
        "etap": etap.name,
        "etap_opis": etap.value,
        "role_opis": ", ".join(sorted(rola.value for rola in role)),
        "jestem_oceniajacym": oceniajacy,
        "jestem_ocenianym": oceniany,
        "jestem_w_kadrach": kadry,
        "os_etapow": os_etapow(etap),
        "terminy": wiersze_terminow(ocena, proces, nieobecnosci, dzien),
        "zadania": zadania_oceny(ocena, role, dzien),
        "kryteria_obowiazkowe": kryteria_obowiazkowe(proces.arkusz),
        "kryteria_dodatkowe": list(proces.kryteria_dodatkowe),
        "kryteria_wyznaczone": proces.data_wyznaczenia_kryteriow is not None,
        "wynik": wynik_do_pokazania(proces),
        # Kadry i oceniający widzą wszystkie pisma w sprawie; oceniany - pisma skierowane do niego.
        "dokumenty": [
            dokument for dokument in proces.dokumenty
            if kadry or oceniajacy or (oceniany and dokument.adresat == Rola.OCENIANY)
        ],
        # Wpisy o notatkach widzi tylko oceniający - inni nie dowiadują się nawet, że notatki powstają.
        # Praca nad oceną jest niejawna do jej sporządzenia, więc ślad użycia asystenta AI strony widzą potem.
        "zdarzenia": [
            zdarzenie for zdarzenie in ocena.zdarzenia.all()
            if oceniajacy or not (
                zdarzenie.czynnosc == CZYNNOSC_NOTATKA
                or (zdarzenie.czynnosc in CZYNNOSCI_AI and etap == Etap.OCENIANIE)
            )
        ],
        "sprzeciwy": sprzeciwy,
        "sprzeciw_w_toku": sprzeciw_w_toku,
        "wnioski_o_termin": wnioski,
        "wniosek_oczekuje": any(wniosek.status == WniosekOTermin.OCZEKUJE for wniosek in wnioski),
        "nastepna": nastepna,
        "poprzednia": ocena.poprzednia,
        "nieobecnosci": list(ocena.oceniany.nieobecnosci.all()) if (kadry or oceniajacy) else [],
        "sa_terminy_do_kalendarza": bool(drukowanie.wydarzenia_kalendarza(ocena, role)),
        "dzis_iso": dzien.isoformat(),
    }
    # Formularze pojawiają się tylko u osoby, która na tym etapie ma coś do zrobienia.
    if oceniajacy and etap in (Etap.KRYTERIA_DO_WYZNACZENIA, Etap.KRYTERIA_DO_POTWIERDZENIA):
        kontekst["formularz_kryteriow"] = formularz_kryteriow(proces, ustawowy["data"])
    if oceniajacy and etap == Etap.OCENIANIE:
        from . import copilot  # import przy użyciu - moduł AI nie jest potrzebny do pracy reszty systemu

        kontekst["formularz_oceny"] = formularz_oceny(ocena, proces, dzien)
        kontekst["mozna_zmienic_termin"] = True
        kontekst["copilot"] = {
            "dostepny": copilot.redakcja_notatek_dostepna(),
            # funkcja wysokiego ryzyka - widoczna tylko wtedy, gdy włączyła ją decyzja urzędu
            "sugestie_dostepne": copilot.sugestie_ocen_dostepne(),
            "liczba_notatek": len(proces.notatki),
            "model": settings.ASYSTENT_MODEL,
            # informacja przy treściach wygenerowanych przez model: klasyfikacja funkcji i decyzja urzędu
            "nota_sugestii": copilot.nota_ai(copilot.FUNKCJA_PROPOZYCJI_OCENY),
            "nota_projektu": copilot.nota_ai(copilot.FUNKCJA_REDAKCJI),
            # wirtualny HR partner: pytania do rozmowy oceniającej, a po decyzji urzędu także kierunki do IPRZ
            "rozmowa_dostepna": copilot.pytania_do_rozmowy_dostepne(),
            "kierunki_dostepne": copilot.kierunki_iprz_dostepne(),
            "nota_rozmowy": copilot.nota_ai(copilot.FUNKCJA_PYTAN_DO_ROZMOWY),
            "nota_kierunkow": copilot.nota_ai(copilot.FUNKCJA_KIERUNKOW_IPRZ),
            # radar: pytania do kart obserwacji - funkcja wysokiego ryzyka, widoczna tylko po decyzji urzędu
            "radar_dostepny": copilot.pytania_radaru_dostepne(),
            "nota_radaru": copilot.nota_ai(copilot.FUNKCJA_RADARU),
        }
    if oceniajacy:
        # Notatki widzi wyłącznie oceniający (decyzja zespołu z 21.11.2026): obserwacje, dodatkowe osiągnięcia
        # pracownika i - przy pierwszej ocenie - wynik egzaminu ze służby przygotowawczej.
        notatki = sorted(proces.notatki, key=lambda notatka: notatka.data, reverse=True)
        kontekst["notatki"] = [notatka for notatka in notatki if notatka.rodzaj == OBSERWACJA]
        kontekst["osiagniecia"] = [notatka for notatka in notatki if notatka.rodzaj == OSIAGNIECIE]
        kontekst["egzamin"] = next((notatka for notatka in notatki if notatka.rodzaj == EGZAMIN), None)
        kontekst["mozna_dodac_notatke"] = not zakonczona
        kontekst["mozna_zapisac_egzamin"] = not zakonczona and ocena.pierwsza
    if oceniany and etap == Etap.KRYTERIA_DO_POTWIERDZENIA:
        kontekst["mozna_potwierdzic_kryteria"] = True
    if oceniany and etap == Etap.OCENIANIE and not kontekst["wniosek_oczekuje"]:
        kontekst["mozna_zlozyc_wniosek_o_termin"] = True
    if oceniany and etap == Etap.OCENA_DO_ZAPOZNANIA:
        kontekst["mozna_potwierdzic_zapoznanie"] = True
    if etap == Etap.OCENA_DO_ZAPOZNANIA and (oceniajacy or kadry or oceniany):
        kontekst["mozna_stwierdzic_fikcje"] = True
    if zakonczona:
        kontekst["pouczenie"] = pouczenie_o_sprzeciwie(
            proces.arkusz, urzad_ma_dyrektora_generalnego=not settings.ASYSTENT_BEZ_DYREKTORA_GENERALNEGO
        )
        if oceniany and not sprzeciwy and nastepna is None:
            kontekst["mozna_wniesc_sprzeciw"] = True
            kontekst["termin_sprzeciwu"] = terminy.termin_sprzeciwu(proces.data_zapoznania_z_ocena)
        if kadry and sprzeciw_w_toku:
            kontekst["mozna_rozpatrzyc_sprzeciw"] = True
            kontekst["skala"] = skala_ocen()
            kontekst["wiersze_zmiany"] = [
                {"numer": numer, "nazwa": nazwa, "wartosc": proces.oceny.get(nazwa)}
                for numer, nazwa in enumerate(nazwy_kryteriow(proces))
            ]
        if kadry and not sprzeciw_w_toku and nastepna is None:
            kontekst["mozna_rozpoczac_kolejny_cykl"] = True
        if kadry or oceniajacy:
            kontekst["skutki"] = opisy_skutkow(ocena)
    # Fakty z EZD RP są jawne dla obu stron oceny; komórka kadr ich nie potrzebuje (minimalizacja danych).
    if oceniajacy or oceniany:
        kontekst["karta_ezd"] = karta_kontekstu(ocena, dzien)
        # Radar Dobrostanu i Doceniania: te same karty obserwacji dla pracownika i przełożonego.
        kontekst["radar"] = radar_oceny(ocena, dzien)
    # Wynik widzą strony dopiero po sporządzeniu oceny; szkicu oceniającego nie widzi nikt poza nim.
    kontekst["widac_wynik"] = proces.wynik is not None
    # Przy sporządzonej ocenie strony widzą informację o użyciu modelu językowego; w trakcie oceniania praca
    # nad oceną jest niejawna, tak jak szkic.
    if kontekst["widac_wynik"] and etap != Etap.OCENIANIE:
        kontekst["uzycie_ai"] = uzycie_ai(ocena)
    return kontekst
