"""Korekta wyraźnie wskazanego pustego arkusza po potwierdzeniu pierwszej umowy."""
from django.db import transaction
from asystent_ocen.przebieg import Etap
from .czas import dzis
from .models import Ocena, Pracownik, Zdarzenie
from .umowy import TERMINOWA, zaloz_umowe


@transaction.atomic
def skoryguj(osoba_id, ocena_id):
    osoba = Pracownik.objects.select_for_update().get(pk=osoba_id)
    stara = Ocena.wszystkie.select_for_update().get(pk=ocena_id, oceniany=osoba)
    if stara.omylkowa:
        return osoba.umowa.pierwsza
    if (osoba.rodzaj_zatrudnienia != TERMINOWA or hasattr(osoba, "umowa") or
            stara.poczatek_cyklu != osoba.data_zatrudnienia or osoba.oceny.count() != 1 or
            stara.etap != Etap.KRYTERIA_DO_WYZNACZENIA.name or stara.poprzednia_id or
            stara.szkic is not None or stara.poprzednia_reczna is not None or stara.termin or stara.wynik or
            stara.zdarzenia.exclude(czynnosc="rozpoczęcie cyklu oceny").exists()):
        raise ValueError("Nie jest to pusty początkowy arkusz dla pierwszej umowy. Sprawa wymaga sprawdzenia przez kadry.")
    zaloz_umowe(osoba, {"kwalifikacja": "pierwsza"})
    stara.omylkowa = True
    stara.save(update_fields=["omylkowa"])
    nowa = osoba.umowa.pierwsza
    Zdarzenie.objects.create(ocena=stara, data=dzis(), podpis="Korekta ewidencji", czynnosc="korekta rodzaju oceny",
        opis=f"Omyłkowo otwarty arkusz okresowy. Właściwa sprawa: pierwsza ocena nr {nowa.pk}.")
    return nowa
