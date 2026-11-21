"""Dane wspólne dla wszystkich szablonów."""

from django.conf import settings
from django.contrib.auth import get_user_model

from . import uprawnienia
from .models import OznaczenieUrzedu
from .czas import dzis
from .kontekst_ezd import integracja_wlaczona


def konta_demo():
    """Konta demonstracyjne: bez hasła i bez dostępu do panelu Django. Poza trybem demo lista jest pusta.
    Wśród nich jest administrator pokazu - żeby dało się obejrzeć zaplecze: konta i dzienniki."""
    konta = get_user_model().objects
    if not settings.ASYSTENT_TRYB_DEMO:
        return konta.none()
    return konta.filter(
        password__startswith="!", is_staff=False, is_active=True
    ).select_related("pracownik").order_by("pracownik__nazwisko", "username")


def wspolny(request):
    uzytkownik = request.user
    oznaczenie = OznaczenieUrzedu.aktualne()
    return {
        "urzad": oznaczenie.nazwa, "logo_png": oznaczenie.logo_png,
        "tryb_demo": settings.ASYSTENT_TRYB_DEMO,
        "konta_demo": konta_demo(),
        "dzis": dzis(),
        "data_symulowana": bool(settings.ASYSTENT_DZIS),
        "ja": uprawnienia.pracownik_uzytkownika(uzytkownik),
        "jestem_kadry": uprawnienia.czy_kadry(uzytkownik),
        "jestem_administratorem": uprawnienia.czy_administrator(uzytkownik),
        "widze_statystyki": uprawnienia.widzi_statystyki(uzytkownik),
        # odnośnik „Moje dane z EZD RP” jest w menu tylko przy włączonej integracji
        "integracja_ezd": uzytkownik.is_authenticated and integracja_wlaczona(),
    }
