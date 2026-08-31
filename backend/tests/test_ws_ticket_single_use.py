"""Regression tests for single-use websocket tickets (audit-01-F09 replay part).

Never print a ticket value. Assertions that could dump locals use booleans.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.core import signing
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from config.asgi import application
from game import models as game_models
from game import services


def _create_user(*, username: str) -> User:
    return User.objects.create_user(username=username, password="pass1234")


def _make_vs_ai_game(user: User) -> str:
    result = services.create_game(user_id=user.id, game_mode="vs_ai")
    game_id = result["game_id"]
    assert isinstance(game_id, str) and game_id
    return game_id


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


@pytest.mark.django_db
def test_verify_ws_ticket_succeeds_once_for_fresh_ticket() -> None:
    user = _create_user(username="ws_su_fresh")
    game_id = _make_vs_ai_game(user)
    issued = services.build_ws_ticket(game_id=game_id, user_id=user.id)
    verified_user_id = services.verify_ws_ticket(game_id=game_id, ticket=issued["ticket"])
    assert verified_user_id == user.id


@pytest.mark.django_db
def test_verify_ws_ticket_rejects_replay_of_same_ticket_string() -> None:
    user = _create_user(username="ws_su_replay")
    game_id = _make_vs_ai_game(user)
    issued = services.build_ws_ticket(game_id=game_id, user_id=user.id)
    ticket = issued["ticket"]
    first = services.verify_ws_ticket(game_id=game_id, ticket=ticket)
    assert first == user.id
    second_failed = False
    try:
        services.verify_ws_ticket(game_id=game_id, ticket=ticket)
    except services.GameNotFoundError:
        second_failed = True
    assert second_failed is True


@pytest.mark.django_db
def test_ticket_for_game_a_is_rejected_for_game_b() -> None:
    user = _create_user(username="ws_su_game_bind")
    game_a = _make_vs_ai_game(user)
    game_b = _make_vs_ai_game(user)
    issued = services.build_ws_ticket(game_id=game_a, user_id=user.id)
    rejected = False
    try:
        services.verify_ws_ticket(game_id=game_b, ticket=issued["ticket"])
    except services.GameNotFoundError:
        rejected = True
    assert rejected is True


@pytest.mark.django_db
def test_ticket_for_non_participant_is_rejected() -> None:
    owner = _create_user(username="ws_su_owner")
    outsider = _create_user(username="ws_su_outsider")
    game_id = _make_vs_ai_game(owner)
    forged = signing.dumps(
        {"game_id": game_id, "user_id": outsider.id},
        salt=services.WS_TICKET_SALT,
        compress=True,
    )
    rejected = False
    try:
        services.verify_ws_ticket(game_id=game_id, ticket=forged)
    except services.GameNotFoundError:
        rejected = True
    assert rejected is True


@pytest.mark.django_db
def test_expired_ticket_is_rejected() -> None:
    user = _create_user(username="ws_su_expired")
    game_id = _make_vs_ai_game(user)
    issued = services.build_ws_ticket(game_id=game_id, user_id=user.id)
    max_age = int(getattr(settings, "GAME_WS_TICKET_MAX_AGE_SECONDS", 10))
    expired = False
    with patch("django.core.signing.time.time", return_value=time.time() + max_age + 1):
        try:
            services.verify_ws_ticket(game_id=game_id, ticket=issued["ticket"])
        except signing.SignatureExpired:
            expired = True
    assert expired is True


@pytest.mark.django_db
def test_two_different_tickets_for_same_user_and_game_each_work_once() -> None:
    user = _create_user(username="ws_su_two_tickets")
    game_id = _make_vs_ai_game(user)
    first_issued = services.build_ws_ticket(game_id=game_id, user_id=user.id)
    second_issued = services.build_ws_ticket(game_id=game_id, user_id=user.id)
    first_user_id = services.verify_ws_ticket(game_id=game_id, ticket=first_issued["ticket"])
    second_user_id = services.verify_ws_ticket(game_id=game_id, ticket=second_issued["ticket"])
    assert first_user_id == user.id
    assert second_user_id == user.id


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_reconnect_fetches_new_http_ticket_and_connects_again() -> None:
    user = await asyncio.to_thread(_create_user, username="ws_su_reconnect")
    waiting = await asyncio.to_thread(services.join_human_queue, user_id=user.id, variant_slug="english")
    game_id = waiting["state"]["game_id"]

    def _http_ticket() -> str:
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(f"/api/game/{game_id}/ws-ticket/")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        ticket = body["ticket"]
        assert isinstance(ticket, str) and bool(ticket)
        return ticket

    ticket1 = await asyncio.to_thread(_http_ticket)
    communicator1 = WebsocketCommunicator(application, f"/ws/game/{game_id}/?ticket={ticket1}")
    connected1, _subprotocol1 = await communicator1.connect()
    assert connected1 is True
    await _receive_until_type(communicator1, "game_state")
    await communicator1.disconnect()

    ticket2 = await asyncio.to_thread(_http_ticket)
    communicator2 = WebsocketCommunicator(application, f"/ws/game/{game_id}/?ticket={ticket2}")
    connected2, _subprotocol2 = await communicator2.connect()
    assert connected2 is True
    await _receive_until_type(communicator2, "game_state")
    await communicator2.disconnect()


@pytest.mark.django_db
def test_consumed_ticket_record_does_not_contain_raw_ticket_string() -> None:
    consumed_model = getattr(game_models, "ConsumedWsTicket", None)
    assert consumed_model is not None
    user = _create_user(username="ws_su_no_raw")
    game_id = _make_vs_ai_game(user)
    issued = services.build_ws_ticket(game_id=game_id, user_id=user.id)
    ticket = issued["ticket"]
    services.verify_ws_ticket(game_id=game_id, ticket=ticket)
    expected_hash = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
    row = consumed_model.objects.get(ticket_hash=expected_hash)
    column_names = {field.column for field in consumed_model._meta.local_concrete_fields}
    assert "ticket" not in column_names
    contains_raw = False
    for field in consumed_model._meta.local_concrete_fields:
        value = getattr(row, field.attname)
        if isinstance(value, str) and (value == ticket or ticket in value):
            contains_raw = True
    hash_matches = row.ticket_hash == expected_hash
    assert hash_matches is True
    assert contains_raw is False


@pytest.mark.django_db
def test_cleanup_removes_expired_consumed_rows_and_leaves_unexpired() -> None:
    consumed_model = getattr(game_models, "ConsumedWsTicket", None)
    assert consumed_model is not None
    cleanup = getattr(services, "cleanup_consumed_ws_tickets", None)
    assert callable(cleanup)
    now = timezone.now()
    expired = consumed_model.objects.create(
        ticket_hash="a" * 64,
        expires_at=now - timedelta(seconds=5),
    )
    living = consumed_model.objects.create(
        ticket_hash="b" * 64,
        expires_at=now + timedelta(hours=1),
    )
    deleted = cleanup()
    assert deleted >= 1
    assert consumed_model.objects.filter(pk=expired.pk).exists() is False
    assert consumed_model.objects.filter(pk=living.pk).exists() is True


@pytest.mark.django_db
def test_game_ws_ticket_view_returns_ticket_for_participant_and_404_for_outsider() -> None:
    participant = _create_user(username="ws_su_view_in")
    outsider = _create_user(username="ws_su_view_out")
    game_id = _make_vs_ai_game(participant)
    in_client = APIClient()
    in_client.force_authenticate(user=participant)
    out_client = APIClient()
    out_client.force_authenticate(user=outsider)
    ok_response = in_client.post(f"/api/game/{game_id}/ws-ticket/")
    assert ok_response.status_code == 200
    body = ok_response.json()
    assert body["ok"] is True
    assert isinstance(body["ticket"], str) and bool(body["ticket"])
    assert body["expires_in"] == int(settings.GAME_WS_TICKET_MAX_AGE_SECONDS)
    denied = out_client.post(f"/api/game/{game_id}/ws-ticket/")
    assert denied.status_code == 404


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_websocket_connect_succeeds_end_to_end_with_fresh_ticket() -> None:
    user = await asyncio.to_thread(_create_user, username="ws_su_e2e")
    waiting = await asyncio.to_thread(services.join_human_queue, user_id=user.id, variant_slug="english")
    game_id = waiting["state"]["game_id"]
    issued = await asyncio.to_thread(services.build_ws_ticket, game_id=game_id, user_id=user.id)
    communicator = WebsocketCommunicator(application, f"/ws/game/{game_id}/?ticket={issued['ticket']}")
    connected, _subprotocol = await communicator.connect()
    assert connected is True
    state_event = await _receive_until_type(communicator, "game_state")
    assert state_event["state"]["game_id"] == game_id
    await communicator.disconnect()
