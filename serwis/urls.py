"""Adresy projektu."""

from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.contrib.staticfiles.views import serve as serwuj_plik_statyczny
from django.core.exceptions import PermissionDenied
from django.urls import include, path, re_path


@login_not_required
def _logowanie_do_panelu(request, extra_context=None):
    """Panel administratora Django nie ma własnego logowania: wejście prowadzi przez logowanie aplikacji, czyli
    przez blokadę po nieudanych próbach, kod jednorazowy i dziennik zdarzeń."""
    if request.user.is_authenticated:
        raise PermissionDenied("To konto nie ma dostępu do panelu administratora.")
    return redirect_to_login(request.GET.get("next") or "/admin/")


admin.site.login = _logowanie_do_panelu

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("oceny.urls")),
    # Prototyp podaje własne pliki statyczne (arkusz stylów) bez osobnego serwera WWW.
    # We wdrożeniu produkcyjnym: `collectstatic` i serwer pośredniczący.
    re_path(r"^static/(?P<path>.*)$", login_not_required(serwuj_plik_statyczny), {"insecure": True}),
]
