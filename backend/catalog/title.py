"""
Builds the /api/title/<id> payload for the detail page (movies, series with
seasons + episodes, single episodes, collections) and /api/person/<id>.
"""

import re
from collections import OrderedDict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from django.conf import settings

from . import jellyfin
from .home import KINDS, _episode_code, _runtime, _unique, image_url, map_item

TICKS_PER_SECOND = 10_000_000
MAX_CAST = 15
MAX_SIMILAR = 12
YOUTUBE_ID = re.compile(r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/)([\w-]{11})")


def _backdrop(item):
    if item.get("BackdropImageTags"):
        return image_url(item["Id"], "Backdrop", 1920)
    if item.get("ParentBackdropImageTags") and item.get("ParentBackdropItemId"):
        return image_url(item["ParentBackdropItemId"], "Backdrop", 1920)
    return None


def _poster(item):
    if item.get("ImageTags", {}).get("Primary") and item.get("Type") != "Episode":
        return image_url(item["Id"])
    if item.get("SeriesId") and item.get("SeriesPrimaryImageTag"):
        return image_url(item["SeriesId"])
    return None


def _resume(item):
    data = item.get("UserData") or {}
    ticks = data.get("PlaybackPositionTicks") or 0
    if not ticks or data.get("Played"):
        return None
    return {"seconds": ticks // TICKS_PER_SECOND, "percent": round(data.get("PlayedPercentage") or 0, 1)}


def _cast(item):
    people = [p for p in item.get("People", []) if p.get("Type") == "Actor"][:MAX_CAST]
    return [
        {
            "id": p["Id"],
            "name": p.get("Name"),
            "role": p.get("Role") or "",
            "image": image_url(p["Id"], "Primary", 200) if p.get("PrimaryImageTag") else None,
        }
        for p in people
    ]


def _trailers(item):
    """YouTube trailers from the metadata (Jellyfin stores links, not files)."""
    out, seen = [], set()
    for t in item.get("RemoteTrailers") or []:
        match = YOUTUBE_ID.search(t.get("Url") or "")
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            out.append({"name": t.get("Name") or "Trailer", "youtubeId": match.group(1)})
    # TMDb mixes in fan clips; prefer real trailers/teasers when there are any.
    real = [t for t in out if re.search(r"trailer|teaser", t["name"], re.I)]
    return (real or out)[:3]


def _similar(item):
    """Jellyfin's similar list; when it's empty (small library), same-genre picks."""
    source_id = item.get("SeriesId") if item.get("Type") == "Episode" else item["Id"]
    exclude = {item["Id"], source_id}
    picks = [i for i in jellyfin.similar(source_id, limit=MAX_SIMILAR) if i["Id"] not in exclude]
    if len(picks) < 6 and item.get("Genres"):
        extra, _ = jellyfin.query(
            limit=MAX_SIMILAR * 2,
            IncludeItemTypes="Movie,Series",
            Genres=item["Genres"][0],
            SortBy="Random",
        )
        names = {(i.get("Name") or "").casefold() for i in picks} | {(item.get("SeriesName") or item.get("Name") or "").casefold()}
        picks += [i for i in extra if i["Id"] not in exclude and (i.get("Name") or "").casefold() not in names]
    return [map_item(i) for i in _unique(picks)[:MAX_SIMILAR]]


def _episode(ep):
    data = ep.get("UserData") or {}
    thumb = image_url(ep["Id"], "Primary", 400) if ep.get("ImageTags", {}).get("Primary") else None
    return {
        "id": ep["Id"],
        "title": ep.get("Name"),
        "number": ep.get("IndexNumber"),
        "code": _episode_code(ep),
        "overview": ep.get("Overview") or "",
        "runtime": _runtime(ep.get("RunTimeTicks")),
        "thumb": thumb,
        "played": bool(data.get("Played")),
        "percent": round(data.get("PlayedPercentage") or 0, 1),
    }


def _season_order(season):
    # Season 1, 2, ... then unnumbered, then Specials (season 0) last.
    index = season.get("IndexNumber")
    return (index is None or index == 0, index == 0, index or 0)


def _seasons(series_id):
    # Two calls total: the season list (for order and names), then every episode
    # grouped by SeasonId — episode numbering in a messy library can't be trusted.
    grouped = OrderedDict(
        (s["Id"], {"id": s["Id"], "name": s.get("Name") or "Season", "episodes": []})
        for s in sorted(jellyfin.seasons(series_id), key=_season_order)
    )
    for ep in jellyfin.episodes(series_id):
        key = ep.get("SeasonId") or "none"
        if key not in grouped:
            grouped[key] = {"id": key, "name": ep.get("SeasonName") or "Episodes", "episodes": []}
        grouped[key]["episodes"].append(_episode(ep))
    return [s for s in grouped.values() if s["episodes"]]


def build_title(item_id):
    item = jellyfin.item(item_id)
    item_type = item.get("Type")
    data = item.get("UserData") or {}

    out = {
        "id": item["Id"],
        "kind": KINDS.get(item_type, item_type),
        "title": item.get("Name"),
        "subtitle": None,
        "year": item.get("ProductionYear"),
        "rating": round(item["CommunityRating"], 1) if item.get("CommunityRating") else None,
        "officialRating": item.get("OfficialRating"),
        "runtime": _runtime(item.get("RunTimeTicks")),
        "genres": item.get("Genres") or [],
        "tagline": (item.get("Taglines") or [None])[0],
        "overview": item.get("Overview") or "",
        "poster": _poster(item),
        "backdrop": _backdrop(item),
        "cast": _cast(item),
        "trailers": _trailers(item),
        "playable": item_type in {"Movie", "Episode", "Video", "MusicVideo"},
        "playId": item["Id"],
        "resume": _resume(item),
        "played": bool(data.get("Played")),
        "favorite": bool(data.get("IsFavorite")),
        "seriesId": None,
        "seasons": [],
        "items": [],  # collection members
        "similar": [],
    }

    if item_type == "Episode":
        out["title"] = item.get("SeriesName") or item.get("Name")
        code = _episode_code(item)
        out["subtitle"] = f"{code} · {item.get('Name')}" if code else item.get("Name")
        out["seriesId"] = item.get("SeriesId")

    elif item_type == "Series":
        out["seasons"] = _seasons(item["Id"])
        up = jellyfin.next_up(item["Id"])
        first = next((s["episodes"][0] for s in out["seasons"] if s["episodes"]), None)
        target = up or (first and {"Id": first["id"]})
        out["playable"] = target is not None
        out["playId"] = target["Id"] if target else None
        if up:
            code = _episode_code(up)
            out["subtitle"] = f"Up next: {code} · {up.get('Name')}" if code else f"Up next: {up.get('Name')}"
            out["resume"] = _resume(up)

    elif item_type == "BoxSet":
        members, _ = jellyfin.query(limit=100, ParentId=item["Id"], SortBy="PremiereDate,SortName", Recursive="false")
        members = _unique(members)
        out["items"] = [map_item(i) for i in members]
        out["subtitle"] = f"{len(members)} {'title' if len(members) == 1 else 'titles'}"

    if item_type != "BoxSet":
        out["similar"] = _similar(item)

    return out


def _local_date(stamp):
    """Jellyfin stores dates as local midnight converted to UTC (…T21:00Z for
    Nairobi), so slicing the string gives the day before. Convert back first."""
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.rstrip("Z")[:26]).replace(tzinfo=timezone.utc)
    except ValueError:
        return stamp[:10]
    return moment.astimezone(ZoneInfo(settings.TIME_ZONE)).date().isoformat()


def build_person(person_id):
    person = jellyfin.item(person_id)
    if person.get("Type") != "Person":
        raise jellyfin.JellyfinError("Not a person")
    credits, _ = jellyfin.query(
        limit=100,
        PersonIds=person_id,
        IncludeItemTypes="Movie,Series",
        SortBy="PremiereDate,SortName",
        SortOrder="Descending",
    )
    born = _local_date(person.get("PremiereDate"))
    return {
        "id": person["Id"],
        "name": person.get("Name"),
        "overview": person.get("Overview") or "",
        "born": born,
        "birthplace": (person.get("ProductionLocations") or [None])[0],
        "image": image_url(person["Id"], "Primary", 400) if person.get("ImageTags", {}).get("Primary") else None,
        "items": [map_item(i) for i in _unique(credits)],
    }
