"""Ustawienia projektu Django - Cyfrowy Asystent Ocen Okresowych.

Wszystko, co zależy od wdrożenia, pochodzi ze zmiennych środowiskowych z prefiksem ASYSTENT_.
Wartości domyślne są bezpieczne: tryb diagnostyczny i tryb demonstracyjny są wyłączone.
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _flaga(nazwa: str) -> bool:
    return os.environ.get(nazwa, "").strip().lower() in ("1", "true", "tak", "yes")


def _lista(nazwa: str, domyslnie: str = "") -> list[str]:
    return [element.strip() for element in os.environ.get(nazwa, domyslnie).split(",") if element.strip()]


# Bez klucza w środowisku klucz jest losowy dla każdego uruchomienia (sesje wygasają po restarcie).
SECRET_KEY = os.environ.get("ASYSTENT_SECRET_KEY") or secrets.token_urlsafe(64)
DEBUG = _flaga("ASYSTENT_DEBUG")
ALLOWED_HOSTS = _lista("ASYSTENT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = _lista("ASYSTENT_CSRF_TRUSTED_ORIGINS")

# --- ustawienia aplikacji ---
ASYSTENT_TRYB_DEMO = _flaga("ASYSTENT_TRYB_DEMO")  # konta demonstracyjne i szybkie przełączanie ról
ASYSTENT_DZIS = os.environ.get("ASYSTENT_DZIS") or None  # RRRR-MM-DD zamiast dzisiejszej daty (pokazy, testy)
ASYSTENT_DNI_PILNE = int(os.environ.get("ASYSTENT_DNI_PILNE", "14"))  # od ilu dni przed terminem zadanie jest pilne
ASYSTENT_URZAD = os.environ.get("ASYSTENT_URZAD", "Urząd")  # nazwa urzędu w nagłówku i na wydrukach
ASYSTENT_MIEJSCOWOSC = os.environ.get("ASYSTENT_MIEJSCOWOSC", "")  # miejscowość przy podpisach na arkuszu
# W urzędzie bez stanowiska dyrektora generalnego sprzeciw wnosi się do kierownika urzędu (pouczenie na arkuszu).
ASYSTENT_BEZ_DYREKTORA_GENERALNEGO = _flaga("ASYSTENT_BEZ_DYREKTORA_GENERALNEGO")
# Wydruk PDF: ścieżka do programu LibreOffice (soffice); bez niej program jest szukany w systemie.
ASYSTENT_SOFFICE = os.environ.get("ASYSTENT_SOFFICE") or None
# HR Copilot: lokalny model językowy uruchomiony w Ollamie - dane nie opuszczają infrastruktury urzędu.
ASYSTENT_OLLAMA_ADRES = os.environ.get("ASYSTENT_OLLAMA_ADRES", "http://localhost:11434")
ASYSTENT_MODEL = os.environ.get("ASYSTENT_MODEL", "pllum-12b-chat-2512:q4_k_m")
ASYSTENT_MODEL_LIMIT_CZASU = int(os.environ.get("ASYSTENT_MODEL_LIMIT_CZASU", "120"))
# EZD RP (tylko odczyt). Bez adresu karta kontekstu pracuje na danych przykładowych - wyraźnie oznaczonych.
ASYSTENT_EZD_ADRES = os.environ.get("ASYSTENT_EZD_ADRES") or None

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "oceny",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Każdy widok wymaga zalogowania, o ile nie jest wprost oznaczony jako publiczny.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "oceny.middleware.NaglowkiBezpieczenstwa",
]

ROOT_URLCONF = "serwis.urls"
WSGI_APPLICATION = "serwis.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "oceny.kontekst.wspolny",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("ASYSTENT_BAZA") or BASE_DIR / "db.sqlite3",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "logowanie"
LOGIN_REDIRECT_URL = "zadania"
LOGOUT_REDIRECT_URL = "logowanie"

LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- bezpieczeństwo sesji i transportu ---
_HTTPS = _flaga("ASYSTENT_HTTPS")  # włączyć, gdy aplikacja jest wystawiona przez HTTPS (zalecane)
SESSION_COOKIE_SECURE = _HTTPS
CSRF_COOKIE_SECURE = _HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_HSTS_SECONDS = 31536000 if _HTTPS else 0
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if _flaga("ASYSTENT_ZA_PROXY") else None
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Powiadomienia: domyślnie na konsolę; serwer pocztowy urzędu ustawia się zmiennymi ASYSTENT_EMAIL_*.
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if os.environ.get("ASYSTENT_EMAIL_HOST")
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("ASYSTENT_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("ASYSTENT_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("ASYSTENT_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("ASYSTENT_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("ASYSTENT_EMAIL_OD", "asystent-ocen@localhost")
