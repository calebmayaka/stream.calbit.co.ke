from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from catalog import jellyfin, streaming
from catalog.models import PlaybackStat


class ProfileTests(TestCase):
    def transcoding(self, caps):
        return jellyfin.browser_profile(caps, 8_000_000)["TranscodingProfiles"][0]

    def test_h264_only_browser_keeps_ts_and_stereo(self):
        t = self.transcoding({})
        self.assertEqual((t["VideoCodec"], t["Container"], t["MaxAudioChannels"]), ("h264", "ts", "2"))

    def test_hevc_browser_copies_hevc_in_fmp4_but_still_encodes_h264(self):
        t = self.transcoding({"hevc": True, "hevc10": True})
        self.assertEqual(t["VideoCodec"].split(",")[0], "h264")  # transcode target
        self.assertIn("hevc", t["VideoCodec"])  # may be copied
        self.assertEqual(t["Container"], "mp4")

    def test_8bit_only_hevc_restricts_bit_depth(self):
        profile = jellyfin.browser_profile({"hevc": True}, 8_000_000)
        cond = profile["CodecProfiles"][0]["Conditions"][0]
        self.assertEqual((cond["Property"], cond["Value"]), ("VideoBitDepth", "8"))
        self.assertEqual(jellyfin.browser_profile({"hevc": True, "hevc10": True})["CodecProfiles"], [])

    def test_surround_audio_copied_when_supported(self):
        t = self.transcoding({"eac3": True})
        self.assertIn("eac3", t["AudioCodec"])
        self.assertEqual(t["MaxAudioChannels"], "6")

    def test_bitrate_ceiling_applied(self):
        self.assertEqual(jellyfin.browser_profile({}, 3_000_000)["MaxStreamingBitrate"], 3_000_000)


class PlayMethodTests(TestCase):
    def method(self, source):
        return streaming._play_method(source)[0]

    def test_classification(self):
        self.assertEqual(self.method({"SupportsDirectPlay": True}), "direct")
        self.assertEqual(self.method({"TranscodingUrl": "/videos/x/master.m3u8?TranscodeReasons=ContainerNotSupported,AudioCodecNotSupported"}), "remux")
        self.assertEqual(self.method({"TranscodingUrl": "/videos/x/master.m3u8?TranscodeReasons=VideoCodecNotSupported"}), "transcode")
        self.assertEqual(self.method({"TranscodingUrl": "/videos/x/master.m3u8?TranscodeReasons=ContainerBitrateExceedsLimit"}), "transcode")

    @override_settings(MEDIAHUB_REMOTE_MAX_BITRATE=8_000_000, JELLYFIN_PUBLIC_URL="https://jellyfin.example")
    def test_auto_quality_caps_remote_but_not_lan(self):
        rf = RequestFactory()
        self.assertEqual(streaming.max_bitrate(rf.get("/", secure=True), "auto"), 8_000_000)
        self.assertEqual(streaming.max_bitrate(rf.get("/"), "auto"), jellyfin.LAN_MAX_BITRATE)
        self.assertEqual(streaming.max_bitrate(rf.get("/", secure=True), "original"), jellyfin.LAN_MAX_BITRATE)
        self.assertEqual(streaming.max_bitrate(rf.get("/"), "480p"), 1_500_000)


@override_settings(MEDIAHUB_DATA_MODE="live")
class PlayEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("viewer", password="a-test-password")
        self.client.force_login(self.user)
        self.url = "/api/play/" + "a" * 32

    def post(self, body):
        return self.client.post(self.url, body, content_type="application/json")

    def test_rejects_unknown_caps_and_quality(self):
        self.assertEqual(self.post({"caps": {"hevc": "yes"}}).status_code, 400)
        self.assertEqual(self.post({"caps": {"vp9": True}}).status_code, 400)
        self.assertEqual(self.post({"quality": "4k"}).status_code, 400)

    @patch("catalog.views.streaming.start", return_value={"ok": True})
    def test_passes_caps_and_quality_through(self, start):
        self.assertEqual(self.post({"caps": {"hevc": True, "hevc10": False}, "quality": "720p"}).status_code, 200)
        self.assertEqual(start.call_args.kwargs, {"caps": {"hevc": True, "hevc10": False}, "quality": "720p"})


@override_settings(MEDIAHUB_DATA_MODE="live")
class PlaybackStatTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("viewer", password="a-test-password")
        self.client.force_login(self.user)
        self.url = "/api/playstats/" + "a" * 32

    def post(self, body):
        return self.client.post(self.url, body, content_type="application/json")

    def test_records_a_watch(self):
        body = {"method": "remux", "codec": "hevc", "quality": "auto", "startupMs": 2100, "stalls": 1,
                "stallMs": 900, "watchedSeconds": 600, "maxBitrate": 8_000_000, "client": "Chrome/Windows"}
        self.assertEqual(self.post(body).json(), {"ok": True, "recorded": True})
        stat = PlaybackStat.objects.get()
        self.assertEqual((stat.method, stat.startup_ms, stat.stalls, stat.user_id), ("remux", 2100, 1, self.user.pk))

    def test_ignores_open_and_close(self):
        self.assertEqual(self.post({"method": "direct", "watchedSeconds": 1}).json()["recorded"], False)
        self.assertFalse(PlaybackStat.objects.exists())

    def test_validates(self):
        self.assertEqual(self.post({"method": "teleport", "watchedSeconds": 60}).status_code, 400)
        self.assertEqual(self.post({"method": "direct", "startupMs": -1, "watchedSeconds": 60}).status_code, 400)
        self.assertEqual(self.post({"method": "direct", "stalls": 1.5, "watchedSeconds": 60}).status_code, 400)
