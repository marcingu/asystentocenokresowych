"""Kalendarz i obliczanie terminów wg Kodeksu cywilnego (art. 111, 112, 115 KC).

Zasady (dokument KPRM „liczenie terminów” oraz Poradnik KPRM 2016, s. 8-9):
- termin w dniach: nie liczy się dnia zdarzenia, upływa z końcem ostatniego dnia (art. 111 § 2 KC),
- termin w miesiącach: kończy się z upływem dnia, który datą odpowiada dniowi początkowemu,
  a gdy takiego dnia nie ma - w ostatnim dniu miesiąca (art. 112 KC),
- koniec terminu w dzień ustawowo wolny od pracy lub w sobotę przesuwa się na najbliższy
  dzień, który nie jest dniem wolnym ani sobotą (art. 115 KC),
- dni wolne w środku terminu wliczają się do jego biegu.
"""

from __future__ import annotations

from datetime import date, timedelta

from .konfiguracja import Przepisy, _ustal_przepisy

_SOBOTA = 5  # date.weekday(): poniedziałek = 0
_NIEDZIELA = 6
_DZIEN = timedelta(days=1)


def wielkanoc(rok: int) -> date:
    """Data Wielkanocy (niedziela) w kalendarzu gregoriańskim."""
    # Algorytm Meeusa/Jonesa/Butchera („anonimowy algorytm gregoriański”).
    zloty = rok % 19
    stulecie, rok_stulecia = divmod(rok, 100)
    przestepne_stulecia, reszta_stulecia = divmod(stulecie, 4)
    poprawka_ksiezycowa = (stulecie - (stulecie + 8) // 25 + 1) // 3
    epakta = (19 * zloty + stulecie - przestepne_stulecia - poprawka_ksiezycowa + 15) % 30
    przestepne_lata, reszta_lat = divmod(rok_stulecia, 4)
    do_niedzieli = (32 + 2 * reszta_stulecia + 2 * przestepne_lata - epakta - reszta_lat) % 7
    korekta = (zloty + 11 * epakta + 22 * do_niedzieli) // 451
    miesiac, dzien = divmod(epakta + do_niedzieli - 7 * korekta + 114, 31)
    return date(rok, miesiac, dzien + 1)


def swieta_ustawowe(rok: int, przepisy: Przepisy | None = None) -> dict[date, str]:
    """Dni ustawowo wolne od pracy w danym roku (bez zwykłych niedziel): data -> nazwa."""
    przepisy = _ustal_przepisy(przepisy)
    swieta: dict[date, str] = {}
    for swieto in przepisy.swieta:
        for dzien in _daty_swieta(swieto, rok):
            if swieto.od_roku is not None and dzien.year < swieto.od_roku:
                continue
            swieta[dzien] = f"{swieta[dzien]} / {swieto.nazwa}" if dzien in swieta else swieto.nazwa
    return dict(sorted(swieta.items()))


def _daty_swieta(swieto, rok: int) -> list[date]:
    """Daty, w które dane święto przypada w roku `rok` (zwykle jedna albo żadna)."""
    if swieto.dni_od_wielkanocy is not None:
        # Sąsiednie lata są potrzebne tylko dla bardzo dużych przesunięć względem Wielkanocy.
        kandydaci = [wielkanoc(r) + timedelta(days=swieto.dni_od_wielkanocy) for r in (rok - 1, rok, rok + 1)]
        return [dzien for dzien in kandydaci if dzien.year == rok]
    if swieto.data is not None:
        try:
            miesiac, dzien_miesiaca = (int(czesc) for czesc in swieto.data.split("-"))
        except ValueError:
            raise ValueError(
                f"Święto „{swieto.nazwa}”: data musi mieć postać \"MM-DD\" (jest: {swieto.data!r})"
            ) from None
        try:
            return [date(rok, miesiac, dzien_miesiaca)]
        except ValueError:
            return []  # np. 29 lutego w roku nieprzestępnym
    return []


def czy_dzien_ustawowo_wolny(dzien: date, przepisy: Przepisy | None = None) -> bool:
    """Niedziela albo święto ustawowe. Sobota NIE jest dniem ustawowo wolnym."""
    return dzien.weekday() == _NIEDZIELA or dzien in swieta_ustawowe(dzien.year, przepisy)


def przesun_na_dzien_roboczy(dzien: date, przepisy: Przepisy | None = None) -> date:
    """Art. 115 KC - przesuwa koniec terminu z dnia wolnego lub soboty na następny dzień roboczy."""
    przepisy = _ustal_przepisy(przepisy)
    while czy_dzien_ustawowo_wolny(dzien, przepisy) or (
        przepisy.sobota_konczy_termin_jak_dzien_wolny and dzien.weekday() == _SOBOTA
    ):
        dzien += _DZIEN
    return dzien


def dodaj_miesiace(dzien: date, miesiace: int) -> date:
    """Art. 112 KC - data odpowiadająca dniowi początkowemu albo ostatni dzień miesiąca."""
    rok, miesiac_od_zera = divmod(dzien.year * 12 + dzien.month - 1 + miesiace, 12)
    miesiac = miesiac_od_zera + 1
    pierwszy_nastepnego = date(rok + 1, 1, 1) if miesiac == 12 else date(rok, miesiac + 1, 1)
    ostatni_dzien_miesiaca = (pierwszy_nastepnego - _DZIEN).day
    return date(rok, miesiac, min(dzien.day, ostatni_dzien_miesiaca))


def koniec_terminu_miesiecy(poczatek: date, miesiace: int, przepisy: Przepisy | None = None) -> date:
    """Koniec terminu oznaczonego w miesiącach, z uwzględnieniem art. 115 KC."""
    return przesun_na_dzien_roboczy(dodaj_miesiace(poczatek, miesiace), przepisy)


def koniec_terminu_dni(zdarzenie: date, dni: int, przepisy: Przepisy | None = None) -> date:
    """Koniec terminu oznaczonego w dniach od zdarzenia (art. 111 § 2 i art. 115 KC)."""
    # Dnia zdarzenia się nie wlicza, więc ostatnim dniem terminu jest dzień zdarzenia + `dni`.
    return przesun_na_dzien_roboczy(zdarzenie + timedelta(days=dni), przepisy)


def uplynelo_wiecej_niz_miesiecy(od: date, dzien: date, miesiace: int) -> bool:
    """Czy w dniu `dzien` upłynęło WIĘCEJ niż `miesiace` miesięcy od dnia `od` (art. 112 KC)."""
    # Termin upływa z końcem dnia odpowiadającego datą dniowi początkowemu, więc „więcej niż” zaczyna się
    # dopiero następnego dnia.
    return dzien > dodaj_miesiace(od, miesiace)
