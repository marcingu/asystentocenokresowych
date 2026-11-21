"""Kody jednorazowe do weryfikacji dwuetapowej: TOTP (RFC 6238) na HOTP (RFC 4226), HMAC-SHA-1, 6 cyfr, krok 30 s.

Takie parametry obsługują popularne aplikacje uwierzytelniające. Moduł korzysta wyłącznie z biblioteki
standardowej Pythona.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

KROK = 30    # sekund
CYFRY = 6
OKNO = 1     # ile kroków wstecz i w przód przyjmujemy - tolerancja na różnicę zegarów


def nowy_sekret() -> str:
    """Losowy klucz 160 bitów (zalecenie RFC 4226) zapisany w Base32 - 32 znaki."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _klucz(sekret: str) -> bytes:
    czysty = "".join(str(sekret).split()).upper()
    return base64.b32decode(czysty + "=" * (-len(czysty) % 8))


def kod(sekret: str, czas: float | None = None, *, licznik: int | None = None, cyfry: int = CYFRY) -> str:
    """Kod dla podanej chwili (sekundy od 1.01.1970; domyślnie teraz) albo wprost dla licznika (HOTP)."""
    if licznik is None:
        licznik = int((time.time() if czas is None else czas) // KROK)
    skrot = hmac.new(_klucz(sekret), struct.pack(">Q", licznik), hashlib.sha1).digest()
    przesuniecie = skrot[-1] & 0x0F
    liczba = struct.unpack(">I", skrot[przesuniecie:przesuniecie + 4])[0] & 0x7FFFFFFF
    return str(liczba % 10 ** cyfry).zfill(cyfry)


def sprawdz(sekret: str, podany: str | None, czas: float | None = None, *, po_kroku: int = 0) -> int | None:
    """Numer kroku czasu, do którego pasuje kod, albo None.

    Przyjmowany jest kod z bieżącego kroku i z kroków sąsiednich (`OKNO`). `po_kroku` to krok ostatnio użytego
    kodu: kod z tego kroku albo starszego jest odrzucany, więc ten sam kod nie zadziała drugi raz.
    Porównanie w stałym czasie.
    """
    czysty = "".join(str(podany or "").split())
    if len(czysty) != CYFRY or not czysty.isdigit():
        return None
    biezacy = int((time.time() if czas is None else czas) // KROK)
    trafiony = None
    for krok in range(biezacy - OKNO, biezacy + OKNO + 1):
        if hmac.compare_digest(kod(sekret, licznik=krok), czysty) and krok > po_kroku:
            trafiony = krok
    return trafiony


def adres_otpauth(sekret: str, konto: str, wystawca: str) -> str:
    """Adres, który aplikacja uwierzytelniająca odczytuje z kodu QR albo z linku."""
    return (
        f"otpauth://totp/{quote(wystawca)}:{quote(konto)}?secret={sekret}&issuer={quote(wystawca)}"
        f"&algorithm=SHA1&digits={CYFRY}&period={KROK}"
    )


def sekret_w_grupach(sekret: str) -> str:
    """Klucz podzielony na czwórki znaków - do ręcznego przepisania."""
    return " ".join(sekret[start:start + 4] for start in range(0, len(sekret), 4))
