"""Status po sprzeciwie od oceny okresowej w postaci do pokazania na stronie.

Sam status (kod, daty, objaśnienie) liczy rdzeń: `asystent_ocen.po_sprzeciwie`. Ten moduł dobiera tylko oznaczenie
stanu i krótki opis tego, co stało się ze sprzeciwem.
"""

from __future__ import annotations

from datetime import date

from asystent_ocen import po_sprzeciwie as rdzen


def widok_statusu(sprzeciw, dzien: date) -> dict:
    """Słownik dla szablonów: stan (klasa oznaczenia), stan_opis (etykieta), powod, wyjasnienie, status."""
    from .zadania import opis_dni_do_terminu as _odleglosc  # import przy użyciu: lista zadań korzysta z tego modułu

    status = sprzeciw.status(dzien)
    dni = (status.termin_rozpatrzenia - dzien).days
    opis, powod = status.opis, ""
    if status.kod == rdzen.W_TOKU:
        stan, opis = "pilne", f"w toku - {_odleglosc(dni)}"
    elif status.kod == rdzen.UWZGLEDNIONY:
        stan, opis = "wykonane", sprzeciw.rozstrzygniecie_opis
    elif status.kod == rdzen.DO_DORECZENIA:
        stan = "pilne"
    else:
        if sprzeciw.rozpatrzony:
            stan = "pilne" if status.kod == rdzen.ODWOLANIE_PRZYSLUGUJE else "informacja"
            powod = "sprzeciw nieuwzględniony"
        else:
            # Rozstrzygnięcia nadal nie ma: dla dyrektora generalnego to zadanie po terminie.
            stan, powod = "po_terminie", f"sprzeciw nierozpatrzony w terminie - {_odleglosc(dni)}"
    return {
        "status": status, "stan": stan, "stan_opis": opis, "powod": powod, "wyjasnienie": status.wyjasnienie,
        "termin_odwolania": status.termin, "do_doreczenia": status.kod == rdzen.DO_DORECZENIA,
    }
