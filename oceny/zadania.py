"""Lista zadań użytkownika: co, w jakiej roli, do kiedy i na jakiej podstawie.

Zadanie wynika z etapu procesu oceny i roli użytkownika w tej ocenie. Terminy liczy rdzeń
(`asystent_ocen.terminy`) - tutaj nic nie jest liczone samodzielnie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.conf import settings

from asystent_ocen import terminy
from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.przebieg import Etap, Rola
from asystent_ocen.skutki import Skutek, skutki_oceny
from asystent_ocen.stopnie import OcenaHistoryczna
from asystent_ocen.wynik import NEGATYWNA

from .models import Ocena, WniosekOTermin
from .po_sprzeciwie import widok_statusu
from .uprawnienia import oceny_widoczne, role_uzytkownika


def opis_dni_do_terminu(dni: int) -> str:
    """Odległość od terminu słowami - stan terminu podaje tekst, a kolor tylko go wzmacnia (WCAG 2.1, 1.4.1)."""
    if dni < 0:
        return "1 dzień po terminie" if dni == -1 else f"{-dni} dni po terminie"
    if dni == 0:
        return "termin mija dzisiaj"
    return "został 1 dzień" if dni == 1 else f"zostało {dni} dni"


@dataclass(frozen=True)
class Zadanie:
    ocena: Ocena
    rola: Rola
    kod: str
    tytul: str
    termin: date | None
    podstawa: str
    dni: int | None  # ile dni zostało do terminu; ujemne - po terminie; None - bez terminu dziennego

    @property
    def stan(self) -> str:
        if self.dni is None:
            return "bez_terminu"
        if self.dni < 0:
            return "po_terminie"
        if self.dni <= settings.ASYSTENT_DNI_PILNE:
            return "pilne"
        return "w_terminie"

    @property
    def stan_opis(self) -> str:
        return "niezwłocznie" if self.dni is None else opis_dni_do_terminu(self.dni)


def _ma_nastepna(ocena: Ocena) -> bool:
    return Ocena.objects.filter(poprzednia=ocena).exists()


def zadania_oceny(ocena: Ocena, role: set[Rola], dzien: date) -> list[Zadanie]:
    """Zadania wynikające z jednej oceny dla osoby występującej w podanych rolach."""
    zadania: list[Zadanie] = []

    def dodaj(rola: Rola, kod: str, tytul: str, termin: date | None, podstawa: str) -> None:
        if rola in role:
            dni = (termin - dzien).days if termin is not None else None
            zadania.append(Zadanie(ocena, rola, kod, tytul, termin, podstawa, dni))

    etap = ocena.etap_rdzenia
    po_negatywnej = ocena.po_negatywnej
    if etap == Etap.KRYTERIA_DO_WYZNACZENIA:
        dodaj(
            Rola.OCENIAJACY, "WYZNACZ_KRYTERIA", "Przeprowadź rozmowę i wyznacz kryteria oceny",
            terminy.termin_wyznaczenia_kryteriow(ocena.poczatek_cyklu, po_negatywnej),
            f"§ 5 i § 7 pkt {2 if po_negatywnej else 1} rozp.",
        )
    elif etap == Etap.KRYTERIA_DO_POTWIERDZENIA:
        dodaj(
            Rola.OCENIANY, "POTWIERDZ_KRYTERIA", "Potwierdź rozmowę i zapoznanie z kryteriami oceny",
            terminy.termin_wyznaczenia_kryteriow(ocena.poczatek_cyklu, po_negatywnej),
            f"§ 6 ust. 2 i § 7 pkt {2 if po_negatywnej else 1} rozp.",
        )
    elif etap == Etap.OCENIANIE:
        dodaj(
            Rola.OCENIAJACY, "SPORZADZ_OCENE", "Przeprowadź rozmowę oceniającą i sporządź ocenę",
            ocena.termin, "art. 81 ust. 4 u.s.c.; § 10 i § 11 rozp.",
        )
        if any(wniosek.status == WniosekOTermin.OCZEKUJE for wniosek in ocena.wnioski_o_termin.all()):
            dodaj(
                Rola.OCENIAJACY, "ROZPATRZ_WNIOSEK_O_TERMIN", "Rozpatrz wniosek ocenianego o zmianę terminu oceny",
                None, "art. 81 ust. 8 pkt 4 u.s.c.",
            )
    elif etap == Etap.OCENA_DO_ZAPOZNANIA:
        dodaj(Rola.OCENIANY, "ZAPOZNAJ_SIE_Z_OCENA", "Zapoznaj się z oceną okresową", None, "§ 12 ust. 1 rozp.")
    elif etap == Etap.ZAKONCZONA:
        w_toku = [sprzeciw for sprzeciw in ocena.sprzeciwy.all() if not sprzeciw.rozpatrzony]
        if w_toku:
            if Rola.OCENIANY not in role:  # sprzeciwu od własnej oceny dyrektor generalny nie rozstrzyga
                dodaj(
                    Rola.DYREKTOR_GENERALNY, "ROZPATRZ_SPRZECIW", "Rozpatrz sprzeciw od oceny",
                    terminy.termin_rozpatrzenia_sprzeciwu(w_toku[0].data_wniesienia), "art. 83 ust. 1 i 3 u.s.c.",
                )
    return zadania


def zadania_uzytkownika(uzytkownik, dzien: date) -> list[Zadanie]:
    """Wszystkie zadania użytkownika, od najbliższego terminu; zadania bez terminu dziennego na końcu."""
    zadania: list[Zadanie] = []
    oceny = oceny_widoczne(uzytkownik).prefetch_related("sprzeciwy", "wnioski_o_termin")
    for ocena in oceny:
        zadania += zadania_oceny(ocena, role_uzytkownika(uzytkownik, ocena), dzien)
    return sorted(zadania, key=lambda z: (z.termin is None, z.termin or date.max, z.ocena.pk))


def sprzeciwy_uzytkownika(uzytkownik, dzien: date) -> list[dict]:
    """Sprzeciwy od ocen widocznych dla użytkownika i status sprawy po sprzeciwie (art. 83 ust. 3-5 u.s.c.):
    w toku z terminem rozpatrzenia, uwzględniony, czekający na doręczenie albo z terminem odwołania do sądu pracy.
    Najpierw sprzeciwy w toku, od najstarszego."""
    wiersze = []
    for ocena in oceny_widoczne(uzytkownik).prefetch_related("sprzeciwy"):
        for sprzeciw in ocena.sprzeciwy.all():
            widok = widok_statusu(sprzeciw, dzien)
            wiersze.append({**widok, "ocena": ocena, "sprzeciw": sprzeciw, "termin": widok["status"].termin_rozpatrzenia})
    return sorted(wiersze, key=lambda wiersz: (wiersz["sprzeciw"].rozpatrzony, wiersz["sprzeciw"].data_wniesienia, wiersz["sprzeciw"].pk))


# --- skutki zakończonej oceny ---

def opisy_skutkow(ocena: Ocena) -> list[dict]:
    """Skutki zakończonej oceny opisane dla użytkownika. Liczby w opisach pochodzą z przepisów."""
    przepisy = wczytaj_przepisy()
    wiersze = []
    for skutek in skutki_oceny_zakonczonej(ocena):
        termin = f"{skutek.termin:%d.%m.%Y}" if skutek.termin else ""
        opis = {
            "PONOWNA_OCENA": (
                f"Ponowna ocena okresowa: {termin} - po upływie {przepisy.ponowna_ocena_po_negatywnej_miesiace} mies. "
                "od zapoznania się z oceną negatywną."
            ),
            "NOWE_KRYTERIA": f"Rozmowa i zapoznanie z kryteriami w nowym cyklu oceny: do {termin}.",
            "TERMIN_KOLEJNEJ_OCENY": f"Kolejna ocena okresowa: najpóźniej {termin}.",
            "STOPIEN_OBLIGATORYJNY": (
                f"Kolejny stopień służbowy przysługuje z mocy prawa. Dyrektor generalny przyznaje go do {termin}."
            ),
            "ROZWIAZANIE_STOSUNKU_PRACY": (
                "Druga z rzędu negatywna ocena urzędnika służby cywilnej. Przepis przewiduje rozwiązanie stosunku "
                "pracy za wypowiedzeniem - system tylko sygnalizuje przepis, sprawę prowadzi dyrektor generalny."
            ),
            "IPRZ": "Wnioski z oceny uwzględnia się w indywidualnym programie rozwoju zawodowego.",
        }.get(skutek.kod, skutek.kod)
        wiersze.append({"kod": skutek.kod, "opis": opis, "podstawa": skutek.podstawa, "termin": skutek.termin})
    return wiersze


def _historia(ocena: Ocena) -> list[OcenaHistoryczna]:
    """Zakończone oceny tej osoby od bieżącej wstecz (bieżąca na końcu listy), uzyskane po ostatnim stopniu."""
    historia: list[OcenaHistoryczna] = []
    data_stopnia = ocena.oceniany.data_stopnia
    wezel: Ocena | None = ocena
    while wezel is not None:
        if wezel.zakonczona and wezel.data_zapoznania and (data_stopnia is None or wezel.data_zapoznania > data_stopnia):
            historia.append(OcenaHistoryczna(wezel.data_zapoznania, wezel.wynik, wezel.poziom))
        reczna = wezel.poprzednia_reczna if wezel.poprzednia_id is None else None
        wezel = wezel.poprzednia
        if reczna and reczna.get("data") and reczna.get("ocena") and reczna.get("poziom"):
            # Ocena sprzed wdrożenia systemu, przepisana z papierowego arkusza; data sporządzenia zastępuje
            # nieznaną datę zapoznania.
            dzien = date.fromisoformat(reczna["data"])
            if data_stopnia is None or dzien > data_stopnia:
                historia.append(OcenaHistoryczna(dzien, str(reczna["ocena"]).upper(), reczna["poziom"]))
    return list(reversed(historia))


def poprzedni_wynik(ocena: Ocena) -> str | None:
    """Wynik poprzedniej oceny: z systemu, a przy pierwszej ocenie w systemie - z danych wpisanych ręcznie."""
    if ocena.poprzednia_id is not None:
        return ocena.poprzednia.wynik or None
    if ocena.poprzednia_reczna and ocena.poprzednia_reczna.get("ocena"):
        return str(ocena.poprzednia_reczna["ocena"]).upper()
    return None


def skutki_oceny_zakonczonej(ocena: Ocena) -> list[Skutek]:
    """Skutki prawne zakończonej oceny (rdzeń: `skutki.skutki_oceny`). Dla oceny w toku - pusta lista."""
    proces = ocena.proces()
    if proces.etap != Etap.ZAKONCZONA or proces.wynik is None or proces.data_zapoznania_z_ocena is None:
        return []
    return skutki_oceny(
        ocena=proces.wynik.ocena,
        poziom=proces.wynik.poziom,
        urzednik=proces.urzednik,
        data_sporzadzenia=proces.data_sporzadzenia,
        data_zapoznania=proces.data_zapoznania_z_ocena,
        poprzednia_ocena=poprzedni_wynik(ocena),
        historia_od_ostatniego_stopnia=_historia(ocena),
        data_ostatniego_stopnia=ocena.oceniany.data_stopnia,
        posiadany_stopien=ocena.oceniany.stopien_sluzbowy,
    )
