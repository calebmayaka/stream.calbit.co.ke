from django.urls import path, register_converter

from . import views


class JellyfinId:
    """Jellyfin item ids are 32 hex chars; anything else never reaches Jellyfin."""

    regex = "[0-9a-f]{32}"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(JellyfinId, "jid")

urlpatterns = [
    path("auth/me", views.auth_me),
    path("auth/login", views.auth_login),
    path("auth/logout", views.auth_logout),
    path("auth/setup", views.auth_setup),
    path("health", views.health),
    path("home", views.home),
    path("browse", views.browse_view),
    path("genres", views.genres_view),
    path("search", views.search_view),
    path("title/<jid:item_id>", views.title),
    path("person/<jid:item_id>", views.person),
    path("played/<jid:item_id>", views.played),
    path("favorite/<jid:item_id>", views.favorite),
    path("play/<jid:item_id>", views.play),
    path("progress/<jid:item_id>", views.progress),
    path("stop", views.stop),
    path("subs/<jid:item_id>/<jid:source_id>/<int:index>", views.subtitles),
    path("img/<jid:item_id>/<str:image_type>", views.image),
]
