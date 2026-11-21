"""Logowania i wylogowania trafiają do dziennika zdarzeń bezpieczeństwa (§ 20 rozporządzenia KRI).

Django zgłasza te zdarzenia sygnałami niezależnie od tego, którędy użytkownik wchodzi, więc wpis powstaje przy
każdym sposobie logowania. Hasło nie trafia do dziennika: Django zastępuje je gwiazdkami, a tutaj zapisywany jest
tylko login.
"""

from django.contrib.admin.models import LogEntry
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver

from . import dziennik


@receiver(user_logged_in, dispatch_uid="oceny.dziennik.logowanie")
def _zalogowano(sender, request, user, **kwargs):
    opis = getattr(request, "sposob_logowania", "") or "bez formularza logowania"
    if user.is_superuser:
        # § 20 ust. 2 pkt 1 KRI: dostęp do systemu z uprawnieniami administracyjnymi odnotowuje się obowiązkowo.
        opis += "; uprawnienia administracyjne"
    dziennik.zapisz(dziennik.LOGOWANIE_UDANE, request=request, uzytkownik=user, opis=opis)


@receiver(user_logged_out, dispatch_uid="oceny.dziennik.wylogowanie")
def _wylogowano(sender, request, user, **kwargs):
    if user is not None:
        dziennik.zapisz(dziennik.WYLOGOWANIE, request=request, uzytkownik=user)


@receiver(user_login_failed, dispatch_uid="oceny.dziennik.nieudane_logowanie")
def _nieudane_logowanie(sender, credentials, request=None, **kwargs):
    dziennik.zapisz(dziennik.LOGOWANIE_NIEUDANE, request=request, uzytkownik=None, login=credentials.get("username", ""))


@receiver(post_save, sender=LogEntry, dispatch_uid="oceny.dziennik.panel_django")
def _zmiana_w_panelu_django(sender, instance, created, **kwargs):
    """Zmiany danych kadrowych w panelu administratora Django trafiają do tego samego dziennika co reszta
    czynności administratora (§ 20 ust. 2 pkt 1 KRI)."""
    if not created:
        return
    czynnosc = {1: "dodanie", 2: "zmiana", 3: "usunięcie"}.get(instance.action_flag, "czynność")
    rodzaj = instance.content_type.name if instance.content_type_id else "obiekt"
    dziennik.zapisz(
        dziennik.PANEL_ADMINISTRATORA, uzytkownik=instance.user, dotyczy=instance.object_repr,
        opis=f"{czynnosc}: {rodzaj} (panel Django)",
    )
