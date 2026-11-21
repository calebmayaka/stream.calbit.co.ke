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


class PlaybackStat(models.Model):
    """One watch, as reported by the player (see views.playback_stats).
    Summarised by `manage.py playbackstats`."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey("auth.User", null=True, on_delete=models.SET_NULL)
    item_id = models.CharField(max_length=32)
    method = models.CharField(max_length=16)  # direct | remux | transcode
    codec = models.CharField(max_length=16, blank=True)  # source video codec
    quality = models.CharField(max_length=16, default="auto")
    max_bitrate = models.PositiveIntegerField(default=0)
    remote = models.BooleanField(default=True)
    startup_ms = models.PositiveIntegerField(default=0)  # Play -> first picture
    stalls = models.PositiveIntegerField(default=0)  # buffering events after start
    stall_ms = models.PositiveIntegerField(default=0)
    watched_seconds = models.PositiveIntegerField(default=0)
    client = models.CharField(max_length=64, blank=True)  # e.g. "Chrome/Windows"
