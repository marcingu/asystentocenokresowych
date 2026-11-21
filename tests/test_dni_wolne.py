"""Wymaganie: kalendarz dni ustawowo wolnych od pracy (potrzebny do art. 115 KC i ciągłości nieobecności).

Źródło: ustawa z dnia 18 stycznia 1951 r. o dniach wolnych od pracy (t.j. Dz. U. z 2025 r. poz. 296),
art. 1 pkt 1; Wigilia od 1.02.2025 r. (ustawa z 6.12.2024 r., Dz. U. poz. 1965).
"""

import pytest

from asystent_ocen.kalendarz import czy_dzien_ustawowo_wolny, swieta_ustawowe, wielkanoc
from stale import d


@pytest.mark.parametrize("rok, data", [(2015, d(2015, 4, 5)), (2025, d(2025, 4, 20)), (2026, d(2026, 4, 5)), (2027, d(2027, 3, 28))])
def test_wielkanoc_jest_wyliczana_dla_kazdego_roku(rok, data):
    assert wielkanoc(rok) == data


def test_swieta_2026_zawieraja_swieta_stale_i_ruchome():
    swieta = swieta_ustawowe(2026)
    oczekiwane = {
        d(2026, 1, 1), d(2026, 1, 6), d(2026, 4, 5), d(2026, 4, 6), d(2026, 5, 1), d(2026, 5, 3),
        d(2026, 5, 24), d(2026, 6, 4), d(2026, 8, 15), d(2026, 11, 1), d(2026, 11, 11),
        d(2026, 12, 24), d(2026, 12, 25), d(2026, 12, 26),
    }
    assert set(swieta) == oczekiwane


def test_w_2024_wigilia_nie_byla_dniem_wolnym():
    assert d(2024, 12, 24) not in swieta_ustawowe(2024)
    assert len(swieta_ustawowe(2024)) == 13


def test_sylwester_nie_jest_dniem_ustawowo_wolnym():
    assert czy_dzien_ustawowo_wolny(d(2026, 12, 31)) is False


def test_niedziela_jest_dniem_ustawowo_wolnym():
    assert czy_dzien_ustawowo_wolny(d(2026, 11, 22)) is True


def test_sobota_nie_jest_dniem_ustawowo_wolnym():
    """Sobota przesuwa koniec terminu (art. 115 KC), ale nie jest świętem ustawowym."""
    assert czy_dzien_ustawowo_wolny(d(2026, 11, 21)) is False
