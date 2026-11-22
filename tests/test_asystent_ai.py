"""Asystent AI: pytania o procedurę i korekta językowa - jedyne funkcje dopuszczone w rejestrze `zgodnosc.toml`.

Źródła wymagań:
- zadanie KPRM: moduł AI wspierający uczestników procesu oraz anonimizacja danych przetwarzanych poza
  infrastrukturą urzędu,
- rozporządzenie (UE) 2024/1689, załącznik III pkt 4 lit. b: system AI do oceny wydajności i zachowania
  pracowników jest systemem wysokiego ryzyka - dlatego model nie ocenia i nie proponuje ocen,
- brzmienie przepisów w `baza_wiedzy.json`: u.s.c. (t.j. Dz. U. z 2026 r. poz. 590), rozp. PRM z 4 kwietnia 2016 r.
  (Dz. U. poz. 470).

Model językowy jest w testach atrapą: funkcją `wiadomości -> tekst`.
"""

import json
import urllib.error
from dataclasses import replace

import pytest

from asystent_ocen.asystent_ai import (
    ZASADY_KOREKTY,
    ZASADY_ODPOWIEDZI,
    BladModelu,
    KlientOllama,
    czy_prosba_o_ocene_osoby,
    dolacz_odeslania,
    odpowiedz_na_pytanie,
    popraw_jezyk,
    wczytaj_fragmenty,
    znajdz_fragmenty,
)
from asystent_ocen.konfiguracja import wczytaj_przepisy
from asystent_ocen.zgodnosc import BladZgodnosci, rejestr_funkcji_ai, wczytaj_wymogi


class AtrapaModelu:
    def __init__(self, odpowiedz="Odpowiedź modelu."):
        self.odpowiedz = odpowiedz
        self.wywolania = []

    def __call__(self, wiadomosci):
        self.wywolania.append(wiadomosci)
        return self.odpowiedz


def _fragment(zrodlo):
    return {fragment.zrodlo: fragment for fragment in wczytaj_fragmenty()}[zrodlo]


# --- baza wiedzy ---

def test_baza_wiedzy_zawiera_przepisy_o_ocenie_sprzeciwie_i_stopniach():
    zrodla = {fragment.zrodlo for fragment in wczytaj_fragmenty()}
    assert {
        "art. 81 ust. 4 u.s.c.", "art. 81 ust. 9 u.s.c.", "art. 83 ust. 1 u.s.c.", "art. 89 ust. 2 u.s.c.",
        "§ 5 rozp.", "§ 7 rozp.", "§ 11 rozp.", "załącznik nr 1 do rozp., kryterium „Rzetelność”",
    } <= zrodla


def test_fragment_ma_doslowne_brzmienie_przepisu():
    """Art. 83 ust. 1 u.s.c. - brzmienie z wyciągu przepisów KPRM."""
    assert _fragment("art. 83 ust. 1 u.s.c.").tresc == (
        "Od oceny okresowej służy, w terminie 7 dni od dnia zapoznania się z oceną, sprzeciw do dyrektora "
        "generalnego urzędu."
    )


def test_baza_wiedzy_jest_spojna_z_parametrami_przepisow():
    """Zmiana przepisu wymaga zmiany w dwóch plikach: `przepisy.toml` i `baza_wiedzy.json`. Test pilnuje,
    żeby asystent nie odpowiadał według starego brzmienia po zmianie samych parametrów."""
    przepisy = wczytaj_przepisy()
    assert f"w terminie {przepisy.sprzeciw_dni} dni" in _fragment("art. 83 ust. 1 u.s.c.").tresc
    assert f"co {przepisy.cykl_oceny_miesiace} miesiące" in _fragment("art. 81 ust. 4 u.s.c.").tresc
    assert f"nie więcej niż {przepisy.max_kryteriow_dodatkowych} kryteria dodatkowe" in _fragment("§ 5 rozp.").tresc
    assert f"{przepisy.termin_kryteriow_dni} dni od dnia sporządzenia" in _fragment("§ 7 rozp.").tresc


# --- wyszukiwanie przepisów do pytania ---

@pytest.mark.parametrize(
    "pytanie, oczekiwane_zrodlo",
    [
        ("W jakim terminie mogę wnieść sprzeciw od oceny okresowej?", "art. 83 ust. 1 u.s.c."),
        ("Ile kryteriów dodatkowych może wybrać oceniający?", "§ 5 rozp."),
        ("Co ile miesięcy sporządza się ocenę okresową?", "art. 81 ust. 4 u.s.c."),
        ("Kiedy urzędnik otrzymuje kolejny stopień służbowy po dwóch ocenach?", "art. 89 ust. 2 u.s.c."),
        ("Co oznacza kryterium rzetelność?", "załącznik nr 1 do rozp., kryterium „Rzetelność”"),
        ("Kiedy ponowna ocena po ocenie negatywnej?", "art. 81 ust. 9 u.s.c."),
        ("Czy nieobecność w pracy przedłuża termin oceny?", "art. 81 ust. 7 u.s.c."),
        # pytania sformułowane potocznie, innymi słowami niż przepis
        ("Byłam cztery miesiące na zwolnieniu lekarskim. Czy termin oceny się przesuwa?", "art. 81 ust. 7 u.s.c."),
        ("Dostałem ocenę negatywną. Co dalej i kiedy będzie następna ocena?", "art. 81 ust. 9 u.s.c."),
        ("Nie zgadzam się z oceną, co mogę zrobić?", "art. 83 ust. 1 u.s.c."),
        ("Ile czasu ma przełożony na wyznaczenie kryteriów?", "§ 7 rozp."),
        ("Który arkusz stosuje się dla naczelnika wydziału?", "§ 3 rozp."),
    ],
)
def test_wyszukiwanie_znajduje_wlasciwy_przepis(pytanie, oczekiwane_zrodlo):
    assert oczekiwane_zrodlo in [fragment.zrodlo for fragment in znajdz_fragmenty(pytanie, limit=4)]


@pytest.mark.parametrize(
    "znalezione, oczekiwane_dodatkowe",
    [
        (["§ 5 rozp."], "§ 7 rozp."),  # § 7: „Czynności, o których mowa w § 5 i § 6, dokonuje się w terminie”
        (["art. 81 ust. 8 u.s.c."], "§ 8 rozp."),  # § 8: „w przypadkach, o których mowa w art. 81 ust. 8 ustawy”
        (["art. 81 ust. 4 u.s.c."], "art. 81 ust. 7 u.s.c."),  # ust. 7: „termin, o którym mowa w ust. 4”
    ],
)
def test_odeslania_dolaczaja_przepis_ktory_powoluje_znaleziony(znalezione, oczekiwane_dodatkowe):
    """Przepisy odsyłają do siebie numerami, więc samo dopasowanie wyrazów pomija np. termin z § 7."""
    wynik = dolacz_odeslania([_fragment(zrodlo) for zrodlo in znalezione], limit=3)

    assert [fragment.zrodlo for fragment in wynik[: len(znalezione)]] == znalezione
    assert oczekiwane_dodatkowe in [fragment.zrodlo for fragment in wynik]
    assert len(wynik) <= len(znalezione) + 3
    assert len({fragment.id for fragment in wynik}) == len(wynik)


def test_wyszukiwanie_zwraca_najwyzej_tyle_fragmentow_ile_wynosi_limit():
    assert len(znajdz_fragmenty("ocena okresowa", limit=2)) == 2


def test_wyszukiwanie_bez_trafien_zwraca_pusta_liste():
    assert znajdz_fragmenty("Jaka będzie jutro pogoda w Gorzowie?") == []


# --- pytania o procedurę ---

def test_pytanie_o_procedure_trafia_do_modelu_razem_z_przepisami():
    model = AtrapaModelu("Sprzeciw wnosi się w terminie 7 dni (art. 83 ust. 1 u.s.c.).")

    odpowiedz = odpowiedz_na_pytanie("W jakim terminie mogę wnieść sprzeciw od oceny okresowej?", model=model)

    assert odpowiedz.tekst == "Sprzeciw wnosi się w terminie 7 dni (art. 83 ust. 1 u.s.c.)."
    assert not odpowiedz.odmowa
    assert "art. 83 ust. 1 u.s.c." in odpowiedz.zrodla
    assert odpowiedz.powolane == ("art. 83 ust. 1 u.s.c.",)
    assert odpowiedz.ostrzezenia == ()
    [wiadomosci] = model.wywolania
    assert wiadomosci[0] == {"role": "system", "content": ZASADY_ODPOWIEDZI}
    assert wiadomosci[-1]["role"] == "user"
    assert "[art. 83 ust. 1 u.s.c.]" in wiadomosci[-1]["content"]
    assert "sprzeciw do dyrektora generalnego urzędu" in wiadomosci[-1]["content"]
    assert "W jakim terminie mogę wnieść sprzeciw od oceny okresowej?" in wiadomosci[-1]["content"]


def test_do_modelu_trafia_tez_przepis_powolujacy_znalezione():
    model = AtrapaModelu("Nie więcej niż 3 (§ 5 rozp.), w terminie 30 dni (§ 7 rozp.).")

    odpowiedz = odpowiedz_na_pytanie("Ile kryteriów dodatkowych może wybrać oceniający?", model=model)

    assert "[§ 7 rozp.]" in model.wywolania[0][-1]["content"]
    assert set(odpowiedz.powolane) == {"§ 5 rozp.", "§ 7 rozp."}


def test_slowa_pomocnicze_do_wyszukiwania_nie_trafiaja_do_modelu():
    """Pole `hasla` w bazie wiedzy pomaga znaleźć przepis, ale nie jest jego treścią."""
    model = AtrapaModelu("Termin ulega przedłużeniu (art. 81 ust. 7 u.s.c.).")
    assert "zwolnienie lekarskie" in _fragment("art. 81 ust. 7 u.s.c.").hasla

    odpowiedz_na_pytanie("Czy nieobecność w pracy przedłuża termin oceny?", model=model)

    assert "zwolnienie lekarskie" not in model.wywolania[0][-1]["content"]


def test_zasady_odpowiedzi_zakazuja_oceniania_i_wymagaja_podstawy_prawnej():
    assert "wyłącznie na podstawie przepisów" in ZASADY_ODPOWIEDZI
    assert "podstawę prawną" in ZASADY_ODPOWIEDZI
    assert "dosłownie" in ZASADY_ODPOWIEDZI
    assert "Nie oceniaj" in ZASADY_ODPOWIEDZI


def test_model_dostaje_wzor_odpowiedzi_zbudowany_z_bazy_wiedzy():
    """Wzór pokazuje modelowi sposób wskazywania podstawy prawnej. Powstaje z bazy wiedzy, więc po zmianie
    przepisów nie podaje nieaktualnej treści."""
    model = AtrapaModelu("Sprzeciw wnosi się w terminie 7 dni (art. 83 ust. 1 u.s.c.).")

    odpowiedz_na_pytanie("W jakim terminie mogę wnieść sprzeciw od oceny okresowej?", model=model)

    [wiadomosci] = model.wywolania
    assert [wiadomosc["role"] for wiadomosc in wiadomosci] == ["system", "user", "assistant", "user"]
    tresci = {fragment.zrodlo: fragment.tresc for fragment in wczytaj_fragmenty()}
    uzyte = [zrodlo for zrodlo in tresci if f"[{zrodlo}] {tresci[zrodlo]}" in wiadomosci[1]["content"]]
    assert len(uzyte) == 2
    for zrodlo in uzyte:
        assert f"{tresci[zrodlo].rstrip('.')} ({zrodlo})." in wiadomosci[2]["content"]


@pytest.mark.decyzja_projektowa
@pytest.mark.parametrize(
    "pytanie, czy_prosba",
    [
        ("Jaką ocenę wystawić Janowi Kowalskiemu za współpracę?", True),
        ("Zaproponuj ocenę cząstkową za rzetelność dla mojego pracownika", True),
        ("Ile punktów dać za kryterium komunikacja?", True),
        ("Oceń pracę Anny Nowak", True),
        ("Czy powinienem zwolnić pracownika po tej ocenie?", True),
        ("Napisz uzasadnienie oceny negatywnej dla Jana", True),
        ("W jakim terminie oceniający sporządza ocenę?", False),
        ("Jaka jest skala ocen cząstkowych?", False),
        ("Co oznacza ocena negatywna dla urzędnika?", False),
        ("Kto ocenia kierownika urzędu?", False),
        ("Kiedy uzasadnienie oceny jest obowiązkowe?", False),
    ],
)
def test_rozpoznanie_prosby_o_ocene_osoby(pytanie, czy_prosba):
    assert czy_prosba_o_ocene_osoby(pytanie) is czy_prosba


@pytest.mark.decyzja_projektowa
def test_prosba_o_ocene_osoby_jest_odmawiana_bez_wywolania_modelu():
    """Decyzja zespołu: AI nie ocenia. Odmowa podaje podstawę z rejestru funkcji AI (funkcja wysokiego ryzyka)."""
    model = AtrapaModelu()
    podstawa = {funkcja.kod: funkcja for funkcja in rejestr_funkcji_ai()}["PROPOZYCJA_OCENY"].podstawa

    odpowiedz = odpowiedz_na_pytanie("Jaką ocenę wystawić Janowi Kowalskiemu za współpracę?", model=model)

    assert odpowiedz.odmowa
    assert odpowiedz.powod == "ocena_osoby"
    assert podstawa in odpowiedz.tekst
    assert odpowiedz.zrodla == ()
    assert model.wywolania == []


def test_pytanie_bez_pokrycia_w_przepisach_nie_trafia_do_modelu():
    model = AtrapaModelu()

    odpowiedz = odpowiedz_na_pytanie("Jaka będzie jutro pogoda w Gorzowie?", model=model)

    assert odpowiedz.odmowa
    assert odpowiedz.powod == "brak_przepisu"
    assert model.wywolania == []


def test_odpowiedz_powolujaca_przepis_spoza_podanych_dostaje_ostrzezenie():
    model = AtrapaModelu("Sprzeciw wnosi się w terminie 7 dni (art. 999 u.s.c.).")

    odpowiedz = odpowiedz_na_pytanie("W jakim terminie mogę wnieść sprzeciw od oceny okresowej?", model=model)

    assert any("art. 999" in ostrzezenie for ostrzezenie in odpowiedz.ostrzezenia)


@pytest.mark.decyzja_projektowa
def test_odpowiedz_bez_podstawy_prawnej_dostaje_ostrzezenie():
    model = AtrapaModelu("Sprzeciw wnosi się w terminie 7 dni.")

    odpowiedz = odpowiedz_na_pytanie("W jakim terminie mogę wnieść sprzeciw od oceny okresowej?", model=model)

    assert odpowiedz.powolane == ()
    assert any("podstawy prawnej" in ostrzezenie for ostrzezenie in odpowiedz.ostrzezenia)


@pytest.mark.decyzja_projektowa
def test_odpowiedz_z_liczba_ktorej_nie_ma_w_przepisach_dostaje_ostrzezenie():
    """Zmyślony termin: przepis mówi o 7 dniach, model podał 21."""
    model = AtrapaModelu("Sprzeciw wnosi się w terminie 21 dni (art. 83 ust. 1 u.s.c.).")

    odpowiedz = odpowiedz_na_pytanie("W jakim terminie mogę wnieść sprzeciw od oceny okresowej?", model=model)

    assert any("21" in ostrzezenie for ostrzezenie in odpowiedz.ostrzezenia)


def test_wylaczona_funkcja_w_rejestrze_blokuje_pytania():
    wymogi = wczytaj_wymogi()
    funkcje = tuple(
        replace(funkcja, wlaczona=False) if funkcja.kod == "PYTANIA_O_PROCEDURE" else funkcja
        for funkcja in wymogi.funkcje_ai
    )
    model = AtrapaModelu()

    with pytest.raises(BladZgodnosci):
        odpowiedz_na_pytanie(
            "W jakim terminie mogę wnieść sprzeciw?", model=model, wymogi=replace(wymogi, funkcje_ai=funkcje)
        )
    assert model.wywolania == []


def test_dane_osobowe_z_pytania_nie_trafiaja_do_modelu():
    """Zadanie KPRM: anonimizacja danych przetwarzanych poza infrastrukturą urzędu."""
    model = AtrapaModelu("Termin wynosi 7 dni (art. 83 ust. 1 u.s.c.).")

    odpowiedz_na_pytanie(
        "Mój PESEL to 90010112345, tel. 501 234 567 - w jakim terminie mogę wnieść sprzeciw od oceny?", model=model
    )

    wyslane = json.dumps(model.wywolania, ensure_ascii=False)
    assert "90010112345" not in wyslane
    assert "501 234 567" not in wyslane


def test_puste_pytanie_jest_odrzucane():
    with pytest.raises(ValueError):
        odpowiedz_na_pytanie("   ", model=AtrapaModelu())


def test_pusta_odpowiedz_modelu_to_blad_modelu():
    with pytest.raises(BladModelu):
        odpowiedz_na_pytanie("W jakim terminie mogę wnieść sprzeciw od oceny okresowej?", model=AtrapaModelu("  "))


# --- korekta językowa uzasadnienia ---

def test_korekta_zwraca_propozycje_obok_oryginalu():
    model = AtrapaModelu("Zadania były wykonywane terminowo.")

    korekta = popraw_jezyk("zadania byly wykonywane terminowo", model=model)

    assert korekta.oryginal == "zadania byly wykonywane terminowo"
    assert korekta.propozycja == "Zadania były wykonywane terminowo."
    assert korekta.ostrzezenia == ()
    [wiadomosci] = model.wywolania
    assert wiadomosci[0] == {"role": "system", "content": ZASADY_KOREKTY}
    assert wiadomosci[-1] == {"role": "user", "content": "zadania byly wykonywane terminowo"}


def test_zasady_korekty_zakazuja_zmiany_tresci():
    assert "Nie zmieniaj treści" in ZASADY_KOREKTY
    assert "liczb" in ZASADY_KOREKTY


@pytest.mark.decyzja_projektowa
def test_korekta_ostrzega_gdy_model_zmienil_liczby():
    model = AtrapaModelu("Pracownik załatwił 15 spraw w 2026 r.")

    korekta = popraw_jezyk("pracownik zalatwil 12 spraw w 2026 r", model=model)

    assert any("liczb" in ostrzezenie for ostrzezenie in korekta.ostrzezenia)


@pytest.mark.decyzja_projektowa
def test_korekta_ostrzega_gdy_tekst_znaczaco_zmienil_dlugosc():
    model = AtrapaModelu("Zadania były wykonywane terminowo. " * 4)

    korekta = popraw_jezyk("zadania byly wykonywane terminowo", model=model)

    assert any("długość" in ostrzezenie for ostrzezenie in korekta.ostrzezenia)


def test_korekta_ukrywa_dane_osobowe_przed_modelem_i_przywraca_je_w_propozycji():
    wyslane = []

    def model(wiadomosci):
        wyslane.append(wiadomosci[-1]["content"])
        return wiadomosci[-1]["content"]

    korekta = popraw_jezyk(
        "Adam Kowalik (PESEL 90010112345) wykonywal zadania terminowo.", model=model, osoby=["Adam Kowalik"]
    )

    assert "Adam Kowalik" not in wyslane[0]
    assert "90010112345" not in wyslane[0]
    assert korekta.propozycja == "Adam Kowalik (PESEL 90010112345) wykonywal zadania terminowo."
    assert korekta.ostrzezenia == ()


@pytest.mark.decyzja_projektowa
def test_korekta_ostrzega_gdy_model_zgubil_znacznik_danych_osobowych():
    korekta = popraw_jezyk(
        "Adam Kowalik wykonywał zadania terminowo.",
        model=AtrapaModelu("Pracownik wykonywał zadania terminowo."),
        osoby=["Adam Kowalik"],
    )

    assert any("znacznik" in ostrzezenie for ostrzezenie in korekta.ostrzezenia)


def test_korekta_pustego_tekstu_jest_odrzucana():
    with pytest.raises(ValueError):
        popraw_jezyk("  \n ", model=AtrapaModelu())


def test_wylaczona_funkcja_w_rejestrze_blokuje_korekte():
    wymogi = wczytaj_wymogi()
    funkcje = tuple(
        replace(funkcja, wlaczona=False) if funkcja.kod == "KOREKTA_JEZYKOWA_UZASADNIENIA" else funkcja
        for funkcja in wymogi.funkcje_ai
    )
    model = AtrapaModelu()

    with pytest.raises(BladZgodnosci):
        popraw_jezyk("zadania byly wykonywane", model=model, wymogi=replace(wymogi, funkcje_ai=funkcje))
    assert model.wywolania == []


# --- klient lokalnego modelu (Ollama) ---

class _OdpowiedzHttp:
    def __init__(self, tresc):
        self._tresc = tresc

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self._tresc


def test_klient_ollama_wysyla_zadanie_czatu_i_zwraca_tresc_odpowiedzi():
    zapis = {}

    def otworz(zadanie, timeout):
        zapis.update(url=zadanie.full_url, dane=json.loads(zadanie.data), limit=timeout, metoda=zadanie.get_method())
        return _OdpowiedzHttp(json.dumps({"message": {"role": "assistant", "content": " Odpowiedź. "}}).encode())

    klient = KlientOllama("http://localhost:11434/", "pllum-12b-chat-2512:q4_k_m", limit_czasu=30, otworz=otworz)

    assert klient([{"role": "user", "content": "Cześć"}]) == "Odpowiedź."
    assert zapis["url"] == "http://localhost:11434/api/chat"
    assert zapis["metoda"] == "POST"
    assert zapis["limit"] == 30
    assert zapis["dane"]["model"] == "pllum-12b-chat-2512:q4_k_m"
    assert zapis["dane"]["stream"] is False
    assert zapis["dane"]["options"]["temperature"] == 0  # odpowiedzi o prawie mają być powtarzalne
    assert zapis["dane"]["messages"] == [{"role": "user", "content": "Cześć"}]
    assert "format" not in zapis["dane"]  # bez schematu model odpowiada zwykłym tekstem


def test_klient_ollama_przekazuje_schemat_odpowiedzi_jako_format():
    """Sugestia ocen wymaga odpowiedzi w ustalonej postaci - Ollama wymusza ją parametrem `format` (JSON Schema)."""
    zapis = {}
    schemat = {"type": "object", "properties": {"ocena": {"type": "integer", "enum": [0, 1, 3]}}, "required": ["ocena"]}

    def otworz(zadanie, timeout):
        zapis.update(dane=json.loads(zadanie.data))
        return _OdpowiedzHttp(json.dumps({"message": {"role": "assistant", "content": '{"ocena": 3}'}}).encode())

    klient = KlientOllama("http://localhost:11434", "pllum", otworz=otworz)

    assert klient([{"role": "user", "content": "Oceń."}], schemat=schemat) == '{"ocena": 3}'
    assert zapis["dane"]["format"] == schemat


def test_klient_ollama_zamienia_blad_polaczenia_na_blad_modelu():
    def otworz(zadanie, timeout):
        raise urllib.error.URLError("connection refused")

    klient = KlientOllama("http://localhost:11434", "pllum", otworz=otworz)

    with pytest.raises(BladModelu):
        klient([{"role": "user", "content": "Cześć"}])


@pytest.mark.parametrize("tresc", [b"to nie jest json", b"{}", b'{"message": {"content": ""}}', b'{"error": "brak modelu"}'])
def test_klient_ollama_odrzuca_odpowiedz_bez_tresci(tresc):
    klient = KlientOllama("http://localhost:11434", "pllum", otworz=lambda zadanie, timeout: _OdpowiedzHttp(tresc))

    with pytest.raises(BladModelu):
        klient([{"role": "user", "content": "Cześć"}])


@pytest.mark.parametrize("adres", ["file:///etc/passwd", "ftp://serwer/model", "localhost:11434", ""])
def test_klient_ollama_przyjmuje_tylko_adres_http(adres):
    with pytest.raises(ValueError):
        KlientOllama(adres, "pllum")


# --- odpowiedź modelu bez znaczników ---
# Strona pokazuje odpowiedź jako zwykły tekst, więc „<br>” albo „**” z modelu byłyby widoczne dosłownie.

def test_odpowiedz_modelu_nie_zawiera_znacznikow_html_ani_markdownu():
    from asystent_ocen.asystent_ai import oczysc_tekst_modelu

    surowa = "## Projekt\nPierwsze zdanie.<br>Drugie **ważne** zdanie.</br><p>Trzeci akapit.</p><BR/>Koniec."

    assert oczysc_tekst_modelu(surowa) == "Projekt\nPierwsze zdanie.\nDrugie ważne zdanie.\nTrzeci akapit.\n\nKoniec."


def test_czyszczenie_nie_rusza_zwyklych_znakow():
    from asystent_ocen.asystent_ai import oczysc_tekst_modelu

    for tekst in ("Średnia < 4 i wynik > 2.", "Art. 81 ust. 4 u.s.c. - 2 * 12 miesięcy.", "- punkt pierwszy\n- punkt drugi", "plik_o_dlugiej_nazwie i __init__"):
        assert oczysc_tekst_modelu(tekst) == tekst


def test_odpowiedz_tekstowa_i_ustrukturyzowana_sa_czyszczone_przed_uzyciem():
    from asystent_ocen.asystent_ai import _zapytaj

    class ModelZeSchematem:
        def __call__(self, wiadomosci, schemat=None):
            if schemat is None:
                return "Zdanie pierwsze.<br>Zdanie **drugie**."
            return json.dumps({"pytania": [{"karta": "URLOP", "pytanie": "Jak zaplanować<br>urlop **w tym roku**?"}], "liczba": 1})

    assert _zapytaj(ModelZeSchematem(), []) == "Zdanie pierwsze.\nZdanie drugie."
    assert json.loads(_zapytaj(ModelZeSchematem(), [], {"type": "object"})) == {
        "pytania": [{"karta": "URLOP", "pytanie": "Jak zaplanować urlop w tym roku?"}], "liczba": 1,
    }


def test_odpowiedz_ktora_nie_jest_poprawnym_json_wraca_bez_zmian_do_kontroli_wywolujacego():
    from asystent_ocen.asystent_ai import _zapytaj

    class Zepsuty:
        def __call__(self, wiadomosci, schemat=None):
            return "to nie jest JSON <br>"

    assert _zapytaj(Zepsuty(), [], {"type": "object"}) == "to nie jest JSON <br>"
