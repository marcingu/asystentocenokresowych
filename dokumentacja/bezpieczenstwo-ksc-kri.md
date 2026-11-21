# Bezpieczeństwo kont i dzienniki - odniesienie do KSC i KRI

Stan prawny i stan kodu: 21.11.2026. Dokument dotyczy aplikacji, a nie całego systemu zarządzania bezpieczeństwem informacji urzędu. Pokazuje, które wymagania przepisów aplikacja wspiera, czym to robi i co zostaje po stronie urzędu.

Oznaczenia: **[F]** fakt z tekstu przepisu, **[W]** wniosek wykonawcy, **[?]** nie wiemy albo nie sprawdzono.

To nie jest wykazanie zgodności. Prototyp nie przeszedł audytu bezpieczeństwa ani testów penetracyjnych.

## 1. Przepisy

| Akt | Metryka | Co z niego bierzemy |
|---|---|---|
| Rozporządzenie Rady Ministrów z 21.05.2024 r. w sprawie Krajowych Ram Interoperacyjności, minimalnych wymagań dla rejestrów publicznych i wymiany informacji w postaci elektronicznej oraz minimalnych wymagań dla systemów teleinformatycznych (KRI) | Dz. U. z 2024 r. poz. 773; obowiązuje, bez zmian (ELI, 21.11.2026) | § 19 - system zarządzania bezpieczeństwem informacji; § 20 - rozliczalność i dzienniki systemów |
| Ustawa z 5.07.2018 r. o krajowym systemie cyberbezpieczeństwa (KSC) | t.j. Dz. U. z 2026 r. poz. 20, zm. poz. 252, 815, 1003 i 1206 | art. 8 ust. 1 i załącznik nr 4 - w brzmieniu nadanym ustawą z 23.01.2026 r. (poz. 252, w życiu od 3.04.2026) |

[F] Późniejsze zmiany KSC nie dotyczą art. 8 ani załącznika nr 4: poz. 815 (art. 20) zmienia art. 15, 26 i 46, poz. 1003 (art. 124) - art. 26 ust. 3, poz. 1206 (art. 35) - załącznik nr 1 (od 11.01.2027). Sprawdzone w tekstach tych ustaw i w wykazie zmian w ELI (21.11.2026).

[?] Nie ustalamy, czy urząd jest podmiotem kluczowym, czy ważnym w rozumieniu KSC. Podmiot ważny będący podmiotem publicznym stosuje załącznik nr 4 zamiast art. 8 ust. 1 (art. 8 ust. 3). Dlatego tabela niżej odnosi się do obu zestawów wymagań. KRI stosuje każdy podmiot realizujący zadania publiczne.

## 2. Wymaganie - co robi aplikacja - co zostaje urzędowi

| Wymaganie | Aplikacja | Po stronie urzędu / luka |
|---|---|---|
| [F] Osoby mają stosowne uprawnienia (§ 19 ust. 2 pkt 4 KRI); dostęp tylko dla uprawnionych i minimalne uprawnienia (zał. nr 4 część I pkt 4 i 5 KSC) | Rola wynika z relacji do konkretnej oceny: oceniany, oceniający, kadry, dyrektor (statystyki zbiorcze), administrator. Cudza ocena daje 404. Notatki i szkic widzi tylko oceniający. Administrator zarządza kontami i czyta dzienniki, ale zaplecze nie pokazuje mu treści ocen | Nadawanie ról (kto jest kadrami, kto przełożonym) to dane kadrowe wprowadzane przez urząd |
| [F] Bezzwłoczna zmiana uprawnień (§ 19 ust. 2 pkt 5 KRI); cofanie uprawnień i ich modyfikacja (zał. nr 4 część I pkt 6 i 7 KSC) | Administrator blokuje konto jednym przyciskiem; blokada działa od razu także na trwającą sesję. Zmiana uprawnień administratora i powiązania z pracownikiem zostaje w dzienniku. Nie da się zablokować własnego konta ani odebrać uprawnień ostatniemu czynnemu administratorowi | Informacja o zmianie zadań pracownika musi trafić do administratora - aplikacja nie jest połączona z systemem kadrowym |
| [F] Zawieszanie uprawnień w przypadku niewykonywania obowiązków co najmniej przez jeden miesiąc (zał. nr 4 część I pkt 6 KSC) | Konto bez udanego logowania przez miesiąc (art. 112 KC; okres w `zgodnosc.toml`) jest zawieszane automatycznie: raz dziennie przy pierwszym żądaniu, poleceniem `manage.py zawies_nieaktywne` albo przyciskiem administratora. Odblokowuje administrator; po odblokowaniu miesiąc biegnie od nowa | [W] Ustawa mówi o niewykonywaniu obowiązków, a aplikacja mierzy brak logowania - to przybliżenie. Długą nieobecność wpisaną przez kadry można by wykorzystać do wcześniejszego zawieszenia; tego nie ma |
| [F] Monitorowanie dostępu do informacji i wykrywanie nieautoryzowanych działań (§ 19 ust. 2 pkt 7 lit. a i b KRI) | Dziennik zdarzeń zapisuje każdy odczyt karty oceny, pobranie arkusza, odmowę dostępu, nieudane logowanie i błędny kod. Użytkownik widzi na stronie „Moje konto” ostatnie logowania i nieudane próby na swoim koncie | Przeglądanie dziennika i reagowanie to zadanie urzędu. Odczyty list (np. lista pracowników w kadrach) nie są zapisywane |
| [F] Środki uniemożliwiające nieautoryzowany dostęp na poziomie aplikacji (§ 19 ust. 2 pkt 7 lit. c KRI); polityki kontroli dostępu (art. 8 ust. 1 pkt 2 lit. n KSC) | Każda strona wymaga zalogowania. Po 5 nieudanych próbach w 15 minut logowanie na konto jest wstrzymane (progi w ustawieniach). Komunikat po nieudanym logowaniu nie zdradza, czy konto istnieje. Hasło: co najmniej 12 znaków, nie z listy popularnych. Administrator nie ustala i nie poznaje hasła - wydaje jednorazowy link ważny dobę. Ochrona przed CSRF, nagłówki CSP i X-Frame-Options, ciasteczka sesji HttpOnly | Blokada liczy próby na konto, nie na adres - ochronę przed próbami na wiele kont z jednego adresu daje serwer pośredniczący urzędu. Sesja trwa do 8 godzin bez ostrzeżenia przed wygaśnięciem |
| [F] Bezpieczne środki komunikacji elektronicznej wewnątrz podmiotu, „uwzględniające uwierzytelnianie wieloskładnikowe w stosownych przypadkach” (art. 8 ust. 1 pkt 2 lit. l KSC). [W] Logowanie do systemu z ocenami pracowników uznajemy za taki przypadek | Drugi składnik: kod jednorazowy TOTP (RFC 6238) z aplikacji uwierzytelniającej. Poza pokazem wymagany od każdego konta (`ASYSTENT_2FA`). Sesja powstaje dopiero po kodzie; kod działa raz; konto bez skonfigurowanej aplikacji nie wejdzie nigdzie poza jej konfigurację. Panel administratora Django nie ma własnego logowania - prowadzi przez to samo wejście | Klucz TOTP leży w bazie w postaci jawnej - we wdrożeniu potrzebne szyfrowanie bazy albo pola. Nie ma kodów zapasowych: po utracie telefonu aplikację odłącza administrator. Nie ma logowania kluczem sprzętowym ani przez login.gov.pl |
| [F] Rozliczalność dokumentowana w dziennikach systemów; obowiązkowo dostęp z uprawnieniami administracyjnymi, do konfiguracji zabezpieczeń i do danych prawnie chronionych (§ 20 ust. 1 i 2 KRI) | Dwa dzienniki, oba tylko do dopisywania: zdarzenia bezpieczeństwa (logowania, kody, zmiany kont, czynności administratora, wgląd w dziennik i jego eksport, odczyty ocen) oraz czynności w procesie oceny. Logowanie administratora jest oznaczone. Wpis ma czas, login, adres IP i opis; hasła i kody nie są zapisywane | Zmiany ustawień serwera (zmienne środowiskowe, pliki konfiguracji) robi się poza aplikacją - ich rejestrowanie zapewnia urząd |
| [F] Wiarygodne dokumentowanie (§ 20 ust. 1 KRI); ochrona przed nieuprawnioną modyfikacją (§ 19 ust. 2 pkt 9 KRI, art. 8 ust. 1 pkt 5 lit. c KSC) | Każdy wpis dziennika bezpieczeństwa zawiera skrót SHA-256 własnej treści i poprzedniego wpisu. Strona dziennika i polecenie `manage.py sprawdz_dziennik` wykrywają zmianę albo usunięcie wpisu poza aplikacją | [W] To wykrywa manipulację, ale jej nie uniemożliwia: osoba z prawem zapisu do bazy może przeliczyć cały łańcuch. Zabezpieczeniem jest kopia dziennika poza serwerem aplikacji |
| [F] Dzienniki przechowuje się 2 lata, gdy przepisy odrębne nie mówią inaczej (§ 20 ust. 4 KRI); można je składować na nośnikach zewnętrznych (§ 20 ust. 5) | Aplikacja nie usuwa wpisów. Okres jest zapisany w `zgodnosc.toml` i pokazany na stronie dziennika. Eksport do CSV z filtrami; wartości zaczynające się jak formuła arkusza są unieszkodliwiane | Archiwizacja i usuwanie po okresie przechowywania, przekazywanie do systemu zbierania logów urzędu (nie ma wysyłki syslog) |
| [F] Mechanizmy kryptograficzne adekwatne do zagrożeń (§ 19 ust. 2 pkt 12 lit. d KRI); polityki stosowania kryptografii (art. 8 ust. 1 pkt 2 lit. k KSC) | Hasła jako skróty PBKDF2-SHA256 (mechanizm Django). Po włączeniu `ASYSTENT_HTTPS`: ciasteczka tylko przez HTTPS i nagłówek HSTS. Dane nie opuszczają urzędu: model językowy działa lokalnie, strony nie pobierają niczego z internetu | Certyfikat i terminacja TLS, szyfrowanie bazy i kopii zapasowych |
| [F] Aktualizacje i podatności (§ 19 ust. 2 pkt 12 lit. a, f, g KRI; zał. nr 4 część I pkt 15 i 16 KSC) | Dwie zależności: Django 5.2 LTS i python-docx. Kody jednorazowe i dziennik korzystają tylko z biblioteki standardowej Pythona | Śledzenie poprawek bezpieczeństwa Django, Pythona, serwera i modelu językowego |
| [F] Zgłaszanie incydentów (§ 19 ust. 2 pkt 13 KRI); zarządzanie incydentami (art. 8 ust. 1 pkt 4 KSC) | Dziennik daje materiał do analizy: kto, kiedy, skąd i co zrobił; naruszenie dziennika jest zgłaszane na stronie | Procedura obsługi i zgłaszania incydentów |
| [F] Kopie zapasowe i ich testowanie (zał. nr 4 część I pkt 10 i 11 KSC); audyt co najmniej raz w roku (§ 19 ust. 2 pkt 14 KRI) | Poza prototypem | W całości po stronie urzędu |

## 3. Zdarzenia w dzienniku bezpieczeństwa

Logowanie, nieudane logowanie, logowanie odrzucone przez blokadę, wylogowanie, kod jednorazowy poprawny i błędny, włączenie, wyłączenie i reset weryfikacji dwuetapowej, zmiana hasła, wydanie linku do hasła, utworzenie, zmiana, blokada, zawieszenie i odblokowanie konta, odmowa dostępu, odczyt karty oceny, pobranie arkusza, wgląd w dziennik, eksport dziennika, czynność w panelu administratora Django.

## 4. Ustawienia

| Ustawienie | Domyślnie | Znaczenie |
|---|---|---|
| `ASYSTENT_2FA` | `wymagane`; w trybie demonstracyjnym `dobrowolne` | Czy każde konto musi mieć aplikację uwierzytelniającą |
| `ASYSTENT_PROBY_LOGOWANIA`, `ASYSTENT_BLOKADA_MINUT` | 5 prób, 15 minut | Blokada logowania po nieudanych próbach (hasło albo kod) |
| `[bezpieczenstwo] zawieszenie_konta_po_miesiacach` w `zgodnosc.toml` | 1 | Po ilu miesiącach bez logowania konto jest zawieszane |
| `[bezpieczenstwo] dziennik_przechowywanie_lat` w `zgodnosc.toml` | 2 | Okres przechowywania dziennika pokazywany administratorowi |
| `ASYSTENT_HTTPS`, `ASYSTENT_ZA_PROXY` | wyłączone | Ciasteczka i HSTS dla HTTPS; adres IP z nagłówka serwera pośredniczącego |

Polecenia: `manage.py zawies_nieaktywne` (przegląd kont, do zadania dziennego), `manage.py sprawdz_dziennik` (kontrola łańcucha skrótów), `manage.py odblokuj_konto <login>` (gdy żaden administrator nie ma czynnego konta; czynność zostaje w dzienniku).

## 5. Znane luki

- Klucz TOTP w bazie nie jest szyfrowany.
- Nie ma kodów zapasowych ani drugiego rodzaju składnika.
- Blokada po nieudanych próbach działa na konto, nie na adres IP. Osoba znająca cudzy login może nią na kwadrans wstrzymać logowanie tej osoby.
- Zmiana polityki z „dobrowolne” na „wymagane” obejmuje trwające sesje dopiero przy następnym logowaniu.
- Łańcuch skrótów wykrywa zmianę dziennika, ale jej nie zapobiega; nie ma wysyłki zdarzeń do zewnętrznego systemu.
- Kontrola łańcucha przy każdym otwarciu dziennika czyta wszystkie wpisy - przy dużym dzienniku trzeba ją przenieść do zadania nocnego.
- Zawieszenie konta nie wysyła powiadomienia do użytkownika ani przełożonego.
- Konto pokazowe administratora działa bez hasła - wyłącznie w trybie demonstracyjnym, na danych fikcyjnych.
- Nie było testów penetracyjnych ani przeglądu kodu przez osobę trzecią.

## 6. Jak to sprawdzić

```
.venv/bin/python manage.py test oceny.tests.test_bezpieczenstwo oceny.tests.test_logowanie oceny.tests.test_administracja
```

Kody jednorazowe są sprawdzane wektorami testowymi z RFC 4226 i RFC 6238. W pokazie: konto „administrator” na pasku u góry, menu „Administracja”; weryfikację dwuetapową włącza się na stronie „Moje konto”.

## 7. Źródła

- Rozporządzenie KRI: `https://api.sejm.gov.pl/eli/acts/DU/2024/773`.
- Ustawa o KSC: `https://api.sejm.gov.pl/eli/acts/DU/2026/20` (tekst jednolity) i `https://api.sejm.gov.pl/eli/acts/DU/2026/252` (zmiana art. 8, załącznik nr 4).
- RFC 4226 (HOTP), RFC 6238 (TOTP).
