"""Wypełnienie oryginalnych wzorów z gov.pl; numeracja akapitów dotyczy plików z wzory/ZRODLA.md."""
from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from lxml import etree

from asystent_ocen.kalendarz import dodaj_miesiace
from .models import OznaczenieUrzedu
from .umowy import DZIEN, koniec_okresu


def _data(wartosc):
    if isinstance(wartosc, str):
        wartosc = date.fromisoformat(wartosc)
    return wartosc.strftime("%d.%m.%Y") if wartosc else ""


def _okres(od, do):
    return f"od {_data(od)} do {_data(do)}" if od and do else ""


def dokument(ocena, rodzaj):
    if rodzaj not in ("arkusz", "sprawozdanie"):
        raise ValueError("Nieznany wzór")
    umowa, dane = ocena.umowa, ocena.dane
    rozmowa, raport, wynik = (dane.get(kod, {}) for kod in ("wstepna", "raport", "ocena"))
    termin = _okres(rozmowa.get("od"), rozmowa.get("do"))
    nazwa = OznaczenieUrzedu.aktualne().nazwa
    pola = {}

    def osoba(nr, kto):
        if kto:
            for i, wartosc in enumerate((kto.imie, kto.nazwisko, kto.komorka, kto.stanowisko)):
                pola[nr + i * 2] = wartosc

    if rodzaj == "sprawozdanie":
        pola.update({7: nazwa, 19: termin, 23: raport.get("tresc")})
        osoba(11, umowa.osoba)
    else:
        pola.update({8: nazwa, 20: _data(dane.get("ustalenie", umowa.poczatek)), 45: _data(rozmowa.get("rozmowa")),
                     47: termin, 49: _okres(koniec_okresu(umowa.poczatek, 8) + DZIEN, dodaj_miesiace(umowa.koniec, -1))})
        osoba(12, umowa.osoba)
        osoba(24, ocena.szef)
        osoba(34, ocena.kierujacy)
        if wynik:
            pola.update({69: _data(wynik["rozmowa"]), 121: str(wynik["srednia"]).replace(".", ","),
                         146: wynik.get("uzasadnienie"), 164: wynik.get("rozwoj"),
                         {"tak": 126, "nie": 128}.get(wynik["egzamin"], 130): "X",
                         134 if wynik["na_czas"] else 136: "X", 140 if wynik["wynik"] == "Pozytywna" else 142: "X"})
            for i in range(5):
                pola[101 + i * 4 + (3, 5, 7).index(wynik[f"pkt{i}"])] = "X"
    # Podpisów, odbioru kopii i dat potwierdzenia nie wpisuje się za uczestników.
    wynik_docx = BytesIO()
    with ZipFile(Path(__file__).parent / "wzory" / (rodzaj + ".docx")) as wzor, ZipFile(wynik_docx, "w") as plik:
        for wpis in wzor.infolist():
            zawartosc = wzor.read(wpis)
            if wpis.filename == "word/document.xml":
                xml = parse_xml(zawartosc)
                # Urzędowy DOCX ma papier Letter; A4 bez zmiany szerokości tabel zapobiega
                # rozdzieleniu linii podpisu od jej opisu podczas wydruku w LibreOffice.
                for sekcja in xml.xpath(".//w:sectPr"):
                    rozmiar, margines = sekcja.find(qn("w:pgSz")), sekcja.find(qn("w:pgMar"))
                    rozmiar.set(qn("w:w"), "11906")
                    rozmiar.set(qn("w:h"), "16838")
                    margines.set(qn("w:left"), "967")
                    margines.set(qn("w:right"), "967")
                akapity = xml.xpath(".//w:body//w:p")
                for nr, wartosc in pola.items():
                    if wartosc:
                        Paragraph(akapity[nr], None).text = wartosc
                zawartosc = etree.tostring(xml, encoding="UTF-8", xml_declaration=True, standalone=True)
            plik.writestr(wpis, zawartosc)
    return wynik_docx.getvalue()
