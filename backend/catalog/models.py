from django.db import models


class LoginAttempt(models.Model):
    # Hash the username/IP pair so the index remains bounded and contains no PII.
    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class StreamToken(models.Model):
    token = models.TextField(unique=True)
    user_id = models.CharField(max_length=64)
    device_id = models.CharField(max_length=80)
    issued_at = models.DateTimeField()
    rotate_at = models.DateTimeField(db_index=True)
    revoke_at = models.DateTimeField(db_index=True)


class PlaybackSession(models.Model):
    id = models.CharField(max_length=128, primary_key=True)
    token = models.ForeignKey(StreamToken, on_delete=models.CASCADE)
