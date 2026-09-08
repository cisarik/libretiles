from django.urls import path

from .admin_views import AdminGameListView, AdminGameReplayView
from .simulation_views import (
    SimulationActionView,
    SimulationCreateView,
    SimulationStateView,
    SimulationStepView,
    SimulationStopView,
)

app_name = "game_admin"

urlpatterns = [
    path("simulate/", SimulationCreateView.as_view(), name="admin-simulation-create"),
    path(
        "simulate/<str:game_id>/",
        SimulationStateView.as_view(),
        name="admin-simulation-state",
    ),
    path(
        "simulate/<str:game_id>/step/",
        SimulationStepView.as_view(),
        name="admin-simulation-step",
    ),
    path(
        "simulate/<str:game_id>/action/",
        SimulationActionView.as_view(),
        name="admin-simulation-action",
    ),
    path(
        "simulate/<str:game_id>/stop/",
        SimulationStopView.as_view(),
        name="admin-simulation-stop",
    ),
    path("games/", AdminGameListView.as_view(), name="admin-game-list"),
    path(
        "games/<str:game_id>/replay/",
        AdminGameReplayView.as_view(),
        name="admin-game-replay",
    ),
]
