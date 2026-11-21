"""Modele aplikacji.

Stan procesu oceny przechowuje rdzeń (`ProcesOceny`) zapisany jako JSON w polu `Ocena.stan`. Pozostałe pola
`Ocena` to kopie do zapytań i sortowania - odświeża je `Ocena.zapisz_proces`.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from asystent_ocen import kryteria
from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.nieobecnosci import Nieobecnosc as NieobecnoscRdzenia
from asystent_ocen.przebieg import Etap, ProcesOceny
from asystent_ocen.wynik import NEGATYWNA
from asystent_ocen.zapis import proces_do_slownika, proces_ze_slownika

MIANOWANIE = "mianowanie"

NAZWY_RODZAJOW_ZATRUDNIENIA = {
    "mianowanie": "mianowanie (urzędnik służby cywilnej)",
    "umowa_na_czas_nieokreslony": "umowa o pracę na czas nieokreślony",
    "umowa_na_czas_okreslony": "umowa o pracę na czas określony",
    "wyzsze_stanowisko": "wyższe stanowisko w służbie cywilnej",
}


def rodzaje_zatrudnienia() -> list[tuple[str, str]]:
    """Rodzaje zatrudnienia z `przepisy.toml` (podlegające i niepodlegające ocenie) z nazwami do wyświetlenia."""
    przepisy = wczytaj_przepisy()
    kody = (*przepisy.rodzaje_zatrudnienia_podlegajace_ocenie, *przepisy.rodzaje_zatrudnienia_niepodlegajace_ocenie)
    return [(kod, NAZWY_RODZAJOW_ZATRUDNIENIA.get(kod, kod)) for kod in kody]


class Wydzial(models.Model):
    nazwa = models.CharField("nazwa wydziału", max_length=160, unique=True)
    kierownik = models.ForeignKey("Pracownik", null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="prowadzone_wydzialy", verbose_name="przełożony pracowników wydziału")
    zwierzchnik = models.ForeignKey("Pracownik", null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="nadzorowane_wydzialy", verbose_name="przełożony kierownika")

    def szef_dla(self, osoba_id):
        return self.zwierzchnik if osoba_id and osoba_id == self.kierownik_id else self.kierownik

    class Meta:
        ordering = ["nazwa"]
        verbose_name = "wydział"
        verbose_name_plural = "wydziały"

    def __str__(self):
        return self.nazwa


class Pracownik(models.Model):
    uzytkownik = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pracownik",
        verbose_name="konto użytkownika",
    )
    imie = models.CharField("imię", max_length=80)
    nazwisko = models.CharField("nazwisko", max_length=120)
    stanowisko = models.CharField("stanowisko", max_length=160)
    opis_stanowiska = models.TextField("opis stanowiska pracy", blank=True)
    komorka_archiwalna = models.CharField("dawna nazwa komórki", max_length=160, blank=True, editable=False)
    wydzial = models.ForeignKey(Wydzial, verbose_name="komórka organizacyjna", on_delete=models.PROTECT,
                                null=True, blank=True, related_name="pracownicy")
    # Dopuszczalne wartości pochodzą z przepisy.toml i są sprawdzane w clean() - bez `choices`, żeby zmiana
    # przepisów nie wymagała migracji bazy.
    rodzaj_zatrudnienia = models.CharField("rodzaj zatrudnienia", max_length=40)
    kierownik_urzedu = models.BooleanField("kierownik urzędu", default=False)
    kieruje_pracownikami = models.BooleanField("kieruje bezpośrednio pracownikami", default=False)
    przelozony = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="podwladni",
        verbose_name="bezpośredni przełożony",
    )
    data_zatrudnienia = models.DateField("data rozpoczęcia zatrudnienia")
    # Starsze wpisy zawierają tylko rok. Nie uzupełniamy nieznanego dnia ani miesiąca.
    rok_mianowania = models.PositiveSmallIntegerField("historyczny rok mianowania", null=True, blank=True, editable=False)
    data_mianowania = models.DateField("data mianowania", null=True, blank=True)
    stopien_sluzbowy = models.PositiveSmallIntegerField("stopień służbowy", null=True, blank=True)
    data_stopnia = models.DateField("data przyznania stopnia służbowego", null=True, blank=True)
    identyfikator_ezd = models.CharField("identyfikator stanowiska w EZD RP", max_length=80, blank=True)
    klauzula_ezd_potwierdzona = models.BooleanField("przekazano informację o danych z EZD RP", default=False)
    rola_kadry = models.BooleanField("komórka kadr (zarządzający)", default=False)
    rola_dyrektor = models.BooleanField("dyrektor (statystyki zbiorcze)", default=False)

    class Meta:
        ordering = ["nazwisko", "imie"]
        verbose_name = "pracownik"
        verbose_name_plural = "pracownicy"

    def __str__(self) -> str:
        return self.imie_i_nazwisko

    @property
    def komorka(self) -> str:
        return self.wydzial.nazwa if self.wydzial_id else ""

    @property
    def imie_i_nazwisko(self) -> str:
        return f"{self.imie} {self.nazwisko}"

    @property
    def urzednik(self) -> bool:
        return self.rodzaj_zatrudnienia == MIANOWANIE

    @property
    def arkusz(self) -> str:
        return kryteria.wybierz_arkusz(
            kierownik_urzedu=self.kierownik_urzedu, kieruje_bezposrednio_pracownikami=self.kieruje_pracownikami
        )

    @property
    def podlega_ocenie(self) -> bool:
        return kryteria.czy_podlega_ocenie(rodzaj_zatrudnienia=self.rodzaj_zatrudnienia)

    @property
    def rodzaj_zatrudnienia_opis(self) -> str:
        return NAZWY_RODZAJOW_ZATRUDNIENIA.get(self.rodzaj_zatrudnienia, self.rodzaj_zatrudnienia)

    @property
    def opis_roli(self) -> str:
        """Krótki opis roli w systemie, np. na pasku trybu demonstracyjnego."""
        role = []
        if self.rola_dyrektor:
            role.append("dyrektor")
        if self.rola_kadry:
            role.append("kadry")
        if self.kieruje_pracownikami or self.kierownik_urzedu:
            role.append("przełożony")
        return ", ".join(role) or "pracownik"

    def biezaca_ocena(self) -> "Ocena | None":
        """Najnowsza ocena tej osoby (ta, po której nie rozpoczęto jeszcze kolejnego cyklu)."""
        return self.oceny.order_by("-poczatek_cyklu", "-pk").first()

    def clean(self) -> None:
        if self.data_mianowania:
            self.rodzaj_zatrudnienia = MIANOWANIE
        if self.urzednik:
            bledy = {}
            if not self.data_mianowania:
                bledy["data_mianowania"] = "Podaj pełną datę mianowania."
            maksimum = wczytaj_przepisy().max_stopien_sluzbowy
            if self.stopien_sluzbowy is None or not 1 <= self.stopien_sluzbowy <= maksimum:
                bledy["stopien_sluzbowy"] = f"Podaj stopień służbowy od 1 do {maksimum}."
            if not self.data_stopnia:
                bledy["data_stopnia"] = "Podaj datę przyznania stopnia służbowego."
            elif self.data_mianowania and self.data_stopnia < self.data_mianowania:
                bledy["data_stopnia"] = "Data stopnia nie może być wcześniejsza niż mianowanie."
            if bledy:
                raise ValidationError(bledy)
        elif self.stopien_sluzbowy is not None or self.data_stopnia:
            raise ValidationError("Dane stopnia służbowego wymagają podania daty mianowania.")
        znane = [kod for kod, _ in rodzaje_zatrudnienia()]
        if self.rodzaj_zatrudnienia not in znane:
            raise ValidationError({"rodzaj_zatrudnienia": f"Nieznany rodzaj zatrudnienia (dopuszczalne: {', '.join(znane)})."})
        if self.przelozony_id is not None and self.przelozony_id == self.pk:
            raise ValidationError({"przelozony": "Pracownik nie może być własnym przełożonym."})


class Ocena(models.Model):
    oceniany = models.ForeignKey(Pracownik, on_delete=models.PROTECT, related_name="oceny")
    oceniajacy = models.ForeignKey(Pracownik, on_delete=models.PROTECT, related_name="oceny_wystawiane")
    poprzednia = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="nastepna",
        verbose_name="poprzednia ocena",
    )
    stan = models.JSONField("stan procesu (rdzeń)")
    # kopie do zapytań - ustawia wyłącznie _ustaw_stan()
    etap = models.CharField(max_length=40, db_index=True)
    termin = models.DateField("termin sporządzenia oceny", null=True, blank=True)
    poczatek_cyklu = models.DateField("początek okresu oceny")
    wynik = models.CharField(max_length=20, blank=True)
    poziom = models.CharField(max_length=60, blank=True)
    data_zapoznania = models.DateField(null=True, blank=True)
    # dane robocze spoza procesu
    szkic = models.JSONField("roboczy formularz części II (widzi tylko oceniający)", null=True, blank=True)
    poprzednia_reczna = models.JSONField("dane poprzedniej oceny wpisane ręcznie", null=True, blank=True)
    utworzono = models.DateTimeField(auto_now_add=True)
    zmieniono = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-poczatek_cyklu", "-pk"]
        verbose_name = "ocena okresowa"
        verbose_name_plural = "oceny okresowe"

    def __str__(self) -> str:
        return f"Ocena: {self.oceniany} (od {self.poczatek_cyklu:%d.%m.%Y})"

    @classmethod
    def utworz(cls, *, oceniany: Pracownik, oceniajacy: Pracownik, poczatek_cyklu, poprzednia: "Ocena | None" = None):
        """Nowa ocena z procesem na pierwszym etapie; arkusz i status urzędnika są utrwalane na początku cyklu."""
        proces = ProcesOceny(arkusz=oceniany.arkusz, urzednik=oceniany.urzednik, poczatek_cyklu=poczatek_cyklu)
        ocena = cls(oceniany=oceniany, oceniajacy=oceniajacy, poprzednia=poprzednia)
        ocena._ustaw_stan(proces)
        ocena.save()
        return ocena

    def proces(self) -> ProcesOceny:
        return proces_ze_slownika(self.stan)

    def zapisz_proces(self, proces: ProcesOceny) -> None:
        self._ustaw_stan(proces)
        self.save()

    def _ustaw_stan(self, proces: ProcesOceny) -> None:
        self.stan = proces_do_slownika(proces)
        self.etap = Etap(proces.etap).name
        self.termin = proces.termin
        self.poczatek_cyklu = proces.poczatek_cyklu
        self.wynik = proces.wynik.ocena if proces.wynik else ""
        self.poziom = proces.wynik.poziom if proces.wynik else ""
        self.data_zapoznania = proces.data_zapoznania_z_ocena

    @property
    def etap_rdzenia(self) -> Etap:
        return Etap[self.etap]

    @property
    def etap_opis(self) -> str:
        return self.etap_rdzenia.value

    @property
    def zakonczona(self) -> bool:
        return self.etap == Etap.ZAKONCZONA.name

    @property
    def pierwsza(self) -> bool:
        """Czy to pierwsza ocena pracownika prowadzona w systemie (nie ma poprzedniej)."""
        return self.poprzednia_id is None

    @property
    def po_negatywnej(self) -> bool:
        """Czy to ponowna ocena po ocenie negatywnej (art. 81 ust. 9 u.s.c., § 7 pkt 2 rozp.)."""
        return self.poprzednia_id is not None and self.poprzednia.wynik == NEGATYWNA


class Nieobecnosc(models.Model):
    """Usprawiedliwiona nieobecność w pracy. Bez przyczyny nieobecności - minimalizacja danych."""

    pracownik = models.ForeignKey(Pracownik, on_delete=models.CASCADE, related_name="nieobecnosci")
    od = models.DateField()
    do = models.DateField()
    usprawiedliwiona = models.BooleanField(default=True)

    class Meta:
        ordering = ["od"]
        verbose_name = "nieobecność"
        verbose_name_plural = "nieobecności"

    def __str__(self) -> str:
        return f"{self.pracownik}: {self.od:%d.%m.%Y}-{self.do:%d.%m.%Y}"

    def clean(self) -> None:
        if self.od and self.do and self.do < self.od:
            raise ValidationError({"do": "Koniec nieobecności nie może być wcześniejszy niż początek."})

    def do_rdzenia(self) -> NieobecnoscRdzenia:
        return NieobecnoscRdzenia(od=self.od, do=self.do, usprawiedliwiona=self.usprawiedliwiona)


class _DziennikQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Dziennik zdarzeń jest tylko do dopisywania - wpisów nie można zmieniać.")

    def delete(self):
        raise ValueError("Dziennik zdarzeń jest tylko do dopisywania - wpisów nie można usuwać.")


class Zdarzenie(models.Model):
    """Dziennik czynności w procesie oceny: kto, kiedy i co zrobił. Tylko dopisywanie."""

    ocena = models.ForeignKey(Ocena, on_delete=models.PROTECT, related_name="zdarzenia")
    uzytkownik = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    podpis = models.CharField("kto (w chwili czynności)", max_length=250, blank=True)
    czas = models.DateTimeField("zapisano", auto_now_add=True)
    data = models.DateField("data czynności")
    czynnosc = models.CharField(max_length=80)
    opis = models.TextField(blank=True)

    objects = _DziennikQuerySet.as_manager()

    class Meta:
        ordering = ["pk"]
        verbose_name = "zdarzenie"
        verbose_name_plural = "dziennik zdarzeń"

    def __str__(self) -> str:
        return f"{self.data:%d.%m.%Y} {self.czynnosc}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Dziennik zdarzeń jest tylko do dopisywania - wpisów nie można zmieniać.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Dziennik zdarzeń jest tylko do dopisywania - wpisów nie można usuwać.")


class WniosekOTermin(models.Model):
    """Wniosek ocenianego o zmianę terminu oceny (art. 81 ust. 8 pkt 4 u.s.c.) - rozpatruje oceniający."""

    OCZEKUJE = "oczekuje"
    UWZGLEDNIONY = "uwzględniony"
    ODRZUCONY = "odrzucony"

    ocena = models.ForeignKey(Ocena, on_delete=models.PROTECT, related_name="wnioski_o_termin")
    data = models.DateField("data złożenia")
    uzasadnienie = models.TextField(blank=True)
    status = models.CharField(max_length=20, default=OCZEKUJE)
    data_rozpatrzenia = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "wniosek o zmianę terminu oceny"
        verbose_name_plural = "wnioski o zmianę terminu oceny"


class Sprzeciw(models.Model):
    """Sprzeciw od oceny okresowej (art. 83 u.s.c.). Puste rozstrzygnięcie oznacza sprzeciw nierozpatrzony."""

    ZMIANA = "zmiana"
    PONOWNE_SPORZADZENIE = "ponowne_sporzadzenie"
    NIEUWZGLEDNIONY = "nieuwzgledniony"
    NAZWY_ROZSTRZYGNIEC = {
        ZMIANA: "uwzględniony - zmiana oceny",
        PONOWNE_SPORZADZENIE: "uwzględniony - ponowne sporządzenie oceny",
        NIEUWZGLEDNIONY: "nieuwzględniony",
    }

    ocena = models.ForeignKey(Ocena, on_delete=models.PROTECT, related_name="sprzeciwy")
    data_wniesienia = models.DateField()
    tresc = models.TextField("treść sprzeciwu")
    po_terminie = models.BooleanField("wniesiony po terminie", default=False)
    rozstrzygniecie = models.CharField(max_length=30, blank=True)
    data_rozstrzygniecia = models.DateField(null=True, blank=True)
    uzasadnienie = models.TextField("uzasadnienie rozstrzygnięcia", blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "sprzeciw"
        verbose_name_plural = "sprzeciwy"

    @property
    def rozpatrzony(self) -> bool:
        return bool(self.rozstrzygniecie)

    @property
    def rozstrzygniecie_opis(self) -> str:
        return self.NAZWY_ROZSTRZYGNIEC.get(self.rozstrzygniecie, "w toku")


class UstaleniaMonitoringu(models.Model):
    """Ustalenia pracodawcy wymagane przed włączeniem danych z EZD RP (art. 22[2] § 6-7 w zw. z art. 22[3] KP).

    Jeden rekord na urząd. Integracja jest domyślnie wyłączona.
    """

    integracja_wlaczona = models.BooleanField("integracja z EZD RP włączona", default=False)
    podstawa = models.TextField("podstawa (układ zbiorowy, regulamin pracy albo obwieszczenie)", blank=True)
    cele = models.TextField("cele", blank=True)
    zakres = models.TextField("zakres", blank=True)
    sposob = models.TextField("sposób zastosowania", blank=True)
    data_poinformowania = models.DateField("data poinformowania pracowników", null=True, blank=True)

    class Meta:
        verbose_name = "ustalenia dotyczące danych z EZD RP"
        verbose_name_plural = "ustalenia dotyczące danych z EZD RP"

    def __str__(self) -> str:
        return "Ustalenia dotyczące danych z EZD RP"

    @classmethod
    def pobierz(cls) -> "UstaleniaMonitoringu":
        return cls.objects.order_by("pk").first() or cls()


class ZdarzenieBezpieczenstwa(models.Model):
    """Dziennik zdarzeń bezpieczeństwa (§ 20 rozporządzenia KRI): logowania, zmiany kont, czynności administratora,
    dostęp do ocen. Tylko dopisywanie. Każdy wpis zawiera skrót poprzedniego - zmiana albo usunięcie wpisu poza
    aplikacją wychodzi przy sprawdzeniu łańcucha (`dziennik.sprawdz_lancuch`)."""

    czas = models.DateTimeField("czas zdarzenia", db_index=True)
    rodzaj = models.CharField("rodzaj zdarzenia", max_length=40, db_index=True)
    uzytkownik = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name="kto wykonał czynność",
    )
    login = models.CharField("login w chwili zdarzenia", max_length=150, blank=True, db_index=True)
    dotyczy = models.CharField("konto albo zasób, którego dotyczy zdarzenie", max_length=150, blank=True)
    adres_ip = models.GenericIPAddressField("adres IP", null=True, blank=True)
    opis = models.TextField(blank=True)
    poprzedni_skrot = models.CharField(max_length=64, blank=True)
    skrot = models.CharField(max_length=64)

    objects = _DziennikQuerySet.as_manager()

    class Meta:
        ordering = ["pk"]
        verbose_name = "zdarzenie bezpieczeństwa"
        verbose_name_plural = "dziennik zdarzeń bezpieczeństwa"

    def __str__(self) -> str:
        return f"{self.czas:%d.%m.%Y %H:%M} {self.rodzaj} {self.login}"

    @property
    def rodzaj_opis(self) -> str:
        from .dziennik import RODZAJE  # import przy użyciu - dziennik korzysta z tego modelu

        return RODZAJE.get(self.rodzaj, self.rodzaj)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Dziennik zdarzeń jest tylko do dopisywania - wpisów nie można zmieniać.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Dziennik zdarzeń jest tylko do dopisywania - wpisów nie można usuwać.")


class GlowaDziennika(models.Model):
    """Jeden wiersz: liczba wpisów i skrót ostatniego wpisu dziennika zdarzeń bezpieczeństwa. Blokada tego wiersza
    ustawia zapisy w kolejce, a jego treść pozwala wykryć usunięcie wpisów z końca dziennika."""

    liczba = models.PositiveBigIntegerField(default=0)
    skrot = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "stan dziennika zdarzeń bezpieczeństwa"
        verbose_name_plural = "stan dziennika zdarzeń bezpieczeństwa"


class UrzadzenieTotp(models.Model):
    """Aplikacja uwierzytelniająca użytkownika - drugi składnik logowania (kody jednorazowe TOTP)."""

    uzytkownik = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp")
    sekret = models.CharField(max_length=64)
    potwierdzone = models.BooleanField("potwierdzone pierwszym kodem", default=False)
    # Krok czasu ostatnio użytego kodu - ten sam kod nie zadziała drugi raz.
    ostatni_krok = models.BigIntegerField(default=0)
    utworzono = models.DateTimeField(auto_now_add=True)
    potwierdzono = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "aplikacja uwierzytelniająca"
        verbose_name_plural = "aplikacje uwierzytelniające"

    def __str__(self) -> str:
        return f"{self.uzytkownik} ({'potwierdzona' if self.potwierdzone else 'niepotwierdzona'})"



class OznaczenieUrzedu(models.Model):
    """Nazwa i przetworzone logo (PNG) do nagłówka; jeden rekord instancji."""
    nazwa = models.CharField(max_length=160)
    logo_png = models.TextField(blank=True)

    @classmethod
    def aktualne(cls):
        return cls.objects.filter(pk=1).first() or cls(pk=1, nazwa=settings.ASYSTENT_URZAD)


class KonfiguracjaProcesu(models.Model):
    """Aktywna kopia przepisów urzędu i wyłączenia funkcji AI. Wersja chroni przed utratą cudzych zmian."""
    wersja = models.PositiveIntegerField(default=0)
    tresc = models.TextField(blank=True)
    wylaczone = models.JSONField(default=list)

    @property
    def toml(self):
        from asystent_ocen.konfiguracja import DOMYSLNY_PLIK
        return self.tresc or DOMYSLNY_PLIK.read_text(encoding="utf-8")

    @classmethod
    def aktualna(cls):
        return cls.objects.filter(pk=1).first() or cls(pk=1)
