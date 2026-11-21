"""
Production entrypoint: Waitress on a loopback port, reverse-proxied by IIS.
NSSM runs this (see README.md). Host/port come from .env.
"""

import os

from waitress import serve

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mediahub.settings")

from mediahub.wsgi import application  # noqa: E402  (needs the settings module set)
from django.conf import settings
from catalog.tokens import start_cleanup_worker

if __name__ == "__main__":
    worker = start_cleanup_worker() if settings.MEDIAHUB_DATA_MODE == "live" else None
    try:
        serve(
            application,
            host=os.environ.get("MEDIAHUB_HOST", "127.0.0.1"),
            port=int(os.environ.get("MEDIAHUB_PORT", "8013")),
            # Requests mostly wait on Jellyfin/Postgres, not CPU; a home page fires
            # ~100 poster requests at once, which saturated 8 threads.
            threads=int(os.environ.get("MEDIAHUB_THREADS", "16")),
            # IIS forwards X-Forwarded-* so Django sees the real host/scheme.
            trusted_proxy="127.0.0.1",
            trusted_proxy_headers={"x-forwarded-host", "x-forwarded-proto", "x-forwarded-for"},
            clear_untrusted_proxy_headers=True,
        )
    finally:
        if worker:
            stop, thread = worker
            stop.set()
            thread.join(timeout=settings.JELLYFIN_TIMEOUT + 1)
