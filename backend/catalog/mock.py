"""
Canned /api/home payload for MEDIAHUB_DATA_MODE=mock, so UI work never hits
live Jellyfin. Posters are null; the UI fills in its gradient placeholders.
"""

import re


def _mk(title, **opts):
    return {"id": re.sub(r"[^a-z0-9]+", "-", title.lower()), "title": title, "poster": None, **opts}


MOVIES = [
    _mk("Nairobi Nights", year=2024, rating=8.1, kind="movie", badge="4K"),
    _mk("The Rift Valley", year=2023, rating=7.4, kind="movie"),
    _mk("Coastal Winds", year=2025, rating=8.8, kind="movie", badge="New"),
    _mk("Savanna", year=2022, rating=7.9, kind="movie"),
    _mk("Mount Kenya", year=2021, rating=8.3, kind="movie"),
    _mk("Lamu", year=2024, rating=7.1, kind="movie"),
    _mk("Harambee", year=2020, rating=8.6, kind="movie", badge="4K"),
    _mk("The Long Rains", year=2025, rating=7.7, kind="movie"),
]

SERIES = [
    _mk("Tatu Season", year=2025, rating=8.9, kind="series", badge="S2"),
    _mk("Office Park", year=2024, rating=7.6, kind="series"),
    _mk("Matatu Diaries", year=2023, rating=8.2, kind="series"),
    _mk("Code & Chai", year=2025, rating=9.0, kind="series", badge="New"),
    _mk("The Newsroom KE", year=2022, rating=7.3, kind="series"),
    _mk("Shamba", year=2024, rating=8.0, kind="series"),
    _mk("Downtown", year=2021, rating=7.8, kind="series"),
]

PHOTOS = [
    _mk("Graduation 2019", year=2019, kind="album", badge="248"),
    _mk("Diani Trip", year=2023, kind="album", badge="112"),
    _mk("Family Christmas", year=2024, kind="album", badge="87"),
    _mk("Nakuru Road Trip", year=2022, kind="album", badge="164"),
    _mk("Baby’s First Year", year=2021, kind="album", badge="503"),
    _mk("Office Offsite", year=2025, kind="album", badge="61"),
    _mk("Mum’s Birthday", year=2023, kind="album", badge="94"),
]

RETRO = [
    _mk("Super Mario World", year=1990, kind="SNES", rating=9.6),
    _mk("Sonic 2", year=1992, kind="Genesis", rating=9.1),
    _mk("Zelda: Link’s Awakening", year=1993, kind="Game Boy", rating=9.4),
    _mk("Street Fighter II", year=1991, kind="Arcade", rating=9.0),
    _mk("Golden Eye 007", year=1997, kind="N64", rating=8.9),
    _mk("Pokémon Red", year=1996, kind="Game Boy", rating=9.3),
    _mk("Crash Bandicoot", year=1996, kind="PS1", rating=8.7),
]

MOCK_HOME = {
    "hero": {
        "id": "coastal-winds",
        "title": "Coastal Winds",
        "badge": "Featured on your server",
        "backdrop": None,
        "meta": ["2025", "1h 58m", "4K HDR", "Drama"],
        "overview": (
            "A fisherman’s family on the Kenyan coast weathers a season of change. "
            "Served by Django in mock mode — flip MEDIAHUB_DATA_MODE=live for your library."
        ),
    },
    "rows": [
        {"title": "Continue Watching", "items": SERIES[:3] + MOVIES[:3]},
        {"title": "Movies", "items": MOVIES},
        {"title": "Series", "items": SERIES},
        {"title": "Family Photos", "items": PHOTOS},
        {"title": "Retro Collection", "items": RETRO},
    ],
}
