"""Dzisiejsza data dla całej aplikacji.

Ustawienie `ASYSTENT_DZIS` (RRRR-MM-DD) zastępuje datę systemową - do pokazów i testów. Wszystkie terminy,
przypomnienia i potwierdzenia czynności biorą datę stąd, nigdy z `date.today()`.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone


def dzis() -> date:
    ustawiona = getattr(settings, "ASYSTENT_DZIS", None)
    if not ustawiona:
        return timezone.localdate()
    try:
        return date.fromisoformat(str(ustawiona))
    except ValueError:
        raise ImproperlyConfigured(
            f"ASYSTENT_DZIS musi mieć postać RRRR-MM-DD (podano: {ustawiona!r})."
        ) from None
