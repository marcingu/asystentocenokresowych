"""Dane wspólne dla wszystkich szablonów."""

from django.conf import settings
from django.contrib.auth import get_user_model

from . import uprawnienia
from .czas import dzis


def konta_demo():
    """Konta demonstracyjne: bez hasła i bez uprawnień administracyjnych. Poza trybem demo lista jest pusta."""
    konta = get_user_model().objects
    if not settings.ASYSTENT_TRYB_DEMO:
        return konta.none()
    return konta.filter(
        password__startswith="!", is_superuser=False, is_staff=False, is_active=True
    ).select_related("pracownik").order_by("pracownik__nazwisko", "username")


def wspolny(request):
    uzytkownik = request.user
    return {
        "urzad": settings.ASYSTENT_URZAD,
        "tryb_demo": settings.ASYSTENT_TRYB_DEMO,
        "konta_demo": konta_demo(),
        "dzis": dzis(),
        "data_symulowana": bool(settings.ASYSTENT_DZIS),
        "ja": uprawnienia.pracownik_uzytkownika(uzytkownik),
        "jestem_kadry": uprawnienia.czy_kadry(uzytkownik),
        "widze_statystyki": uprawnienia.widzi_statystyki(uzytkownik),
    }
