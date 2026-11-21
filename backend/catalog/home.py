"""
Builds the /api/home payload the UI renders:

    { hero: {title, overview, backdrop, meta[], badge},
      rows: [{title, items: [{id, title, poster, year?, rating?, kind?, badge?}]}] }

`poster` / `backdrop` may be null; the UI then draws its gradient placeholder.
"""

import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from . import jellyfin
from .mock import MOCK_HOME

KINDS = {
    "Movie": "movie",
    "Series": "series",
    "Episode": "episode",
    "BoxSet": "collection",
    "Person": "person",
    "PhotoAlbum": "album",
    "Photo": "photo",
}

NEW_WINDOW = timedelta(days=14)


def image_url(item_id, image_type="Primary", width=400):
    return f"/api/img/{item_id}/{image_type}?w={width}"


def _is_new(item):
    created = item.get("DateCreated")
    if not created:
        return False
    try:
        # Jellyfin sends 7-digit fractions ("...00.1234567Z"); trim to what Python parses.
        stamp = datetime.fromisoformat(created.rstrip("Z")[:26]).replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - stamp < NEW_WINDOW


def map_item(item):
    item_type = item.get("Type")
    # Episodes show their series' poster and name, like every streaming UI.
    if item_type == "Episode" and item.get("SeriesId"):
        poster = image_url(item["SeriesId"]) if item.get("SeriesPrimaryImageTag") else None
        title = item.get("SeriesName") or item.get("Name")
        badge = _episode_code(item)
    else:
        poster = image_url(item["Id"]) if item.get("ImageTags", {}).get("Primary") else None
        title = item.get("Name")
        badge = None

    if item_type == "PhotoAlbum" and item.get("ChildCount"):
        badge = str(item["ChildCount"])
    elif badge is None and _is_new(item):
        badge = "New"

    out = {"id": item["Id"], "title": title, "poster": poster, "kind": KINDS.get(item_type, item_type)}
    if item_type == "Person":
        out["href"] = f"/person/{item['Id']}"
    if item.get("ProductionYear"):
        out["year"] = item["ProductionYear"]
    if item.get("CommunityRating"):
        out["rating"] = round(item["CommunityRating"], 1)
    if badge:
        out["badge"] = badge

    data = item.get("UserData") or {}
    if data.get("Played"):
        out["played"] = True
    elif data.get("PlayedPercentage"):
        out["progress"] = round(data["PlayedPercentage"], 1)
    if data.get("IsFavorite"):
        out["favorite"] = True
    return out


def _episode_code(item):
    season, episode = item.get("ParentIndexNumber"), item.get("IndexNumber")
    if season is None or episode is None:
        return None
    return f"S{season}E{episode}"


def _runtime(ticks):
    if not ticks:
        return None
    minutes = ticks // 600_000_000  # 10,000,000 ticks per second
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def map_hero(item):
    meta = [
        str(item["ProductionYear"]) if item.get("ProductionYear") else None,
        _runtime(item.get("RunTimeTicks")),
        item.get("OfficialRating"),
        (item.get("Genres") or [None])[0],
    ]
    return {
        "id": item["Id"],
        "title": item.get("Name"),
        "badge": "Featured on your server",
        "backdrop": image_url(item["Id"], "Backdrop", 1920) if item.get("BackdropImageTags") else None,
        "meta": [m for m in meta if m],
        "overview": item.get("Overview") or "",
        "favorite": bool((item.get("UserData") or {}).get("IsFavorite")),
    }


HERO_COUNT = 8


def _unique(items):
    """Drop repeat copies of the same title (the library has duplicates/split seasons)."""
    seen, out = set(), []
    for i in items:
        key = ((i.get("Name") or "").casefold(), i.get("ProductionYear"))
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out


GENRE_ROWS = 3
ROW_SIZE = 20
MIN_GENRE_ITEMS = 6


def continue_watching(resume, next_up):
    """One card per show: the in-progress episode if any, else the next one up.
    Movies in progress come first in last-played order, as Jellyfin returns them."""
    seen_series, out = set(), []
    for item in resume + next_up:
        series_id = item.get("SeriesId")
        if series_id:
            if series_id in seen_series:
                continue
            seen_series.add(series_id)
        out.append(item)
    return out[:ROW_SIZE]


def _genre_rows():
    """A few random genres per load, each with a random handful of titles."""
    names = jellyfin.genres()
    random.shuffle(names)
    rows = []
    for name in names:
        if len(rows) == GENRE_ROWS:
            break
        items, _ = jellyfin.query(limit=ROW_SIZE * 2, IncludeItemTypes="Movie,Series", Genres=name, SortBy="Random")
        items = _unique(items)[:ROW_SIZE]
        if len(items) >= MIN_GENRE_ITEMS:
            rows.append((name, items))
    return rows


def live_home():
    calls = {
        "resume": lambda: jellyfin.resume(),
        "next_up": lambda: jellyfin.next_up(limit=ROW_SIZE),
        # watched films drop out of "Recently Added"
        "movies": lambda: jellyfin.recent("Movie", IsPlayed="false"),
        "series": lambda: jellyfin.recent("Series"),
        "favorites": lambda: jellyfin.query(limit=ROW_SIZE, IsFavorite="true", IncludeItemTypes="Movie,Series,BoxSet", SortBy="DateCreated", SortOrder="Descending")[0],
        "collections": lambda: jellyfin.query(limit=ROW_SIZE, IncludeItemTypes="BoxSet", SortBy="SortName")[0],
        "photos": lambda: jellyfin.recent("PhotoAlbum"),
        "featured": lambda: jellyfin.featured(limit=HERO_COUNT * 2),
        "genres": _genre_rows,
    }
    # ~9 independent Jellyfin calls: run them side by side, not one after another.
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = {name: pool.submit(fn) for name, fn in calls.items()}
        got = {name: f.result() for name, f in futures.items()}

    rows = [
        ("Continue Watching", continue_watching(got["resume"], got["next_up"])),
        ("My List", got["favorites"]),
        ("Recently Added Movies", _unique(got["movies"])),
        ("Recently Added Series", _unique(got["series"])),
        *[(name, items) for name, items in got["genres"]],
        ("Collections", got["collections"]),
        ("Family Photos", got["photos"]),
    ]

    # A fresh random pick of titles with backdrop art on every load; the UI
    # cycles through them. Fall back to the newest title if none have art.
    featured = _unique(got["featured"])[:HERO_COUNT]
    if not featured:
        newest = next(iter(got["movies"] + got["series"]), None)
        featured = [newest] if newest else []
    heroes = [map_hero(i) for i in featured]
    # "See all" for a genre goes to whichever page most of that row's titles live on.
    genre_links = {
        name: f"/{'series' if sum(i.get('Type') == 'Series' for i in items) * 2 > len(items) else 'movies'}?genre={quote(name)}"
        for name, items in got["genres"]
    }

    return {
        "hero": heroes[0] if heroes else None,
        "heroes": heroes,
        "rows": [
            {"title": title, "items": [map_item(i) for i in items], "href": ROW_LINKS.get(title) or genre_links.get(title)}
            for title, items in rows
            if items
        ],
    }


# "See all" targets for rows that have a full page.
ROW_LINKS = {
    "My List": "/mylist",
    "Recently Added Movies": "/movies",
    "Recently Added Series": "/series",
    "Collections": "/collections",
}


def mock_home():
    return {**MOCK_HOME, "heroes": [MOCK_HOME["hero"]]}
