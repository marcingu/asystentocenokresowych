"""Wymaganie: system pobiera wiedzę o pracy pracownika z EZD RP przez Integrator API v2 - tylko do odczytu,
bez treści pism.

Źródła: specyfikacja OpenAPI „Integrator API v2” EZD RP, wersja v2.11.5 z 10.09.2026 (kopia z 4.11.2026):
POST /ezdrp/integrator/v2/sprawy/_search (V2PostSprawyWyszukajQuery, V2PostSprawyWyszukajDto, pageInfo),
GET /ezdrp/integrator/v2/dokumenty/{idDokumentPrzestrzeni}/akceptacje (V2AkceptacjaDokumentuDto,
TypStatusAkceptacji: Zaakceptowany = 1, Odrzucony = 2, Do akceptacji = 3, Anulowany = 4), schematy
bezpieczeństwa Bearer i SID, GET /rejestry/{idRejestr}/wpisy (dane o strukturze zdefiniowanej przez urząd).
Atrapa serwera w tym pliku filtruje sprawy tak, jak opisuje to specyfikacja wyszukiwania.
"""

import dataclasses
from datetime import date

import pytest

from asystent_ocen.ezdrp import (
    BladIntegracji,
    KlientEzdRp,
    MapowanieRejestruOdwolan,
    akceptacja_z_api,
    data_z_api,
    odwolania_z_rejestru,
    sprawa_z_api,
)
from asystent_ocen.wskazniki_pracy import AkceptacjaEzd, Odwolanie, SprawaEzd
from asystent_ocen.zgodnosc import wczytaj_wymogi
from stale import d

SZUKAJ = "/ezdrp/integrator/v2/sprawy/_search"


def rekord_sprawy(nr, wszczecie, termin, status=4, prowadzacy="Anna Nowak (DA.III)"):
    return {
        "idSprawa": f"s{nr}",
        "tytul": f"Sprawa nr {nr}",
        "znak": f"DA.III.4000.{nr}.2025",
        "status": "Zakończona" if status == 4 else "W toku",
        "statusEnum": status,
        "rokZalozenia": 2025,
        "dataRejestracji": f"{wszczecie}T09:12:44",
        "dataWszczecia": f"{wszczecie}T00:00:00",
        "terminZalatwienia": f"{termin}T00:00:00" if termin else None,
        "czasRealizacjiDni": 17,
        "prowadzacy": {"czyAktywny": True, "pelnaPrezentacja": prowadzacy},
        "czyDoPoprawy": False,
    }


REKORD_AKCEPTACJI = {
    "idDokument": "dok-A",
    "idAkceptacjaDokument": "akc-1",
    "idDokumentWersja": "wer-1",
    "wersja": "1",
    "czyZastepstwo": False,
    "osobaAkceptujaca": {"idStanowisko": "st-2", "imie": "Ewa", "nazwisko": "Lis", "stanowisko": "naczelnik"},
    "osobaAkceptujacaZastepstwo": None,
    "dataOperacji": "2025-02-10T10:41:00",
    "opis": "Brak podstawy prawnej w rozstrzygnięciu.",
    "typ": "Odrzucony",
    "typEnum": 2,
}


class AtrapaEzdRp:
    """Sprawy jako pary (rekord, ukryta data zakończenia) - prawdziwe API też nie zwraca daty zakończenia."""

    def __init__(self, sprawy=(), akceptacje=None):
        self.sprawy = list(sprawy)
        self.akceptacje = akceptacje or {}
        self.wywolania = []

    def __call__(self, metoda, sciezka, *, naglowki, json=None):
        self.wywolania.append({"metoda": metoda, "sciezka": sciezka, "naglowki": naglowki, "json": json})
        if (metoda, sciezka) == ("POST", SZUKAJ):
            pasujace = [r for r, koniec in self.sprawy if self._pasuje(r, koniec, json)]
            nr, rozmiar = json["pageInfo"]["pageNumber"], json["pageInfo"]["pageSize"]
            return {
                "lista": pasujace[(nr - 1) * rozmiar : nr * rozmiar],
                "pageInfo": {"pageNumber": nr, "pageSize": rozmiar, "isNextPageExists": nr * rozmiar < len(pasujace)},
            }
        if metoda == "GET" and sciezka.startswith("/ezdrp/integrator/v2/dokumenty/") and sciezka.endswith("/akceptacje"):
            return {"lista": self.akceptacje.get(sciezka.split("/")[-2], [])}
        raise AssertionError(f"Klient użył operacji spoza dozwolonych: {metoda} {sciezka}")

    @staticmethod
    def _pasuje(rekord, koniec, q):
        def dzien(klucz):
            return date.fromisoformat(q[klucz][:10])

        if "prowadzacySprawe" in q and q["prowadzacySprawe"] not in rekord["prowadzacy"]["pelnaPrezentacja"]:
            return False
        if q.get("status") not in (None, 0) and q["status"] != rekord["statusEnum"]:
            return False
        wszczecie = date.fromisoformat(rekord["dataWszczecia"][:10])
        if "dataWszczeciaOd" in q and wszczecie < dzien("dataWszczeciaOd"):
            return False
        if "dataWszczeciaDo" in q and wszczecie > dzien("dataWszczeciaDo"):
            return False
        if "dataZakonczeniaOd" in q and (koniec is None or koniec < dzien("dataZakonczeniaOd")):
            return False
        if "dataZakonczeniaDo" in q and (koniec is None or koniec > dzien("dataZakonczeniaDo")):
            return False
        return True


def klient(atrapa, **kw):
    return KlientEzdRp(atrapa, token=lambda: "TOKEN-1", sid="st-7", **kw)


SPRAWY_W_EZD = [
    (rekord_sprawy(1, "2025-02-03", "2025-03-05"), d(2025, 2, 20)),
    (rekord_sprawy(2, "2025-04-01", "2025-05-01"), d(2025, 5, 15)),
    (rekord_sprawy(3, "2025-04-14", "2025-05-14"), d(2025, 5, 15)),
    (rekord_sprawy(4, "2026-10-01", "2026-10-31", status=1), None),
    (rekord_sprawy(5, "2025-03-03", "2025-04-02", prowadzacy="Jan Inny (DA.II)"), d(2025, 3, 20)),
]


# --- mapowanie rekordów API ---

def test_rekord_sprawy_z_wyszukiwarki_jest_mapowany_na_sprawe():
    assert sprawa_z_api(rekord_sprawy(1, "2025-02-03", "2025-03-05")) == SprawaEzd(
        id="s1",
        znak="DA.III.4000.1.2025",
        tytul="Sprawa nr 1",
        status="zakończona",
        data_wszczecia=d(2025, 2, 3),
        termin_zalatwienia=d(2025, 3, 5),
        data_zakonczenia=None,
        czas_realizacji_dni=17,
        do_poprawy=False,
    )


def test_sprawa_bez_terminu_zalatwienia_i_w_toku():
    s = sprawa_z_api(rekord_sprawy(4, "2026-10-01", None, status=1))
    assert (s.status, s.termin_zalatwienia) == ("w toku", None)


def test_nieznany_status_sprawy_jest_bledem_integracji():
    """Lepiej zatrzymać import niż policzyć wskaźnik z błędnie rozpoznanego statusu."""
    with pytest.raises(BladIntegracji):
        sprawa_z_api(rekord_sprawy(1, "2025-02-03", "2025-03-05", status=99))


def test_rekord_akceptacji_jest_mapowany_razem_z_uwaga_przelozonego():
    assert akceptacja_z_api(REKORD_AKCEPTACJI) == AkceptacjaEzd(
        id_dokumentu="dok-A",
        wynik="odrzucony",
        data=d(2025, 2, 10),
        akceptujacy="Ewa Lis",
        opis="Brak podstawy prawnej w rozstrzygnięciu.",
        wersja="1",
    )


@pytest.mark.parametrize("kod, wynik", [(1, "zaakceptowany"), (2, "odrzucony"), (3, "do akceptacji"), (4, "anulowany")])
def test_wyniki_akceptacji_odpowiadaja_slownikowi_api(kod, wynik):
    assert akceptacja_z_api({**REKORD_AKCEPTACJI, "typEnum": kod, "opis": None}).wynik == wynik
    assert akceptacja_z_api({**REKORD_AKCEPTACJI, "typEnum": kod, "opis": None}).opis == ""


def test_nieznany_wynik_akceptacji_jest_bledem_integracji():
    with pytest.raises(BladIntegracji):
        akceptacja_z_api({**REKORD_AKCEPTACJI, "typEnum": 9})


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize(
    "napis, oczekiwana",
    [
        ("2025-02-03T09:12:44", d(2025, 2, 3)),
        ("2025-02-03T09:12:44.1234567", d(2025, 2, 3)),
        ("2025-02-03", d(2025, 2, 3)),
        ("2025-02-02T23:30:00Z", d(2025, 2, 3)),
        ("2025-06-30T22:30:00+00:00", d(2025, 7, 1)),
        ("", None),
        (None, None),
    ],
)
def test_daty_z_api_sa_liczone_w_czasie_polskim(napis, oczekiwana):
    """Specyfikacja podaje tylko format date-time. Czas ze strefą przeliczamy na Europe/Warsaw, żeby północ
    nie przesuwała daty o dzień; czas bez strefy bierzemy wprost."""
    assert data_z_api(napis) == oczekiwana


# --- klient: wyszukiwanie spraw ---

def test_wyszukiwanie_spraw_wysyla_kryteria_i_naglowki_zgodne_ze_specyfikacja():
    atrapa = AtrapaEzdRp(SPRAWY_W_EZD)
    wynik = klient(atrapa).szukaj_spraw(
        prowadzacy="Anna Nowak", wszczete_od=d(2025, 1, 1), wszczete_do=d(2025, 12, 31)
    )
    assert [s.znak for s in wynik] == ["DA.III.4000.1.2025", "DA.III.4000.2.2025", "DA.III.4000.3.2025"]
    (wywolanie,) = atrapa.wywolania
    assert (wywolanie["metoda"], wywolanie["sciezka"]) == ("POST", SZUKAJ)
    assert wywolanie["naglowki"]["Authorization"] == "Bearer TOKEN-1"
    assert wywolanie["naglowki"]["SID"] == "st-7"
    assert wywolanie["json"] == {
        "prowadzacySprawe": "Anna Nowak",
        "dataWszczeciaOd": "2025-01-01T00:00:00",
        "dataWszczeciaDo": "2025-12-31T23:59:59",
        "pageInfo": {"pageNumber": 1, "pageSize": 50},
    }


def test_wyszukiwanie_pobiera_wszystkie_strony_wynikow():
    atrapa = AtrapaEzdRp(SPRAWY_W_EZD)
    male_strony = dataclasses.replace(wczytaj_wymogi(), ezdrp_rozmiar_strony=2)
    wynik = klient(atrapa, wymogi=male_strony).szukaj_spraw(wszczete_od=d(2025, 1, 1), wszczete_do=d(2026, 12, 31))
    assert len(wynik) == 5
    assert [w["json"]["pageInfo"] for w in atrapa.wywolania] == [
        {"pageNumber": 1, "pageSize": 2},
        {"pageNumber": 2, "pageSize": 2},
        {"pageNumber": 3, "pageSize": 2},
    ]


def test_odpowiedz_bez_listy_jest_bledem_integracji():
    with pytest.raises(BladIntegracji):
        klient(lambda metoda, sciezka, *, naglowki, json=None: {"blad": "Problem z logowaniem"}).szukaj_spraw(status=4)


# --- klient: dokładne daty zakończenia spraw ---

def test_daty_zakonczenia_spraw_sa_ustalane_przez_podzial_okna_wyszukiwania():
    """API nie zwraca daty zakończenia sprawy - jest tylko filtr dataZakonczeniaOd/Do. Klient zawęża okno,
    aż każda sprawa trafi do okna jednodniowego."""
    atrapa = AtrapaEzdRp(SPRAWY_W_EZD)
    wynik = klient(atrapa).sprawy_zakonczone("Anna Nowak", d(2025, 1, 1), d(2026, 12, 31))
    assert [(s.znak, s.data_zakonczenia) for s in wynik] == [
        ("DA.III.4000.1.2025", d(2025, 2, 20)),
        ("DA.III.4000.2.2025", d(2025, 5, 15)),
        ("DA.III.4000.3.2025", d(2025, 5, 15)),
    ]
    assert all(s.status == "zakończona" for s in wynik)


def test_podzial_okna_wymaga_wielokrotnie_mniej_zapytan_niz_pytanie_o_kazdy_dzien():
    """Okres ma 730 dni, a różne dni zakończenia są dwa - wystarcza kilkadziesiąt zapytań."""
    atrapa = AtrapaEzdRp(SPRAWY_W_EZD)
    klient(atrapa).sprawy_zakonczone("Anna Nowak", d(2025, 1, 1), d(2026, 12, 31))
    assert len(atrapa.wywolania) < 100
    assert all(w["json"]["status"] == 4 and w["json"]["prowadzacySprawe"] == "Anna Nowak" for w in atrapa.wywolania)


def test_brak_spraw_zakonczonych_konczy_sie_na_jednym_zapytaniu():
    atrapa = AtrapaEzdRp(SPRAWY_W_EZD)
    assert klient(atrapa).sprawy_zakonczone("Nikt Taki", d(2025, 1, 1), d(2026, 12, 31)) == []
    assert len(atrapa.wywolania) == 1


# --- klient: akceptacje ---

def test_akceptacje_dokumentu_sa_pobierane_z_wlasciwej_sciezki():
    atrapa = AtrapaEzdRp(akceptacje={"dok-A": [REKORD_AKCEPTACJI, {**REKORD_AKCEPTACJI, "typEnum": 1, "opis": None}]})
    wynik = klient(atrapa).akceptacje_dokumentu("dok-A")
    assert [a.wynik for a in wynik] == ["odrzucony", "zaakceptowany"]
    (wywolanie,) = atrapa.wywolania
    assert (wywolanie["metoda"], wywolanie["sciezka"]) == ("GET", "/ezdrp/integrator/v2/dokumenty/dok-A/akceptacje")
    assert wywolanie["naglowki"] == {"Authorization": "Bearer TOKEN-1", "SID": "st-7"}


def test_token_jest_pobierany_przy_kazdym_zadaniu():
    """Token SSO wygasa - klient nie może go zapamiętywać na stałe."""
    tokeny = iter(["T1", "T2"])
    atrapa = AtrapaEzdRp()
    k = KlientEzdRp(atrapa, token=lambda: next(tokeny), sid="st-7")
    k.akceptacje_dokumentu("dok-A")
    k.akceptacje_dokumentu("dok-B")
    assert [w["naglowki"]["Authorization"] for w in atrapa.wywolania] == ["Bearer T1", "Bearer T2"]


# --- odwołania z rejestru własnego urzędu ---

MAPOWANIE = MapowanieRejestruOdwolan(
    pole_znak_sprawy="Znak sprawy I instancji",
    pole_wynik="Rozstrzygnięcie organu II instancji",
    pole_data="Data rozstrzygnięcia",
    utrzymana=("utrzymano w mocy",),
    uchylona=("uchylono", "uchylono i przekazano do ponownego rozpatrzenia"),
    zmieniona=("zmieniono",),
)


def wpis(znak, wynik, data):
    return {"Znak sprawy I instancji": znak, "Rozstrzygnięcie organu II instancji": wynik, "Data rozstrzygnięcia": data}


def test_wynik_odwolania_pochodzi_z_rejestru_wlasnego_urzedu():
    """Integrator API nie ma pola o wyniku odwołania - urząd wskazuje rejestr własny i nazwy jego pól."""
    wpisy = [
        wpis("DA.III.4000.1.2025", "Utrzymano w mocy", "2025-06-30"),
        wpis("DA.III.4000.3.2025", " uchylono i przekazano do ponownego rozpatrzenia ", "15.09.2025"),
        wpis("DA.III.4000.4.2025", "zmieniono", "2025-10-20T00:00:00"),
        wpis("DA.III.4000.6.2026", None, None),
        wpis("DA.III.4000.7.2026", "umorzono postępowanie odwoławcze", "2026-11-03"),
        wpis("", "utrzymano w mocy", "2026-11-03"),
    ]
    assert odwolania_z_rejestru(wpisy, MAPOWANIE) == [
        Odwolanie("DA.III.4000.1.2025", "utrzymana", d(2025, 6, 30)),
        Odwolanie("DA.III.4000.3.2025", "uchylona", d(2025, 9, 15)),
        Odwolanie("DA.III.4000.4.2025", "zmieniona", d(2025, 10, 20)),
        Odwolanie("DA.III.4000.6.2026", "w toku", None),
        Odwolanie("DA.III.4000.7.2026", "nierozpoznany", d(2026, 11, 3)),
    ]
