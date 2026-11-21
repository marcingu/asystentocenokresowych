"""Nazwa i logo urzędu: domyślnie lokalne godło, zmiany tylko w administracji."""
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from .test_administracja import Podstawa
from .test_widoki import klient

ADRES = "/administracja/urzad/"


class UstawieniaTest(Podstawa):
    def test_domyslne_godlo(self):
        self.assertContains(self.client.get("/logowanie/"), "/static/oceny/godlo.svg")

    def test_kadry_nie_zmieniaja(self):
        self.assertEqual(klient(self.z.kadry).post(ADRES, {"nazwa": "Inny urząd"}).status_code, 403)

    def test_zapis_nazwy_i_lokalnego_logo(self):
        bufor = BytesIO()
        Image.new("RGB", (20, 30)).save(bufor, "PNG")
        obraz = SimpleUploadedFile("logo.png", bufor.getvalue(), content_type="image/png")
        self.assertEqual(self.przegladarka.post(ADRES, {"nazwa": "Urząd Testowy", "logo": obraz}).status_code, 302)
        odpowiedz = self.client.get("/logowanie/")
        self.assertContains(odpowiedz, "Urząd Testowy")
        self.assertContains(odpowiedz, 'src="data:image/png;base64,')
        self.przegladarka.post(ADRES, {"nazwa": "Urząd po zmianie"})
        self.assertContains(self.client.get("/logowanie/"), 'src="data:image/png;base64,')
        self.przegladarka.post(ADRES, {"nazwa": "Urząd po zmianie", "domyslne": "on"})
        self.assertContains(self.client.get("/logowanie/"), "/static/oceny/godlo.svg")

    def test_odrzuca_nieprawidlowy_plik_bez_zmiany_nazwy(self):
        plik = SimpleUploadedFile("logo.png", b"to nie jest obraz", content_type="image/png")
        self.assertContains(self.przegladarka.post(ADRES, {"nazwa": "Inny urząd", "logo": plik}), "Popraw")
        self.assertNotContains(self.client.get("/logowanie/"), "Inny urząd")
