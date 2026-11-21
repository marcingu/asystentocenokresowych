"""Stałe testowe przepisane ze źródeł KPRM (bez wywołań kodu produkcyjnego)."""

from datetime import date

# Kryteria obowiązkowe - § 4 rozporządzenia PRM z 4.04.2016 r. (Dz. U. poz. 470)
OBOWIAZKOWE_A = [
    "Zarządzanie ludźmi",
    "Podejmowanie decyzji i odpowiedzialność",
    "Organizacja pracy i orientacja na osiąganie celów",
    "Współpraca",
    "Komunikacja",
    "Zarządzanie strategiczne",
]
OBOWIAZKOWE_B = OBOWIAZKOWE_A[:5]
OBOWIAZKOWE_C = [
    "Wykorzystywanie wiedzy i doskonalenie zawodowe",
    "Rzetelność",
    "Organizacja pracy i orientacja na osiąganie celów",
    "Współpraca",
    "Komunikacja",
]

# Wykaz kryteriów - załącznik nr 1 do rozporządzenia (14 pozycji)
KATALOG = [
    "Komunikacja",
    "Kreatywność",
    "Negocjowanie",
    "Organizacja pracy i orientacja na osiąganie celów",
    "Orientacja na klienta/interesanta",
    "Podejmowanie decyzji i odpowiedzialność",
    "Radzenie sobie w sytuacjach kryzysowych",
    "Rzetelność",
    "Myślenie analityczne",
    "Wykorzystywanie wiedzy i doskonalenie zawodowe",
    "Współpraca",
    "Wystąpienia publiczne",
    "Zarządzanie ludźmi",
    "Zarządzanie strategiczne",
]


def d(rok: int, miesiac: int, dzien: int) -> date:
    """Skrót do zapisu dat w testach."""
    return date(rok, miesiac, dzien)
