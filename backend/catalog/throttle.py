"""Reserve login attempts with a single conditional SQL update.

Reservations happen before password verification, so concurrent requests cannot
all pass a read-then-increment check. A successful login clears its reservation.
"""

import hashlib
import threading
from datetime import timedelta

from django.conf import settings
from django.db.models import Case, F, Q, Value, When
from django.utils import timezone

from .models import LoginAttempt

_lock = threading.Lock()  # Keep SQLite dev connections from contending on creation.


def _key(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reserve(value):
    with _lock:
        return _reserve(value)


def _reserve(value):
    now = timezone.now()
    expiry = now + timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
    key = _key(value)
    LoginAttempt.objects.get_or_create(key=key, defaults={"expires_at": expiry})
    return bool(
        LoginAttempt.objects.filter(key=key)
        .filter(Q(expires_at__lte=now) | Q(attempts__lt=settings.LOGIN_ATTEMPTS))
        .update(
            attempts=Case(When(expires_at__lte=now, then=Value(1)), default=F("attempts") + 1),
            expires_at=Case(When(expires_at__lte=now, then=Value(expiry)), default=F("expires_at")),
        )
    )


def clear(value):
    LoginAttempt.objects.filter(key=_key(value)).delete()
