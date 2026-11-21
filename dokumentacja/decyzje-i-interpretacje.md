# Decyzje i interpretacje przyjęte w rdzeniu reguł

Stan: 21.11.2026. Każda pozycja ma test albo przełącznik w `asystent_ocen/przepisy.toml`. Pozycje z sekcji 2 i 3 wymagają potwierdzenia przez osobę odpowiedzialną za prawo (Daniel Dudek) albo mentorów KPRM.

## 1. Decyzje zespołu (Marcin, 21.11.2026)

| Kwestia | Decyzja | Gdzie zapisana |
|---|---|---|
| Pierwsza ocena: od kiedy liczy się 6 miesięcy z art. 81 ust. 6 i 8 u.s.c. | Od nawiązania stosunku pracy (zgodnie z warunkami brzegowymi przypadków użycia KPRM; Poradnik KPRM s. 10 liczy od zapoznania z kryteriami) | `[interpretacje] pierwsza_ocena_6_miesiecy_od` |
| Ponowna ocena po negatywnej (art. 81 ust. 9 u.s.c.) | Pierwszy dzień roboczy po upływie 6 miesięcy (Poradnik KPRM s. 13 podaje dzień bez przesunięcia) | `[interpretacje] ponowna_ocena_w_dniu_roboczym` |
| Precyzja średniej | Jedno miejsce po przecinku, zaokrąglenie arytmetyczne; poziom ustala się z dokładnej średniej | `[interpretacje] miejsca_po_przecinku_sredniej` |
| Notatki robocze przełożonego | Oceniany ich nie widzi | `tests/test_przebieg_procesu.py` |
| Fikcja zapoznania z oceną | Może ją stwierdzić oceniający, oceniany i zarządzający; data stwierdzenia jest datą zapoznania | `tests/test_przebieg_procesu.py` |
| Dostępność cyfrowa | WCAG 2.1 na poziomach A i AA (załącznik do ustawy o dostępności cyfrowej) jest wymaganiem interfejsu i wydruków | `dokumentacja/dostepnosc.md`, `oceny/tests/test_dostepnosc.py` |
| Sugestia ocen cząstkowych przez model językowy | Model podpowiada oceniającemu oceny na podstawie jego notatek. To funkcja wysokiego ryzyka: po instalacji wyłączona. O włączeniu decyduje urząd po wykonaniu analiz z listy w `zgodnosc.toml`; decyzja podaje organ, datę i dokument każdej analizy. Pokaz włącza ją wpisem pokazowym, na danych fikcyjnych | `decyzje-ai-wzor.toml`, `decyzje-ai-pokaz.toml`, `tests/test_zgodnosc_funkcje_ai.py` |

Bez decyzji: wartość pola „do” okresu oceny przy ocenie sporządzonej po terminie (data terminu według schematu pól czy data sporządzenia według przypisu 7 do części II arkusza B). Rdzeń przyjmuje datę sporządzenia.

## 2. Rozstrzygnięcia wykonawcy tam, gdzie testy i przepisy milczą

1. **Przedłużenie terminu (art. 81 ust. 7 u.s.c.).** O progu „dłużej niż miesiąc” decyduje cała nieobecność ciągła. Nieobecność zaczęta przed początkiem cyklu liczy się od początku cyklu, a trwająca po terminie - do swojego końca. Uwzględniana jest też długa nieobecność zaczęta w okresie przedłużenia.
2. **Ciągłość nieobecności.** Sobota, niedziela i święto między dwiema nieobecnościami nie przerywają ciągłości (`[kalendarz] sobota_nie_przerywa_ciaglosci_nieobecnosci`).
3. **Stopień obligatoryjny (art. 89 ust. 2 u.s.c.).** Badane są dwie ostatnie oceny z datą zapoznania późniejszą niż dzień otrzymania stopnia; ocena z tego samego dnia się nie liczy.
4. **Zmiana terminu przez oceniającego.** Warunek „więcej niż 6 miesięcy” stosuje się do wszystkich przypadków z art. 81 ust. 8 u.s.c. (tak Poradnik KPRM s. 15). Wymagana jest przyczyna i etap oceniania.
5. **Uprawnienia nieobjęte testami.** Oceniającego zmienia tylko zarządzający. Notatki dodaje i czyta tylko oceniający (kadry i administrator bez wglądu). Korekta kryteriów: tylko administrator w trybie korekty.
6. **Sprzeciw.** Uwzględnić sprzeciw można tylko po zakończeniu procesu. Tryb „zmiana” zostawia proces zakończony.
7. **Odwołanie do sądu pracy (art. 83 ust. 5 u.s.c.).** Gdy znane są obie daty, 14 dni liczy się od doręczenia decyzji.
8. **Rodzaj zatrudnienia.** Nieznana wartość powoduje błąd, a nie wynik „nie podlega ocenie” - literówka nie wyłączy nikogo z oceny.
9. **Okres oceny „od-do”.** „Do” to wcześniejsza z dat: sporządzenie oceny albo ostatni dzień na stanowisku (przypis 7 do części II arkusza B).
10. **Formularz.** Brak odpowiedzi o wniosek o stopień oznacza brak wniosku. Oceny cząstkowe muszą być liczbami całkowitymi ze skali.
11. **Pouczenie o sprzeciwie.** W arkuszu A adresata wpisuje oceniający; w arkuszach B i C adresat wynika ze wzoru.
12. **Zmiana stanowiska (art. 81 ust. 6 u.s.c., § 9 rozp.).** Terminy „najpóźniej” przesuwają się zgodnie z art. 115 KC; granica „najwcześniej” się nie przesuwa.
13. **Druga kolejna ocena negatywna urzędnika.** Obok sygnału o rozwiązaniu stosunku pracy (art. 71 ust. 1 pkt 1 u.s.c.) system nadal pokazuje ponowną ocenę i nowe kryteria, bo przepisy ich nie wyłączają.
14. **Sugestia ocen cząstkowych: granice.** Model dostaje tylko notatki oceniającego, bez danych z EZD RP i bez szkicu oceny. Przy mniej niż 3 notatkach nie jest pytany. Podpowiedzi nie da się przenieść do formularza. Ocena z krańca skali dostaje ostrzeżenie. Próg 3 notatek jest decyzją wykonawcy po próbach na modelu, nie przepisem.
15. **Ślad użycia modelu.** Wpis o użyciu modelu przy pracy nad oceną widzi oceniający, a oceniany dopiero po sporządzeniu oceny - tak jak szkic.
16. **Analizy przed włączeniem funkcji wysokiego ryzyka.** Lista w `zgodnosc.toml` ma pięć pozycji sprawdzonych w tekście AI Act i RODO. To minimum wybrane przez wykonawcę, a nie pełny katalog obowiązków; system sprawdza, czy decyzja urzędu wskazuje dokument każdej pozycji, i nie ocenia jego treści.
17. **Ostrzeżenia przy treściach modelu.** Przy sugestii ocen stoi ostrzeżenie o funkcji wysokiego ryzyka z decyzją urzędu, a w pokazie - z informacją, że analiz nie wykonano. Przy projekcie uzasadnienia i odpowiedziach asystenta stoi informacja o treści modelu i klasyfikacji funkcji. Po sporządzeniu oceny oceniany widzi przy niej, z jakich funkcji modelu korzystał oceniający. Arkusz drukowany zostaje zgodny ze wzorem z rozporządzenia, więc tej informacji na nim nie ma.

## 3. Znane ograniczenia

- Anonimizacja zastępuje nazwiska tylko w podanym brzmieniu; formy odmienione („Adama Kowalika”) zostają w tekście. NIP i numery rachunków nie są objęte. Do poprawy przed użyciem modelu spoza infrastruktury urzędu.
- Integracja z EZD RP nie była testowana na działającej instancji (patrz `analiza-prawna-ai-act-kp-rodo.md`, pkt 5).
- Sugestia ocen cząstkowych: w próbach model PLLuM-12B zbyt łatwo sugerował oceny z krańców skali i przypisywał notatki do niewłaściwych kryteriów (patrz `analiza-prawna-ai-act-kp-rodo.md`, pkt 6). Funkcja jest po instalacji wyłączona.
- Decyzja urzędu o funkcji wysokiego ryzyka: system sprawdza, czy decyzja wskazuje organ, datę i dokument każdej analizy, ale nie sprawdza treści dokumentów ani tego, kto zapisał plik. Informacja dla ocenianego podaje decyzję według obecnego stanu pliku, a nie stanu z dnia użycia funkcji.
- Lista analiz przed włączeniem funkcji wysokiego ryzyka dotyczy urzędu jako podmiotu stosującego. Obowiązków dostawcy systemu wysokiego ryzyka (art. 16 AI Act) prototyp nie obejmuje.
