"""Delete a MediaHub login (and sign it out everywhere).

    .venv\\Scripts\\python manage.py removeuser someone
"""

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Delete a MediaHub login and end its sessions."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, username, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username__iexact=username.strip())
        except User.DoesNotExist:
            raise CommandError(f"No login called '{username}'.")

        ended = 0
        for session in Session.objects.all():
            if session.get_decoded().get("_auth_user_id") == str(user.pk):
                session.delete()
                ended += 1
        user.delete()
        self.stdout.write(self.style.SUCCESS(f"Removed '{user.username}' ({ended} session(s) ended)."))
