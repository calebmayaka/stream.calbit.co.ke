"""
Playback broker.

The browser streams directly from Jellyfin with a limited-user credential.
The database and the service cleanup worker manage its lifetime (see tokens.py).
"""

from urllib.parse import parse_qs, urlsplit

from django.conf import settings

from . import jellyfin
from .models import PlaybackSession
from .tokens import StreamConfigError, stream_session


def media_base(request):
    """Use the public Jellyfin hostname for HTTPS/tunnel viewers."""
    remote = "HTTP_CF_CONNECTING_IP" in request.META or request.is_secure()
    if not remote:
        return settings.JELLYFIN_URL
    if not settings.JELLYFIN_PUBLIC_URL:
        raise StreamConfigError("Remote playback needs JELLYFIN_PUBLIC_URL (e.g. https://stream.calbit.co.ke).")
    return settings.JELLYFIN_PUBLIC_URL


TICKS = 10_000_000
SEGMENT_KINDS = {"Intro": "intro", "Recap": "recap", "Outro": "credits", "Preview": "preview"}


LANGUAGES = {
    "eng": "English", "jpn": "Japanese", "ita": "Italian", "fre": "French", "fra": "French",
    "spa": "Spanish", "ger": "German", "deu": "German", "por": "Portuguese", "swa": "Swahili",
    "chi": "Chinese", "zho": "Chinese", "kor": "Korean", "hin": "Hindi", "ara": "Arabic",
    "rus": "Russian", "dut": "Dutch", "nld": "Dutch", "zxx": "Signs", "und": "Unknown",
}


def _track_label(s, used):
    """Short, human label ("English", "English (Signs)", "Japanese 5.1") instead
    of release-group soup like "[EveTaku] - [Coalgirls] - English - ASS"."""
    lang = s.get("Language") or "und"
    name = LANGUAGES.get(lang, lang.upper())
    title = (s.get("Title") or "").lower()
    extras = []
    if s.get("Type") == "Audio" and s.get("Channels"):
        extras.append({1: "Mono", 2: "Stereo", 6: "5.1", 8: "7.1"}.get(s["Channels"], f"{s['Channels']}ch"))
    if s.get("Type") == "Subtitle":
        if "sign" in title or "song" in title or lang == "zxx":
            extras.append("Signs")
        elif s.get("IsForced") or "forced" in title:
            extras.append("Forced")
        elif s.get("IsHearingImpaired") or "sdh" in title:
            extras.append("SDH")
    label = f"{name} ({', '.join(extras)})" if extras and name != "Signs" else name
    used[label] = used.get(label, 0) + 1
    return label if used[label] == 1 else f"{label} {used[label]}"


def _audio_tracks(streams):
    used = {}
    return [
        {"index": s["Index"], "label": _track_label(s, used), "lang": s.get("Language")}
        for s in streams
        if s.get("Type") == "Audio"
    ]


def _subtitles(streams, item_id, source_id, audio_lang):
    """Text subtitle tracks, served as cleaned WebVTT through /api/subs/ (same
    origin, no token in the URL). Picture subs (PGS/VobSub) would need burning
    in, so they're skipped."""
    used, out = {}, []
    for s in streams:
        if s.get("Type") != "Subtitle" or not s.get("IsTextSubtitleStream"):
            continue
        label = _track_label(s, used)
        out.append({
            "index": s["Index"],
            "label": label,
            "lang": s.get("Language") or "und",
            "url": f"/api/subs/{item_id}/{source_id}/{s['Index']}",
            "full": not any(k in label for k in ("Signs", "Forced")),  # whole dialogue, not just signs
            "default": False,
        })
    full_english = next((t for t in out if t["lang"] == "eng" and t["full"]), None)
    if audio_lang and audio_lang != "eng" and full_english:
        full_english["default"] = True  # foreign audio: proper English subs on
    else:
        # Same-language audio: only signs/forced tracks, if any, like other players.
        signs = next((t for t in out if not t["full"] and t["lang"] in (audio_lang, "zxx", "und")), None)
        if signs:
            signs["default"] = True
    for t in out:
        t.pop("full")
    return out


def _next_episode(item):
    if item.get("Type") != "Episode" or not item.get("SeriesId"):
        return None
    nxt = jellyfin.next_episode(item["SeriesId"], item["Id"])
    if not nxt:
        return None
    season, number = nxt.get("ParentIndexNumber"), nxt.get("IndexNumber")
    code = f"S{season}E{number}" if season is not None and number is not None else None
    return {
        "id": nxt["Id"],
        "title": nxt.get("Name"),
        "label": " · ".join(p for p in (code, nxt.get("Name")) if p),
        "thumb": f"/api/img/{nxt['Id']}/Primary?w=400" if nxt.get("ImageTags", {}).get("Primary") else None,
    }


def _segments(item_id):
    out = []
    for seg in jellyfin.media_segments(item_id):
        kind = SEGMENT_KINDS.get(seg.get("Type"))
        if kind:
            out.append({"kind": kind, "start": seg.get("StartTicks", 0) / TICKS, "end": seg.get("EndTicks", 0) / TICKS})
    return out


# Player "Quality" menu -> bitrate ceiling (bits/s). None = automatic.
QUALITIES = {"auto": None, "original": jellyfin.LAN_MAX_BITRATE, "720p": 3_000_000, "480p": 1_500_000}
# Transcode reasons that mean the *video* is re-encoded (CPU-heavy); anything
# else (container, audio, subtitles) is just repackaging.
VIDEO_REASONS = ("Video", "Bitrate", "RefFrames", "Anamorphic", "Interlaced", "Level", "Profile", "Framerate")


def max_bitrate(request, quality):
    """Ceiling for this stream: the viewer's choice, else LAN speed at home and
    MEDIAHUB_REMOTE_MAX_BITRATE (shared home upload) for everyone else."""
    chosen = QUALITIES.get(quality)
    if chosen:
        return chosen
    remote = media_base(request) != settings.JELLYFIN_URL
    return settings.MEDIAHUB_REMOTE_MAX_BITRATE if remote else jellyfin.LAN_MAX_BITRATE


def _play_method(source):
    """'direct' (file as-is), 'remux' (repackaged, video copied) or 'transcode'."""
    if source.get("SupportsDirectPlay"):
        return "direct", []
    query = parse_qs(urlsplit(source.get("TranscodingUrl") or "").query)
    reasons = [r for r in (query.get("TranscodeReasons", [""])[0]).split(",") if r]
    video = any(any(k in r for k in VIDEO_REASONS) for r in reasons)
    return ("transcode" if video else "remux"), reasons


def _source_video(streams):
    v = next((s for s in streams if s.get("Type") == "Video"), {})
    return {"codec": (v.get("Codec") or "").lower() or None, "bitDepth": v.get("BitDepth"), "height": v.get("Height")}


def start(request, item_id, start_seconds=0, audio_index=None, caps=None, quality="auto"):
    session = stream_session()
    base = media_base(request)
    item = jellyfin.item(item_id)
    ceiling = max_bitrate(request, quality)
    profile = jellyfin.browser_profile(caps, ceiling)
    info = jellyfin.playback_info(item_id, session.token, session.user_id, audio_index, device=session.device_id, profile=profile)
    sources = info.get("MediaSources") or []
    if not sources:
        raise jellyfin.JellyfinError("No playable media source")
    source = sources[0]
    play_session = info.get("PlaySessionId")
    if play_session:
        PlaybackSession.objects.update_or_create(id=play_session, defaults={"token": session})
    streams = source.get("MediaStreams") or []
    chosen_audio = audio_index if audio_index is not None else source.get("DefaultAudioStreamIndex")
    audio = _audio_tracks(streams)
    audio_lang = next((a["lang"] for a in audio if a["index"] == chosen_audio), None)

    if source.get("SupportsDirectPlay"):
        url = (
            f"{base}/Videos/{item_id}/stream?static=true&mediaSourceId={source['Id']}"
            f"&playSessionId={play_session}&deviceId={session.device_id}&api_key={session.token}"
        )
        kind = "file"
    elif source.get("TranscodingUrl"):
        # Jellyfin's HLS playlist spans the whole runtime; the player seeks and
        # Jellyfin starts transcoding from that segment.
        url = base + source["TranscodingUrl"]
        kind = "hls"
    else:
        raise jellyfin.JellyfinError("Jellyfin offered no browser-playable stream")

    method, reasons = _play_method(source)
    return {
        "method": method,
        "reasons": reasons,
        "sourceVideo": _source_video(streams),
        "quality": quality if quality in QUALITIES else "auto",
        "maxBitrate": ceiling,
        "url": url,
        "type": kind,
        "startSeconds": start_seconds,
        "duration": (source.get("RunTimeTicks") or 0) / TICKS,
        "playSessionId": play_session,
        "audioTracks": audio,
        "audioIndex": chosen_audio,
        "subtitles": _subtitles(streams, item_id, source["Id"], audio_lang),
        "next": _next_episode(item),
        "segments": _segments(item_id),
    }


def stop(play_session_id):
    session = PlaybackSession.objects.select_related("token").filter(pk=play_session_id).first()
    if session:
        jellyfin.stop_encoding(session.token.token, play_session_id, device=session.token.device_id)
        session.delete()
