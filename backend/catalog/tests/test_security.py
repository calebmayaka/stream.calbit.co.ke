from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from catalog import throttle
from catalog.models import LoginAttempt
from catalog.views import MAX_SECONDS


class NoNetworkTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.network = patch("requests.sessions.Session.request", side_effect=AssertionError("Tests must not contact Jellyfin"))
        self.network.start()
        self.addCleanup(self.network.stop)
        cache.clear()


class AuthTests(NoNetworkTestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("viewer", password="a-test-password")

    def login(self, password="a-test-password"):
        return self.client.post("/api/auth/login", {"username": "viewer", "password": password}, content_type="application/json")

    def test_login_gate_and_logout(self):
        self.assertEqual(self.client.get("/api/home").status_code, 401)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/home").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", {}, content_type="application/json").status_code, 200)
        self.assertEqual(self.client.get("/api/home").status_code, 401)

    def test_csrf_and_foreign_origin(self):
        client = Client(enforce_csrf_checks=True)
        client.get("/api/auth/me")
        body = {"username": "viewer", "password": "a-test-password"}
        self.assertEqual(client.post("/api/auth/login", body, content_type="application/json").status_code, 403)
        token = client.cookies["mediahub_csrf"].value
        self.assertEqual(client.post("/api/auth/login", body, content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/login", body, content_type="application/json", HTTP_ORIGIN="https://foreign.invalid").status_code, 403)

    def test_lockout_survives_artwork_cache_clear_and_expires(self):
        for _ in range(5):
            self.assertEqual(self.login("incorrect").status_code, 400)
        cache.clear()
        self.assertEqual(self.login().status_code, 429)
        LoginAttempt.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.login().status_code, 200)
        self.assertFalse(LoginAttempt.objects.exists())

    def test_success_resets_failed_attempts(self):
        self.login("incorrect")
        self.assertEqual(self.login().status_code, 200)
        self.assertFalse(LoginAttempt.objects.exists())

    def test_long_password_is_not_silently_truncated(self):
        password = "long-password-" * 30
        self.user.set_password(password)
        self.user.save()
        self.assertEqual(self.login(password).status_code, 200)

    @override_settings(MEDIAHUB_SETUP_CODE="TEST-CODE")
    def test_setup_is_closed_when_a_user_exists(self):
        response = self.client.post("/api/auth/setup", {"code": "TEST-CODE"}, content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_mock_health_never_calls_jellyfin(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/health").status_code, 200)


class SetupTests(NoNetworkTestCase):
    @override_settings(MEDIAHUB_SETUP_CODE="TEST-CODE")
    def test_setup_lockout_survives_cache_eviction(self):
        for _ in range(5):
            response = self.client.post("/api/auth/setup", {"code": "WRONG"}, content_type="application/json")
            self.assertEqual(response.status_code, 400)
        cache.clear()
        response = self.client.post("/api/auth/setup", {"code": "TEST-CODE"}, content_type="application/json")
        self.assertEqual(response.status_code, 429)


@override_settings(MEDIAHUB_DATA_MODE="live")
class InputTests(NoNetworkTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(get_user_model().objects.create_user("viewer", password="password"))
        self.item_id = "a" * 32

    def post(self, route, body):
        return self.client.post(route, body, content_type="application/json")

    def test_every_json_endpoint_rejects_non_objects(self):
        routes = ["auth/login", "auth/setup", "auth/logout", "stop"]
        routes += [f"{name}/{self.item_id}" for name in ("play", "progress", "played", "favorite")]
        for route in routes:
            for body in ('[]', 'null', '"string"', '42', 'true'):
                with self.subTest(route=route, body=body):
                    self.assertEqual(self.post(f"/api/{route}", body).status_code, 400)

    def test_malformed_and_non_finite_json(self):
        for body in ('{', '{"positionSeconds":NaN}', '{"positionSeconds":Infinity}', '{"positionSeconds":1e309}', '[' * 1500):
            with self.subTest(body=body[:40]):
                self.assertEqual(self.post(f"/api/progress/{self.item_id}", body).status_code, 400)

    def test_auth_fields_require_bounded_strings(self):
        for body in ({"username": []}, {"password": 42}, {"username": "a" * 151}, {"password": "a" * 1025}):
            self.assertEqual(self.post("/api/auth/login", body).status_code, 400)

    def test_play_rejects_invalid_positions_and_audio(self):
        for value in (True, False, None, [], "", -1, MAX_SECONDS + 1):
            with self.subTest(value=value):
                self.assertEqual(self.post(f"/api/play/{self.item_id}", {"startSeconds": value}).status_code, 400)
        for value in (True, -1, "2", 2**31, 1.2):
            self.assertEqual(self.post(f"/api/play/{self.item_id}", {"audioIndex": value}).status_code, 400)

    def test_progress_rejects_bad_fields_without_upstream_calls(self):
        for value in (True, False, None, "1", -1, MAX_SECONDS + 1):
            self.assertEqual(self.post(f"/api/progress/{self.item_id}", {"positionSeconds": value, "durationSeconds": 100}).status_code, 400)

    @patch("catalog.views.jellyfin.save_progress")
    def test_progress_converts_ticks_and_marks_watched_at_threshold(self, save):
        for position, expected in ((89.5, False), (90, True)):
            response = self.post(f"/api/progress/{self.item_id}", {"positionSeconds": position, "durationSeconds": 100})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["played"], expected)
            save.assert_called_with(self.item_id, int(position * 10_000_000), expected)

    @patch("catalog.views.streaming.start", return_value={"type": "file"})
    def test_start_defaults_to_zero_and_accepts_audio(self, start):
        response = self.post(f"/api/play/{self.item_id}", {"audioIndex": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(start.call_args.args[1:], (self.item_id, 0, 2))

    def test_stop_requires_a_bounded_session_id(self):
        for value in (None, [], "", "../other", "a" * 129):
            self.assertEqual(self.post("/api/stop", {"playSessionId": value}).status_code, 400)


class ConcurrentThrottleTests(TransactionTestCase):
    def test_only_five_concurrent_attempts_are_reserved(self):
        def attempt(_):
            close_old_connections()
            try:
                return throttle.reserve("concurrent-user-ip")
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(attempt, range(20)))
        self.assertEqual(sum(outcomes), 5)
        self.assertEqual(LoginAttempt.objects.get().attempts, 5)


@override_settings(MEDIAHUB_PROXY_KEY="proxy-secret")
class ProxyClientIpTests(NoNetworkTestCase):
    """Behind the VPS, lockouts must count real visitors, not the proxy."""

    def setUp(self):
        super().setUp()
        get_user_model().objects.create_user("viewer", password="a-test-password")

    def fail_from(self, ip, key="proxy-secret"):
        headers = {"HTTP_X_MEDIAHUB_CLIENT_IP": ip}
        if key is not None:
            headers["HTTP_X_MEDIAHUB_PROXY_KEY"] = key
        return self.client.post(
            "/api/auth/login", {"username": "viewer", "password": "wrong"}, content_type="application/json", **headers
        )

    def test_lockout_is_per_visitor_behind_the_proxy(self):
        for _ in range(5):
            self.assertEqual(self.fail_from("203.0.113.7").status_code, 400)
        self.assertEqual(self.fail_from("203.0.113.7").status_code, 429)
        # Someone else on another address can still try.
        self.assertEqual(self.fail_from("198.51.100.9").status_code, 400)

    def test_client_ip_header_ignored_without_the_key(self):
        # A visitor can't dodge the lockout by inventing addresses.
        for i in range(5):
            self.assertEqual(self.fail_from(f"192.0.2.{i}", key="guess").status_code, 400)
        self.assertEqual(self.fail_from("192.0.2.99", key=None).status_code, 429)
