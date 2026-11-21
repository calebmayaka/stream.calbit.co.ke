import threading

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.tokens import cleanup_loop, cleanup_once


class Command(BaseCommand):
    help = "Revoke expired stream credentials; --watch runs cleanup alongside a live dev server."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")

    def handle(self, watch, **options):
        if settings.MEDIAHUB_DATA_MODE != "live":
            raise CommandError("Token cleanup requires live mode; mock mode never contacts Jellyfin.")
        if watch:
            try:
                cleanup_loop(threading.Event())
            except KeyboardInterrupt:
                pass
        else:
            count = cleanup_once()
            self.stdout.write(f"Revoked {count} expired stream credential(s). Failures remain queued for retry.")
