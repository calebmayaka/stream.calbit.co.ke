"""
Set or change the pass key used by the "Forgot password?" page. Only a hash is
stored, in backend/.env as MEDIAHUB_RESET_KEY_HASH. Restart the API afterwards.

    .venv\\Scripts\\python manage.py setresetkey          (prompts, hidden)
    .venv\\Scripts\\python manage.py setresetkey --off    (disables the reset page)
"""

import getpass
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError

MIN_LENGTH = 12


class Command(BaseCommand):
    help = "Set the pass key for password resets (stores only its hash in .env)."

    def add_arguments(self, parser):
        parser.add_argument("--off", action="store_true", help="Disable password reset")

    def handle(self, off, **options):
        if off:
            value = ""
        else:
            key = getpass.getpass("New reset pass key: ")
            if key != getpass.getpass("Again: "):
                raise CommandError("Keys don't match.")
            if len(key) < MIN_LENGTH:
                raise CommandError(f"Use at least {MIN_LENGTH} characters.")
            value = make_password(key)

        env_file = Path(settings.BASE_DIR) / ".env"
        lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
        lines = [l for l in lines if not re.match(r"\s*MEDIAHUB_RESET_KEY_HASH\s*=", l)]
        # Single-quoted: python-dotenv leaves the hash's $ characters alone.
        lines.append(f"MEDIAHUB_RESET_KEY_HASH='{value}'")
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        state = "disabled" if off else "set"
        self.stdout.write(self.style.SUCCESS(f"Reset pass key {state}. Now run: nssm restart mediahub-api"))
