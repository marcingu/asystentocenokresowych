"""Automatyczny początek okresowej; nie zastępuje nieustalonych danych kadrowych."""
from django.db import transaction
from asystent_ocen.przebieg import Etap
from .czas import dzis
from .models import Ocena, Pracownik, Zdarzenie


@transaction.atomic
def uzgodnij(osoba_id):
    osoba = Pracownik.objects.select_for_update().select_related("przelozony").get(pk=osoba_id)
    if not (osoba.podlega_ocenie and osoba.przelozony_id and osoba.opis_stanowiska.strip()):
        return None
    ostatnia = osoba.oceny.first()
    if ostatnia:
        if (ostatnia.etap != Etap.ZAKONCZONA.name or osoba.oceny.exclude(etap=Etap.ZAKONCZONA.name).exists()
                or ostatnia.sprzeciwy.filter(rozstrzygniecie="").exists() or hasattr(ostatnia, "nastepna")):
            return None
        od = ostatnia.proces().data_sporzadzenia
    else:
        od = getattr(getattr(osoba, "umowa", None), "stala_od", None) or osoba.data_zatrudnienia
    if od is None:
        return None
    nowa = Ocena.utworz(oceniany=osoba, oceniajacy=osoba.przelozony, poczatek_cyklu=od, poprzednia=ostatnia)
    Zdarzenie.objects.create(ocena=nowa, data=dzis(), podpis="System", czynnosc="automatyczne rozpoczęcie cyklu oceny")
    return nowa
