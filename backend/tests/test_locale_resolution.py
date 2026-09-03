"""LocaleMiddleware + Accept-Language resolve Django/DRF framework messages.

R7: USE_I18N and LocaleMiddleware are inert unless the client sends
Accept-Language. These tests go through the real middleware stack.
"""

from __future__ import annotations

import json

import pytest
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import translation
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.test import APIClient

_NUMERIC_PASSWORD = "12345678901234"
_SK_NUMERIC = "Toto heslo pozostáva iba z číslic."
_EN_NUMERIC = "This password is entirely numeric."
_CS_NUMERIC = "Heslo se skládá pouze z čísel."
_PL_NUMERIC = "Hasło składa się wyłącznie z cyfr."

_SESSION = "django.contrib.sessions.middleware.SessionMiddleware"
_LOCALE = "django.middleware.locale.LocaleMiddleware"
_COMMON = "django.middleware.common.CommonMiddleware"
_AXES_FLAG = "config.middleware.AxesDrfLockoutFlagMiddleware"
_AXES = "axes.middleware.AxesMiddleware"


def _register_numeric(*, username: str, accept_language: str | None) -> Response:
    extra: dict[str, str] = {}
    if accept_language is not None:
        extra["HTTP_ACCEPT_LANGUAGE"] = accept_language
    return APIClient().post(
        "/api/auth/register/",
        {
            "username": username,
            "email": f"{username}@example.com",
            "password": _NUMERIC_PASSWORD,
        },
        format="json",
        **extra,
    )


def _body_text(response: Response) -> str:
    return json.dumps(response.json(), ensure_ascii=False)


@pytest.mark.django_db
def test_accept_language_sk_differs_from_en_on_password_validators() -> None:
    en_resp = _register_numeric(username="locres_en", accept_language="en")
    sk_resp = _register_numeric(username="locres_sk", accept_language="sk")
    cs_resp = _register_numeric(username="locres_cs", accept_language="cs")
    pl_resp = _register_numeric(username="locres_pl", accept_language="pl")
    assert en_resp.status_code == 400
    assert sk_resp.status_code == 400
    assert cs_resp.status_code == 400
    assert pl_resp.status_code == 400
    en_body = _body_text(en_resp)
    sk_body = _body_text(sk_resp)
    cs_body = _body_text(cs_resp)
    pl_body = _body_text(pl_resp)
    assert sk_body != en_body
    assert _EN_NUMERIC in en_body
    assert _SK_NUMERIC in sk_body
    assert _CS_NUMERIC in cs_body
    assert _PL_NUMERIC in pl_body


@pytest.mark.django_db
def test_missing_accept_language_falls_back_to_english() -> None:
    response = _register_numeric(username="locres_fallback", accept_language=None)
    assert response.status_code == 400
    body = _body_text(response)
    assert _EN_NUMERIC in body
    assert _SK_NUMERIC not in body


def test_locale_middleware_order() -> None:
    mw = list(settings.MIDDLEWARE)
    session_at = mw.index(_SESSION)
    locale_at = mw.index(_LOCALE)
    common_at = mw.index(_COMMON)
    assert session_at < locale_at < common_at
    assert locale_at == session_at + 1
    assert common_at == locale_at + 1
    assert mw[-2] == _AXES_FLAG
    assert mw[-1] == _AXES


def test_czech_minimum_length_validator_catalog_mismatch() -> None:
    """Residual 4.5: cs still carries the old %(min_length)d msgid."""

    def messages(lang: str) -> list[str]:
        with translation.override(lang):
            try:
                validate_password("Ab1!xy")
            except ValidationError as exc:
                return list(exc.messages)
            return []

    sk = messages("sk")
    cs = messages("cs")
    assert any("príliš krátke" in msg for msg in sk)
    assert any("This password is too short" in msg for msg in cs)


def test_drf_throttle_wait_suffix_stays_english() -> None:
    for lang in ("en", "sk", "cs", "pl"):
        with translation.override(lang):
            detail = str(Throttled(wait=3300).detail)
            assert "3300" in detail
            assert "seconds" in detail
