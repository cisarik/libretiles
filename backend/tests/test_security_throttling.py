"""Regression tests for auth/AI-context throttles and registration password policy.

Throttle counters live in Django's default cache. Tests clear it explicitly so
results do not depend on collection order.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import AIModel
from catalog.selection import DEFAULT_FREE_MODEL_ID, OPENROUTER_PROVIDER

# Must match backend/config/settings.py REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].
REGISTER_LIMIT = 20
LOGIN_LIMIT = 60
REFRESH_LIMIT = 60
CHANGE_PASSWORD_LIMIT = 5
ME_LIMIT = 200
AI_CONTEXT_LIMIT = 200
# Slovak games run ~29 plies. One AI turn may call ai-context once per
# fallback lane (MAX_FALLBACK_ATTEMPTS = 3). Conservatively treat every ply
# as an AI turn: 29 * 3 = 87 reads in one pathological full game.
NORMAL_PLAY_AI_CONTEXT_READS = 87
# Item B realistic same-IP session:
#   2 browser profiles × (1 success + 2 typos) = 6
#   interviewer 2 accounts × (1 success + 2 typos) = 6
#   4 extra logout/login cycles = 4
#   Total login attempts = 16, below LOGIN_LIMIT=60 and above axes 8/account
#   so a presenter spread across accounts trips neither control.
DEMO_LOGIN_ATTEMPTS = 16
# 2 local accounts + interviewer 2, each with a rejected first password then a
# retry, plus a couple of extra validation retries: 12 < REGISTER_LIMIT=20.
DEMO_REGISTER_ATTEMPTS = 12
STRONG_PASSWORD = "testpass123"


@pytest.fixture(autouse=True)
def _reset_throttle_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


def _seed_model() -> AIModel:
    model, _created = AIModel.objects.get_or_create(
        model_id=DEFAULT_FREE_MODEL_ID,
        defaults={
            "provider": OPENROUTER_PROVIDER,
            "display_name": "Throttle Test Model",
            "openrouter_available": True,
            "is_active": True,
            "model_type": "language",
            "tags": ["tools"],
            "sort_order": 10,
        },
    )
    return model


def _auth_client(username: str) -> APIClient:
    user = User.objects.create_user(username=username, password=STRONG_PASSWORD)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _create_vs_ai_game(client: APIClient) -> str:
    _seed_model()
    response = client.post("/api/game/create/", {"game_mode": "vs_ai"})
    assert response.status_code == 201, response.content
    game_id = response.json()["game_id"]
    assert isinstance(game_id, str)
    return game_id


@pytest.mark.django_db
def test_register_throttled_after_limit() -> None:
    client = APIClient()
    under = client.post(
        "/api/auth/register/",
        {
            "username": "reg_under",
            "email": "reg_under@example.com",
            "password": STRONG_PASSWORD,
        },
    )
    assert under.status_code == 201

    cache.clear()
    statuses: list[int] = []
    for index in range(REGISTER_LIMIT + 1):
        response = client.post(
            "/api/auth/register/",
            {
                "username": f"reg_burst_{index}",
                "email": f"reg_burst_{index}@example.com",
                "password": STRONG_PASSWORD,
            },
        )
        statuses.append(response.status_code)
    assert statuses[0] == 201
    assert statuses[REGISTER_LIMIT - 1] == 201
    assert statuses[REGISTER_LIMIT] == 429


@pytest.mark.django_db
def test_login_throttled_after_limit() -> None:
    User.objects.create_user(username="login_under", password=STRONG_PASSWORD)
    client = APIClient()
    under = client.post(
        "/api/auth/login/",
        {"username": "login_under", "password": STRONG_PASSWORD},
    )
    assert under.status_code == 200

    cache.clear()
    statuses: list[int] = []
    for index in range(LOGIN_LIMIT + 1):
        # Distinct usernames: ScopedRateThrottle keys unauthenticated
        # auth_login on IP (get_ident), so the IP budget still accumulates
        # while the axes per-(username, IP) counter stays at 1.
        username = f"login_burst_{index}"
        User.objects.create_user(username=username, password=STRONG_PASSWORD)
        response = client.post(
            "/api/auth/login/",
            {"username": username, "password": "wrong-password"},
        )
        statuses.append(response.status_code)
    assert statuses[0] == 401
    assert statuses[LOGIN_LIMIT - 1] == 401
    assert statuses[LOGIN_LIMIT] == 429


@pytest.mark.django_db
def test_refresh_throttled_after_limit() -> None:
    User.objects.create_user(username="refresh_under", password=STRONG_PASSWORD)
    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"username": "refresh_under", "password": STRONG_PASSWORD},
    )
    assert login.status_code == 200
    refresh = login.json()["refresh"]
    under = client.post("/api/auth/refresh/", {"refresh": refresh})
    assert under.status_code == 200

    cache.clear()
    statuses: list[int] = []
    for _ in range(REFRESH_LIMIT + 1):
        response = client.post("/api/auth/refresh/", {"refresh": "not-a-token"})
        statuses.append(response.status_code)
    assert statuses[0] == 401
    assert statuses[REFRESH_LIMIT - 1] == 401
    assert statuses[REFRESH_LIMIT] == 429


@pytest.mark.django_db
def test_change_password_throttled_after_limit() -> None:
    client = _auth_client("change_pw_under")
    under = client.post(
        "/api/auth/change-password/",
        {"current_password": STRONG_PASSWORD, "new_password": "newpass1234"},
    )
    assert under.status_code == 200

    cache.clear()
    statuses: list[int] = []
    for _ in range(CHANGE_PASSWORD_LIMIT + 1):
        response = client.post(
            "/api/auth/change-password/",
            {"current_password": "wrong-password", "new_password": "newpass1234"},
        )
        statuses.append(response.status_code)
    assert statuses[0] == 400
    assert statuses[CHANGE_PASSWORD_LIMIT - 1] == 400
    assert statuses[CHANGE_PASSWORD_LIMIT] == 429


@pytest.mark.django_db
def test_me_throttled_after_limit() -> None:
    client = _auth_client("me_under")
    under = client.get("/api/auth/me/")
    assert under.status_code == 200

    cache.clear()
    statuses: list[int] = []
    for _ in range(ME_LIMIT + 1):
        statuses.append(client.get("/api/auth/me/").status_code)
    assert statuses[0] == 200
    assert statuses[ME_LIMIT - 1] == 200
    assert statuses[ME_LIMIT] == 429


@pytest.mark.django_db
def test_ai_context_throttled_after_limit() -> None:
    client = _auth_client("ai_ctx_under")
    game_id = _create_vs_ai_game(client)
    under = client.get(f"/api/game/{game_id}/ai-context/")
    assert under.status_code == 200

    cache.clear()
    statuses: list[int] = []
    for _ in range(AI_CONTEXT_LIMIT + 1):
        statuses.append(client.get(f"/api/game/{game_id}/ai-context/").status_code)
    assert statuses[0] == 200
    assert statuses[AI_CONTEXT_LIMIT - 1] == 200
    assert statuses[AI_CONTEXT_LIMIT] == 429


@pytest.mark.django_db
def test_ai_context_normal_play_headroom_is_not_throttled() -> None:
    client = _auth_client("ai_ctx_headroom")
    game_id = _create_vs_ai_game(client)
    statuses = [
        client.get(f"/api/game/{game_id}/ai-context/").status_code
        for _ in range(NORMAL_PLAY_AI_CONTEXT_READS)
    ]
    assert statuses == [200] * NORMAL_PLAY_AI_CONTEXT_READS
    assert 429 not in statuses


@pytest.mark.django_db
def test_login_demo_session_headroom_is_not_throttled() -> None:
    client = APIClient()
    statuses: list[int] = []
    for index in range(DEMO_LOGIN_ATTEMPTS):
        username = f"login_demo_{index}"
        User.objects.create_user(username=username, password=STRONG_PASSWORD)
        statuses.append(
            client.post(
                "/api/auth/login/",
                {"username": username, "password": "wrong-password"},
            ).status_code
        )
    assert statuses == [401] * DEMO_LOGIN_ATTEMPTS
    assert 429 not in statuses


@pytest.mark.django_db
def test_register_demo_session_headroom_is_not_throttled() -> None:
    client = APIClient()
    statuses = [
        client.post(
            "/api/auth/register/",
            {
                "username": f"reg_demo_{index}",
                "email": f"reg_demo_{index}@example.com",
                "password": STRONG_PASSWORD,
            },
        ).status_code
        for index in range(DEMO_REGISTER_ATTEMPTS)
    ]
    assert statuses == [201] * DEMO_REGISTER_ATTEMPTS
    assert 429 not in statuses


@pytest.mark.django_db
def test_throttle_state_does_not_leak_across_users() -> None:
    client_a = _auth_client("throttle_user_a")
    client_b = _auth_client("throttle_user_b")
    for _ in range(ME_LIMIT + 1):
        client_a.get("/api/auth/me/")
    exhausted = client_a.get("/api/auth/me/")
    other = client_b.get("/api/auth/me/")
    assert exhausted.status_code == 429
    assert other.status_code == 200


@pytest.mark.django_db
def test_register_rejects_six_character_password() -> None:
    response = APIClient().post(
        "/api/auth/register/",
        {
            "username": "shortpw",
            "email": "shortpw@example.com",
            "password": "Ab1!xy",
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_register_rejects_common_password() -> None:
    response = APIClient().post(
        "/api/auth/register/",
        {
            "username": "commonpw",
            "email": "commonpw@example.com",
            "password": "password123456",
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_register_rejects_password_similar_to_username() -> None:
    response = APIClient().post(
        "/api/auth/register/",
        {
            "username": "aliceplayer",
            "email": "aliceplayer@example.com",
            "password": "aliceplayer",
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_register_rejects_numeric_password() -> None:
    response = APIClient().post(
        "/api/auth/register/",
        {
            "username": "numericpw",
            "email": "numericpw@example.com",
            "password": "12345678901234",
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_register_accepts_strong_password() -> None:
    response = APIClient().post(
        "/api/auth/register/",
        {
            "username": "strongpw",
            "email": "strongpw@example.com",
            "password": STRONG_PASSWORD,
        },
    )
    assert response.status_code == 201
