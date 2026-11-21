"""Bieżący przełożony z wydziału; oceniający trwającej oceny pozostaje bez zmian."""
from django.urls import reverse

from oceny.models import Pracownik, Wydzial
from .test_administracja import Podstawa
from .test_kadry_pracownik import NOWY, dane
from .test_struktura import ADRES
from .test_widoki import klient


class PodlegloscTest(Podstawa):
    def ustaw(self, wydzial, szef, zwierzchnik=None):
        return self.przegladarka.post(ADRES, {"akcja": "obsada", "pk": wydzial.pk,
            "kierownik": szef.pk, "zwierzchnik": zwierzchnik.pk if zwierzchnik else ""}, follow=True)

    def test_kadry_nie_wybieraja_przelozonego_i_nie_podmienia_go_w_post(self):
        wydzial = self.z.ola.wydzial
        self.ustaw(wydzial, self.z.szef)
        kadry = klient(self.z.kadry)
        self.assertNotContains(kadry.get(NOWY), 'name="przelozony"')
        self.assertContains(kadry.get(NOWY), 'data-szef="Szef Testowy"')
        r = kadry.post(NOWY, dane(przelozony=self.z.obcy.pk))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Pracownik.objects.get(nazwisko="Nowicki").przelozony, self.z.szef)

    def test_zmiana_komorki_aktualizuje_szefa(self):
        drugi = Wydzial.objects.create(nazwa="Drugi")
        self.ustaw(drugi, self.z.obcy)
        klient(self.z.kadry).post(reverse("kadry_pracownik", args=[self.z.ola.pk]), dane(wydzial=drugi.pk))
        self.z.ola.refresh_from_db()
        self.assertEqual(self.z.ola.przelozony, self.z.obcy)

    def test_zmiana_obsady_nie_przepisuje_trwajacej_oceny(self):
        ocena = self.z.nowa_ocena()
        self.ustaw(self.z.ola.wydzial, self.z.obcy)
        self.z.ola.refresh_from_db(); self.z.obcy.refresh_from_db(); ocena.refresh_from_db()
        self.assertEqual(self.z.ola.przelozony, self.z.obcy)
        self.assertIsNone(self.z.obcy.przelozony_id)
        self.assertEqual(ocena.oceniajacy, self.z.szef)

    def test_szef_ma_zwierzchnika_a_nie_siebie(self):
        kierownictwo = Wydzial.objects.create(nazwa="Kierownictwo")
        Pracownik.objects.filter(pk=self.z.obcy.pk).update(wydzial=kierownictwo)
        self.ustaw(self.z.ola.wydzial, self.z.szef, self.z.obcy)
        self.z.szef.refresh_from_db()
        self.assertEqual(self.z.szef.przelozony, self.z.obcy)
        wynik = self.ustaw(kierownictwo, self.z.szef)
        self.assertContains(wynik, "pętlę")
        self.z.obcy.refresh_from_db()
        self.assertIsNone(self.z.obcy.przelozony_id)

    def test_brak_obsady_nie_pozwala_podac_wlasnego_szefa(self):
        pusty = Wydzial.objects.create(nazwa="Bez obsady")
        kadry = klient(self.z.kadry)
        wynik = kadry.post(NOWY, dane(wydzial=pusty.pk, przelozony=self.z.obcy.pk), follow=True)
        self.assertContains(wynik, "Nie wyznaczono przełożonego")
        self.assertIsNone(Pracownik.objects.get(nazwisko="Nowicki").przelozony)
