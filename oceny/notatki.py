"""Notatki oceniającego w interfejsie: rodzaje wpisów, komunikaty i powrót po zapisie.

Rodzaje i ich reguły należą do rdzenia (`asystent_ocen.przebieg`); tu są tylko nazwy pokazywane użytkownikowi.
Rodzaj „dobrostan” łączy notatki z Radarem Dobrostanu i Doceniania: karta dobrostanu odpowiada notatce
o dobrostanie, karta docenienia - dodatkowemu osiągnięciu pracownika.
"""

from __future__ import annotations

from asystent_ocen import radar
from asystent_ocen.przebieg import DOBROSTAN, OBSERWACJA, OSIAGNIECIE

RODZAJE_NOTATEK = (
    (OBSERWACJA, "obserwacja z pracy"),
    (OSIAGNIECIE, "dodatkowe osiągnięcie pracownika"),
    (DOBROSTAN, "dobrostan i organizacja pracy"),
)
ZAPISANO = {
    OBSERWACJA: "Notatka została zapisana. Widzi ją tylko oceniający.",
    OSIAGNIECIE: "Dodatkowe osiągnięcie zostało zapisane. Widzi je tylko oceniający.",
    DOBROSTAN: "Notatka o dobrostanie została zapisana. Widzi ją tylko oceniający.",
}
# Rodzaj notatki, którą przełożony zapisuje do karty obserwacji Radaru.
RODZAJ_DLA_KARTY = {radar.DOBROSTAN: DOBROSTAN, radar.DOCENIENIE: OSIAGNIECIE}
# Dokąd wraca formularz notatki po zapisie. Nazwy zamiast adresów: parametr z formularza nie może wskazać obcej strony.
POWROTY = ("zadania", "przeglad")


def adres_powrotu(powrot: str, ocena) -> str | None:
    """Adres strony, z której przełożony dodawał notatkę; None - karta oceny (dotychczasowe zachowanie)."""
    from django.urls import reverse

    if powrot == "zadania":
        return reverse("zadania")
    if powrot == "przeglad":
        return reverse("przeglad_wspolpracy", args=[ocena.oceniany_id])
    return None


def adres_formularza(powrot: str, ocena, rodzaj: str = "") -> str | None:
    """Adres formularza, do którego wraca odrzucona notatka; None - karta oceny."""
    from django.urls import reverse

    if powrot == "zadania":
        wybor = f"&rodzaj={rodzaj}" if rodzaj in dict(RODZAJE_NOTATEK) else ""
        return f"{reverse('nowa_notatka', args=[ocena.pk])}?powrot=zadania{wybor}"
    return adres_powrotu(powrot, ocena)
