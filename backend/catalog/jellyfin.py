"""
Thin Jellyfin client. All calls are server-side: the admin API key never reaches
the browser, and images are re-served through /api/img/ (see views.image).

Uses the 10.9+ route layout (/Items?userId=..., /UserItems/...) and the
standard `Authorization: MediaBrowser ...` header.
"""

import requests
from django.conf import settings

ITEM_FIELDS = "Overview,Genres,DateCreated,ChildCount,PrimaryImageAspectRatio"
CLIENT = 'MediaBrowser Client="MediaHub", Device="MediaHub Web", DeviceId="{device}", Version="0.1.0"'
DEVICE_ID = "mediahub-web"

_session = requests.Session()


class JellyfinError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def auth_header(token=None, device=DEVICE_ID):
    header = CLIENT.format(device=device)
    return f'{header}, Token="{token}"' if token else header


def _request(method, path, token=None, timeout=None, device=DEVICE_ID, **kwargs):
    url = f"{settings.JELLYFIN_URL}{path}"
    headers = {"Authorization": auth_header(token or settings.JELLYFIN_API_KEY, device=device)}
    try:
        res = _session.request(method, url, headers=headers, timeout=timeout or settings.JELLYFIN_TIMEOUT, **kwargs)
        res.raise_for_status()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else None
        raise JellyfinError(f"Jellyfin request failed: {method} {path}: {exc}", status_code=status) from exc
    return res


def _get(path, **params):
    return _request("GET", path, params=params)


def _items(path, **params):
    data = _get(path, userId=settings.JELLYFIN_USER_ID, Fields=ITEM_FIELDS, **params).json()
    # /Items/Latest returns a bare list; everything else wraps it in Items.
    return data if isinstance(data, list) else data.get("Items", [])


def resume(limit=20):
    return _items("/UserItems/Resume", Limit=limit, MediaTypes="Video")


def recent(item_types, limit=20, **filters):
    return _items(
        "/Items",
        IncludeItemTypes=item_types,
        Recursive="true",
        CollapseBoxSetItems="false",
        SortBy="DateCreated",
        SortOrder="Descending",
        Limit=limit,
        **filters,
    )


def featured(limit=8):
    """Random movies/series that have backdrop art (for the rotating hero)."""
    return _items(
        "/Items",
        IncludeItemTypes="Movie,Series",
        Recursive="true",
        ImageTypes="Backdrop",
        SortBy="Random",
        Limit=limit,
    )


def item(item_id):
    """Full item (People, Genres, UserData, ...) as the library user sees it."""
    return _get(f"/Items/{item_id}", userId=settings.JELLYFIN_USER_ID).json()


def seasons(series_id):
    return _items(f"/Shows/{series_id}/Seasons")


def episodes(series_id):
    """Every episode of a series, in order, with SeasonId/SeasonName on each."""
    return _items(f"/Shows/{series_id}/Episodes")


def next_up(series_id=None, limit=1):
    """Next unwatched episode(s). With series_id: that show only (or None)."""
    params = {"seriesId": series_id} if series_id else {}
    items = _items("/Shows/NextUp", Limit=limit, EnableResumable="false", **params)
    if series_id:
        return items[0] if items else None
    return items


def query(limit=40, start=0, **params):
    """Paged /Items query. Returns (items, total)."""
    params.setdefault("Recursive", "true")
    data = _get(
        "/Items",
        userId=settings.JELLYFIN_USER_ID,
        Fields=ITEM_FIELDS,
        # Otherwise Jellyfin hides films that belong to a collection (Thor, Iron Man…)
        # in some sort orders but not others.
        CollapseBoxSetItems="false",
        StartIndex=start,
        Limit=limit,
        **params,
    ).json()
    return data.get("Items", []), data.get("TotalRecordCount", 0)


def similar(item_id, limit=12):
    return _items(f"/Items/{item_id}/Similar", Limit=limit)


def genres(item_types="Movie,Series"):
    data = _get("/Genres", userId=settings.JELLYFIN_USER_ID, IncludeItemTypes=item_types, Recursive="true").json()
    return [g["Name"] for g in data.get("Items", [])]


def search_hints(term, limit=24, types="Movie,Series,Episode,BoxSet,Person"):
    data = _get(
        "/Search/Hints",
        userId=settings.JELLYFIN_USER_ID,
        searchTerm=term,
        Limit=limit,
        IncludeItemTypes=types,
        IncludePeople="true" if "Person" in types else "false",
    ).json()
    return data.get("SearchHints", [])


def next_episode(series_id, episode_id):
    """The episode after episode_id in the show's order, or None."""
    items = _items(f"/Shows/{series_id}/Episodes", startItemId=episode_id, Limit=2)
    return items[1] if len(items) > 1 and items[0]["Id"] == episode_id else None


def media_segments(item_id):
    """Intro/Outro/Recap markers (needs a segment plugin on the server; else empty)."""
    try:
        return _get(f"/MediaSegments/{item_id}").json().get("Items", [])
    except JellyfinError:
        return []


def set_played(item_id, played):
    method = "POST" if played else "DELETE"
    return _request(method, f"/UserPlayedItems/{item_id}", params={"userId": settings.JELLYFIN_USER_ID}).json()


def set_favorite(item_id, favorite):
    method = "POST" if favorite else "DELETE"
    return _request(method, f"/UserFavoriteItems/{item_id}", params={"userId": settings.JELLYFIN_USER_ID}).json()


def image(item_id, image_type, max_width):
    """Return (bytes, content_type) for an item image."""
    res = _get(f"/Items/{item_id}/Images/{image_type}", maxWidth=max_width, quality=90)
    return res.content, res.headers.get("Content-Type", "image/jpeg")


def subtitle_vtt(item_id, source_id, index):
    """A subtitle stream converted to WebVTT by Jellyfin (admin key, server-side).
    First request for an embedded track makes Jellyfin read through the whole
    file to extract it, which can take a minute on big MKVs; then it's cached."""
    res = _request("GET", f"/Videos/{item_id}/{source_id}/Subtitles/{index}/0/Stream.vtt", timeout=120)
    res.encoding = "utf-8"
    return res.text


def public_info():
    """Unauthenticated server info, used by the health check."""
    try:
        res = _session.get(f"{settings.JELLYFIN_URL}/System/Info/Public", timeout=3)
        res.raise_for_status()
        return res.json()
    except requests.RequestException:
        return None


# --- Playback ----------------------------------------------------------------

# Tells Jellyfin what a browser can play: MP4/H.264 directly, everything else
# (MKV, HEVC, DTS, 5.1, ...) transcoded to HLS H.264/AAC stereo.
BROWSER_PROFILE = {
    "MaxStreamingBitrate": 40_000_000,
    "DirectPlayProfiles": [
        {"Container": "mp4,m4v", "Type": "Video", "VideoCodec": "h264", "AudioCodec": "aac,mp3"},
    ],
    "TranscodingProfiles": [
        {
            "Container": "ts",
            "Type": "Video",
            "VideoCodec": "h264",
            "AudioCodec": "aac",
            "Context": "Streaming",
            "Protocol": "hls",
            "MaxAudioChannels": "2",
            "MinSegments": 1,
            "BreakOnNonKeyFrames": True,
        }
    ],
    "SubtitleProfiles": [{"Format": "vtt", "Method": "External"}],
}


def authenticate(username, password, device=DEVICE_ID):
    """Log a (non-admin) user in. Returns (access_token, user_id)."""
    url = f"{settings.JELLYFIN_URL}/Users/AuthenticateByName"
    try:
        res = _session.post(
            url,
            json={"Username": username, "Pw": password},
            headers={"Authorization": auth_header(device=device)},
            timeout=settings.JELLYFIN_TIMEOUT,
        )
        res.raise_for_status()
    except requests.RequestException as exc:
        raise JellyfinError(f"Stream user login failed: {exc}") from exc
    data = res.json()
    return data["AccessToken"], data["User"]["Id"], data["User"].get("Policy", {})


def logout(token, device=DEVICE_ID):
    try:
        _request("POST", "/Sessions/Logout", token=token, device=device)
    except JellyfinError as exc:
        if exc.status_code != 401:
            raise  # Outages must be retried; only 401 proves the token is invalid.


def playback_info(item_id, token, user_id, audio_index=None, device=DEVICE_ID):
    body = {
        "UserId": user_id,
        "DeviceProfile": BROWSER_PROFILE,
        "MaxStreamingBitrate": BROWSER_PROFILE["MaxStreamingBitrate"],
        "AutoOpenLiveStream": False,
    }
    if audio_index is not None:
        body["AudioStreamIndex"] = audio_index
    return _request("POST", f"/Items/{item_id}/PlaybackInfo", token=token, device=device, params={"userId": user_id}, json=body).json()


def stop_encoding(token, play_session_id, device=DEVICE_ID):
    try:
        _request(
            "DELETE",
            "/Videos/ActiveEncodings",
            token=token,
            device=device,
            params={"deviceId": device, "playSessionId": play_session_id},
        )
    except JellyfinError:
        pass  # nothing running


def save_progress(item_id, position_ticks, played):
    """Record watch position on the library user (admin key, server-side)."""
    body = {"PlaybackPositionTicks": 0 if played else position_ticks, "Played": played}
    _request("POST", f"/UserItems/{item_id}/UserData", params={"userId": settings.JELLYFIN_USER_ID}, json=body)
