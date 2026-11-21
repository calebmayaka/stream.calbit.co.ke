from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.utils import timezone

from catalog import jellyfin, streaming, tokens
from catalog.models import PlaybackSession, StreamToken
from .test_security import NoNetworkTestCase


@override_settings(MEDIAHUB_DATA_MODE="live", JELLYFIN_STREAM_TOKEN_HOURS=6)
class TokenTests(NoNetworkTestCase):
    def setUp(self):
        super().setUp()
        self.now = timezone.now()
        self.clock = patch("catalog.tokens.timezone.now", return_value=self.now)
        self.clock_mock = self.clock.start()
        self.addCleanup(self.clock.stop)
        auth_patch = patch("catalog.tokens.jellyfin.authenticate", side_effect=[
            ("fake-token-1", "user", {}), ("fake-token-2", "user", {})
        ])
        self.auth = auth_patch.start()
        self.addCleanup(auth_patch.stop)
        logout_patch = patch("catalog.tokens.jellyfin.logout")
        self.logout = logout_patch.start()
        self.addCleanup(logout_patch.stop)

    def test_tokens_survive_cache_eviction_and_rotate_with_distinct_devices(self):
        first = tokens.stream_session()
        cache.clear()
        self.assertEqual(tokens.stream_session().pk, first.pk)
        self.clock_mock.return_value = self.now + timedelta(hours=6)
        second = tokens.stream_session()
        self.assertNotEqual(first.device_id, second.device_id)
        self.assertEqual(first.revoke_at, self.now + timedelta(hours=12))
        self.assertEqual(StreamToken.objects.count(), 2)

    def test_idle_token_is_revoked_without_another_playback(self):
        first = tokens.stream_session()
        self.clock_mock.return_value = self.now + timedelta(hours=12)
        self.assertEqual(tokens.revoke_expired_tokens(), 1)
        self.logout.assert_called_once_with(first.token, device=first.device_id)
        self.assertFalse(StreamToken.objects.exists())

    def test_rotation_keeps_an_older_stream_alive_until_its_deadline(self):
        first = tokens.stream_session()
        self.clock_mock.return_value = self.now + timedelta(hours=7)
        tokens.stream_session()
        self.assertEqual(tokens.revoke_expired_tokens(), 0)
        self.assertTrue(StreamToken.objects.filter(pk=first.pk).exists())
        self.logout.assert_not_called()

    def test_broker_returns_matching_device_and_records_playback_owner(self):
        item_id = "a" * 32
        source = {"Id": "b" * 32, "SupportsDirectPlay": True, "RunTimeTicks": 100_000_000}
        with patch("catalog.streaming.jellyfin.item", return_value={"Type": "Movie"}), \
             patch("catalog.streaming.jellyfin.playback_info", return_value={"PlaySessionId": "session1", "MediaSources": [source]}) as info, \
             patch("catalog.streaming.jellyfin.media_segments", return_value=[]):
            response = streaming.start(RequestFactory().get("/api/play"), item_id, 3)
        record = StreamToken.objects.get()
        self.assertEqual(info.call_args.kwargs["device"], record.device_id)
        self.assertIn(f"deviceId={record.device_id}", response["url"])
        self.assertIn(f"api_key={record.token}", response["url"])
        self.assertEqual(response["startSeconds"], 3)
        self.assertEqual(PlaybackSession.objects.get(pk="session1").token_id, record.pk)

    def test_failed_revocation_is_kept_and_retried(self):
        tokens.stream_session()
        self.clock_mock.return_value = self.now + timedelta(hours=13)
        self.logout.side_effect = jellyfin.JellyfinError("unavailable")
        self.assertEqual(tokens.revoke_expired_tokens(), 0)
        self.assertEqual(StreamToken.objects.count(), 1)
        self.logout.side_effect = None
        self.assertEqual(tokens.revoke_expired_tokens(), 1)

    def test_legacy_cache_tokens_are_recorded_before_eviction(self):
        cache.set("stream-token", {"current": {"token": "legacy", "user_id": "user"}}, timeout=None)
        self.logout.side_effect = jellyfin.JellyfinError("unavailable")
        tokens.revoke_expired_tokens()
        cache.clear()
        self.assertTrue(StreamToken.objects.filter(token="legacy").exists())
        self.logout.side_effect = None
        self.assertEqual(tokens.revoke_expired_tokens(), 1)

    def test_admin_credential_is_never_returned_and_failed_logout_is_retried(self):
        self.auth.side_effect = None
        self.auth.return_value = ("admin-token", "admin", {"IsAdministrator": True})
        self.logout.side_effect = jellyfin.JellyfinError("unavailable")
        with self.assertRaises(tokens.StreamConfigError):
            tokens.stream_session()
        self.assertTrue(StreamToken.objects.filter(token="admin-token", revoke_at=self.now).exists())

    def test_stop_uses_original_credential_after_rotation(self):
        first = tokens.stream_session()
        PlaybackSession.objects.create(id="session1", token=first)
        self.clock_mock.return_value = self.now + timedelta(hours=7)
        tokens.stream_session()
        with patch("catalog.streaming.jellyfin.stop_encoding") as stop:
            streaming.stop("session1")
        stop.assert_called_once_with(first.token, "session1", device=first.device_id)
        self.assertFalse(PlaybackSession.objects.exists())

    def test_cleanup_loop_retries_independently_of_requests(self):
        stop = Mock()
        stop.is_set.side_effect = [False, False, True]
        with patch("catalog.tokens.cleanup_once", side_effect=[RuntimeError("temporary failure"), 1]) as cleanup:
            tokens.cleanup_loop(stop)
        self.assertEqual(cleanup.call_count, 2)
        self.assertEqual(stop.wait.call_count, 2)


class LogoutTests(NoNetworkTestCase):
    def test_only_invalid_tokens_are_treated_as_already_revoked(self):
        for code in (401, 403, 500, None):
            with self.subTest(code=code), patch("catalog.jellyfin._request", side_effect=jellyfin.JellyfinError("failed", status_code=code)):
                if code == 401:
                    jellyfin.logout("fake")
                else:
                    with self.assertRaises(jellyfin.JellyfinError):
                        jellyfin.logout("fake")
