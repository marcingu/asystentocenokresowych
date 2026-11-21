"""Nagłówki bezpieczeństwa dodawane do każdej odpowiedzi i ochrona kont."""

from django.conf import settings
from django.db import DatabaseError
from django.shortcuts import redirect
from django.utils import timezone

# Żadnych zasobów spoza własnego adresu: system ma działać w sieci urzędu bez dostępu do internetu,
# a przeglądarka nie może niczego wysłać ani pobrać z zewnątrz.
POLITYKA_TRESCI = (
    "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


class NaglowkiBezpieczenstwa:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        odpowiedz = self.get_response(request)
        odpowiedz.setdefault("Content-Security-Policy", POLITYKA_TRESCI)
        odpowiedz.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.user.is_authenticated:
            # Strony z danymi osobowymi nie zostają w pamięci podręcznej przeglądarki ani serwerów pośrednich.
            odpowiedz.setdefault("Cache-Control", "no-store")
        return odpowiedz


# Strony dostępne dla konta, które musi najpierw skonfigurować aplikację uwierzytelniającą.
_BEZ_DWUETAPOWEGO = {"konto_dwuetapowe", "wylogowanie"}
_dzien_przegladu = None


def _przeglad_kont() -> None:
    """Raz dziennie, przy pierwszym żądaniu: zawieszenie kont bez aktywności (zał. nr 4 część I pkt 6 ustawy
    o KSC). Dzięki temu zawieszanie działa także tam, gdzie nikt nie ustawił zadania cyklicznego."""
    global _dzien_przegladu
    dzien = timezone.localdate()
    if _dzien_przegladu == dzien:
        return
    _dzien_przegladu = dzien
    from . import bezpieczenstwo  # import przy użyciu - modele są gotowe dopiero po starcie aplikacji

    try:
        bezpieczenstwo.zawies_nieaktywne(dzien)
    except DatabaseError:
        _dzien_przegladu = None  # np. baza przed migracją - spróbujemy przy następnym żądaniu


class BezpieczenstwoKont:
    """Przegląd kont raz dziennie, wymuszenie konfiguracji weryfikacji dwuetapowej i zapis odmów dostępu."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _przeglad_kont()
        odpowiedz = self.get_response(request)
        if odpowiedz.status_code == 403:
            from . import dziennik

            dziennik.zapisz(dziennik.ODMOWA_DOSTEPU, request=request, dotyczy=request.path, opis=request.method)
        return odpowiedz

    def process_view(self, request, view_func, view_args, view_kwargs):
        from . import bezpieczenstwo
        from .widoki_kont import WYMAGA_KONFIGURACJI

        if not request.user.is_authenticated or not request.session.get(WYMAGA_KONFIGURACJI):
            return None
        if bezpieczenstwo.urzadzenie(request.user) is not None or not bezpieczenstwo.dwuetapowe_wymagane():
            del request.session[WYMAGA_KONFIGURACJI]  # skonfigurowano w innej sesji albo urząd zmienił politykę
            return None
        nazwa = request.resolver_match.url_name if request.resolver_match else None
        if nazwa in _BEZ_DWUETAPOWEGO or request.path.startswith(f"/{settings.STATIC_URL.strip('/')}/"):
            return None
        return redirect("konto_dwuetapowe")


class PrzepisyUrzedu:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from asystent_ocen.konfiguracja import stosuj_przepisy
        from .models import KonfiguracjaProcesu

        if not request.user.is_authenticated:
            return self.get_response(request)
        request.konfiguracja = KonfiguracjaProcesu.aktualna()
        with stosuj_przepisy(request.konfiguracja.tresc):
            return self.get_response(request)
