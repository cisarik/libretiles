"""Regression tests for per-account login lockout (orch-01-F20) and admin revocation.

Must match backend/config/settings.py axes wiring once configured. Does not
import axes at module level so the file still collects on an unmodified tree.
"""

from __future__ import annotations

from collections.abc import Iterator
import time

import pytest
from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from accounts.models import User

# Must match AXES_FAILURE_LIMIT in backend/config/settings.py after Item A.
FAILURE_LIMIT = 8
LOCKOUT_STATUS = 429
STRONG_PASSWORD = "testpass123"
WRONG_PASSWORD = "wrong-password-not-the-secret"
_NEW_PASSWORD = "newpass1234"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_auth_brakes() -> Iterator[None]:
    cache.clear()
    _clear_axes_records()
    yield
    cache.clear()
    _clear_axes_records()


def _clear_axes_records() -> None:
    if not apps.is_installed("axes"):
        return
    for model_name in ("AccessAttempt", "AccessLog", "AccessFailureLog"):
        try:
            model = apps.get_model("axes", model_name)
        except LookupError:
            continue
        model.objects.all().delete()


def _lockout_status() -> int:
    return int(getattr(settings, "AXES_HTTP_RESPONSE_CODE", LOCKOUT_STATUS))


def _failed_admin_login(client: Client, username: str) -> int:
    return client.post(
        "/admin/login/",
        {
            "username": username,
            "password": WRONG_PASSWORD,
            "next": "/admin/",
        },
    ).status_code


def test_admin_login_locks_out_after_configured_failures() -> None:
    User.objects.create_superuser(
        username="axes_admin_lock",
        email="axes_admin_lock@example.com",
        password=STRONG_PASSWORD,
    )
    client = Client()
    # axes/conf.py AXES_FAILURE_LIMIT compared with >=, so attempt 8 is 429.
    statuses = [
        _failed_admin_login(client, "axes_admin_lock")
        for _ in range(FAILURE_LIMIT - 1)
    ]
    assert statuses == [200] * (FAILURE_LIMIT - 1)
    locked = _failed_admin_login(client, "axes_admin_lock")
    assert locked == _lockout_status()


def test_api_login_locks_out_after_configured_failures() -> None:
    User.objects.create_user(username="axes_api_lock", password=STRONG_PASSWORD)
    client = APIClient()
    statuses = [
        client.post(
            "/api/auth/login/",
            {"username": "axes_api_lock", "password": WRONG_PASSWORD},
            format="json",
        ).status_code
        for _ in range(FAILURE_LIMIT - 1)
    ]
    assert statuses == [401] * (FAILURE_LIMIT - 1)
    locked = client.post(
        "/api/auth/login/",
        {"username": "axes_api_lock", "password": WRONG_PASSWORD},
        format="json",
    )
    assert locked.status_code == _lockout_status()


def test_lockout_is_keyed_on_username_and_ip_not_ip_alone() -> None:
    User.objects.create_user(username="axes_combo_a", password=STRONG_PASSWORD)
    User.objects.create_user(username="axes_combo_b", password=STRONG_PASSWORD)
    client = APIClient()
    for _ in range(FAILURE_LIMIT):
        client.post(
            "/api/auth/login/",
            {"username": "axes_combo_a", "password": WRONG_PASSWORD},
            format="json",
        )
    locked = client.post(
        "/api/auth/login/",
        {"username": "axes_combo_a", "password": WRONG_PASSWORD},
        format="json",
    )
    other_wrong = client.post(
        "/api/auth/login/",
        {"username": "axes_combo_b", "password": WRONG_PASSWORD},
        format="json",
    )
    other_ok = client.post(
        "/api/auth/login/",
        {"username": "axes_combo_b", "password": STRONG_PASSWORD},
        format="json",
    )
    assert locked.status_code == _lockout_status()
    assert other_wrong.status_code == 401
    assert other_ok.status_code == 200


def test_successful_login_resets_failure_counter_for_that_pair() -> None:
    User.objects.create_user(username="axes_reset_pair", password=STRONG_PASSWORD)
    client = APIClient()
    for _ in range(FAILURE_LIMIT - 1):
        response = client.post(
            "/api/auth/login/",
            {"username": "axes_reset_pair", "password": WRONG_PASSWORD},
            format="json",
        )
        assert response.status_code == 401
    success = client.post(
        "/api/auth/login/",
        {"username": "axes_reset_pair", "password": STRONG_PASSWORD},
        format="json",
    )
    assert success.status_code == 200
    for _ in range(FAILURE_LIMIT - 1):
        response = client.post(
            "/api/auth/login/",
            {"username": "axes_reset_pair", "password": WRONG_PASSWORD},
            format="json",
        )
        assert response.status_code == 401
    locked = client.post(
        "/api/auth/login/",
        {"username": "axes_reset_pair", "password": WRONG_PASSWORD},
        format="json",
    )
    assert locked.status_code == _lockout_status()


def test_axes_is_wired_in_required_order() -> None:
    assert "axes" in settings.INSTALLED_APPS
    assert settings.MIDDLEWARE[-2] == "config.middleware.AxesDrfLockoutFlagMiddleware"
    assert settings.MIDDLEWARE[-1] == "axes.middleware.AxesMiddleware"
    backends = list(settings.AUTHENTICATION_BACKENDS)
    assert backends[0] == "axes.backends.AxesStandaloneBackend"
    assert "django.contrib.auth.backends.ModelBackend" in backends
    assert backends.index("django.contrib.auth.backends.ModelBackend") > 0
    assert int(settings.AXES_FAILURE_LIMIT) == FAILURE_LIMIT


def test_axes_failure_models_are_reachable_in_admin() -> None:
    axes_models = [
        model
        for model in admin.site._registry
        if model._meta.app_label == "axes"
    ]
    assert axes_models, "django-axes did not register durable models in admin"
    actor = User.objects.create_superuser(
        username="axes_admin_audit",
        email="axes_admin_audit@example.com",
        password=STRONG_PASSWORD,
    )
    browser = Client()
    browser.force_login(actor)
    for model in axes_models:
        url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
        response = browser.get(url)
        assert response.status_code == 200, url


def test_admin_password_change_blacklists_outstanding_refresh() -> None:
    actor = User.objects.create_superuser(
        username="admin_pw_actor",
        email="admin_pw_actor@example.com",
        password=STRONG_PASSWORD,
    )
    target = User.objects.create_user(
        username="admin_pw_target",
        email="admin_pw_target@example.com",
        password=STRONG_PASSWORD,
    )
    login = APIClient().post(
        "/api/auth/login/",
        {"username": "admin_pw_target", "password": STRONG_PASSWORD},
    )
    assert login.status_code == 200
    refresh = login.json()["refresh"]
    assert isinstance(refresh, str)
    assert OutstandingToken.objects.filter(user=target).exists()

    remainder = 1.0 - (time.time() % 1.0)
    time.sleep(remainder + 0.05)

    browser = Client()
    browser.force_login(actor)
    url = reverse("admin:auth_user_password_change", args=[target.pk])
    page = browser.get(url)
    assert page.status_code == 200
    changed = browser.post(
        url,
        {
            "password1": _NEW_PASSWORD,
            "password2": _NEW_PASSWORD,
            "usable_password": "true",
        },
    )
    assert changed.status_code == 302

    target.refresh_from_db()
    assert target.password_changed_at is not None
    rejected = APIClient().post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert rejected.status_code in {400, 401}
    assert BlacklistedToken.objects.filter(token__user=target).exists()
