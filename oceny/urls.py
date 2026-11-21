"""Adresy aplikacji."""

from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("logowanie/", login_not_required(views.Logowanie.as_view()), name="logowanie"),
    path("wylogowanie/", LogoutView.as_view(), name="wylogowanie"),
    path("demo/zaloguj/", views.demo_zaloguj, name="demo_zaloguj"),
    path("", views.zadania, name="zadania"),
    path("oceny/<int:pk>/", views.ocena, name="ocena"),
    path("oceny/<int:pk>/czynnosc/<slug:nazwa>/", views.czynnosc, name="czynnosc"),
    path("oceny/<int:pk>/arkusz.docx", views.arkusz_docx, name="arkusz_docx"),
    path("oceny/<int:pk>/arkusz.pdf", views.arkusz_pdf, name="arkusz_pdf"),
    path("oceny/<int:pk>/terminy.ics", views.kalendarz, name="kalendarz"),
    path("kadry/", views.kadry, name="kadry"),
    path("kadry/pracownik/<int:pk>/rozpocznij/", views.kadry_rozpocznij, name="kadry_rozpocznij"),
    path("kadry/pracownik/<int:pk>/nieobecnosc/", views.kadry_nieobecnosc, name="kadry_nieobecnosc"),
    path("statystyki/", views.statystyki, name="statystyki"),
    path("przepisy/", views.przepisy, name="przepisy"),
    path("asystent/", views.asystent, name="asystent"),
]
