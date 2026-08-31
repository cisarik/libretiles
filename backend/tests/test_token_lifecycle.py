"""Regression tests for JWT logout, rotation, and password-change revocation.

Never print a token value. Throttle counters live in LocMemCache; clear them
so this module does not depend on collection order.
"""

from __future__ import annotations

from collections.abc import Iterator
import time

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import resolve
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.models import User

_PASSWORD = "testpass123"
_NEW_PASSWORD = "newpass1234"


@pytest.fixture(autouse=True)
def _reset_throttle_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


def _advance_past_current_jwt_iat_second() -> None:
    """JWT iat is an integer Unix second; wait until the next one."""
    remainder = 1.0 - (time.time() % 1.0)
    time.sleep(remainder + 0.05)


def _register_and_login(username: str) -> tuple[APIClient, str, str]:
    User.objects.create_user(username=username, password=_PASSWORD)
    client = APIClient()
    response = client.post(
        "/api/auth/login/",
        {"username": username, "password": _PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    access = body["access"]
    refresh = body["refresh"]
    assert isinstance(access, str)
    assert isinstance(refresh, str)
    return client, access, refresh


@pytest.mark.django_db
def test_access_token_issued_before_password_change_is_rejected() -> None:
    client, access, _refresh = _register_and_login("jwt_lc_pre_access")
    _advance_past_current_jwt_iat_second()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    changed = client.post(
        "/api/auth/change-password/",
        {"current_password": _PASSWORD, "new_password": _NEW_PASSWORD},
        format="json",
    )
    assert changed.status_code == 200
    me = client.get("/api/auth/me/")
    assert me.status_code == 401


@pytest.mark.django_db
def test_refresh_token_issued_before_password_change_is_rejected() -> None:
    client, access, refresh = _register_and_login("jwt_lc_pre_refresh")
    _advance_past_current_jwt_iat_second()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    changed = client.post(
        "/api/auth/change-password/",
        {"current_password": _PASSWORD, "new_password": _NEW_PASSWORD},
        format="json",
    )
    assert changed.status_code == 200
    client.credentials()
    refreshed = client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert refreshed.status_code in {400, 401}


@pytest.mark.django_db
def test_logout_blacklists_refresh_token() -> None:
    client, access, refresh = _register_and_login("jwt_lc_logout")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    logged_out = client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
    assert logged_out.status_code == 200
    client.credentials()
    refreshed = client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert refreshed.status_code in {400, 401}


@pytest.mark.django_db
def test_logout_twice_returns_clean_4xx() -> None:
    client, access, refresh = _register_and_login("jwt_lc_logout_twice")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    first = client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
    assert first.status_code == 200
    second = client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
    assert 400 <= second.status_code < 500
    body = second.content.decode()
    assert "Traceback" not in body


@pytest.mark.django_db
def test_logout_malformed_refresh_returns_clean_4xx() -> None:
    client, access, _refresh = _register_and_login("jwt_lc_logout_malformed")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = client.post(
        "/api/auth/logout/",
        {"refresh": "not-a-jwt"},
        format="json",
    )
    assert response.status_code in {400, 401}
    assert "Traceback" not in response.content.decode()


@pytest.mark.django_db
def test_logout_unauthenticated_returns_401() -> None:
    response = APIClient().post(
        "/api/auth/logout/",
        {"refresh": "not-a-jwt"},
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_refresh_rotates_and_rejects_old_refresh_token() -> None:
    _client, _access, refresh = _register_and_login("jwt_lc_rotate")
    rotated = APIClient().post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert rotated.status_code == 200
    body = rotated.json()
    new_refresh = body.get("refresh")
    assert isinstance(new_refresh, str)
    rotated_distinct = new_refresh != refresh
    assert rotated_distinct
    old = APIClient().post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert old.status_code in {400, 401}
    new = APIClient().post("/api/auth/refresh/", {"refresh": new_refresh}, format="json")
    assert new.status_code == 200


@pytest.mark.django_db
def test_user_who_never_changed_password_authenticates_normally() -> None:
    client, access, _refresh = _register_and_login("jwt_lc_never_changed")
    user = User.objects.get(username="jwt_lc_never_changed")
    assert user.password_changed_at is None
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["username"] == "jwt_lc_never_changed"


@pytest.mark.django_db
def test_token_issued_after_password_change_works() -> None:
    client, access, _refresh = _register_and_login("jwt_lc_post_change")
    _advance_past_current_jwt_iat_second()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    changed = client.post(
        "/api/auth/change-password/",
        {"current_password": _PASSWORD, "new_password": _NEW_PASSWORD},
        format="json",
    )
    assert changed.status_code == 200
    login = APIClient().post(
        "/api/auth/login/",
        {"username": "jwt_lc_post_change", "password": _NEW_PASSWORD},
    )
    assert login.status_code == 200
    new_access = login.json()["access"]
    fresh = APIClient()
    fresh.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
    me = fresh.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["username"] == "jwt_lc_post_change"


@pytest.mark.django_db
def test_current_access_token_reaches_game_history() -> None:
    client, access, _refresh = _register_and_login("jwt_lc_history")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    history = client.get("/api/game/history/")
    assert history.status_code == 200


@pytest.mark.django_db
def test_django_admin_session_login_still_works() -> None:
    User.objects.create_superuser(
        username="jwt_lc_admin",
        email="jwt_lc_admin@example.com",
        password=_PASSWORD,
    )
    browser = Client()
    login_page = browser.get("/admin/login/")
    assert login_page.status_code == 200
    response = browser.post(
        "/admin/login/",
        {
            "username": "jwt_lc_admin",
            "password": _PASSWORD,
            "next": "/admin/",
        },
    )
    assert response.status_code == 302
    location = response.headers.get("Location", "")
    assert location.endswith("/admin/") or location.endswith("/admin")
    admin_home = browser.get("/admin/")
    assert admin_home.status_code == 200
    assert b"jwt_lc_admin" in admin_home.content


@pytest.mark.django_db
def test_login_and_refresh_views_are_scoped_subclasses() -> None:
    login_cls = resolve("/api/auth/login/").func.view_class
    refresh_cls = resolve("/api/auth/refresh/").func.view_class
    assert login_cls.throttle_scope == "auth_login"
    assert refresh_cls.throttle_scope == "auth_refresh"
    assert login_cls is not TokenObtainPairView
    assert refresh_cls is not TokenRefreshView
    assert issubclass(login_cls, TokenObtainPairView)
    assert issubclass(refresh_cls, TokenRefreshView)
    assert getattr(TokenObtainPairView, "throttle_scope", None) is None
    assert getattr(TokenRefreshView, "throttle_scope", None) is None


@pytest.mark.django_db
def test_access_token_without_iat_is_rejected() -> None:
    user = User.objects.create_user(username="jwt_lc_no_iat", password=_PASSWORD)
    token = AccessToken.for_user(user)
    del token.payload["iat"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token)}")
    me = client.get("/api/auth/me/")
    assert me.status_code == 401
