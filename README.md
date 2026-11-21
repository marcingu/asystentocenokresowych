# Cyfrowy asystent ocen okresowych

Prototyp na HackNation 2026 (wyzwanie KPRM). System prowadzi ocenę okresową w służbie cywilnej od wyznaczenia kryteriów do skutków oceny: pilnuje terminów, sprawdza arkusz i przy każdym komunikacie podaje podstawę prawną.

## Pokaz w jednym poleceniu

```
./uruchom-demo.sh
```

Skrypt tworzy środowisko Pythona, instaluje dwie zależności, zakłada bazę z fikcyjnym urzędem i uruchamia serwer pod adresem `http://127.0.0.1:8000/`. Na pasku u góry strony wybiera się osobę (oceniany, przełożony, kadry, dyrektor) - konta pokazowe nie mają haseł i działają tylko w trybie demonstracyjnym.

Wymagany Python 3.11 lub nowszy. Wydruk PDF wymaga LibreOffice na serwerze; bez niego arkusz pobiera się jako DOCX. Asystent AI wymaga lokalnego modelu w Ollamie; bez niego reszta systemu działa bez zmian.

Opcje: `./uruchom-demo.sh --od-nowa` buduje bazę pokazową od początku, `./uruchom-demo.sh 8080` zmienia port.

## Co działa (stan na 21.11.2026)

- **Przebieg oceny** dla arkuszy A, B i C: kryteria i termin (część I), rozmowa i ocena (część II), wniosek o stopień służbowy (część III), zapoznanie z oceną, sprzeciw i jego rozstrzygnięcie, kolejny cykl.
- **Moje zadania**: każda osoba widzi, co ma zrobić, do kiedy i na jakiej podstawie prawnej. Terminy liczone według Kodeksu cywilnego, z dniami wolnymi i przedłużeniem o długie nieobecności.
- **Wynik liczony z przepisów**: średnia, poziom i ocena pozytywna albo negatywna. Formularz nie pozwala zatwierdzić oceny z brakami i mówi, czego brakuje.
- **Skutki oceny**: ponowna ocena po negatywnej, termin nowych kryteriów, stopień służbowy z mocy prawa.
- **Role i poufność**: oceniany, oceniający, kadry, dyrektor, administrator. Notatki i szkic oceny widzi tylko oceniający. Statystyki są zbiorcze, bez nazwisk.
- **Wydruk arkusza** zgodnego ze wzorem z rozporządzenia (PDF do podpisu, DOCX) i terminy do kalendarza (iCalendar).
- **Asystent AI** na lokalnym modelu PLLuM: odpowiada na pytania o procedurę, wskazuje przepisy i ostrzega, gdy odpowiedź modelu powołuje przepis albo liczbę spoza źródeł.
- **Projekt uzasadnienia z notatek**: na karcie oceny model układa notatki przełożonego w tekst uzasadnienia. Dostaje wyłącznie notatki - bez ocen cząstkowych i danych z EZD RP. Projekt jest oznaczony jako tekst AI, nie zapisuje się sam, a do formularza przenosi go oceniający.
- **Kontekst z EZD RP**: karta faktów o sprawach ocenianego za okres oceny (liczba spraw, terminowość, akceptacje pism), jawna dla obu stron, bez punktów i rankingów. Włącza ją komórka kadr po spełnieniu warunków Kodeksu pracy. W pokazie karta działa na danych przykładowych; klient Integrator API jest w rdzeniu, przetestowany na atrapie i jeszcze niepodłączony do karty.

Testy: 628 testów rdzenia i 213 testów aplikacji.

## Założenia

- **Prawo w konfiguracji, nie w kodzie.** Parametry przepisów są w `asystent_ocen/przepisy.toml`, wymogi zgodności w `asystent_ocen/zgodnosc.toml`. Zmiana przepisu to zmiana pliku. Aplikacja pokazuje ten plik na stronie „Przepisy”.
- **AI nie ocenia pracownika.** Rejestr funkcji AI w `zgodnosc.toml` dopuszcza odpowiedzi na pytania o procedurę, korektę językową i ułożenie notatek oceniającego w projekt uzasadnienia. Model nie dostaje ocen ani danych z EZD RP. Funkcji wysokiego ryzyka nie da się włączyć w tej wersji.
- **Dane zostają w urzędzie.** Model językowy działa lokalnie, a strony nie pobierają niczego z internetu (wymusza to polityka treści w nagłówkach odpowiedzi).
- **Tylko licencje permisywne.** Django (BSD-3-Clause), python-docx (MIT), model PLLuM-12B-chat (Apache-2.0).
- **Dostępność cyfrowa jest wymaganiem.** Interfejs i wydruki mają spełniać WCAG 2.1 na poziomach A i AA, czyli załącznik do ustawy o dostępności cyfrowej. Automatyczny audyt 71 stron pokazu nie wykazuje naruszeń, a strony działają przy szerokości 320 px. Testu z czytnikiem ekranu jeszcze nie było - stan kontroli i znane braki opisuje `dokumentacja/dostepnosc.md`.

## Testy

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest python-dateutil
.venv/bin/python -m pytest -q
.venv/bin/python manage.py test oceny
```

Reguły oparte na interpretacji albo decyzji zespołu mają znaczniki `interpretacja` i `decyzja_projektowa`:

```
.venv/bin/python -m pytest --collect-only -q -m "interpretacja or decyzja_projektowa"
```

Sprawdzian modelu językowego (test odbiorczy przy wymianie modelu):

```
.venv/bin/python -m asystent_ocen.sprawdzian_modelu --adres http://localhost:11434 --model pllum-12b-chat-2512:q4_k_m
```

## Ustawienia wdrożenia

Wszystko, co zależy od urzędu, ustawia się zmiennymi środowiskowymi z prefiksem `ASYSTENT_` (pełna lista w `serwis/settings.py`). Najważniejsze:

| Zmienna | Znaczenie |
|---|---|
| `ASYSTENT_SECRET_KEY` | klucz sesji - wymagany we wdrożeniu |
| `ASYSTENT_ALLOWED_HOSTS` | nazwy, pod którymi działa serwis |
| `ASYSTENT_HTTPS` | `1`, gdy serwis działa przez HTTPS (ciasteczka tylko po HTTPS, HSTS) |
| `ASYSTENT_URZAD`, `ASYSTENT_MIEJSCOWOSC` | nazwa urzędu i miejscowość na wydrukach |
| `ASYSTENT_BAZA` | plik bazy danych |
| `ASYSTENT_OLLAMA_ADRES`, `ASYSTENT_MODEL` | lokalny model językowy |
| `ASYSTENT_TRYB_DEMO` | `1` włącza konta pokazowe - nigdy we wdrożeniu |

Skrypt `uruchom-demo.sh` używa serwera deweloperskiego Django i służy do pokazu. We wdrożeniu aplikację uruchamia się przez serwer WSGI za serwerem pośredniczącym z HTTPS.

## Układ repozytorium

| Katalog | Zawartość |
|---|---|
| `asystent_ocen/` | rdzeń reguł - czyste funkcje, bez bazy danych i interfejsu |
| `oceny/` | aplikacja webowa: modele, usługi, widoki, szablony, dane pokazowe |
| `serwis/` | ustawienia projektu Django |
| `tests/` | testy rdzenia; każdy cytuje przepis albo wymaganie |
| `oceny/tests/` | testy aplikacji: role, dostęp, przebieg oceny przez przeglądarkę |
| `dokumentacja/` | architektura, decyzje i interpretacje, analiza prawna, dostępność cyfrowa |

## Podstawy prawne

- ustawa z dnia 21 listopada 2008 r. o służbie cywilnej (t.j. Dz. U. z 2026 r. poz. 590),
- rozporządzenie Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych urzędników służby cywilnej i pracowników służby cywilnej (Dz. U. poz. 470),
- Kodeks cywilny, art. 110-116 (terminy),
- ustawa z dnia 4 kwietnia 2019 r. o dostępności cyfrowej stron internetowych i aplikacji mobilnych podmiotów publicznych (t.j. Dz. U. z 2023 r. poz. 1440) - wymagania WCAG 2.1.
