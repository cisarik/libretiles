from django.urls import path

from .views import (
    AIContextView,
    ApplyAIMoveView,
    CreateGameView,
    ExchangeView,
    GameStateView,
    PassView,
    SubmitMoveView,
    ValidateMoveView,
    ValidateWordsView,
)

urlpatterns = [
    path("create/", CreateGameView.as_view(), name="game-create"),
    path("<str:game_id>/", GameStateView.as_view(), name="game-state"),
    path("<str:game_id>/move/", SubmitMoveView.as_view(), name="game-move"),
    path("<str:game_id>/exchange/", ExchangeView.as_view(), name="game-exchange"),
    path("<str:game_id>/pass/", PassView.as_view(), name="game-pass"),
    path("<str:game_id>/ai-context/", AIContextView.as_view(), name="game-ai-context"),
    path("<str:game_id>/validate-move/", ValidateMoveView.as_view(), name="game-validate-move"),
    path("<str:game_id>/validate-words/", ValidateWordsView.as_view(), name="game-validate-words"),
    path("<str:game_id>/ai-move/", ApplyAIMoveView.as_view(), name="game-ai-move"),
]
