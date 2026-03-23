from __future__ import annotations

import asyncio

import pytest
from channels.testing import WebsocketCommunicator
from django.test import override_settings

from accounts.models import User
from config.asgi import application
from game import services
from game.models import GameSession


async def _receive_until_type(
    communicator: WebsocketCommunicator,
    expected_type: str,
    *,
    attempts: int = 6,
) -> dict:
    for _ in range(attempts):
        payload = await asyncio.wait_for(communicator.receive_json_from(), timeout=2)
        if payload.get("type") == expected_type:
            return payload
    raise AssertionError(f"Did not receive {expected_type}")


def _set_slot_rack(*, game_id: str, slot_number: int, rack: list[str]) -> None:
    session = GameSession.objects.get(public_id=game_id)
    slot = session.slots.get(slot=slot_number)
    slot.rack = rack
    slot.save(update_fields=["rack"])


def _create_user(*, username: str) -> User:
    return User.objects.create_user(username=username, password="pass1234")


def _set_current_turn(*, game_id: str, slot_number: int) -> None:
    session = GameSession.objects.get(public_id=game_id)
    session.current_turn_slot = slot_number
    session.save(update_fields=["current_turn_slot"])


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_waiting_player_receives_match_found_event() -> None:
    user1 = await asyncio.to_thread(_create_user, username="ws_player1")
    user2 = await asyncio.to_thread(_create_user, username="ws_player2")

    waiting = await asyncio.to_thread(services.join_human_queue, user_id=user1.id, variant_slug="english")
    game_id = waiting["state"]["game_id"]
    ticket1 = await asyncio.to_thread(services.build_ws_ticket, game_id=game_id, user_id=user1.id)

    communicator1 = WebsocketCommunicator(application, f"/ws/game/{game_id}/?ticket={ticket1['ticket']}")
    connected, _subprotocol = await communicator1.connect()
    assert connected is True
    await _receive_until_type(communicator1, "game_state")

    await asyncio.to_thread(services.join_human_queue, user_id=user2.id, variant_slug="english")
    match_event = await _receive_until_type(communicator1, "match_found")
    assert match_event["state"]["status"] == "active"
    assert len(match_event["state"]["my_rack"]) == 7

    await communicator1.disconnect()


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_chat_and_game_state_events_are_user_specific() -> None:
    user1 = await asyncio.to_thread(_create_user, username="chat_player1")
    user2 = await asyncio.to_thread(_create_user, username="chat_player2")

    await asyncio.to_thread(services.join_human_queue, user_id=user1.id, variant_slug="english")
    joined = await asyncio.to_thread(services.join_human_queue, user_id=user2.id, variant_slug="english")
    game_id = joined["state"]["game_id"]
    await asyncio.to_thread(
        _set_slot_rack,
        game_id=game_id,
        slot_number=0,
        rack=["A", "B", "C", "D", "E", "F", "G"],
    )
    await asyncio.to_thread(
        _set_slot_rack,
        game_id=game_id,
        slot_number=1,
        rack=["H", "I", "J", "K", "L", "M", "N"],
    )
    await asyncio.to_thread(_set_current_turn, game_id=game_id, slot_number=0)

    ticket1 = await asyncio.to_thread(services.build_ws_ticket, game_id=game_id, user_id=user1.id)
    ticket2 = await asyncio.to_thread(services.build_ws_ticket, game_id=game_id, user_id=user2.id)

    communicator1 = WebsocketCommunicator(application, f"/ws/game/{game_id}/?ticket={ticket1['ticket']}")
    communicator2 = WebsocketCommunicator(application, f"/ws/game/{game_id}/?ticket={ticket2['ticket']}")
    assert (await communicator1.connect())[0] is True
    assert (await communicator2.connect())[0] is True

    state1 = await _receive_until_type(communicator1, "game_state")
    state2 = await _receive_until_type(communicator2, "game_state")
    assert state1["state"]["my_rack"] == ["A", "B", "C", "D", "E", "F", "G"]
    assert state2["state"]["my_rack"] == ["H", "I", "J", "K", "L", "M", "N"]

    await communicator1.send_json_to({"type": "chat_message", "body": "hello there"})
    chat1 = await _receive_until_type(communicator1, "chat_message")
    chat2 = await _receive_until_type(communicator2, "chat_message")
    assert chat1["message"]["body"] == "hello there"
    assert chat1["message"]["mine"] is True
    assert chat2["message"]["mine"] is False

    await asyncio.to_thread(services.submit_pass_for_user, game_id, user1.id)
    update1 = await _receive_until_type(communicator1, "game_state")
    update2 = await _receive_until_type(communicator2, "game_state")
    assert update1["state"]["my_slot"] == 0
    assert update2["state"]["my_slot"] == 1
    assert update1["state"]["my_rack"] == ["A", "B", "C", "D", "E", "F", "G"]
    assert update2["state"]["my_rack"] == ["H", "I", "J", "K", "L", "M", "N"]

    await communicator1.disconnect()
    await communicator2.disconnect()


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_invalid_ticket_is_rejected() -> None:
    user = await asyncio.to_thread(_create_user, username="ws_invalid")
    waiting = await asyncio.to_thread(services.join_human_queue, user_id=user.id, variant_slug="english")
    game_id = waiting["state"]["game_id"]

    communicator = WebsocketCommunicator(application, f"/ws/game/{game_id}/?ticket=invalid-ticket")
    connected, _subprotocol = await communicator.connect()
    assert connected is False
