"""Adresy projektu."""

from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.contrib.staticfiles.views import serve as serwuj_plik_statyczny
from django.urls import include, path, re_path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("oceny.urls")),
    # Prototyp podaje własne pliki statyczne (arkusz stylów) bez osobnego serwera WWW.
    # We wdrożeniu produkcyjnym: `collectstatic` i serwer pośredniczący.
    re_path(r"^static/(?P<path>.*)$", login_not_required(serwuj_plik_statyczny), {"insecure": True}),
]
