import json
import logging
import math
import re
from functools import wraps
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout, password_validation
from django.contrib.auth.hashers import check_password
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import Http404, HttpResponse, JsonResponse
from django.http.request import validate_host
from django.views.decorators.http import require_GET, require_POST

from . import browse, jellyfin, streaming, throttle
from .home import live_home, mock_home
from .models import PlaybackStat
from .title import build_person, build_title

log = logging.getLogger(__name__)

IMAGE_TYPES = {"Primary", "Backdrop", "Thumb"}
IMAGE_WIDTHS = (200, 400, 800, 1280, 1920)  # snap requests so the cache stays small
PLAYED_AT = 0.9  # fraction watched that marks an item as played
MAX_SECONDS = (2**63 - 1) // 10_000_000  # Jellyfin uses signed 64-bit ticks


def _json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite number")
    return number


def _reject_constant(value):
    raise ValueError("Invalid JSON constant")


def _valid_seconds(value):
    return type(value) in (int, float) and 0 <= value <= MAX_SECONDS


def _invalid_strings(body, fields):
    for field, maximum in fields.items():
        value = body.get(field, "")
        if not isinstance(value, str) or len(value) > maximum:
            return _error(f"{field} must be a string of at most {maximum} characters", 400)
    return None


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


def live_only(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if settings.MEDIAHUB_DATA_MODE != "live":
            return _error("Not available in mock mode", 404)
        try:
            return view(request, *args, **kwargs)
        except streaming.StreamConfigError as exc:
            log.warning("Playback not configured: %s", exc)
            return _error(str(exc), 503)
        except jellyfin.JellyfinError:
            log.exception("Jellyfin call failed in %s", view.__name__)
            return _error("Media server unavailable", 502)

    return wrapper


def json_post(view):
    """POST with a JSON body from our own origin (blocks cross-site form posts)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        # Compare against ALLOWED_HOSTS, not the Host header: proxies in front
        # (Vite in dev, IIS/ARR in prod) may rewrite Host to the backend address.
        origin = request.headers.get("Origin")
        if origin:
            try:
                valid_origin = validate_host(urlsplit(origin).hostname or "", settings.ALLOWED_HOSTS)
            except ValueError:
                valid_origin = False
            if not valid_origin:
                return _error("Cross-origin request refused", 403)
        if request.content_type != "application/json":
            return _error("Expected application/json", 415)
        try:
            body = json.loads(request.body or b"{}", parse_float=_json_float, parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            return _error("Invalid JSON", 400)
        if not isinstance(body, dict):
            return _error("Expected a JSON object", 400)
        return view(request, body, *args, **kwargs)

    return require_POST(wrapper)


# --- Login -------------------------------------------------------------------


def _user_json(user):
    return {"username": user.get_username(), "name": user.get_full_name() or user.get_username()}


def _client_ip(request):
    """The visitor's address, for the login lockout and logs.

    Behind the VPS, Caddy sends it as X-MediaHub-Client-IP together with the
    shared MEDIAHUB_PROXY_KEY; without a matching key that header is ignored, so
    nobody can pick their own address. Behind the Cloudflare tunnel it arrives
    as CF-Connecting-IP. Otherwise it's the connection address."""
    key = settings.MEDIAHUB_PROXY_KEY
    if key and constant_time_compare(request.headers.get("X-MediaHub-Proxy-Key", ""), key):
        forwarded = request.headers.get("X-MediaHub-Client-IP", "").strip()
        if forwarded:
            return forwarded[:64]
    return request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("REMOTE_ADDR", "")


def _setup_open():
    """First-run: no accounts yet and a setup code is configured."""
    return bool(settings.MEDIAHUB_SETUP_CODE) and not get_user_model().objects.exists()


@require_GET
@ensure_csrf_cookie  # the SPA reads this cookie and echoes it back as X-CSRFToken
def auth_me(request):
    if request.user.is_authenticated:
        return JsonResponse({"authenticated": True, "user": _user_json(request.user)})
    return JsonResponse({"authenticated": False, "setup": _setup_open()})


@json_post
def auth_setup(request, body):
    """Create the very first account from the browser (e.g. from a phone).

    Only works while there are no accounts at all, and only with the setup code
    from the server's .env — so nobody else can claim the site. After that,
    accounts are added with `manage.py adduser`."""
    invalid = _invalid_strings(body, {"code": 128, "username": 150, "name": 150, "password": 1024})
    if invalid is not None:
        return invalid
    if not _setup_open():
        return _error("Setup is closed. Sign in instead.", 403)
    key = f"setup-fail:{_client_ip(request)}"
    if not throttle.reserve(key):
        return _error("Too many attempts. Try again in 15 minutes.", 429)

    code = body.get("code", "").strip()
    if not constant_time_compare(code, settings.MEDIAHUB_SETUP_CODE):
        log.warning("Bad setup code from %s", _client_ip(request))
        return _error("That setup code isn't right.", 400)

    throttle.clear(key)
    username = body.get("username", "").strip()
    name = body.get("name", "").strip()
    password = body.get("password", "")
    User = get_user_model()
    user = User(username=username, first_name=name)
    try:
        user.username = User.normalize_username(username)
        user.full_clean(exclude=["password"])
        password_validation.validate_password(password, user)
    except ValidationError as exc:
        return _error(" ".join(exc.messages), 400)

    user.set_password(password)
    with transaction.atomic():
        if User.objects.select_for_update().exists():  # two tabs racing
            return _error("Setup is closed. Sign in instead.", 403)
        user.save()
    log.info("First account %r created via setup from %s", username, _client_ip(request))
    login(request, user)
    return JsonResponse({"authenticated": True, "user": _user_json(user)})


def end_sessions(user):
    """Sign a user out on every device (password reset, removeuser). Deletes
    through the session engine so cached copies (cached_db) go too, not just
    the database rows. Returns how many sessions were ended."""
    from importlib import import_module

    from django.contrib.sessions.models import Session

    store = import_module(settings.SESSION_ENGINE).SessionStore
    ended = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            store(session_key=session.session_key).delete()
            ended += 1
    return ended


@json_post
def auth_reset(request, body):
    """Set a new password with the server's reset pass key ("Forgot password?").

    The key is stored only as a hash (MEDIAHUB_RESET_KEY_HASH, see
    `manage.py setresetkey`). Attempts are limited per address and site-wide, and
    the reply never says whether the account exists. A reset signs that account
    out everywhere, then signs it in here."""
    invalid = _invalid_strings(body, {"username": 150, "key": 256, "password": 1024})
    if invalid is not None:
        return invalid
    if not settings.MEDIAHUB_RESET_KEY_HASH:
        return _error("Password reset isn't enabled on this server.", 404)

    ip_key, site_key = f"reset-fail:{_client_ip(request)}", "reset-fail:site"
    if not throttle.reserve(ip_key) or not throttle.reserve(site_key):
        return _error("Too many attempts. Try again in 15 minutes.", 429)

    username = body.get("username", "").strip()
    supplied = body.get("key", "")
    password = body.get("password", "")
    User = get_user_model()
    user = User.objects.filter(username=username, is_active=True).first()
    key_ok = check_password(supplied, settings.MEDIAHUB_RESET_KEY_HASH)
    if not key_ok or user is None:
        log.warning("Failed password reset for %r from %s", username, _client_ip(request))
        return _error("Wrong account name or pass key.", 400)

    try:
        password_validation.validate_password(password, user)
    except ValidationError as exc:
        return _error(" ".join(exc.messages), 400)

    throttle.clear(ip_key)
    throttle.clear(site_key)
    user.set_password(password)
    user.save(update_fields=["password"])
    end_sessions(user)
    log.warning("Password reset for %r from %s", user.username, _client_ip(request))
    login(request, user)
    return JsonResponse({"authenticated": True, "user": _user_json(user)})


@json_post
def auth_login(request, body):
    invalid = _invalid_strings(body, {"username": 150, "password": 1024})
    if invalid is not None:
        return invalid
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        return _error("Enter your username and password.", 400)

    key = f"login-fail:{_client_ip(request)}:{username.lower()}"
    if not throttle.reserve(key):
        return _error("Too many attempts. Try again in 15 minutes.", 429)

    user = authenticate(request, username=username, password=password)
    if user is None:
        log.warning("Failed login for %r from %s", username, _client_ip(request))
        return _error("Wrong username or password.", 400)

    throttle.clear(key)
    login(request, user)  # also rotates the session key and CSRF token
    return JsonResponse({"authenticated": True, "user": _user_json(user)})


@json_post
def auth_logout(request, body):
    logout(request)
    return JsonResponse({"authenticated": False})


@require_GET
def health(request):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": True})  # uptime checks only; details need a session
    info = jellyfin.public_info() if settings.MEDIAHUB_DATA_MODE == "live" else None
    return JsonResponse({
        "ok": True,
        "mode": settings.MEDIAHUB_DATA_MODE,
        "jellyfin": {"reachable": info is not None, "version": info and info.get("Version")},
        "playback": bool(settings.JELLYFIN_STREAM_USER and settings.JELLYFIN_STREAM_PASSWORD),
    })


@require_GET
def home(request):
    if settings.MEDIAHUB_DATA_MODE == "mock":
        return JsonResponse(mock_home())
    try:
        return JsonResponse(live_home())
    except jellyfin.JellyfinError:
        log.exception("Building /api/home from Jellyfin failed")
        return _error("Media server unavailable", 502)


@require_GET
@live_only
def title(request, item_id):
    return JsonResponse(build_title(item_id))


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@require_GET
@live_only
def browse_view(request):
    q = request.GET
    try:
        data = browse.browse(
            q.get("type", "movies"),
            sort=q.get("sort", "added"),
            genre=q.get("genre", "")[:80],
            start=_int(q.get("start"), 0),
            limit=_int(q.get("limit"), 48),
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    return JsonResponse(data)


@require_GET
@live_only
def genres_view(request):
    try:
        return JsonResponse({"genres": browse.genres(request.GET.get("type", "movies"))})
    except ValueError as exc:
        return _error(str(exc), 400)


@require_GET
@live_only
def search_view(request):
    term = request.GET.get("q", "").strip()[:100]
    if len(term) < 2:
        return JsonResponse({"results": [], "people": []})
    return JsonResponse(browse.search(term))


@require_GET
@live_only
def person(request, item_id):
    return JsonResponse(build_person(item_id))


@json_post
@live_only
def played(request, body, item_id):
    value = body.get("played")
    if not isinstance(value, bool):
        return _error("played must be true or false", 400)
    data = jellyfin.set_played(item_id, value)
    return JsonResponse({"played": bool(data.get("Played"))})


@json_post
@live_only
def favorite(request, body, item_id):
    value = body.get("favorite")
    if not isinstance(value, bool):
        return _error("favorite must be true or false", 400)
    data = jellyfin.set_favorite(item_id, value)
    return JsonResponse({"favorite": bool(data.get("IsFavorite"))})


@json_post
@live_only
def play(request, body, item_id):
    start = body.get("startSeconds", 0)
    if not _valid_seconds(start):
        return _error(f"startSeconds must be a number between 0 and {MAX_SECONDS}", 400)
    audio = body.get("audioIndex")
    if audio is not None and (type(audio) is not int or not 0 <= audio <= 2**31 - 1):
        return _error("audioIndex must be a non-negative integer or null", 400)
    caps = body.get("caps") or {}
    if not isinstance(caps, dict) or not all(k in CAPS and type(v) is bool for k, v in caps.items()):
        return _error(f"caps must map {', '.join(CAPS)} to true/false", 400)
    quality = body.get("quality", "auto")
    if quality not in streaming.QUALITIES:
        return _error(f"quality must be one of {', '.join(streaming.QUALITIES)}", 400)
    return JsonResponse(streaming.start(request, item_id, start, audio, caps=caps, quality=quality))


CAPS = ("hevc", "hevc10", "av1", "av1_10", "ac3", "eac3")
PLAY_METHODS = ("direct", "remux", "transcode")


@json_post
@live_only
def playback_stats(request, body, item_id):
    """One record per watch from the player: how long until the picture
    appeared, how often and how long it stalled, and how it was delivered.
    Feeds `manage.py playbackstats`."""
    ints = {"startupMs": 600_000, "stalls": 10_000, "stallMs": 86_400_000, "watchedSeconds": 86_400, "maxBitrate": 10**9}
    for field, maximum in ints.items():
        value = body.get(field, 0)
        if type(value) is not int or not 0 <= value <= maximum:
            return _error(f"{field} must be an integer between 0 and {maximum}", 400)
    invalid = _invalid_strings(body, {"method": 16, "quality": 16, "codec": 16, "client": 64})
    if invalid is not None:
        return invalid
    if body.get("method") not in PLAY_METHODS or body.get("quality", "auto") not in streaming.QUALITIES:
        return _error("unknown method or quality", 400)
    if body.get("watchedSeconds", 0) < 2:
        return JsonResponse({"ok": True, "recorded": False})  # opened and closed: not a watch
    PlaybackStat.objects.create(
        user=request.user,
        item_id=item_id,
        method=body["method"],
        codec=body.get("codec", "")[:16],
        quality=body.get("quality", "auto"),
        max_bitrate=body.get("maxBitrate", 0),
        remote=streaming.media_base(request) != settings.JELLYFIN_URL,
        startup_ms=body.get("startupMs", 0),
        stalls=body.get("stalls", 0),
        stall_ms=body.get("stallMs", 0),
        watched_seconds=body.get("watchedSeconds", 0),
        client=body.get("client", "")[:64],
    )
    return JsonResponse({"ok": True, "recorded": True})


@json_post
@live_only
def progress(request, body, item_id):
    position, duration = body.get("positionSeconds"), body.get("durationSeconds")
    if not all(_valid_seconds(v) for v in (position, duration)):
        return _error(f"positionSeconds and durationSeconds must be numbers between 0 and {MAX_SECONDS}", 400)
    played = duration > 0 and position / duration >= PLAYED_AT
    jellyfin.save_progress(item_id, int(position * 10_000_000), played)
    return JsonResponse({"ok": True, "played": played})


@json_post
@live_only
def stop(request, body):
    session_id = body.get("playSessionId")
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9]{1,128}", session_id):
        return _error("playSessionId must be a non-empty alphanumeric string of at most 128 characters", 400)
    streaming.stop(session_id)
    return JsonResponse({"ok": True})


ASS_TAGS = re.compile(r"\{\\[^}]*\}")
CUE_TIMING = re.compile(r"^(\d[\d:.]+ --> \d[\d:.]+)")
ASS_DRAWING = re.compile(r"^[mnlbspc\d\s.\-]+$")  # vector shapes like "m 60 0 b 45 21 ..."


def clean_vtt(text):
    """Make Jellyfin's ASS->VTT output readable in a browser.

    Fan-sub ASS files carry styling codes ({\\fad..}, \\N), vector drawings,
    one cue per karaoke syllable and duplicate layers (shadow/outline copies).
    Browsers print all of that literally. Per timestamp, keep only distinct
    real lines and drop fragments that are part of a longer line."""
    groups, order, timing = {}, [], None
    for line in text.lstrip("﻿").splitlines():
        match = CUE_TIMING.match(line)
        if match:
            timing = match.group(1)  # cue settings (region/line/position) dropped
            if timing not in groups:
                groups[timing] = []
                order.append(timing)
            continue
        if timing is None or not line.strip():
            if not line.strip():
                timing = None
            continue
        clean = ASS_TAGS.sub("", line).replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ").strip()
        if clean and not ASS_DRAWING.match(clean) and clean not in groups[timing]:
            groups[timing].append(clean)

    cues = []  # (start, end, timing, text)
    for timing in order:
        start, end = (_seconds(t) for t in timing.split(" --> "))
        cues += [(start, end, timing, t) for t in groups[timing]]

    # A karaoke syllable has its own (shorter) timing, so also drop any cue whose
    # text is part of a longer line that is on screen for the whole of it.
    by_start = sorted(cues)
    keep = []
    for start, end, timing, text in cues:
        covered = False
        for o_start, o_end, _, other in by_start:
            if o_start > start:
                break
            if o_end >= end and other != text and text in other:
                covered = True
                break
        if not covered:
            keep.append((timing, text))

    out = ["WEBVTT", ""]
    for timing in order:
        lines = _join_drop_caps([t for tm, t in keep if tm == timing])
        if lines:
            out += [timing, *lines, ""]
    return "\n".join(out)


def _join_drop_caps(lines):
    """Song styles split a decorative first letter off its line ("S" + "ie sind…")."""
    merged = []
    for line in lines:
        if merged and len(merged[-1]) == 1 and merged[-1].isupper() and line[:1].islower():
            merged[-1] += line
        else:
            merged.append(line)
    return merged


def _seconds(stamp):
    parts = [float(p) for p in stamp.strip().split(":")]
    return sum(p * 60 ** i for i, p in enumerate(reversed(parts)))


@require_GET
@live_only
def subtitles(request, item_id, source_id, index):
    key = f"vtt:{item_id}:{source_id}:{index}"
    body = cache.get(key)
    if body is None:
        body = clean_vtt(jellyfin.subtitle_vtt(item_id, source_id, index))
        cache.set(key, body, timeout=60 * 60 * 24 * 7)
    res = HttpResponse(body, content_type="text/vtt; charset=utf-8")
    res["Cache-Control"] = "public, max-age=86400"
    return res


@require_GET
def image(request, item_id, image_type):
    if settings.MEDIAHUB_DATA_MODE == "mock" or image_type not in IMAGE_TYPES:
        raise Http404
    try:
        wanted = int(request.GET.get("w", 400))
    except ValueError:
        wanted = 400
    width = next((w for w in IMAGE_WIDTHS if w >= wanted), IMAGE_WIDTHS[-1])

    key = f"img:{item_id}:{image_type}:{width}"
    cached = cache.get(key)
    if cached is None:
        try:
            cached = jellyfin.image(item_id, image_type, width)
        except jellyfin.JellyfinError:
            raise Http404
        cache.set(key, cached)

    body, content_type = cached
    res = HttpResponse(body, content_type=content_type)
    res["Cache-Control"] = "public, max-age=86400"
    return res
