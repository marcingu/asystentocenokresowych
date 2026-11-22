"""Dane wspólne dla wszystkich szablonów."""

import hashlib

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


# Strony zaplecza administratora: nazwa adresu -> (pozycja menu zaplecza, nagłówek strony).
ZAPLECZE = {
    "administracja": ("konta", "Konta użytkowników"),
    "administracja_konto": ("konta", "Konta użytkowników"),
    "administracja_nowe_konto": ("konta", "Konta użytkowników"),
    "wydzialy": ("wydzialy", "Struktura urzędu"),
    "administracja_urzad": ("urzad", "Oznaczenie urzędu"),
    "administracja_poczta": ("poczta", "Poczta i przypomnienia"),
    "przepisy": ("przepisy", "Konfiguracja procesu"),
}


def strona_zaplecza(request) -> tuple[str, str]:
    """Pozycja menu zaplecza i nagłówek bieżącej strony; puste napisy poza zapleczem i dla osób bez uprawnień."""
    dopasowanie = getattr(request, "resolver_match", None)
    nazwa = dopasowanie.url_name if dopasowanie else ""
    if not uprawnienia.czy_administrator(request.user):
        return "", ""
    if nazwa == "administracja_dziennik":
        if request.GET.get("dziennik") == "proces":
            return "proces", "Czynności w procesie oceny"
        return "bezpieczenstwo", "Dziennik zdarzeń bezpieczeństwa"
    return ZAPLECZE.get(nazwa, ("", ""))


def wersja_logo(logo_png: str) -> str:
    """Krótki skrót logo w adresie ikony strony - po zmianie logo przeglądarka pobiera nową ikonę."""
    return hashlib.sha256((logo_png or "godlo").encode("ascii", "ignore")).hexdigest()[:8]


def wspolny(request):
    uzytkownik = request.user
    oznaczenie = OznaczenieUrzedu.aktualne()
    zakladka, naglowek = strona_zaplecza(request)
    return {
        "urzad": oznaczenie.nazwa, "logo_png": oznaczenie.logo_png, "logo_wersja": wersja_logo(oznaczenie.logo_png),
        "zakladka_zaplecza": zakladka, "naglowek_zaplecza": naglowek,
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
