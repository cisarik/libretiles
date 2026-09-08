from django.urls import path

from .admin_views import AdminGameListView, AdminGameReplayView

app_name = "game_admin"

urlpatterns = [
    path("games/", AdminGameListView.as_view(), name="admin-game-list"),
    path(
        "games/<str:game_id>/replay/",
        AdminGameReplayView.as_view(),
        name="admin-game-replay",
    ),
]
