"""
Library listings for the Movies / Series / Collections / My List pages, and
search. Sorting and genre filtering happen in Jellyfin; pages are fetched in
chunks so the UI can scroll forever.
"""

from . import jellyfin
from .home import KINDS, _unique, image_url, map_item

TYPES = {
    "movies": {"IncludeItemTypes": "Movie"},
    "series": {"IncludeItemTypes": "Series"},
    "collections": {"IncludeItemTypes": "BoxSet"},
    "mylist": {"IncludeItemTypes": "Movie,Series,BoxSet,Episode", "IsFavorite": "true"},
}

SORTS = {
    "added": ("DateCreated,SortName", "Descending"),
    "title": ("SortName", "Ascending"),
    "year": ("ProductionYear,PremiereDate,SortName", "Descending"),
    "rating": ("CommunityRating,SortName", "Descending"),
    "random": ("Random", "Ascending"),
}

MAX_PAGE = 100


def browse(kind, sort="added", genre="", start=0, limit=48):
    if kind not in TYPES:
        raise ValueError("type must be one of: " + ", ".join(TYPES))
    if sort not in SORTS:
        raise ValueError("sort must be one of: " + ", ".join(SORTS))
    sort_by, order = SORTS[sort]
    params = {**TYPES[kind], "SortBy": sort_by, "SortOrder": order}
    if genre:
        params["Genres"] = genre
    items, total = jellyfin.query(limit=max(1, min(limit, MAX_PAGE)), start=max(0, start), **params)
    # `next` is the raw offset for the following page; duplicate copies of a
    # title are hidden within a page, so items can be fewer than `limit`.
    return {"items": [map_item(i) for i in _unique(items)], "total": total, "next": start + len(items)}


def genres(kind):
    if kind not in ("movies", "series"):
        raise ValueError("type must be movies or series")
    return jellyfin.genres(TYPES[kind]["IncludeItemTypes"])


def search(term):
    """Instant search: titles (movies, shows, episodes, collections) and people
    as separate lists, so a common first name can't crowd out every title."""
    titles = _hints(jellyfin.search_hints(term, limit=24, types="Movie,Series,Episode,BoxSet"))
    people = _hints(jellyfin.search_hints(term, limit=10, types="Person"))
    seen, unique = set(), []
    for t in titles:
        key = (t["title"].casefold(), t.get("year"), t["kind"], t.get("badge"))
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return {"results": unique, "people": people}


def _hints(hints):
    out = []
    for hint in hints:
        item_id = hint.get("Id") or hint.get("ItemId")
        item_type = hint.get("Type")
        if not item_id:
            continue
        has_image = bool(hint.get("PrimaryImageTag"))
        result = {
            "id": item_id,
            "title": hint.get("Name"),
            "kind": KINDS.get(item_type, item_type),
            "poster": image_url(item_id) if has_image else None,
        }
        if hint.get("ProductionYear"):
            result["year"] = hint["ProductionYear"]
        if item_type == "Person":
            result["href"] = f"/person/{item_id}"
        elif item_type == "Episode":
            result["badge"] = hint.get("Series")
            if not has_image and hint.get("ThumbImageItemId"):
                result["poster"] = image_url(hint["ThumbImageItemId"])
        out.append(result)
    return out
