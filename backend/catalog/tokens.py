"""Durable playback credentials and request-independent expiry cleanup."""

import logging
import threading
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.utils import timezone

from . import jellyfin
from .models import LoginAttempt, StreamToken

log = logging.getLogger(__name__)
_lock = threading.Lock()


class StreamConfigError(Exception):
    pass


def import_legacy_tokens():
    """Preserve any pre-upgrade cached credentials until logout succeeds."""
    state = cache.get("stream-token") or {}
    now = timezone.now()
    for name in ("current", "previous"):
        old = state.get(name)
        if old and old.get("token"):
            StreamToken.objects.get_or_create(
                token=old["token"],
                defaults={"user_id": old["user_id"], "device_id": jellyfin.DEVICE_ID,
                          "issued_at": now, "rotate_at": now, "revoke_at": now},
            )
    # Never discard a legacy token until it is durably recorded.
    cache.delete("stream-token")


def stream_session():
    with _lock:
        now = timezone.now()
        current = StreamToken.objects.filter(rotate_at__gt=now, revoke_at__gt=now).order_by("-issued_at").first()
        if current:
            return current
        if not (settings.JELLYFIN_STREAM_USER and settings.JELLYFIN_STREAM_PASSWORD):
            raise StreamConfigError("Set JELLYFIN_STREAM_USER and JELLYFIN_STREAM_PASSWORD to enable playback.")
        # A distinct device prevents upstream logins reusing the previous token.
        device = f"mediahub-{uuid.uuid4().hex}"
        token, user_id, policy = jellyfin.authenticate(
            settings.JELLYFIN_STREAM_USER, settings.JELLYFIN_STREAM_PASSWORD, device=device
        )
        now = timezone.now()
        ttl = timedelta(hours=settings.JELLYFIN_STREAM_TOKEN_HOURS)
        admin = policy.get("IsAdministrator", False)
        try:
            record = StreamToken.objects.create(
                token=token, user_id=user_id, device_id=device, issued_at=now,
                rotate_at=now if admin else now + ttl,
                revoke_at=now if admin else now + 2 * ttl,
            )
        except Exception:
            # A credential which cannot be recorded must never reach the browser.
            try:
                jellyfin.logout(token, device=device)
            except jellyfin.JellyfinError:
                log.error("Could not revoke an unrecorded stream credential; check Jellyfin sessions.")
            raise
        if admin:
            # Retain the record for retry if the immediate logout fails.
            revoke_expired_tokens()
            raise StreamConfigError("JELLYFIN_STREAM_USER is a Jellyfin admin; use a limited user.")
        return record


def revoke_expired_tokens():
    if settings.MEDIAHUB_DATA_MODE != "live":
        return 0
    import_legacy_tokens()
    revoked = 0
    for record in StreamToken.objects.filter(revoke_at__lte=timezone.now()).iterator():
        try:
            jellyfin.logout(record.token, device=record.device_id)
        except jellyfin.JellyfinError:
            log.warning("Stream credential %s logout failed; retaining it for retry.", record.pk)
        else:
            record.delete()
            revoked += 1
    return revoked


def cleanup_once():
    try:
        close_old_connections()
        revoked = revoke_expired_tokens()
        LoginAttempt.objects.filter(expires_at__lt=timezone.now() - timedelta(days=1)).delete()
        return revoked
    finally:
        connections.close_all()


def cleanup_loop(stop):
    while not stop.is_set():
        try:
            cleanup_once()
        except Exception:
            log.exception("MediaHub credential cleanup failed; retrying on the next interval.")
        stop.wait(settings.JELLYFIN_TOKEN_CLEANUP_SECONDS)


def start_cleanup_worker():
    # Fail startup before accepting traffic if the required migration is missing.
    StreamToken.objects.exists()
    stop = threading.Event()
    thread = threading.Thread(target=cleanup_loop, args=(stop,), name="stream-token-cleanup", daemon=True)
    thread.start()
    return stop, thread
