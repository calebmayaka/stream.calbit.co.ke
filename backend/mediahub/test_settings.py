"""Isolated tests: no production database, disk cache, or Jellyfin credentials."""

import os

os.environ["MEDIAHUB_DATA_MODE"] = "mock"
os.environ.setdefault("DJANGO_SECRET_KEY", "isolated-tests-only")

from .settings import *  # noqa: F403, E402

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIAHUB_DATA_MODE = "mock"
MEDIAHUB_SETUP_CODE = ""
ALLOWED_HOSTS = ["testserver", "localhost"]
JELLYFIN_API_KEY = "test-key"
JELLYFIN_STREAM_USER = "test-stream"
JELLYFIN_STREAM_PASSWORD = "test-password"
JELLYFIN_URL = "http://jellyfin.invalid"
JELLYFIN_USER_ID = "test-user"
