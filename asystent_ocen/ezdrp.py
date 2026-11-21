"""Integracja z EZD RP przez Integrator API v2 - tylko odczyt metadanych spraw i akceptacji dokumentów.

Źródło: specyfikacja OpenAPI „Integrator API v2”, wersja v2.11.5 z 10.09.2026.
Używane operacje (prefiks z `zgodnosc.toml`: /ezdrp/integrator/v2):
- POST /sprawy/_search - kryteria m.in. prowadzacySprawe, status, dataWszczeciaOd/Do, dataZakonczeniaOd/Do,
  pageInfo {pageNumber, pageSize}; odpowiedź {lista: [...], pageInfo: {pageNumber, isNextPageExists, ...}};
- GET /dokumenty/{idDokumentPrzestrzeni}/akceptacje - odpowiedź {lista: [...]}.
Uwierzytelnienie: nagłówki `Authorization: Bearer <token>` i `SID: <identyfikator stanowiska>`.

Ograniczenia API, które ten moduł uwzględnia:
- rekord sprawy nie zawiera daty zakończenia (jest tylko filtr dataZakonczeniaOd/Do), dlatego dokładną datę
  ustala się przez podział okna wyszukiwania (`KlientEzdRp.sprawy_zakonczone`);
- API nie ma pola o wyniku odwołania; wynik bierze się z rejestru własnego urzędu (`odwolania_z_rejestru`).
Moduł nie pobiera treści pism ani korespondencji (art. 22[3] § 2 KP) i niczego w EZD RP nie zapisuje.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .wskazniki_pracy import (
    NIEROZPOZNANY,
    ODWOLANIE_W_TOKU,
    UCHYLONA,
    UTRZYMANA,
    ZMIENIONA,
    AkceptacjaEzd,
    Odwolanie,
    SprawaEzd,
)
from .zgodnosc import Wymogi, wczytaj_wymogi

# transport(metoda, sciezka, *, naglowki: dict[str, str], json: dict | None = None) -> dict
Transport = Callable[..., dict]

_STREFA_POLSKA = "Europe/Warsaw"
_POCZATEK_DNIA = "00:00:00"
_KONIEC_DNIA = "23:59:59"
_DATA_DD_MM_RRRR = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


class BladIntegracji(Exception):
    """Odpowiedź EZD RP niezgodna ze specyfikacją albo nieznana wartość słownikowa."""


def data_z_api(wartosc: str | None) -> date | None:
    """Zamienia napis date-time z API na datę. None i pusty napis -> None. Czas z przesunięciem strefowym
    (także „Z”) jest najpierw przeliczany na czas polski (Europe/Warsaw); czas bez strefy bierze się wprost."""
    if wartosc is None:
        return None
    if not isinstance(wartosc, str):
        raise BladIntegracji(f"Data z EZD RP nie jest napisem: {wartosc!r}.")
    napis = wartosc.strip()
    if not napis:
        return None
    try:
        chwila = datetime.fromisoformat(napis)
    except ValueError as blad:
        raise BladIntegracji(f"Nieprawidłowa data z EZD RP: {wartosc!r}.") from blad
    if chwila.tzinfo is not None:
        chwila = chwila.astimezone(ZoneInfo(_STREFA_POLSKA))
    return chwila.date()


def sprawa_z_api(rekord: dict, wymogi: Wymogi | None = None) -> SprawaEzd:
    """Rekord V2PostSprawyWyszukajDto / V2GetSprawaDto -> SprawaEzd.
    Mapowanie: idSprawa -> id, znak, tytul, statusEnum -> status (słownik `ezdrp_statusy_sprawy`; nieznany kod
    -> BladIntegracji), dataWszczecia -> data_wszczecia, terminZalatwienia -> termin_zalatwienia,
    czasRealizacjiDni -> czas_realizacji_dni, czyDoPoprawy -> do_poprawy. Data zakończenia pozostaje None.

    Rekord bez idSprawa albo bez daty wszczęcia -> BladIntegracji (bez daty wszczęcia nie da się policzyć czasu
    załatwienia)."""
    wymogi = _wymogi(wymogi)
    id_sprawy = _wymagane(rekord, "idSprawa", "sprawy")
    wszczecie = data_z_api(rekord.get("dataWszczecia"))
    if wszczecie is None:
        raise BladIntegracji(f"Sprawa {id_sprawy}: brak daty wszczęcia (dataWszczecia).")
    return SprawaEzd(
        id=id_sprawy,
        znak=rekord.get("znak") or "",
        tytul=rekord.get("tytul") or "",
        status=_ze_slownika(wymogi.ezdrp_statusy_sprawy, rekord.get("statusEnum"), f"status sprawy {id_sprawy}"),
        data_wszczecia=wszczecie,
        termin_zalatwienia=data_z_api(rekord.get("terminZalatwienia")),
        czas_realizacji_dni=rekord.get("czasRealizacjiDni"),
        do_poprawy=bool(rekord.get("czyDoPoprawy")),
    )


def akceptacja_z_api(rekord: dict, wymogi: Wymogi | None = None) -> AkceptacjaEzd:
    """Rekord V2AkceptacjaDokumentuDto -> AkceptacjaEzd.
    Mapowanie: idDokument -> id_dokumentu, typEnum -> wynik (słownik `ezdrp_wyniki_akceptacji`; nieznany kod
    -> BladIntegracji), dataOperacji -> data, osobaAkceptujaca.imie + nazwisko -> akceptujacy,
    opis -> opis (None -> ""), wersja -> wersja.

    Rekord bez idDokument albo bez dataOperacji (pola wymagane w specyfikacji) -> BladIntegracji."""
    wymogi = _wymogi(wymogi)
    id_dokumentu = _wymagane(rekord, "idDokument", "akceptacji")
    data = data_z_api(rekord.get("dataOperacji"))
    if data is None:
        raise BladIntegracji(f"Akceptacja dokumentu {id_dokumentu}: brak daty operacji (dataOperacji).")
    osoba = rekord.get("osobaAkceptujaca")
    if not isinstance(osoba, dict):
        osoba = {}
    wersja = rekord.get("wersja")
    return AkceptacjaEzd(
        id_dokumentu=id_dokumentu,
        wynik=_ze_slownika(
            wymogi.ezdrp_wyniki_akceptacji, rekord.get("typEnum"), f"wynik akceptacji dokumentu {id_dokumentu}"
        ),
        data=data,
        akceptujacy=" ".join(czesc for czesc in (_napis(osoba.get("imie")), _napis(osoba.get("nazwisko"))) if czesc),
        opis=rekord.get("opis") or "",
        wersja=None if wersja is None else str(wersja),
    )


@dataclass(frozen=True)
class MapowanieRejestruOdwolan:
    """Nazwy pól i wartości w rejestrze własnym urzędu (GET /rejestry/{idRejestr}/wpisy zwraca dane o strukturze
    zdefiniowanej przez urząd, dlatego mapowanie jest konfiguracją wdrożenia)."""

    pole_znak_sprawy: str
    pole_wynik: str
    pole_data: str
    utrzymana: tuple[str, ...]
    uchylona: tuple[str, ...]
    zmieniona: tuple[str, ...] = ()


def odwolania_z_rejestru(wpisy: Iterable[dict], mapowanie: MapowanieRejestruOdwolan) -> list[Odwolanie]:
    """Wpisy rejestru własnego -> lista Odwolanie. Wartość pola wyniku porównuje się bez rozróżniania wielkości
    liter i skrajnych odstępów. Pusty wynik (None, "") -> „w toku”; wartość spoza mapowania -> „nierozpoznany”.
    Data: napis ISO (RRRR-MM-DD, także z czasem) albo DD.MM.RRRR; brak -> None. Wpis bez znaku sprawy jest pomijany.

    Data w innym zapisie -> BladIntegracji (odwołanie bez daty wypadłoby po cichu ze wskaźnika)."""
    wyniki = _slownik_wynikow(mapowanie)
    odwolania = []
    for wpis in wpisy:
        znak = _napis(wpis.get(mapowanie.pole_znak_sprawy))
        if not znak:
            continue
        opis_wyniku = _napis(wpis.get(mapowanie.pole_wynik))
        wynik = wyniki.get(opis_wyniku.casefold(), NIEROZPOZNANY) if opis_wyniku else ODWOLANIE_W_TOKU
        odwolania.append(Odwolanie(znak, wynik, _data_z_rejestru(wpis.get(mapowanie.pole_data), znak)))
    return odwolania


class KlientEzdRp:
    """Klient tylko do odczytu. `token()` jest wywoływany przy każdym żądaniu (pozwala odświeżać token).

    Klient wywołuje transport wyłącznie w dwóch miejscach: POST {prefiks}/sprawy/_search (`szukaj_spraw`)
    i GET {prefiks}/dokumenty/{id}/akceptacje (`akceptacje_dokumentu`)."""

    def __init__(self, transport: Transport, *, token: Callable[[], str], sid: str, wymogi: Wymogi | None = None):
        self._transport = transport
        self._token = token
        self._sid = sid
        self._wymogi = _wymogi(wymogi)
        self._prefiks = self._wymogi.ezdrp_prefiks.rstrip("/")

    def szukaj_spraw(
        self,
        *,
        prowadzacy: str | None = None,
        status: int | None = None,
        wszczete_od: date | None = None,
        wszczete_do: date | None = None,
        zakonczone_od: date | None = None,
        zakonczone_do: date | None = None,
    ) -> list[SprawaEzd]:
        """POST /sprawy/_search ze stronicowaniem. W treści żądania tylko podane kryteria:
        prowadzacySprawe, status, dataWszczeciaOd/dataZakonczeniaOd jako „RRRR-MM-DDT00:00:00”,
        dataWszczeciaDo/dataZakonczeniaDo jako „RRRR-MM-DDT23:59:59” oraz pageInfo {pageNumber, pageSize}.
        Pierwsza strona = `ezdrp_pierwsza_strona`; kolejna = pageInfo.pageNumber z odpowiedzi + 1, dopóki
        pageInfo.isNextPageExists. Odpowiedź bez klucza `lista` -> BladIntegracji.

        Żeby nie zwrócić po cichu niepełnych wyników: pełna strona bez informacji isNextPageExists albo numer
        kolejnej strony, który nie rośnie -> BladIntegracji."""
        kryteria: dict = {}
        if prowadzacy is not None:
            kryteria["prowadzacySprawe"] = prowadzacy
        if status is not None:
            kryteria["status"] = status
        for klucz, dzien, godzina in (
            ("dataWszczeciaOd", wszczete_od, _POCZATEK_DNIA),
            ("dataWszczeciaDo", wszczete_do, _KONIEC_DNIA),
            ("dataZakonczeniaOd", zakonczone_od, _POCZATEK_DNIA),
            ("dataZakonczeniaDo", zakonczone_do, _KONIEC_DNIA),
        ):
            if dzien is not None:
                kryteria[klucz] = f"{dzien.year:04d}-{dzien.month:02d}-{dzien.day:02d}T{godzina}"

        sciezka = f"{self._prefiks}/sprawy/_search"
        rozmiar = self._wymogi.ezdrp_rozmiar_strony
        strona = self._wymogi.ezdrp_pierwsza_strona
        sprawy: list[SprawaEzd] = []
        while True:
            # treść budowana od nowa dla każdej strony - transport może zachować przekazany słownik
            tresc = {**kryteria, "pageInfo": {"pageNumber": strona, "pageSize": rozmiar}}
            odpowiedz = self._transport("POST", sciezka, naglowki=self._naglowki(), json=tresc)
            lista = _lista_z_odpowiedzi(odpowiedz, f"POST {sciezka}")
            sprawy.extend(sprawa_z_api(rekord, self._wymogi) for rekord in lista)
            info = odpowiedz.get("pageInfo")
            if not isinstance(info, dict):
                info = {}
            jest_kolejna = info.get("isNextPageExists")
            if jest_kolejna is None and len(lista) >= rozmiar:
                raise BladIntegracji(
                    f"Odpowiedź EZD RP na POST {sciezka} nie podaje pageInfo.isNextPageExists, a strona wyników "
                    "jest pełna - nie można ustalić, czy są kolejne wyniki."
                )
            if not jest_kolejna or not lista:
                return sprawy
            numer = info.get("pageNumber")
            if not isinstance(numer, int) or isinstance(numer, bool) or numer + 1 <= strona:
                raise BladIntegracji(
                    f"Stronicowanie POST {sciezka} nie postępuje: zażądano strony {strona}, "
                    f"odpowiedź podaje pageNumber = {numer!r}."
                )
            strona = numer + 1

    def sprawy_zakonczone(self, prowadzacy: str, od: date, do: date) -> list[SprawaEzd]:
        """Sprawy prowadzącego zakończone w okresie [od, do], z dokładną `data_zakonczenia`.
        Metoda podziału okna: zapytanie o cały okres (status = `ezdrp_status_sprawy_zakonczona`); okno bez
        wyników kończy gałąź; okno jednodniowe wyznacza datę; w pozostałych przypadkach okno dzieli się na pół.
        Liczba zapytań jest rzędu 2 x log2(liczba dni) na każdy różny dzień zakończenia, a nie liczba dni okresu.
        Wynik w kolejności (data zakończenia, znak).

        Sprawa widoczna w oknie, której nie zwraca żadna z jego połówek -> BladIntegracji (zamiast pominięcia)."""
        if od > do:
            raise ValueError(f"Początek okresu ({od}) jest późniejszy niż jego koniec ({do}).")
        return sorted(self._zakonczone_w_oknie(prowadzacy, od, do), key=lambda s: (s.data_zakonczenia, s.znak))

    def _zakonczone_w_oknie(self, prowadzacy: str, od: date, do: date) -> list[SprawaEzd]:
        sprawy = self.szukaj_spraw(
            prowadzacy=prowadzacy,
            status=self._wymogi.ezdrp_status_sprawy_zakonczona,
            zakonczone_od=od,
            zakonczone_do=do,
        )
        if not sprawy:
            return []
        if od == do:
            return [replace(sprawa, data_zakonczenia=od) for sprawa in sprawy]
        srodek = od + timedelta(days=(do - od).days // 2)
        z_datami = self._zakonczone_w_oknie(prowadzacy, od, srodek) + self._zakonczone_w_oknie(
            prowadzacy, srodek + timedelta(days=1), do
        )
        bez_daty = sorted({s.id for s in sprawy} - {s.id for s in z_datami})
        if bez_daty:
            raise BladIntegracji(
                f"Nie udało się ustalić daty zakończenia spraw {', '.join(bez_daty)}: są w oknie "
                f"{od} - {do}, ale nie zwraca ich żadna z jego połówek."
            )
        return z_datami

    def akceptacje_dokumentu(self, id_dokumentu: str) -> list[AkceptacjaEzd]:
        """GET /dokumenty/{id_dokumentu}/akceptacje -> lista akceptacji w kolejności z odpowiedzi."""
        # identyfikator trafia do ścieżki jako jeden zakodowany segment, żeby nie mógł zmienić wywoływanej operacji
        if not isinstance(id_dokumentu, str) or not id_dokumentu.strip().strip("."):
            raise ValueError(f"Nieprawidłowy identyfikator dokumentu: {id_dokumentu!r}.")
        sciezka = f"{self._prefiks}/dokumenty/{quote(id_dokumentu.strip(), safe='')}/akceptacje"
        odpowiedz = self._transport("GET", sciezka, naglowki=self._naglowki())
        return [akceptacja_z_api(rekord, self._wymogi) for rekord in _lista_z_odpowiedzi(odpowiedz, f"GET {sciezka}")]

    def _naglowki(self) -> dict[str, str]:
        # token pobierany przy każdym żądaniu (może wygasnąć) i nigdzie niezapamiętywany
        return {"Authorization": f"Bearer {self._token()}", "SID": self._sid}


def _wymogi(wymogi: Wymogi | None) -> Wymogi:
    """Przekazane wymogi mają pierwszeństwo; bez nich obowiązuje plik z pakietu."""
    return wczytaj_wymogi() if wymogi is None else wymogi


def _napis(wartosc: object) -> str:
    return "" if wartosc is None else str(wartosc).strip()


def _wymagane(rekord: object, pole: str, czego: str) -> str:
    """Identyfikator z rekordu API jako napis; rekord niebędący obiektem albo bez pola -> BladIntegracji."""
    if not isinstance(rekord, dict):
        raise BladIntegracji(f"Rekord {czego} z EZD RP nie jest obiektem: {type(rekord).__name__}.")
    wartosc = _napis(rekord.get(pole))
    if not wartosc:
        raise BladIntegracji(f"Rekord {czego} z EZD RP nie ma pola {pole}.")
    return wartosc


def _ze_slownika(slownik: dict[int, str], kod: object, czego: str) -> str:
    # bool jest w Pythonie podtypem int (True == 1), a nie jest kodem słownikowym
    if not isinstance(kod, int) or isinstance(kod, bool) or kod not in slownik:
        raise BladIntegracji(f"Nieznany {czego}: kod {kod!r} spoza słownika w zgodnosc.toml.")
    return slownik[kod]


def _lista_z_odpowiedzi(odpowiedz: object, operacja: str) -> list:
    if not isinstance(odpowiedz, dict) or not isinstance(odpowiedz.get("lista"), list):
        # same nazwy kluczy - treść odpowiedzi mogłaby zawierać dane osobowe
        klucze = sorted(map(str, odpowiedz)) if isinstance(odpowiedz, dict) else type(odpowiedz).__name__
        raise BladIntegracji(
            f"Odpowiedź EZD RP na {operacja} nie zawiera listy wyników w polu `lista` (klucze odpowiedzi: {klucze})."
        )
    return odpowiedz["lista"]


def _slownik_wynikow(mapowanie: MapowanieRejestruOdwolan) -> dict[str, str]:
    """Wartości z rejestru (bez wielkości liter i skrajnych odstępów) -> wynik odwołania."""
    slownik: dict[str, str] = {}
    for wynik, wartosci in (
        (UTRZYMANA, mapowanie.utrzymana),
        (UCHYLONA, mapowanie.uchylona),
        (ZMIENIONA, mapowanie.zmieniona),
    ):
        # pojedynczy napis zamiast krotki (brak przecinka) rozpadłby się na litery
        for wartosc in (wartosci,) if isinstance(wartosci, str) else wartosci:
            klucz = _napis(wartosc).casefold()
            if slownik.setdefault(klucz, wynik) != wynik:
                raise ValueError(
                    f"Mapowanie rejestru odwołań: wartość „{wartosc}” przypisano do dwóch wyników "
                    f"({slownik[klucz]} i {wynik})."
                )
    return slownik


def _data_z_rejestru(wartosc: object, znak: str) -> date | None:
    napis = _napis(wartosc)
    if not napis:
        return None
    try:
        dopasowanie = _DATA_DD_MM_RRRR.fullmatch(napis)
        if dopasowanie:
            dzien, miesiac, rok = (int(czesc) for czesc in dopasowanie.groups())
            return date(rok, miesiac, dzien)
        return data_z_api(napis)
    except (ValueError, BladIntegracji) as blad:
        raise BladIntegracji(
            f"Rejestr odwołań, sprawa {znak}: nieprawidłowa data {wartosc!r} (oczekiwano RRRR-MM-DD albo DD.MM.RRRR)."
        ) from blad
