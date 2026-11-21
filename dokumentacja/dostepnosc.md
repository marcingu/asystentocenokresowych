# Dostępność cyfrowa (WCAG)

## Wymaganie

Interfejs systemu i dokumenty, które system generuje, spełniają wymagania dostępności cyfrowej na poziomie WCAG 2.1 AA.

- **Miara:** załącznik do ustawy z dnia 4 kwietnia 2019 r. o dostępności cyfrowej stron internetowych i aplikacji mobilnych podmiotów publicznych (t.j. Dz. U. z 2023 r. poz. 1440) - „Wytyczne dla dostępności treści internetowych 2.1”, 49 kryteriów sukcesu na poziomach A i AA. Odsyła do niego art. 5 ust. 1 ustawy.
- **Dlaczego dotyczy systemu wewnętrznego:** ustawę stosuje się do stron internetowych podmiotów publicznych (art. 2), a stroną jest zbiór elementów prezentowanych w przeglądarce pod jednolitym adresem (art. 4 pkt 10). Z treści w intranecie wyłączone są tylko opublikowane przed 23 września 2019 r. i od tego czasu nieprzebudowane (art. 3 ust. 2 pkt 6). To odczytanie przepisów przez zespół - kwalifikację potwierdza prawnik urzędu przy wdrożeniu.
- **Dlaczego wersja 2.1:** aktualnym zaleceniem W3C jest WCAG 2.2 (od 5 października 2023 r., https://www.w3.org/TR/WCAG22/), ale ustawa wskazuje wersję 2.1. Wymaganie mierzymy załącznikiem do ustawy.
- **Decyzja:** prowadzący projekt, 21.11.2026.

## Stan na 21.11.2026

| Co sprawdzono | Jak | Wynik |
|---|---|---|
| Reguły WCAG 2.0 i 2.1 (A, AA) oraz dobre praktyki | axe-core 4.14.1 w przeglądarce (HeadlessChrome 156), 71 stron: wszystkie strony dostępne 11 kontom pokazowym, logowanie i strona błędu | 0 naruszeń, 0 pozycji do ręcznej oceny; 51 reguł ocenionych, 30 857 sprawdzeń elementów |
| Czy audyt wykrywa błędy | próba kontrolna: do strony wstrzyknięto obraz bez opisu, pole bez etykiety, pusty przycisk, pusty link i tekst o za małym kontraście | wszystkie pięć wykryte |
| Układ przy 320 px, czyli powiększenie 400% (1.4.10) | pomiar szerokości strony i położenia elementów na 70 stronach | żadna strona nie przewija się w poziomie; przewija się tylko obszar szerokiej tabeli |
| Odstępy w tekście (1.4.12) | odstępy z kryterium wymuszone stylem na 10 stronach przy 1280 px i 6 stronach przy 320 px | nic nie jest ucięte ani nie wystaje poza kartę |
| Kontrast tekstu, ramek pól i obrysu fokusu (1.4.3, 1.4.11) | test liczy kontrast z arkusza stylów wzorem WCAG | najsłabsza para tekstu 4,97:1; ramka pola co najmniej 3,66:1; obrys fokusu co najmniej 5,13:1 na każdym tle |
| Fokus z klawiatury (2.4.1, 2.4.3, 2.4.7) | 16 kolejnych naciśnięć Tab na karcie oceny | pierwszy przystanek to „Przejdź do treści”; każdy element jest widoczny i ma obrys |
| Wydruk arkusza | `pdfinfo` i odczyt pliku | PDF ma znaczniki struktury, tytuł i język polski; DOCX ma tytuł i język polski |

Testy automatyczne: `oceny/tests/test_dostepnosc.py` (kontrola znaczników na wszystkich stronach pokazu i kontrast z arkusza stylów) oraz `test_tresc_dokumentu_ma_jezyk_polski` w `tests/test_druk_arkusza.py`.

## Usterki znalezione i usunięte 21.11.2026

Żadnej z nich nie wykrył automat axe - wyszły w pomiarach i przeglądzie.

1. **1.4.10 Dopasowanie do ekranu.** Przy 320 px tabele rozpychały stronę i tekst był ucinany (8 z 10 zmierzonych stron). Tabele przewijają się teraz we własnym obszarze, do którego da się wejść klawiaturą; kolumny układu mogą się zwężać; etykieta stanu zawija się poza tabelą.
2. **1.4.11 Kontrast elementów nietekstowych.** Obrys fokusu miał 2,07:1 na białym tle. Jest dwukolorowy: jasny obrys widać na ciemnym nagłówku, ciemną obwódkę na jasnych kartach.
3. **1.4.11.** Ramka pola wyszukiwania miała 3,07:1 na białym i 2,54:1 na najciemniejszym z jasnych teł. Wszystkie pola mają jedną ramkę o kontraście co najmniej 3,66:1.
4. **1.4.3 Kontrast.** Mały tekst na pasku pokazowym po najechaniu miał 4,43:1 (teraz 5,18:1). Kolor podpowiedzi w polu ustawia arkusz (6,00:1), bo domyślny zależy od przeglądarki.
5. **1.4.1 Użycie koloru.** Stan terminu na karcie oceny pokazywał tylko kolor obramowania. Jest podany tekstem („wykonano”, „zostało 5 dni”).
6. **4.1.3 Komunikaty o stanie.** Komunikat „Model pracuje...” był odkrywany razem z treścią, czego czytniki ekranu zwykle nie ogłaszają. Miejsce na komunikat jest w stronie od początku, a tekst wpisuje skrypt.
7. **3.1.1 Język strony.** Wydruk DOCX i PDF miał język angielski (z szablonu biblioteki). Ma polski.
8. **2.4.2 Tytuł strony.** Karty dwóch ocen tej samej osoby miały ten sam tytuł. Tytuł zawiera początek okresu oceny.
9. **1.3.1 Informacje i relacje.** Cztery tabele nie miały nazwy. Każda tabela ma podpis.

## Czego nie sprawdzono

- **Czytnik ekranu.** Nie było testu z NVDA, JAWS ani VoiceOver. Automat i kontrola znaczników wykrywają tylko część barier, więc zgodności z WCAG nie można uznać za potwierdzoną bez takiego testu.
- **Pełne przejście klawiaturą.** Sprawdzona jest próbka (16 przystanków na jednej stronie), nie każdy formularz od początku do końca.
- **2.2.1 Dostosowanie czasu.** Sesja wygasa po 8 godzinach, bez ostrzeżenia i bez możliwości przedłużenia; WCAG zwalnia z tego wymogu limity dłuższe niż 20 godzin. Do rozstrzygnięcia przy wdrożeniu: ostrzeżenie z przedłużeniem sesji albo logowanie przez system tożsamości urzędu.
- **Struktura wydruku.** Język, tytuł i obecność znaczników PDF są sprawdzone; poprawność nagłówków i tabel w DOCX i PDF nie. Układ arkusza wynika ze wzoru w rozporządzeniu.
- **Panel administratora** (`/admin/`, wbudowany w Django) - poza kontrolą.
- **Podpis szerokiej tabeli przy 320 px** bywa widoczny w części; resztę widać po przewinięciu obszaru tabeli.
- **Deklaracja dostępności** (art. 10 ustawy) to obowiązek urzędu, który wdraża system. System jej nie tworzy.

## Jak powtórzyć kontrolę

```
.venv/bin/python manage.py test oceny.tests.test_dostepnosc
```

Kontrola w przeglądarce: axe-core albo rozszerzenie axe DevTools na każdej stronie pokazu, okno zwężone do 320 px, przejście klawiszem Tab. Biblioteka axe-core (licencja MPL-2.0) jest narzędziem kontroli - nie jest częścią repozytorium ani zależnością systemu.

## Zasady dla nowych ekranów

- Tabela stoi w obszarze `przewijana` (`role="region"`, `tabindex="0"`, nazwa z podpisu tabeli) i ma podpis oraz nagłówki z zakresem.
- Każde pole ma etykietę, każdy przycisk i link nazwę.
- Stan podaje tekst; kolor tylko go wzmacnia.
- Kolory pochodzą ze zmiennych arkusza stylów; nowy kolor musi przejść test kontrastu.
- Tekst bez zawijania jest dozwolony tylko w tabeli.
- Komunikat pojawiający się bez przeładowania strony trafia do elementu `role="status"`, który jest w stronie od początku.
