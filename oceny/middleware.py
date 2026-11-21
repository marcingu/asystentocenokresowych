"""Nagłówki bezpieczeństwa dodawane do każdej odpowiedzi."""

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
