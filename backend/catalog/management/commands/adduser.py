"""
Create a MediaHub login. The password is typed at a hidden prompt, never on
the command line (so it stays out of shell history).

    .venv\\Scripts\\python manage.py adduser caleb --name "Caleb"
    .venv\\Scripts\\python manage.py changepassword caleb     (built in)
    .venv\\Scripts\\python manage.py removeuser caleb
"""

import getpass

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a MediaHub login (prompts for the password)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--name", default="", help="Display name, e.g. 'Caleb'")

    def handle(self, username, name, **options):
        User = get_user_model()
        username = username.strip()
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError(f"'{username}' already exists. Use: manage.py changepassword {username}")

        user = User(username=username, first_name=name.strip())
        for _ in range(3):
            password = getpass.getpass(f"Password for {username}: ")
            if password != getpass.getpass("Again: "):
                self.stderr.write("Passwords don't match.")
                continue
            try:
                password_validation.validate_password(password, user)
            except ValidationError as exc:
                self.stderr.write("\n".join(exc.messages))
                continue
            break
        else:
            raise CommandError("No user created.")

        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Created login '{username}'."))
