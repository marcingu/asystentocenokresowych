# Cyfrowy asystent ocen okresowych

Prototyp na HackNation 2026 (wyzwanie KPRM). System prowadzi ocenę okresową w służbie cywilnej od wyznaczenia kryteriów do skutków oceny: pilnuje terminów, sprawdza arkusz i przy każdym komunikacie podaje podstawę prawną.

## Stan na 21.11.2026

Gotowe i pokryte testami (476 testów):

- rdzeń reguł: terminy liczone według Kodeksu cywilnego, arkusze A/B/C i kryteria, wynik oceny, skutki oceny, stopnie służbowe, sprzeciw, przebieg procesu z rolami,
- integracja z EZD RP (tylko odczyt) i wskaźniki pracy liczone jawnymi regułami,
- wymogi Kodeksu pracy, RODO i AI Act zapisane jako konfiguracja, z bramkami w kodzie,
- wydruk arkusza oceny do DOCX i eksport terminów do kalendarza (iCalendar).

W budowie: aplikacja webowa (Django), asystent AI na lokalnym modelu PLLuM, instalacja jednym poleceniem.

## Założenia

- **Prawo w konfiguracji, nie w kodzie.** Parametry przepisów są w `asystent_ocen/przepisy.toml`, wymogi zgodności w `asystent_ocen/zgodnosc.toml`. Zmiana przepisu to zmiana pliku.
- **AI nie ocenia pracownika.** Rejestr funkcji AI w `zgodnosc.toml` dopuszcza odpowiedzi na pytania o procedurę i korektę językową. Funkcji wysokiego ryzyka nie da się włączyć w tej wersji.
- **Dane zostają w urzędzie.** Model językowy ma działać lokalnie, a aplikacja nie pobiera zasobów z internetu.
- **Tylko licencje permisywne.** Django (BSD-3-Clause), python-docx (MIT).

## Testy

```
python3 -m venv .venv
.venv/bin/pip install "django>=5.2,<5.3" "python-docx>=1.2" pytest python-dateutil
.venv/bin/python -m pytest -q
```

Wymagany Python 3.11 lub nowszy. Reguły oparte na interpretacji albo decyzji zespołu (35 testów) mają znaczniki `interpretacja` i `decyzja_projektowa`:

```
.venv/bin/python -m pytest --collect-only -q -m "interpretacja or decyzja_projektowa"
```

## Układ repozytorium

| Katalog | Zawartość |
|---|---|
| `asystent_ocen/` | rdzeń reguł - czyste funkcje, bez bazy danych i interfejsu |
| `tests/` | testy rdzenia; każdy cytuje przepis albo wymaganie |
| `dokumentacja/` | architektura, decyzje i interpretacje, analiza prawna |

## Podstawy prawne

- ustawa z dnia 21 listopada 2008 r. o służbie cywilnej (t.j. Dz. U. z 2026 r. poz. 590),
- rozporządzenie Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych urzędników służby cywilnej i pracowników służby cywilnej (Dz. U. poz. 470),
- Kodeks cywilny, art. 110-116 (terminy).
