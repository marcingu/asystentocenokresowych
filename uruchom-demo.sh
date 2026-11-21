#!/bin/sh
# Pokaz Cyfrowego Asystenta Ocen Okresowych na danych fikcyjnych.
#
# Użycie:  ./uruchom-demo.sh [--od-nowa] [port]
#   --od-nowa   usuwa bazę pokazową (demo.sqlite3) i buduje ją od początku z dzisiejszą datą
#   port        port serwera, domyślnie 8000
#
# Skrypt tworzy środowisko Pythona (.venv), instaluje dwie zależności, zakłada bazę pokazową
# i uruchamia serwer dostępny tylko z tego komputera (127.0.0.1). Niczego poza bazą pokazową nie usuwa.
set -eu
cd "$(dirname "$0")"

PORT=8000
OD_NOWA=0
for argument in "$@"; do
  case "$argument" in
    --od-nowa) OD_NOWA=1 ;;
    *[!0-9]*|"") echo "Nieznany argument: $argument" >&2; exit 2 ;;
    *) PORT="$argument" ;;
  esac
done

PYTHON="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  echo "Tworzę środowisko Pythona (.venv)..."
  "$PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c "import django, docx" 2>/dev/null; then
  echo "Instaluję zależności (Django, python-docx)..."
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

export ASYSTENT_TRYB_DEMO=1
export ASYSTENT_BAZA="$PWD/demo.sqlite3"
export ASYSTENT_URZAD="${ASYSTENT_URZAD:-Kancelaria Prezesa Rady Ministrów}"
export ASYSTENT_MIEJSCOWOSC="${ASYSTENT_MIEJSCOWOSC:-Warszawa}"
# Tylko w pokazie, na danych fikcyjnych: funkcje wysokiego ryzyka według AI Act (sugestia ocen cząstkowych,
# propozycja kierunków do IPRZ i pytania do kart obserwacji radaru) włączone plikiem decyzji. Pokaz bez nich: ASYSTENT_DECYZJE_AI= ./uruchom-demo.sh
export ASYSTENT_DECYZJE_AI="${ASYSTENT_DECYZJE_AI-$PWD/decyzje-ai-pokaz.toml}"
# Klucz sesji pokazu zapisany obok bazy pokazowej: ponowne uruchomienie nie wylogowuje oglądających.
# Plik jest tylko dla właściciela i nie trafia do repozytorium. We wdrożeniu klucz podaje się zmienną środowiskową.
if [ -z "${ASYSTENT_SECRET_KEY:-}" ]; then
  if [ ! -s .demo-klucz ]; then
    (umask 077 && .venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))" > .demo-klucz)
  fi
  ASYSTENT_SECRET_KEY="$(cat .demo-klucz)"
  export ASYSTENT_SECRET_KEY
fi

if [ "$OD_NOWA" = 1 ] && [ -f demo.sqlite3 ]; then
  rm demo.sqlite3
fi
NOWA_BAZA=0
[ -f demo.sqlite3 ] || NOWA_BAZA=1
.venv/bin/python manage.py migrate --noinput --verbosity 0
if [ "$NOWA_BAZA" = 1 ]; then
  .venv/bin/python manage.py demo
fi

echo "Pokaz działa pod adresem http://127.0.0.1:$PORT/ (zatrzymanie: Ctrl+C)"
exec .venv/bin/python manage.py runserver "127.0.0.1:$PORT" --noreload
