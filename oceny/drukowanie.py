"""Wydruki: arkusz oceny (DOCX i PDF) oraz kalendarz terminów (iCalendar).

Treść arkusza i terminów tworzy rdzeń (`asystent_ocen.druk`, `asystent_ocen.ics`). Tutaj są tylko dane spoza
procesu oceny: nazwa urzędu, osoby, poprzednia ocena, stopień służbowy.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from asystent_ocen.druk import DaneArkusza, Osoba, PoprzedniaOcena, generuj_arkusz_docx
from asystent_ocen.ics import kalendarz_ics, wydarzenia_procesu
from asystent_ocen.przebieg import Rola

from .models import Ocena, Pracownik

TYP_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ZNANE_MIEJSCA_KONWERTERA = ("/Applications/LibreOffice.app/Contents/MacOS/soffice", "/usr/bin/soffice")


class BladKonwersji(Exception):
    """Nie udało się przygotować pliku PDF."""


def _osoba(pracownik: Pracownik) -> Osoba:
    return Osoba(pracownik.imie, pracownik.nazwisko, pracownik.stanowisko, pracownik.komorka)


def poprzednia_ocena(ocena: Ocena) -> PoprzedniaOcena | None:
    """Poprzednia ocena: z systemu, a przy pierwszej ocenie w systemie - przepisana ręcznie z papierowego arkusza."""
    if ocena.poprzednia_id is not None and ocena.poprzednia.wynik:
        return PoprzedniaOcena(
            ocena.poprzednia.wynik, ocena.poprzednia.poziom, ocena.poprzednia.proces().data_sporzadzenia
        )
    reczna = ocena.poprzednia_reczna or {}
    if reczna.get("ocena"):
        dzien = date.fromisoformat(reczna["data"]) if reczna.get("data") else None
        return PoprzedniaOcena(str(reczna["ocena"]).upper(), reczna.get("poziom", ""), dzien)
    return None


def dane_arkusza(ocena: Ocena) -> DaneArkusza:
    proces = ocena.proces()
    oceniany = ocena.oceniany
    return DaneArkusza(
        nazwa_urzedu=settings.ASYSTENT_URZAD,
        oceniany=_osoba(oceniany),
        oceniajacy=_osoba(ocena.oceniajacy),
        proces=proces,
        miejscowosc_oceniajacego=settings.ASYSTENT_MIEJSCOWOSC,
        miejscowosc_ocenianego=settings.ASYSTENT_MIEJSCOWOSC,
        poprzednia_ocena=poprzednia_ocena(ocena) if proces.urzednik else None,
        urzad_ma_dyrektora_generalnego=not settings.ASYSTENT_BEZ_DYREKTORA_GENERALNEGO,
        rok_mianowania=oceniany.rok_mianowania if proces.urzednik else None,
        posiadany_stopien=oceniany.stopien_sluzbowy if proces.urzednik else None,
        data_przyznania_stopnia=oceniany.data_stopnia if proces.urzednik else None,
    )


def arkusz_docx(ocena: Ocena) -> bytes:
    return generuj_arkusz_docx(dane_arkusza(ocena))


def nazwa_pliku(ocena: Ocena, rozszerzenie: str) -> str:
    """Nazwa pliku bez danych osobowych - arkusz trafia do katalogu pobranych plików."""
    return f"arkusz-oceny-{ocena.proces().arkusz}-{ocena.pk}.{rozszerzenie}"


def znajdz_konwerter() -> str | None:
    """Program LibreOffice do zamiany DOCX na PDF. Jawne ustawienie ma pierwszeństwo i nie jest zastępowane."""
    wskazany = getattr(settings, "ASYSTENT_SOFFICE", None)
    if wskazany:
        return wskazany if os.path.isfile(wskazany) and os.access(wskazany, os.X_OK) else None
    znaleziony = shutil.which("soffice") or shutil.which("libreoffice")
    if znaleziony:
        return znaleziony
    return next((miejsce for miejsce in _ZNANE_MIEJSCA_KONWERTERA if os.access(miejsce, os.X_OK)), None)


def docx_do_pdf(docx: bytes, limit_czasu: int = 90) -> bytes:
    """Zamienia DOCX na PDF lokalnym LibreOffice (bez wysyłania dokumentu poza serwer)."""
    program = znajdz_konwerter()
    if program is None:
        raise BladKonwersji(
            "Wydruk PDF wymaga programu LibreOffice na serwerze (ustawienie ASYSTENT_SOFFICE). "
            "Pobierz arkusz w formacie DOCX."
        )
    with tempfile.TemporaryDirectory(prefix="asystent-ocen-") as katalog:
        wejscie = Path(katalog) / "arkusz.docx"
        wejscie.write_bytes(docx)
        # Osobny profil na każde wywołanie: konwersja nie koliduje z otwartym LibreOffice ani z innym żądaniem.
        profil = Path(katalog) / "profil"
        polecenie = [
            program, f"-env:UserInstallation={profil.as_uri()}", "--headless", "--norestore",
            "--convert-to", "pdf", "--outdir", katalog, str(wejscie),
        ]
        try:
            subprocess.run(polecenie, check=True, capture_output=True, timeout=limit_czasu)
        except (OSError, subprocess.SubprocessError) as blad:
            raise BladKonwersji("Nie udało się przygotować pliku PDF. Pobierz arkusz w formacie DOCX.") from blad
        wynik = Path(katalog) / "arkusz.pdf"
        if not wynik.is_file():
            raise BladKonwersji("Nie udało się przygotować pliku PDF. Pobierz arkusz w formacie DOCX.")
        return wynik.read_bytes()


def wydarzenia_kalendarza(ocena: Ocena, role: set[Rola]) -> list:
    """Terminy biegnące w tej ocenie. Oceniany dostaje wydarzenia bez swojego nazwiska."""
    tylko_oceniany = role == {Rola.OCENIANY}
    return wydarzenia_procesu(
        ocena.proces(),
        kto="" if tylko_oceniany else ocena.oceniany.imie_i_nazwisko,
        identyfikator=f"ocena-{ocena.pk}",
        po_negatywnej=ocena.po_negatywnej,
        nieobecnosci=[nieobecnosc.do_rdzenia() for nieobecnosc in ocena.oceniany.nieobecnosci.all()],
    )


def kalendarz(ocena: Ocena, role: set[Rola]) -> str | None:
    """Plik iCalendar z terminami oceny; None, gdy na obecnym etapie nie biegnie żaden termin."""
    wydarzenia = wydarzenia_kalendarza(ocena, role)
    if not wydarzenia:
        return None
    return kalendarz_ics(wydarzenia, wytworzono=timezone.now())
