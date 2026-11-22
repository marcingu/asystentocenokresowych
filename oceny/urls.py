"""Adresy aplikacji."""

from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LogoutView
from django.urls import path

from . import (pierwsza, poczta, przeglad, przypomnienia, umowy, panel_przepisow, urzad, views, widoki_administracji, widoki_kadr,
               widoki_kont, wydzialy)

urlpatterns = [
    path("pierwsza-ocena/<int:pk>/", pierwsza.karta, name="pierwsza_ocena"),
    # Przed wzorcem wydruków: „terminy.ics” pasuje także do niego.
    path("pierwsza-ocena/<int:pk>/terminy.ics", pierwsza.kalendarz, name="pierwsza_kalendarz"),
    path("pierwsza-ocena/<int:pk>/<slug:rodzaj>.<slug:format>", pierwsza.wydruk, name="pierwsza_wydruk"),
    path("kadry/umowa/<int:pk>/", umowy.karta_umowy, name="karta_umowy"),
    path("administracja/wydzialy/", wydzialy.struktura, name="wydzialy"),
    path("administracja/urzad/", urzad.ustawienia, name="administracja_urzad"),
    path("favicon.png", urzad.ikona, name="ikona_strony"),
    path("administracja/poczta/", poczta.ustawienia, name="administracja_poczta"),
    path("konto/przypomnienie/", przypomnienia.podglad, name="konto_przypomnienie"),
    path("konto/kalendarz/", przypomnienia.kalendarz_konta, name="konto_kalendarz"),
    # Program kalendarza nie loguje się do systemu: dostęp daje losowy klucz w adresie (widok sam zdejmuje wymóg logowania).
    path("kalendarz/<str:token>/terminy.ics", przypomnienia.kalendarz_osobisty, name="kalendarz_osobisty"),
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
    path("oceny/<int:pk>/notatka/", przeglad.nowa_notatka, name="nowa_notatka"),
    path("pracownicy/<int:pk>/przeglad/", przeglad.przeglad, name="przeglad_wspolpracy"),
    path("oceny/<int:pk>/arkusz.docx", views.arkusz_docx, name="arkusz_docx"),
    path("oceny/<int:pk>/arkusz.pdf", views.arkusz_pdf, name="arkusz_pdf"),
    path("oceny/<int:pk>/terminy.ics", views.kalendarz, name="kalendarz"),
    path("kadry/", views.kadry, name="kadry"),
    path("kadry/pracownik/nowy/", widoki_kadr.pracownik, name="kadry_pracownik_nowy"),
    path("kadry/pracownik/<int:pk>/", widoki_kadr.pracownik, name="kadry_pracownik"),
    path("kadry/pracownik/<int:pk>/nieobecnosc/", views.kadry_nieobecnosc, name="kadry_nieobecnosc"),
    path("kadry/pracownik/<int:pk>/stanowisko/", views.kadry_stanowisko, name="kadry_stanowisko"),
    path("kadry/ezd/", views.kadry_ezd, name="kadry_ezd"),
    path("moje-dane-ezd/", views.moje_dane_ezd, name="moje_dane_ezd"),
    path("statystyki/", views.statystyki, name="statystyki"),
    path("przepisy/", panel_przepisow.przepisy, name="przepisy"),
    path("asystent/", views.asystent, name="asystent"),
]
