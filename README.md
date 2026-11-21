# Cyfrowy asystent ocen okresowych

Prototyp na HackNation 2026 (wyzwanie KPRM). System prowadzi ocenę okresową w służbie cywilnej od wyznaczenia kryteriów do skutków oceny: pilnuje terminów, sprawdza arkusz i przy każdym komunikacie podaje podstawę prawną.

## Pokaz w jednym poleceniu

```
./uruchom-demo.sh
```

Skrypt tworzy środowisko Pythona, instaluje zależności, zakłada bazę z fikcyjnym urzędem i uruchamia serwer pod adresem `http://127.0.0.1:8000/`. Na pasku u góry strony wybiera się osobę (oceniany, przełożony, kadry, dyrektor) - konta pokazowe nie mają haseł i działają tylko w trybie demonstracyjnym.

Wymagany Python 3.11 lub nowszy. Wydruk PDF wymaga LibreOffice na serwerze; bez niego arkusz pobiera się jako DOCX. Asystent AI wymaga lokalnego modelu w Ollamie; bez niego reszta systemu działa bez zmian.

Opcje: `./uruchom-demo.sh --od-nowa` buduje bazę pokazową od początku, `./uruchom-demo.sh 8080` zmienia port.

Pokaz włącza - wyłącznie na danych fikcyjnych - trzy funkcje modelu językowego: sugestię ocen cząstkowych, propozycję kierunków do IPRZ i pytania do kart obserwacji radaru. To funkcje wysokiego ryzyka według AI Act, po instalacji wyłączone (patrz „Założenia”). Wpisy pokazowe nie zawierają analiz, które urząd wykonuje przed włączeniem, i poza trybem demonstracyjnym niczego nie włączają. Pokaz bez tych funkcji: `ASYSTENT_DECYZJE_AI= ./uruchom-demo.sh`.

## Co działa (stan na 21.11.2026)

- **Przebieg oceny** dla arkuszy A, B i C: kryteria i termin (część I), rozmowa i ocena (część II), wniosek o stopień służbowy (część III), zapoznanie z oceną, sprzeciw i jego rozstrzygnięcie, kolejny cykl.
- **Moje zadania**: każda osoba widzi, co ma zrobić, do kiedy i na jakiej podstawie prawnej. Terminy liczone według Kodeksu cywilnego, z dniami wolnymi i przedłużeniem o długie nieobecności.
- **Wynik liczony z przepisów**: średnia, poziom i ocena pozytywna albo negatywna. Formularz nie pozwala zatwierdzić oceny z brakami i mówi, czego brakuje.
- **Skutki oceny**: ponowna ocena po negatywnej, termin nowych kryteriów, stopień służbowy z mocy prawa.
- **Sprzeciw od oceny**: oceniany wnosi go w systemie, a rozstrzyga dyrektor generalny urzędu (art. 83 u.s.c.). Dyrektor widzi tylko oceny, od których wniesiono sprzeciw. Stan sprzeciwu i termin rozpatrzenia są na stronie „Moje zadania”.
- **Role i poufność**: oceniany, oceniający, kadry, dyrektor, administrator. Notatki i szkic oceny widzi tylko oceniający. Statystyki są zbiorcze, bez nazwisk.
- **Kadry**: lista pracowników z wyszukiwaniem, filtrami (komórka organizacyjna, status oceny) i sortowaniem.
- **Notatki oceniającego**: obserwacje z pracy, dodatkowe osiągnięcia pracownika i - przy pierwszej ocenie - wynik egzaminu ze służby przygotowawczej.
- **Moje dane z EZD RP** - strona pracownika: na jaki poziom w jego kryteriach wskazują fakty z EZD RP według jawnych progów urzędu, bez modelu AI. Jest w menu tylko przy włączonej integracji z EZD RP. Mówi wprost, że to przypuszczenie, i niczego nie zapisuje.
- **Wydruk arkusza** zgodnego ze wzorem z rozporządzenia (PDF do podpisu, DOCX) i terminy do kalendarza (iCalendar).
- **Asystent AI** na lokalnym modelu PLLuM: odpowiada na pytania o procedurę, wskazuje przepisy i ostrzega, gdy odpowiedź modelu powołuje przepis albo liczbę spoza źródeł.
- **Projekt uzasadnienia z notatek**: na karcie oceny model układa notatki przełożonego w tekst uzasadnienia. Dostaje wyłącznie notatki - bez ocen cząstkowych i danych z EZD RP. Projekt jest oznaczony jako tekst AI, nie zapisuje się sam, a do formularza przenosi go oceniający.
- **Wirtualny HR partner - przygotowanie rozmowy oceniającej**: karta oceny przypomina, co omawia się w rozmowie (§ 10 rozporządzenia), a model układa z notatek przełożonego od 3 do 5 pytań otwartych. Pytania o zdrowie i sprawy prywatne są odrzucane. Podpowiedź nie jest zapisywana - pytania wybiera i zadaje oceniający.
- **Propozycja kierunków do IPRZ** (po instalacji wyłączona): razem z pytaniami model proponuje najwyżej 3 kierunki rozwoju i przy każdym wskazuje notatkę, z której go wyprowadził. Wymaga co najmniej 3 notatek. Do wniosków dotyczących IPRZ kierunki trafiają dopiero po decyzji oceniającego, który może je zmienić.
- **Sugestia ocen cząstkowych** (po instalacji wyłączona): model podpowiada oceniającemu ocenę w każdym kryterium na podstawie jego notatek, a podpowiedzi nie da się przenieść do formularza. Wymaga co najmniej 3 notatek. W próbach model zbyt łatwo sugerował oceny skrajne, więc system oznacza je ostrzeżeniem.
- **Informacja o AI przy treściach modelu**: przy odpowiedziach asystenta i projekcie uzasadnienia stoi klasyfikacja funkcji według rejestru urzędu, a przy sugestii ocen i propozycji kierunków do IPRZ - ostrzeżenie o funkcji wysokiego ryzyka z decyzją urzędu i listą analiz. Po sporządzeniu oceny oceniany widzi przy niej, z jakich funkcji modelu korzystał oceniający.
- **Bezpieczeństwo kont**: weryfikacja dwuetapowa kodem TOTP z aplikacji uwierzytelniającej (poza pokazem wymagana od każdego konta), blokada logowania po 5 nieudanych próbach, hasła od 12 znaków ustawiane przez użytkownika z jednorazowego linku. Strona „Moje konto” pokazuje ostatnie logowania.
- **Dziennik zdarzeń**: logowania, kody, zmiany kont, czynności administratora, odmowy dostępu, odczyty kart ocen i pobrania arkuszy. Wpisów nie da się zmienić ani usunąć, a łańcuch skrótów wykrywa ingerencję w bazie. Filtry, eksport CSV, osobny wgląd w czynności procesu oceny.
- **Zaplecze administratora**: zakładanie i blokowanie kont, nadawanie uprawnień, odłączanie aplikacji uwierzytelniającej, wgląd w dzienniki. Konto bez logowania przez miesiąc system zawiesza sam. Zaplecze nie pokazuje notatek ani szkiców, a administrator nie poznaje haseł. Uwaga: konto administratora ma też rolę administratora procesu - otwiera kartę każdej oceny (po sporządzeniu oceny z wynikiem i uzasadnieniem) i może pobrać arkusz; notatek oceniającego, karty z EZD RP i radaru nie widzi. Każde otwarcie karty i pobranie arkusza zostaje w dzienniku zdarzeń. Rozdzielenie administratora technicznego od wglądu w oceny jest do decyzji przed wdrożeniem.
- **Kontekst z EZD RP**: karta faktów o sprawach ocenianego za okres oceny (liczba spraw, terminowość, akceptacje pism), jawna dla obu stron, bez punktów i rankingów. Włącza ją komórka kadr po spełnieniu warunków Kodeksu pracy. W pokazie karta działa na danych przykładowych; klient Integrator API jest w rdzeniu, przetestowany na atrapie i jeszcze niepodłączony do karty.
- **Radar Dobrostanu i Doceniania**: na karcie oceny pracownik i jego przełożony widzą te same karty obserwacji - fakty z systemu kadrowego i EZD RP, np. urlop zaległy z terminem z Kodeksu pracy, godziny nadliczbowe, sprawy przejęte po nieobecnych, terminowość. Karty liczy zwykły kod według progów urzędu (`asystent_ocen/radar.toml`): bez punktów, rankingu i wniosków o zdrowiu albo emocjach. Radar działa po spełnieniu tych samych warunków Kodeksu pracy co karta z EZD RP. W pokazie liczby są przykładowe - prototyp nie ma połączenia z systemem kadrowym.
- **Pytania do kart obserwacji** (po instalacji wyłączone): model układa do każdej karty jedno pytanie otwarte dla przełożonego. Dostaje same karty, bez danych osobowych; pytanie o zdrowie, emocje albo sprawy prywatne jest odrzucane. To funkcja wysokiego ryzyka - włącza ją decyzja urzędu.

Testy: 749 testów rdzenia i 428 testów aplikacji.

## Założenia

- **Prawo w konfiguracji, nie w kodzie.** Parametry przepisów są w `asystent_ocen/przepisy.toml`, wymogi zgodności w `asystent_ocen/zgodnosc.toml`. Informatyk (konto administratora) edytuje TOML na stronie „Przepisy”. Po zapisie aplikacja WWW stosuje kopię z bazy zamiast zmieniać plik pakietu. Kadry i dyrektor generalny mają podgląd. Dziennik przechowuje autora, czas i różnice treści. Nie podawaj w TOML sekretów ani danych osób.
- **Przełączniki AI** w tym samym panelu pozwalają wyłączać i ponownie włączać funkcje dopuszczone przez rejestr i decyzje urzędu. Przełącznik nie zastępuje decyzji wymaganej przy wysokim ryzyku.
- **Ewidencja pracowników:** kadry dodają i edytują pracownika, wybierają wydział ze słownika urzędu, przełożonego i arkusz A/B/C. Wpisanie daty mianowania ustawia zatrudnienie jako urzędnik służby cywilnej i wymaga stopnia służbowego oraz daty jego przyznania. Administrator prowadzi listę w zakładce „Wydziały urzędu”; można usunąć tylko pusty wydział. Nowy arkusz obowiązuje od kolejnego cyklu; konta do logowania zakłada administrator.
- **Ocenę wystawia człowiek.** Po instalacji dozwolone są tylko funkcje AI spoza wysokiego ryzyka: odpowiedzi na pytania o procedurę, ułożenie notatek oceniającego w projekt uzasadnienia, pytania do rozmowy oceniającej i korekta językowa (ta ostatnia jest w rdzeniu, bez przycisku w aplikacji). Sugestia ocen cząstkowych i propozycja kierunków do IPRZ są w rejestrze (`zgodnosc.toml`) funkcjami wysokiego ryzyka i są wyłączone. Funkcji zakazanych nie włącza nic. Model nie dostaje danych z EZD RP.
- **O funkcji wysokiego ryzyka decyduje urząd.** Najpierw wykonuje analizy i czynności z listy w `zgodnosc.toml`: ocenę skutków dla praw podstawowych, ocenę skutków dla ochrony danych, powierzenie nadzoru, poinformowanie pracowników i rejestrację w bazie danych UE. Potem zapisuje decyzję - organ, datę i dokument każdej pozycji - w pliku wskazanym zmienną `ASYSTENT_DECYZJE_AI` (wzór: `decyzje-ai-wzor.toml`). Bez kompletnej decyzji system funkcji nie uruchomi, a usunięcie wpisu wyłącza ją od razu. System nie ocenia treści analiz - odpowiada za nie urząd. Lista to minimum, nie pełny katalog obowiązków z AI Act i RODO.
- **Dane zostają w urzędzie.** Model językowy działa lokalnie, a strony nie pobierają niczego z internetu (wymusza to polityka treści w nagłówkach odpowiedzi).
- **Tylko licencje permisywne.** Django (BSD-3-Clause), python-docx (MIT), model PLLuM-12B-chat (Apache-2.0).
- **Wygląd wzorowany na gov.pl.** Kolory, krój pisma i układ nagłówka nawiązują do stron Prezesa Rady Ministrów w portalu gov.pl. Domyślne [godło ze strony KPRM](https://www.gov.pl/img/icons/godlo-12.svg) jest serwowane lokalnie. Administrator zmienia nazwę i logo w zakładce „Oznaczenie urzędu”. Prototyp nie pobiera czcionek z sieci - stopka mówi wprost, że to nie jest serwis urzędowy. Urzędem w pokazie jest Kancelaria Prezesa Rady Ministrów; osoby i dane są fikcyjne.
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
| `ASYSTENT_DECYZJE_AI` | plik z decyzją urzędu o włączeniu funkcji AI wysokiego ryzyka (wzór: `decyzje-ai-wzor.toml`); bez niego żadna taka funkcja nie działa |
| `ASYSTENT_2FA` | `wymagane` (domyślnie) albo `dobrowolne` - weryfikacja dwuetapowa kodem TOTP |
| `ASYSTENT_PROBY_LOGOWANIA`, `ASYSTENT_BLOKADA_MINUT` | blokada logowania po nieudanych próbach (domyślnie 5 prób, 15 minut) |
| `ASYSTENT_TRYB_DEMO` | `1` włącza konta pokazowe - nigdy we wdrożeniu |

Pierwsze konto administratora zakłada się poleceniem `manage.py createsuperuser`; kolejne konta tworzy administrator w menu „Administracja”, wybierając pracownika bez konta. Login powstaje z imienia i nazwiska bez polskich znaków (np. `jan.nowak`), a przy kolizji dostaje pierwszy wolny numer: `jan.nowak1`, `jan.nowak2` itd. Zawieszanie kont bez aktywności działa samo (przegląd przy pierwszym żądaniu dnia); do zadania cyklicznego służy `manage.py zawies_nieaktywne`, a nienaruszalność dziennika sprawdza `manage.py sprawdz_dziennik`.

Skrypt `uruchom-demo.sh` używa serwera deweloperskiego Django i służy do pokazu. We wdrożeniu aplikację uruchamia się przez serwer WSGI za serwerem pośredniczącym z HTTPS.

## Układ repozytorium

| Katalog | Zawartość |
|---|---|
| `asystent_ocen/` | rdzeń reguł - czyste funkcje, bez bazy danych i interfejsu |
| `oceny/` | aplikacja webowa: modele, usługi, widoki, szablony, dane pokazowe |
| `serwis/` | ustawienia projektu Django |
| `tests/` | testy rdzenia; każdy cytuje przepis albo wymaganie |
| `oceny/tests/` | testy aplikacji: role, dostęp, przebieg oceny przez przeglądarkę |
| `dokumentacja/` | architektura, decyzje i interpretacje, analiza prawna, dostępność cyfrowa, bezpieczeństwo kont i dzienniki (KSC, KRI) |

## Podstawy prawne

- ustawa z dnia 21 listopada 2008 r. o służbie cywilnej (t.j. Dz. U. z 2026 r. poz. 590),
- rozporządzenie Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych urzędników służby cywilnej i pracowników służby cywilnej (Dz. U. poz. 470),
- Kodeks cywilny, art. 110-116 (terminy),
- ustawa z dnia 4 kwietnia 2019 r. o dostępności cyfrowej stron internetowych i aplikacji mobilnych podmiotów publicznych (t.j. Dz. U. z 2023 r. poz. 1440) - wymagania WCAG 2.1,
- ustawa z dnia 5 lipca 2018 r. o krajowym systemie cyberbezpieczeństwa (t.j. Dz. U. z 2026 r. poz. 20, 252, 815, 1003 i 1206), art. 8 i załącznik nr 4 - kontrola dostępu, uwierzytelnianie wieloskładnikowe, zawieszanie uprawnień,
- rozporządzenie Rady Ministrów z dnia 21 maja 2024 r. w sprawie Krajowych Ram Interoperacyjności, minimalnych wymagań dla rejestrów publicznych i wymiany informacji w postaci elektronicznej oraz minimalnych wymagań dla systemów teleinformatycznych (Dz. U. z 2024 r. poz. 773), § 19 i § 20 - bezpieczeństwo informacji i dzienniki systemów.
