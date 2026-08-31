"""Regression tests for fail-closed Django security defaults.

Probes load ``config.settings`` in an isolated subprocess so dotenv cannot
fill values from a local ``.env`` file. Probe JSON never includes secret
material. Catalog product-protection tests use the live Django test client.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from rest_framework.test import APIClient

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PUBLIC_INSECURE_SECRET_KEY = "insecure-dev-key-change-in-production"
_SYNTHETIC_TEST_SECRET_KEY = (
    "TEST-ONLY-synthetic-django-secret-key-not-for-production-00000"
)
_WEAK_TEST_SECRET_KEY = "tooshort"
_FORBIDDEN_DEPLOY_CHECK_IDS = frozenset(
    {
        "security.W004",
        "security.W008",
        "security.W012",
        "security.W016",
        "security.W018",
    }
)
_KEEP_ENV_NAMES = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "USER",
    "TMPDIR",
    "TMP",
    "TEMP",
)

_PROBE_SOURCE = r"""
import json
import os
import sys

import dotenv

def _disabled_load_dotenv(*args, **kwargs):
    return False

dotenv.load_dotenv = _disabled_load_dotenv

from django.core.exceptions import ImproperlyConfigured

try:
    from config import settings as settings_mod
except ImproperlyConfigured:
    json.dump(
        {"status": "improperly_configured", "error_type": "ImproperlyConfigured"},
        sys.stdout,
    )
    raise SystemExit(0)
except Exception as exc:
    json.dump({"status": "error", "error_type": type(exc).__name__}, sys.stdout)
    raise SystemExit(0)

payload = {
    "status": "ok",
    "debug": bool(settings_mod.DEBUG),
    "allowed_hosts": list(settings_mod.ALLOWED_HOSTS),
    "cors_allow_all_origins": bool(
        getattr(settings_mod, "CORS_ALLOW_ALL_ORIGINS", False)
    ),
    "session_cookie_secure": bool(
        getattr(settings_mod, "SESSION_COOKIE_SECURE", False)
    ),
    "csrf_cookie_secure": bool(getattr(settings_mod, "CSRF_COOKIE_SECURE", False)),
    "secure_ssl_redirect": bool(getattr(settings_mod, "SECURE_SSL_REDIRECT", False)),
    "secure_hsts_seconds": int(getattr(settings_mod, "SECURE_HSTS_SECONDS", 0)),
    "default_permission_classes": list(
        settings_mod.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]
    ),
}

if os.environ.get("LIBRETILES_SECURITY_PROBE_CHECKS") == "1":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    from django.core.checks import run_checks

    issues = run_checks(include_deployment_checks=True)
    payload["check_ids"] = sorted({issue.id for issue in issues})

json.dump(payload, sys.stdout)
"""


def _base_env() -> dict[str, str]:
    env = {name: os.environ[name] for name in _KEEP_ENV_NAMES if name in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_settings_probe(
    *,
    secret: str | None,
    debug: str | None = None,
    allowed_hosts: str | None = None,
    run_checks: bool = False,
) -> dict[str, Any]:
    env = _base_env()
    if secret is None:
        env.pop("DJANGO_SECRET_KEY", None)
    else:
        env["DJANGO_SECRET_KEY"] = secret
    if debug is None:
        env.pop("DJANGO_DEBUG", None)
    else:
        env["DJANGO_DEBUG"] = debug
    if allowed_hosts is None:
        env.pop("DJANGO_ALLOWED_HOSTS", None)
    else:
        env["DJANGO_ALLOWED_HOSTS"] = allowed_hosts
    if run_checks:
        env["LIBRETILES_SECURITY_PROBE_CHECKS"] = "1"

    completed = subprocess.run(
        [sys.executable, "-c", _PROBE_SOURCE],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise AssertionError(
            "settings probe produced no stdout "
            f"(returncode={completed.returncode})"
        )
    try:
        payload: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError("settings probe stdout was not JSON") from exc
    return payload


def test_secret_key_absent_raises() -> None:
    payload = _run_settings_probe(secret=None)
    assert payload["status"] == "improperly_configured"


def test_secret_key_public_fallback_raises() -> None:
    payload = _run_settings_probe(secret=_PUBLIC_INSECURE_SECRET_KEY)
    assert payload["status"] == "improperly_configured"


def test_secret_key_empty_raises() -> None:
    payload = _run_settings_probe(secret="")
    assert payload["status"] == "improperly_configured"


def test_secret_key_whitespace_only_raises() -> None:
    payload = _run_settings_probe(secret=" \t\n")
    assert payload["status"] == "improperly_configured"


def test_secret_key_below_minimum_strength_raises() -> None:
    payload = _run_settings_probe(secret=_WEAK_TEST_SECRET_KEY)
    assert payload["status"] == "improperly_configured"


def test_secret_key_sufficiently_strong_loads() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug="false",
        allowed_hosts="example.test",
    )
    assert payload["status"] == "ok"


def test_debug_absent_defaults_false() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug=None,
        allowed_hosts="example.test",
    )
    assert payload["status"] == "ok"
    assert payload["debug"] is False


def test_debug_false_rejects_absent_allowed_hosts() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug="false",
        allowed_hosts=None,
    )
    if payload["status"] == "ok":
        assert "*" not in payload["allowed_hosts"]
        assert payload["allowed_hosts"] != ["*"]
        pytest.fail("DEBUG=false silently accepted a missing ALLOWED_HOSTS value")
    assert payload["status"] == "improperly_configured"


def test_debug_false_rejects_wildcard_allowed_hosts() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug="false",
        allowed_hosts="*",
    )
    if payload["status"] == "ok":
        assert "*" not in payload["allowed_hosts"]
        pytest.fail("DEBUG=false silently accepted a wildcard ALLOWED_HOSTS value")
    assert payload["status"] == "improperly_configured"


def test_cors_allow_all_origins_unreachable_when_debug_absent() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug=None,
        allowed_hosts="example.test",
    )
    assert payload["status"] == "ok"
    assert payload["debug"] is False
    assert payload["cors_allow_all_origins"] is False


def test_cors_allow_all_origins_false_when_debug_false() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug="false",
        allowed_hosts="example.test",
    )
    assert payload["status"] == "ok"
    assert payload["cors_allow_all_origins"] is False


def test_production_like_environment_enables_https_security_flags() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug="false",
        allowed_hosts="example.test",
    )
    assert payload["status"] == "ok"
    assert payload["session_cookie_secure"] is True
    assert payload["csrf_cookie_secure"] is True
    assert payload["secure_ssl_redirect"] is True
    assert payload["secure_hsts_seconds"] > 0


def test_production_like_deploy_check_omits_named_warnings() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug="false",
        allowed_hosts="example.test",
        run_checks=True,
    )
    assert payload["status"] == "ok"
    check_ids = set(payload["check_ids"])
    leaked = sorted(check_ids & _FORBIDDEN_DEPLOY_CHECK_IDS)
    assert leaked == []


def test_debug_true_keeps_plain_http_workable() -> None:
    payload = _run_settings_probe(
        secret=_SYNTHETIC_TEST_SECRET_KEY,
        debug="true",
        allowed_hosts="localhost",
    )
    assert payload["status"] == "ok"
    assert payload["debug"] is True
    assert payload["session_cookie_secure"] is False
    assert payload["csrf_cookie_secure"] is False
    assert payload["secure_ssl_redirect"] is False
    assert payload["secure_hsts_seconds"] == 0


def test_drf_default_permission_classes_are_fail_closed() -> None:
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated",
    ]


def test_auth_password_validators_include_django_defaults() -> None:
    names = {item["NAME"] for item in settings.AUTH_PASSWORD_VALIDATORS}
    assert names >= {
        "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "django.contrib.auth.password_validation.MinimumLengthValidator",
        "django.contrib.auth.password_validation.CommonPasswordValidator",
        "django.contrib.auth.password_validation.NumericPasswordValidator",
    }


@pytest.mark.django_db
def test_catalog_models_unauthenticated_get_returns_200() -> None:
    response = APIClient().get("/api/catalog/models/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_catalog_prompts_unauthenticated_get_returns_200() -> None:
    response = APIClient().get("/api/catalog/prompts/")
    assert response.status_code == 200
