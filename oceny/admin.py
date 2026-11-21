"""Panel administratora: dane kadrowe i ustalenia. Stan ocen i dziennik zdarzeń są tu tylko do odczytu -
proces oceny zmienia się wyłącznie czynnościami w aplikacji, które przechodzą przez reguły rdzenia."""

from django.contrib import admin

from .models import Nieobecnosc, Ocena, Pracownik, Sprzeciw, UstaleniaMonitoringu, WniosekOTermin, Zdarzenie


class TylkoOdczyt(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pracownik)
class PracownikAdmin(admin.ModelAdmin):
    list_display = ("nazwisko", "imie", "stanowisko", "komorka", "rodzaj_zatrudnienia", "przelozony", "rola_kadry")
    list_filter = ("rodzaj_zatrudnienia", "komorka", "rola_kadry", "rola_dyrektor")
    search_fields = ("nazwisko", "imie", "stanowisko")
    autocomplete_fields = ("przelozony",)


@admin.register(Nieobecnosc)
class NieobecnoscAdmin(admin.ModelAdmin):
    list_display = ("pracownik", "od", "do", "usprawiedliwiona")
    autocomplete_fields = ("pracownik",)


@admin.register(UstaleniaMonitoringu)
class UstaleniaMonitoringuAdmin(admin.ModelAdmin):
    list_display = ("__str__", "integracja_wlaczona", "data_poinformowania")


@admin.register(Ocena)
class OcenaAdmin(TylkoOdczyt):
    list_display = ("oceniany", "oceniajacy", "etap", "termin", "wynik", "poziom")
    list_filter = ("etap", "wynik")
    # Szkic i notatki oceniającego (wewnątrz stanu procesu) nie są pokazywane administratorowi.
    exclude = ("stan", "szkic")


@admin.register(Zdarzenie)
class ZdarzenieAdmin(TylkoOdczyt):
    list_display = ("data", "czynnosc", "ocena", "podpis", "czas")
    list_filter = ("czynnosc",)


@admin.register(Sprzeciw)
class SprzeciwAdmin(TylkoOdczyt):
    list_display = ("ocena", "data_wniesienia", "po_terminie", "rozstrzygniecie", "data_rozstrzygniecia")


@admin.register(WniosekOTermin)
class WniosekOTerminAdmin(TylkoOdczyt):
    list_display = ("ocena", "data", "status", "data_rozpatrzenia")
