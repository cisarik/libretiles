from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .models import GameSession


def room_name(game_id: str) -> str:
    return f"game_{game_id}"


def _group_send(group: str, message: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(group, message)


def publish_game_state_refresh(session: GameSession, *, event_name: str) -> None:
    game_id = str(session.public_id)

    def send() -> None:
        _group_send(
            room_name(game_id),
            {
                "type": "room.game_state",
                "event_name": event_name,
                "game_id": game_id,
            },
        )

    transaction.on_commit(send)


def publish_chat_message(session: GameSession, *, payload: dict) -> None:
    game_id = str(session.public_id)

    def send() -> None:
        _group_send(
            room_name(game_id),
            {
                "type": "room.chat_message",
                "event_name": "chat_message",
                "game_id": game_id,
                "payload": payload,
            },
        )

    transaction.on_commit(send)


def publish_presence_event(*, game_id: str, event_name: str, username: str) -> None:
    _group_send(
        room_name(game_id),
        {
            "type": "room.presence",
            "event_name": event_name,
            "game_id": game_id,
            "username": username,
        },
    )
