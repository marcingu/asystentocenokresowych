"""Wspólny typ błędu walidacji (kod maszynowy + komunikat dla użytkownika + podstawa prawna)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Blad:
    kod: str
    komunikat: str = ""
    podstawa: str = ""


class BladWalidacji(Exception):
    """Operacja odrzucona, bo dane naruszają reguły (lista błędów w atrybucie `bledy`)."""

    def __init__(self, bledy: list[Blad]):
        super().__init__("; ".join(b.kod for b in bledy))
        self.bledy = bledy

    @property
    def kody(self) -> set[str]:
        return {b.kod for b in self.bledy}
