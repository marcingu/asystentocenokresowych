# Analiza prawna: EZD RP jako źródło wiedzy o pracy i funkcje AI

Stan prawny i stan źródeł: 21.11.2026. Opracowanie robocze zespołu do decyzji projektowych - to nie jest opinia prawna.
Do weryfikacji: Daniel Dudek (prawo i administracja).

Oznaczenia: **[F]** fakt sprawdzony w tekście źródła, **[W]** wniosek zespołu, **[?]** niesprawdzone albo do rozstrzygnięcia.

## 1. Wnioski

1. **Art. 22[3] Kodeksu pracy.** [F] Brzmienie przytoczone przez Marcina jest zgodne z obowiązującym. [W] Zestawianie danych o pracy konkretnej osoby z EZD RP traktujemy ostrożnie jako „inną formę monitoringu” (§ 4), więc przed uruchomieniem urząd musi spełnić wymogi z art. 22[2] § 6-8 KP.
2. **Otwarte ryzyko.** [?] Art. 22[3] § 4 dopuszcza inne formy monitoringu tylko dla celów z § 1 (organizacja pracy, właściwe użytkowanie narzędzi pracy). „Ocena okresowa” nie jest tam wymieniona. Do rozstrzygnięcia przez prawnika (pkt 7).
3. **AI Act.** [W] Założenie „decyzję w 100% podejmuje dyrektor, więc to nie jest system wysokiego ryzyka” nie wystarcza. O klasyfikacji decyduje przeznaczenie systemu AI, a nie to, kto podpisuje decyzję. System AI, który ocenia wydajność lub zachowanie pracownika, mieści się w załączniku III pkt 4 lit. b, a ponieważ taka ocena jest profilowaniem, wyjątek z art. 6 ust. 3 nie działa.
4. **Projekt.** [W] AI nie ocenia. Terminy, średnie, skutki i wskaźniki z EZD RP liczy zwykły kod - to nie jest system AI. Model językowy dostaje wyłącznie zadania spoza oceny osoby: pytania o procedurę, korektę językową tekstu napisanego przez oceniającego i ułożenie jego własnych notatek w projekt uzasadnienia (kwalifikacja robocza - pkt 7.6).
5. **Daty.** [F] Wymogi dla systemów wysokiego ryzyka z załącznika III stosuje się od 2.12.2027. Zakazy z art. 5 obowiązują od 2.02.2025.
6. **API EZD RP.** [F] Da się pobrać daty i terminy spraw oraz historię akceptacji dokumentów. [F] Nie ma pola o wyniku odwołania - potrzebny rejestr własny urzędu albo wpis ręczny.

## 2. Kodeks pracy

### 2.1. Co sprawdzono

- [F] Art. 22[3] § 1-4 w tekście jednolitym Dz. U. z 2026 r. poz. 1245 (stan prawny tekstu jednolitego według API ELI Sejmu: 27.08.2026) brzmi tak, jak w pytaniu.
- [F] Jedyna późniejsza zmiana Kodeksu pracy: ustawa z 19.06.2026 (Dz. U. z 2026 r. poz. 1046, w życie 5.11.2026). Zmienia art. 18[3a], 18[3d]-18[3g], 94, 94[3], 94[3a] i 104[1]. Nie zmienia art. 22[2] ani 22[3].
- [F] Art. 9 ust. 1 ustawy o służbie cywilnej: w sprawach stosunku pracy w służbie cywilnej nieuregulowanych w ustawie stosuje się Kodeks pracy. [F] W tekście ustawy o służbie cywilnej słowo „monitoring” nie występuje. [W] Art. 22[2]-22[3] KP stosuje się więc do członków korpusu.

### 2.2. Treść istotna dla projektu

- § 1: cel - zapewnienie organizacji pracy umożliwiającej pełne wykorzystanie czasu pracy oraz właściwego użytkowania udostępnionych pracownikowi narzędzi pracy.
- § 2: monitoring nie może naruszać tajemnicy korespondencji ani innych dóbr osobistych pracownika.
- § 3: art. 22[2] § 6-10 stosuje się odpowiednio.
- § 4: § 1-3 stosuje się odpowiednio do innych form monitoringu, jeśli ich zastosowanie jest konieczne do realizacji celów z § 1.

### 2.3. Ocena

- [W] Systematyczne, zautomatyzowane zbieranie danych o aktywności konkretnego pracownika w systemie teleinformatycznym (sprawy, terminy, akceptacje) ma cechy „innej formy monitoringu”. Przyjmujemy wariant ostrożny i spełniamy wymogi monitoringu.
- [?] § 4 pozwala na inne formy monitoringu tylko dla celów z § 1. Podstawą samej oceny są: art. 81 ust. 1 i 3 u.s.c. (obowiązek oceny; ocena dotyczy wykonywania obowiązków wynikających z opisu stanowiska) oraz art. 94 pkt 9 KP (obiektywne i sprawiedliwe kryteria oceny pracowników oraz wyników ich pracy). Możliwe są dwie konstrukcje:
  - (a) monitoring w celu organizacji pracy (terminowość załatwiania spraw), którego wyniki oceniający bierze pod uwagę;
  - (b) zwykłe korzystanie przez przełożonego z wyników pracy, bez kwalifikacji jako monitoring.

  Nie wiem, którą konstrukcję przyjmują UODO, PIP i sądy - nie sprawdzałem orzecznictwa ani stanowisk organów.
- [F] Od 5.11.2026 art. 94 pkt 2c KP nakłada obowiązek przeciwdziałania naruszaniu godności i innych dóbr osobistych pracownika, m.in. w obszarze „efektów pracy oraz jej oceny”. [W] To argument za wskaźnikami jawnymi, sprawdzalnymi i dostępnymi także dla ocenianego.

### 2.4. Obowiązki przed uruchomieniem (art. 22[2] § 6-10 stosowane odpowiednio)

| Przepis | Obowiązek | Realizacja w systemie |
|---|---|---|
| § 6 | Cele, zakres i sposób zastosowania monitoringu ustala się w układzie zbiorowym pracy, regulaminie pracy albo obwieszczeniu | `UstaleniaMonitoringu`: podstawa, cele, zakres, sposób. Brak któregokolwiek blokuje integrację |
| § 7 | Informacja dla pracowników nie później niż 2 tygodnie przed uruchomieniem | Data poinformowania + 14 dni; wcześniej błąd `MONITORING_ZA_WCZESNIE` |
| § 8 | Nowy pracownik dostaje informacje z § 6 przed dopuszczeniem do pracy, na papierze lub elektronicznie | Do zrobienia w aplikacji: potwierdzenie przy zakładaniu konta ocenianego |
| § 9 | Oznaczenie pomieszczeń i terenu monitorowanego | [W] Stosowany odpowiednio: stała informacja o źródle danych na karcie faktów |
| § 10 | § 9 nie narusza art. 12 i 13 RODO | Klauzula informacyjna urzędu (poza systemem) |

### 2.5. Ograniczenia zakresu danych

- Tylko metadane spraw i akceptacji: daty, terminy, statusy, wyniki akceptacji z opisem. Bez treści pism i korespondencji (art. 22[3] § 2 KP).
- Odczyt na potrzeby konkretnej oceny i okresu oceny, bez śledzenia aktywności na bieżąco.
- Integracja tylko do odczytu; domyślnie wyłączona.

## 3. AI Act

### 3.1. Źródło i daty

- [F] Rozporządzenie (UE) 2024/1689, zmienione rozporządzeniem (UE) 2026/1744 z 8.07.2026 („akt zbiorczy prawa cyfrowego dotyczący AI”). Analiza na wersji skonsolidowanej z 27.07.2026.
- [F] Art. 113 po zmianie: rozdziały I i II (w tym zakazy z art. 5) stosuje się od 2.02.2025; rozdział III sekcje 1-3 dla systemów z art. 6 ust. 2 i załącznika III - od 2.12.2027 (lit. c ppkt (i)); pozostałe przepisy co do zasady od 2.08.2026.

### 3.2. Co jest systemem AI

- [F] Art. 3 pkt 1: system maszynowy, który wnioskuje, jak generować na podstawie danych wejściowych wyniki takie jak predykcje, treści, zalecenia lub decyzje.
- [F] Motyw 12: pojęcie nie obejmuje „systemów opartych na zasadach określonych wyłącznie przez osoby fizyczne w celu automatycznego wykonywania operacji”.
- [W] Silnik reguł (terminy, średnia, poziom, skutki, przypomnienia) i wskaźniki z EZD RP (zliczenia, mediany, udziały) nie są systemami AI.
- [W] Informacja o skutku wynikającym wprost z ustawy to reguła, a nie rekomendacja AI. Przykład: dwie kolejne negatywne oceny urzędnika - art. 71 ust. 1 pkt 1 u.s.c.
- [W] Moduł z modelem językowym jest systemem AI.

### 3.3. Załącznik III pkt 4 lit. b

[F] Wysokiego ryzyka są „systemy AI przeznaczone do wykorzystywania do celów podejmowania decyzji wpływających na warunki stosunków pracy, decyzji o awansie lub rozwiązaniu umownego stosunku pracy, przydzielania zadań w oparciu o indywidualne zachowanie lub cechy osobowości lub charakter lub do monitorowania lub oceny wydajności i zachowania osób pozostających w takich stosunkach”.

[W] Ocena okresowa mieści się tu podwójnie: jest oceną wydajności i zachowania, a jej wynik wpływa na awans (stopień służbowy - art. 89 ust. 1 i 2 u.s.c.) i na rozwiązanie stosunku pracy (art. 71 ust. 1 pkt 1 u.s.c.).

### 3.4. Wyjątek z art. 6 ust. 3 i profilowanie

- [F] Systemu z załącznika III nie uznaje się za system wysokiego ryzyka, gdy nie stwarza znaczącego ryzyka, w tym nie wpływa znacząco na wynik procesu decyzyjnego, i spełnia jeden z warunków: (a) wąsko określone zadanie proceduralne, (b) poprawienie wyniku zakończonej uprzednio czynności człowieka, (c) wykrywanie wzorców decyzyjnych bez zastępowania oceny człowieka, (d) zadania przygotowawcze.
- [F] Art. 6 ust. 3 akapit trzeci: system z załącznika III zawsze uznaje się za system wysokiego ryzyka, gdy dokonuje profilowania osób fizycznych.
- [F] Art. 3 pkt 52 AI Act odsyła do art. 4 pkt 4 RODO: profilowanie to zautomatyzowane przetwarzanie danych osobowych do oceny czynników osobowych, w szczególności do analizy lub prognozy aspektów dotyczących „efektów pracy”.
- [F] Art. 6 ust. 4: dostawca, który uważa, że system z załącznika III nie jest systemem wysokiego ryzyka, dokumentuje ocenę i podlega rejestracji z art. 49 ust. 2.

### 3.5. Hipoteza „decyzja w 100% dyrektora”

[W] Udział człowieka nie rozstrzyga klasyfikacji:

1. Załącznik III pkt 4 lit. b obejmuje nie tylko podejmowanie decyzji, ale też samo monitorowanie lub ocenę wydajności i zachowania.
2. System AI oceniający efekty pracy osoby profiluje, a przy profilowaniu wyjątek z art. 6 ust. 3 nie ma zastosowania - niezależnie od tego, kto podejmuje decyzję.
3. Rekomendacja zwolnienia jest przypadkiem oczywistym, ale granica leży wcześniej: już propozycja oceny cząstkowej albo podsumowanie pracy osoby wygenerowane przez model to wysokie ryzyko.

Kierunek ten potwierdza projekt wytycznych Komisji Europejskiej do art. 6 (AI Act Service Desk, pobrano 21.11.2026):

- [F] pkt 71: dostawca nie może zakwalifikować systemu jako niskiego ryzyka tylko przez dodanie wymogu udziału człowieka;
- [F] pkt 258: „decyzja” obejmuje też sytuację, w której człowiek formalnie decyduje, ale w znacznym stopniu opiera się na wyniku systemu AI;
- [F] pkt 274-275: „monitorowanie” i „ocena” to warunki alternatywne i samodzielna kategoria wysokiego ryzyka; wydajność obejmuje liczbę zadań, szybkość i jakość pracy, w tym oceny generowane przez AI, które trafiają do akt pracownika;
- [F] pkt 112: bez oceny, prognozy albo osądu o osobie nie ma profilowania;
- [?] to projekt (konsultacje publiczne do 23.07.2026), niewiążący. Nie wiem, czy Komisja przyjęła wersję ostateczną.

### 3.6. Klasyfikacja funkcji systemu

| Funkcja | System AI? | Klasyfikacja | Status w systemie |
|---|---|---|---|
| Silnik procesu: terminy, arkusze, średnia, poziom, skutki, przypomnienia | nie | poza AI Act | jest |
| Karta faktów z EZD RP: liczby spraw, mediana czasu, terminowość, akceptacje, odwołania | nie | poza AI Act; podlega RODO i KP | jest |
| Pytania o procedurę i przepisy (model odpowiada z przekazanych fragmentów przepisów) | tak | poza załącznikiem III; przejrzystość z art. 50 ust. 1 | włączona |
| Korekta językowa uzasadnienia napisanego przez oceniającego | tak | wyjątek z art. 6 ust. 3 lit. b (motyw 53); dokumentacja oceny i rejestracja - art. 6 ust. 4, art. 49 ust. 2 | włączona |
| Ułożenie notatek oceniającego w projekt uzasadnienia (HR Copilot z architektury zespołu); model nie dostaje ocen cząstkowych, wyniku ani danych z EZD RP | tak | [W] wyjątek z art. 6 ust. 3 lit. d (zadania przygotowawcze; motyw 53: przetwarzanie tekstów); bez oceny, prognozy albo osądu o osobie nie ma profilowania (projekt wytycznych, pkt 112). [?] Kwalifikacja robocza - pkt 7.6 | włączona |
| Propozycja ocen cząstkowych, poziomu lub uzasadnienia z danych o pracy | tak | wysokie ryzyko | zablokowana |
| Podsumowanie albo interpretacja wskaźników pracy osoby przez model | tak | wysokie ryzyko | zablokowana |
| Rekomendacja zwolnienia, awansu, nagrody; ranking pracowników | tak | wysokie ryzyko; dodatkowo art. 22 RODO | zablokowana |
| Wnioskowanie o emocjach pracownika | tak | praktyka zakazana - art. 5 ust. 1 lit. f | zablokowana |

Rejestr jest w `asystent_ocen/zgodnosc.toml`. Funkcji wysokiego ryzyka i zakazanych nie da się włączyć konfiguracją.

### 3.7. Gdyby urząd chciał funkcję wysokiego ryzyka

[F] Od 2.12.2027 obowiązują m.in.: nadzór człowieka (art. 14), poinformowanie przedstawicieli pracowników i pracowników przed użyciem systemu w miejscu pracy (art. 26 ust. 7), poinformowanie osób, których dotyczą decyzje (art. 26 ust. 11), ocena skutków dla praw podstawowych przez podmioty prawa publicznego przed wdrożeniem (art. 27 ust. 1), rejestracja w bazie UE (art. 49 ust. 1 i 3). [?] Pełnego katalogu wymogów z rozdziału III sekcji 2 nie analizowano.

## 4. RODO

- [F] Art. 4 pkt 4: profilowaniem jest także zautomatyzowana analiza efektów pracy osoby. [W] Karta faktów z EZD RP jest więc profilowaniem w rozumieniu RODO, mimo że nie jest systemem AI.
- [F] Art. 22 ust. 1: prawo do tego, by nie podlegać decyzji opartej wyłącznie na zautomatyzowanym przetwarzaniu, która wywołuje skutki prawne. [W] Dlatego ocenę wystawia oceniający, a system nie proponuje ocen i nie liczy oceny zbiorczej ze wskaźników.
- [F] Art. 35 ust. 3 lit. a: ocena skutków dla ochrony danych jest wymagana przy systematycznej, kompleksowej ocenie czynników osobowych opartej na zautomatyzowanym przetwarzaniu, która jest podstawą decyzji wywołujących skutki prawne. [W] Ocena okresowa wywołuje skutki prawne, więc DPIA uważamy za konieczną. [?] Do potwierdzenia z IOD urzędu.
- [F] Art. 88: państwa członkowskie mogą przyjąć szczegółowe przepisy o przetwarzaniu danych pracowników, w tym o systemach monitorujących w miejscu pracy.
- [W] Nieobecności: system używa dat, nie przyczyn. [?] Kwalifikacji przyczyn nieobecności jako danych o zdrowiu (art. 9 RODO) nie sprawdzano.

## 5. Co daje API EZD RP

Źródło: specyfikacja OpenAPI „Integrator API v2”, wersja v2.11.5 z 10.09.2026 (kopia z 4.11.2026). W dniu 21.11.2026 środowisko demo zwracało stronę przerwy technicznej. Nie testowano na działającej instancji.

| Potrzeba | Co daje API | Operacja | Status |
|---|---|---|---|
| Szybkość załatwiania spraw | `dataWszczecia`, `terminZalatwienia`, `status`, `czasRealizacjiDni`; filtry `prowadzacySprawe`, `dataZakonczeniaOd/Do` | `POST /sprawy/_search`, `GET /sprawy/{id}` | [F] pola są. Rekord nie zawiera daty zakończenia - ustalamy ją podziałem okna wyszukiwania. [?] Znaczenie `czasRealizacjiDni` nie jest opisane |
| Uwagi przełożonych do projektów pism | Historia akceptacji: wynik (zaakceptowany, odrzucony, do akceptacji, anulowany), osoba, data, wersja, pole `opis` | `GET /dokumenty/{id}/akceptacje` | [F] pola są. [?] Czy `opis` zawiera treść uwagi - do potwierdzenia na instancji |
| Zdarzenia na bieżąco | Webhooki, m.in. `dokument.akceptacja.odrzucono`, `dokument.akceptacja.zaakceptowano`, `zadanie.zakonczono` | `POST /subskrypcje` | [F] |
| Prawidłowość merytoryczna, odwołania | Brak pola o odwołaniu i jego wyniku | - | [F] brak. [W] Rejestr własny urzędu (`GET /rejestry/{id}/wpisy`, struktura definiowana przez urząd) albo wpis ręczny |
| Struktura organizacyjna | Komórki, stanowiska, użytkownicy | `GET /struktura` i pochodne | [F] |

Ograniczenia: [F] wyszukiwanie spraw wymaga uprawnienia `Sprawy.Podglad`, a wyniki zależą od uprawnień konta klucza API. [F] Uwierzytelnienie: nagłówki `Authorization: Bearer` i `SID`.

## 6. Decyzje projektowe zapisane w testach

| Decyzja | Testy |
|---|---|
| Integracja z EZD RP rusza dopiero po ustaleniach z art. 22[2] § 6 i po 2 tygodniach od poinformowania pracowników | `tests/test_zgodnosc_monitoring.py` |
| Rejestr funkcji AI z klasyfikacją; wysokie ryzyko i funkcje zakazane nie do włączenia | `tests/test_zgodnosc_funkcje_ai.py` |
| Zamknięta lista jawnych wskaźników z listą spraw źródłowych; bez oceny zbiorczej i rankingu; minimalna liczność 5 | `tests/test_wskazniki_pracy.py` |
| Klient EZD RP tylko do odczytu, bez treści pism; wynik odwołań z rejestru własnego | `tests/test_ezdrp_api.py` |
| Projekt uzasadnienia z notatek: model dostaje wyłącznie notatki (bez ocen, szkicu, wyniku i danych z EZD RP), projekt nie jest zapisywany, a kontrola oznacza pola do uzupełnienia, liczby spoza notatek, pominięte liczby i sformułowania o ocenie | `tests/test_redakcja_notatek.py`, `oceny/tests/test_copilot.py` |

Poza testami: model PLLuM-12B-chat-2512 działa lokalnie (licencja Apache-2.0 według karty modelu na Hugging Face, sprawdzone 21.11.2026), więc dane nie opuszczają urzędu. W próbach z 21.11.2026 model układał notatki wiernie co do liczb, ale potrafił zmienić sens zdania (np. podmiot) - tego kontrola automatyczna nie wykrywa, dlatego projekt zawsze sprawdza oceniający.

## 7. Do rozstrzygnięcia

1. Czy art. 22[3] § 4 KP obejmuje cel „ocena okresowa”, czy bezpieczniejsza jest konstrukcja (a) albo (b) z pkt 2.3.
2. DPIA i klauzula informacyjna - uzgodnienie z IOD.
3. Kto będzie dostawcą w rozumieniu AI Act po przeniesieniu praw do rozwiązania na KPRM.
4. Czy korekta językowa uzasadnienia na pewno mieści się w art. 6 ust. 3 lit. b i kogo obciąża rejestracja z art. 49 ust. 2.
5. Czy urzędy prowadzą w EZD RP rejestr odwołań z wynikiem.
6. Czy ułożenie notatek oceniającego w projekt uzasadnienia mieści się w art. 6 ust. 3 lit. d (albo b) AI Act. Model nie ocenia i nie dostaje ocen ani danych z EZD RP, ale jego tekst po akceptacji oceniającego trafia do arkusza. Do rozstrzygnięcia funkcję można wyłączyć jedną zmianą w `zgodnosc.toml`.

## 8. Źródła

- Kodeks pracy: Dz. U. z 2026 r. poz. 1245 i 1046 (API ELI Sejmu, 21.11.2026).
- Ustawa o służbie cywilnej: tekst z materiałów KPRM (art. 9, 71, 81, 89).
- AI Act: CELEX 32024R1689, wersja skonsolidowana 02024R1689-20260727; rozporządzenie zmieniające CELEX 32026R1744 (Urząd Publikacji UE).
- RODO: CELEX 32016R0679.
- Projekt wytycznych Komisji do art. 6 AI Act: AI Act Service Desk, „Guidelines on the classification of high-risk AI systems” (pobrano 21.11.2026).
- EZD RP: specyfikacja OpenAPI Integrator API v2, v2.11.5.
