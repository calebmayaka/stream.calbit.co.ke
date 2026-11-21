"""
MediaHub API settings.

Everything deployment-specific comes from environment variables, loaded from
backend/.env when present (see .env.example). Secrets never live in this file.
"""

import os
import math
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [v.strip() for v in env(name, default).split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off.")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

# IIS (and cloudflared in front of it) terminate the public connection.
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "catalog.middleware.LoginRequiredMiddleware",
]

# --- Login -------------------------------------------------------------------
# Session cookie login for the SPA. Accounts are managed with
# `manage.py adduser` / `changepassword` (see README).
SESSION_COOKIE_AGE = int(env("MEDIAHUB_SESSION_DAYS", "30")) * 24 * 3600
SESSION_COOKIE_NAME = "mediahub_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# Browsers accept Secure cookies on http://localhost, so dev keeps working.
SESSION_COOKIE_SECURE = env_bool("MEDIAHUB_SECURE_COOKIES", True)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_COOKIE_NAME = "mediahub_csrf"
CSRF_COOKIE_SAMESITE = "Lax"
# IIS/ARR rewrites Host to 127.0.0.1:8013, so the browser's Origin must be trusted explicitly.
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "https://stream.calbit.co.ke,http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
)
# One-time code that lets the first account be created from the login page
# while no accounts exist (see views.auth_setup). Empty = setup disabled.
MEDIAHUB_SETUP_CODE = env("MEDIAHUB_SETUP_CODE", "")
# Hash (never the key itself) of the pass key for the "Forgot password?" page.
# Set/rotate with `manage.py setresetkey`; empty = reset page disabled.
MEDIAHUB_RESET_KEY_HASH = env("MEDIAHUB_RESET_KEY_HASH", "")
# Shared secret the VPS reverse proxy (Caddy) sends with X-MediaHub-Client-IP.
# Only with it is that header believed, so the login lockout counts real visitor
# addresses instead of the proxy's. Empty = header ignored. (deploy/vps/)
MEDIAHUB_PROXY_KEY = env("MEDIAHUB_PROXY_KEY", "")
LOGIN_ATTEMPTS = 5  # per username + IP …
LOGIN_LOCKOUT_SECONDS = 15 * 60  # … within this window
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

ROOT_URLCONF = "mediahub.urls"
WSGI_APPLICATION = "mediahub.wsgi.application"

# PostgreSQL in production (own DB + user, like the other apps on this box).
# Without POSTGRES_DB set, fall back to SQLite so local dev needs no DB setup.
if env("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": env("POSTGRES_HOST", "127.0.0.1"),
            "PORT": env("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "var" / "dev.sqlite3",
        }
    }

# Poster/backdrop bytes proxied from Jellyfin are cached on disk.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": BASE_DIR / "var" / "cache",
        "TIMEOUT": 60 * 60 * 24,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Jellyfin -----------------------------------------------------------------
# "mock" serves canned data (no Jellyfin calls); "live" reads the real library.
MEDIAHUB_DATA_MODE = env("MEDIAHUB_DATA_MODE", "mock").lower()
if MEDIAHUB_DATA_MODE not in {"mock", "live"}:
    raise ImproperlyConfigured("MEDIAHUB_DATA_MODE must be 'mock' or 'live'.")

# Server-side address Django uses to talk to Jellyfin (never sent to browsers).
JELLYFIN_URL = env("JELLYFIN_URL", "http://10.30.0.12:8096").rstrip("/")
JELLYFIN_API_KEY = env("JELLYFIN_API_KEY", "")
JELLYFIN_USER_ID = env("JELLYFIN_USER_ID", "")
JELLYFIN_TIMEOUT = float(env("JELLYFIN_TIMEOUT", "8"))

if MEDIAHUB_DATA_MODE == "live" and not (JELLYFIN_API_KEY and JELLYFIN_USER_ID):
    raise ImproperlyConfigured("Live mode needs JELLYFIN_API_KEY and JELLYFIN_USER_ID.")

# Playback. Browsers stream straight from Jellyfin using a session token for a
# dedicated NON-admin Jellyfin user; the admin API key above never leaves Django.
# Watch progress is written back to JELLYFIN_USER_ID's library by Django.
JELLYFIN_STREAM_USER = env("JELLYFIN_STREAM_USER", "")
JELLYFIN_STREAM_PASSWORD = env("JELLYFIN_STREAM_PASSWORD", "")
# New playback uses a fresh token after this long; each token is revoked at 2x age.
JELLYFIN_STREAM_TOKEN_HOURS = float(env("JELLYFIN_STREAM_TOKEN_HOURS", "6"))
JELLYFIN_TOKEN_CLEANUP_SECONDS = float(env("JELLYFIN_TOKEN_CLEANUP_SECONDS", "60"))
for name in ("JELLYFIN_STREAM_TOKEN_HOURS", "JELLYFIN_TOKEN_CLEANUP_SECONDS"):
    value = globals()[name]
    if not math.isfinite(value) or value <= 0:
        raise ImproperlyConfigured(f"{name} must be a positive finite number.")
# Base URL browsers use for media. LAN users get JELLYFIN_URL; requests that came
# through Cloudflare (or over https) get this public hostname instead.
JELLYFIN_PUBLIC_URL = env("JELLYFIN_PUBLIC_URL", "").rstrip("/")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
