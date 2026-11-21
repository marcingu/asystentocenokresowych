"""Adresy aplikacji."""

from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views, widoki_administracji, widoki_kadr, widoki_kont

urlpatterns = [
    path("logowanie/", login_not_required(widoki_kont.Logowanie.as_view()), name="logowanie"),
    path("logowanie/kod/", widoki_kont.logowanie_kod, name="logowanie_kod"),
    path("wylogowanie/", LogoutView.as_view(), name="wylogowanie"),
    path("demo/zaloguj/", widoki_kont.demo_zaloguj, name="demo_zaloguj"),
    path("konto/", widoki_kont.konto, name="konto"),
    path("konto/dwuetapowe/", widoki_kont.konto_dwuetapowe, name="konto_dwuetapowe"),
    path("konto/haslo/", widoki_kont.ZmianaHasla.as_view(), name="konto_haslo"),
    path("haslo/<uidb64>/<token>/", login_not_required(widoki_kont.UstawienieHasla.as_view()), name="haslo_ustaw"),
    path("administracja/", widoki_administracji.konta, name="administracja"),
    path("administracja/konta/nowe/", widoki_administracji.nowe_konto, name="administracja_nowe_konto"),
    path("administracja/konta/<int:pk>/", widoki_administracji.konto, name="administracja_konto"),
    path("administracja/konta/<int:pk>/<slug:akcja>/", widoki_administracji.akcja, name="administracja_akcja"),
    path("administracja/zawies-nieaktywne/", widoki_administracji.zawies_nieaktywne, name="administracja_zawies"),
    path("administracja/dziennik/", widoki_administracji.dziennik_zdarzen, name="administracja_dziennik"),
    path("administracja/dziennik.csv", widoki_administracji.dziennik_csv, name="administracja_dziennik_csv"),
    path("", views.zadania, name="zadania"),
    path("oceny/<int:pk>/", views.ocena, name="ocena"),
    path("oceny/<int:pk>/czynnosc/<slug:nazwa>/", views.czynnosc, name="czynnosc"),
    path("oceny/<int:pk>/arkusz.docx", views.arkusz_docx, name="arkusz_docx"),
    path("oceny/<int:pk>/arkusz.pdf", views.arkusz_pdf, name="arkusz_pdf"),
    path("oceny/<int:pk>/terminy.ics", views.kalendarz, name="kalendarz"),
    path("kadry/", views.kadry, name="kadry"),
    path("kadry/pracownik/nowy/", widoki_kadr.pracownik, name="kadry_pracownik_nowy"),
    path("kadry/pracownik/<int:pk>/", widoki_kadr.pracownik, name="kadry_pracownik"),
    path("kadry/pracownik/<int:pk>/rozpocznij/", views.kadry_rozpocznij, name="kadry_rozpocznij"),
    path("kadry/pracownik/<int:pk>/nieobecnosc/", views.kadry_nieobecnosc, name="kadry_nieobecnosc"),
    path("kadry/ezd/", views.kadry_ezd, name="kadry_ezd"),
    path("moje-dane-ezd/", views.moje_dane_ezd, name="moje_dane_ezd"),
    path("statystyki/", views.statystyki, name="statystyki"),
    path("przepisy/", views.przepisy, name="przepisy"),
    path("asystent/", views.asystent, name="asystent"),
]
