"""JWT authentication that rejects tokens issued before a password change.

JWT ``iat`` is an integer Unix second (SimpleJWT ``datetime_to_epoch`` /
``timegm``). ``password_changed_at`` has microsecond precision. A token is
rejected only when ``iat`` is strictly less than ``int(password_changed_at.timestamp())``.
That is a documented one-second claim-granularity window: tokens that share the
same Unix second as the password change remain valid so an immediate re-login
is not locked out. No additional leeway is added.

A missing or non-numeric ``iat`` claim fails closed: the token is rejected.
A user with ``password_changed_at is None`` (never changed) authenticates
normally.
"""

from __future__ import annotations

from datetime import datetime

from django.contrib.auth.models import AbstractBaseUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.models import TokenUser
from rest_framework_simplejwt.tokens import Token

# Extra seconds subtracted from password_changed_at. Zero: JWT iat granularity
# already admits same-second tokens. Do not raise this without a new test lock.
PASSWORD_CHANGE_IAT_SKEW_SECONDS = 0


def coerce_iat(raw: object) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    return None


def token_iat_predates_password_change(iat: int, changed_at: datetime) -> bool:
    cutoff = int(changed_at.timestamp()) - PASSWORD_CHANGE_IAT_SKEW_SECONDS
    return iat < cutoff


def reject_if_issued_before_password_change(
    token: Token, user: AbstractBaseUser | TokenUser
) -> None:
    iat = coerce_iat(token.get("iat"))
    if iat is None:
        raise InvalidToken("Token contained no iat claim")
    changed_at = getattr(user, "password_changed_at", None)
    if changed_at is None:
        return
    if not isinstance(changed_at, datetime):
        raise InvalidToken("Token was issued before the password was changed")
    if token_iat_predates_password_change(iat, changed_at):
        raise InvalidToken("Token was issued before the password was changed")


class PasswordAwareJWTAuthentication(JWTAuthentication):
    def get_user(  # type: ignore[override]
        self, validated_token: Token
    ) -> AbstractBaseUser | TokenUser:
        user = super().get_user(validated_token)
        reject_if_issued_before_password_change(validated_token, user)
        return user
