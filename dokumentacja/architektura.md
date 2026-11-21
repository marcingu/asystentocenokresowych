# Architektura - Cyfrowy Asystent Ocen Okresowych

Stan: 21.11.2026. Dokument jest kontraktem dla wykonawców poszczególnych części.

## 1. Zasady

1. **Prawo tylko w rdzeniu.** Reguły są w pakiecie `asystent_ocen/` (czyste funkcje, bez Django) oraz w `przepisy.toml` i `zgodnosc.toml`. Aplikacja webowa niczego nie liczy sama: woła rdzeń i pokazuje wynik razem z podstawą prawną z obiektu `Blad` albo `Skutek`.
2. **Jedno źródło stanu procesu.** Stan oceny to obiekt `asystent_ocen.przebieg.ProcesOceny`, zapisywany w bazie jako JSON. Każda czynność: wczytaj proces, wywołaj metodę rdzenia z rolą użytkownika, zapisz proces i wpis w dzienniku zdarzeń.
3. **Bez zasobów zewnętrznych w przeglądarce.** Żadnych CDN, czcionek ani bibliotek JS z internetu - system ma działać w sieci urzędu bez dostępu do internetu. Zwykłe formularze HTML renderowane po stronie serwera.
4. **Tylko licencje permisywne.** Django 5.2 LTS (BSD-3-Clause), python-docx (MIT). Nowa zależność wymaga uzgodnienia.
5. **TDD.** Najpierw test, potem kod. Testy cytują wymaganie albo przepis.
6. **Dane demonstracyjne są fikcyjne.** Żadnych prawdziwych osób ani urzędów.

## 2. Układ katalogów (korzeń repozytorium)

```
manage.py
serwis/            ustawienia projektu Django: settings.py, urls.py, wsgi.py
oceny/             aplikacja: models.py, uslugi.py, uprawnienia.py, czas.py, views.py, urls.py, forms.py,
                   templates/oceny/, static/oceny/, management/commands/, tests/
asystent_ocen/     rdzeń reguł (bez Django)
tests/             testy rdzenia (pytest)
dokumentacja/
```

## 3. Środowisko

- Interpreter: `.venv/bin/python` (Python 3.12, Django 5.2.19, python-docx 1.2.0, pytest 9.2.0). Nie instalować nowych pakietów.
- Testy rdzenia: `.venv/bin/python -m pytest -q -p no:cacheprovider`
- Testy aplikacji: `.venv/bin/python manage.py test oceny`
- Baza: SQLite, plik `db.sqlite3` (poza repozytorium). Strefa czasowa `Europe/Warsaw`, język `pl`.
- Ustawienia ze zmiennych środowiskowych: `ASYSTENT_SECRET_KEY`, `ASYSTENT_DEBUG` (domyślnie wyłączony), `ASYSTENT_ALLOWED_HOSTS`, `ASYSTENT_TRYB_DEMO` (domyślnie wyłączony), `ASYSTENT_DZIS` (opcjonalna data RRRR-MM-DD zastępująca dzisiejszą - do pokazów i testów).

## 4. Zapis procesu: `asystent_ocen/zapis.py`

```python
WERSJA_ZAPISU = 1
def proces_do_slownika(proces: ProcesOceny) -> dict      # wynik przechodzi przez json.dumps bez dodatkowych koderów
def proces_ze_slownika(dane: dict) -> ProcesOceny       # nieznana wersja zapisu -> ValueError
```

- Daty jako `RRRR-MM-DD`, wyliczenia (`Rola`, `Etap`) jako wartości, `Fraction` jako napis `licznik/mianownik`.
- Zagnieżdżone: `WynikOceny`, `Formularz`, listy `Notatka` i `Dokument`, `oceny_anulowane`.
- Pole `przepisy` nie jest zapisywane (po wczytaniu `None`, czyli przepisy domyślne).
- Wymóg: `proces_ze_slownika(proces_do_slownika(p)) == p` dla procesu na każdym etapie.

## 5. Modele (`oceny/models.py`)

| Model | Pola | Uwagi |
|---|---|---|
| `Pracownik` | `uzytkownik` (OneToOne do `auth.User`, opcjonalne), `imie`, `nazwisko`, `stanowisko`, `komorka`, `rodzaj_zatrudnienia`, `kierownik_urzedu`, `kieruje_pracownikami`, `przelozony` (FK do siebie), `data_zatrudnienia`, `stopien_sluzbowy`, `data_stopnia`, `identyfikator_ezd`, `rola_kadry`, `rola_dyrektor` | `rodzaj_zatrudnienia` przyjmuje wartości z `przepisy.toml`. Właściwości `urzednik`, `arkusz`, `podlega_ocenie` wołają rdzeń (`kryteria.wybierz_arkusz`, `kryteria.czy_podlega_ocenie`) |
| `Ocena` | `oceniany`, `oceniajacy` (FK do `Pracownik`), `poprzednia` (FK do siebie), `stan` (JSONField z `proces_do_slownika`), kopie do zapytań: `etap`, `termin`, `poczatek_cyklu`; `utworzono`, `zmieniono` | Metody `proces()` i `zapisz_proces(p)` |
| `Nieobecnosc` | `pracownik`, `od`, `do`, `usprawiedliwiona` | Bez przyczyny nieobecności (minimalizacja danych) |
| `Zdarzenie` | `ocena`, `uzytkownik`, `czas`, `czynnosc`, `opis` | Dziennik czynności; tylko dopisywanie |

## 6. Role i uprawnienia (`oceny/uprawnienia.py`)

Role z rdzenia (`przebieg.Rola`) wynikają z relacji użytkownika do konkretnej oceny:

- `OCENIANY` - użytkownik jest ocenianym,
- `OCENIAJACY` - użytkownik jest oceniającym,
- `ZARZADZAJACY` - `Pracownik.rola_kadry`,
- `ADMIN` - `User.is_superuser`.

Dodatkowo `rola_dyrektor` daje dostęp do statystyk zbiorczych (bez danych osób).

Zasady: `role_uzytkownika(user, ocena) -> set[Rola]`; każdy widok czynności deklaruje rolę, w której działa, i odmawia, gdy użytkownik jej nie ma. Oceny, do której użytkownik nie ma żadnej roli, nie widać (odpowiedź 404). Notatki oceniającego widzi wyłącznie oceniający. Niezalogowany trafia na stronę logowania.

## 7. Usługi (`oceny/uslugi.py`)

Cienka warstwa: jedna funkcja na czynność procesu (wyznaczenie kryteriów, potwierdzenie kryteriów, notatka, zmiana terminu, wniosek o zmianę terminu, sporządzenie oceny, potwierdzenie zapoznania, stwierdzenie fikcji zapoznania, uwzględnienie sprzeciwu, rozpoczęcie kolejnego cyklu). Każda działa w transakcji, wywołuje metodę `ProcesOceny`, zapisuje stan i dopisuje `Zdarzenie`. Wyjątki rdzenia (`BladWalidacji`, `BladUprawnien`, `BladEtapu`) nie są połykane: widok pokazuje komunikat i podstawę prawną.

Terminy pokazywane użytkownikowi liczy wyłącznie rdzeń: `terminy.termin_wyznaczenia_kryteriow`, `terminy.termin_oceny` (z nieobecnościami z bazy), `terminy.termin_sprzeciwu`, `skutki.skutki_oceny`, `przypomnienia.przypomnienia_na_dzien`. Dzisiejszą datę podaje `oceny/czas.py: dzis()` (uwzględnia `ASYSTENT_DZIS`).

## 8. Widoki

| Adres | Kto | Co |
|---|---|---|
| `/logowanie/`, `/wyloguj/` | wszyscy | W trybie demo lista kont demonstracyjnych do szybkiego przełączania ról |
| `/` | zalogowany | „Moje zadania”: czynności do wykonania z terminami i stanem (po terminie, pilne, w toku) |
| `/oceny/<id>/` | strony oceny, kadry | Przebieg oceny krok po kroku, dozwolone czynności dla roli, terminy z podstawą prawną, dziennik zdarzeń |
| `/oceny/<id>/<czynnosc>/` | według roli | Formularze czynności z walidacją rdzenia |
| `/kadry/` | kadry | Wszyscy pracownicy, stan cyklu, terminy, alerty; dodanie nieobecności; rozpoczęcie cyklu |
| `/kadry/kontrola-arkusza/` | kadry | Kontrola arkusza wypełnionego ręcznie: oceny, wpisana średnia, poziom i wynik -> lista niespójności (`wynik.niespojnosci_arkusza`, `kryteria.bledy_kryteriow_dodatkowych`) |
| `/statystyki/` | dyrektor, kadry | Liczby zbiorcze: oceny według etapu i poziomu, terminy w najbliższych 30 dniach, przeterminowane |
| `/przepisy/` | zalogowany | Aktualne parametry z `przepisy.toml` z podstawami prawnymi (pokazuje, że zmiana prawa to zmiana konfiguracji) |
| `/admin/` | administrator | Panel Django do korekt |

Kolejne etapy (osobni wykonawcy): druk arkusza i eksport terminów (`asystent_ocen/druk.py`, `asystent_ocen/ics.py`), karta faktów z EZD RP, asystent AI.

## 9. Dane demonstracyjne

Polecenie `manage.py demo` tworzy fikcyjny urząd z kilkunastoma pracownikami i ocenami na różnych etapach, liczonymi względem `dzis()`: kryteria do wyznaczenia, kryteria do potwierdzenia, ocena z terminem za kilkanaście dni, ocena po terminie, termin przedłużony długą nieobecnością, ocena do zapoznania, ocena negatywna z biegnącym terminem sprzeciwu, urzędnik ze stopniem obligatoryjnym, arkusz A i B. Polecenie jest powtarzalne (drugie uruchomienie nie dubluje danych).
