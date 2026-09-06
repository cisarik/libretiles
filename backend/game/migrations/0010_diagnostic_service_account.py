"""Seed the reserved account after its durable ownership flag exists."""

from typing import Any

from django.db import migrations


def ensure_diagnostic_service_user_forward(apps: Any, schema_editor: Any) -> None:
    from game.services import ensure_diagnostic_service_user

    ensure_diagnostic_service_user()


def unensure_diagnostic_service_user(apps: Any, schema_editor: Any) -> None:
    """Delete the reserved user only if this migration owns it.

    Ownership is ``not user.has_usable_password()`` — the managed
    unusable-password account. A claimant with a usable password is not
    ours and is left in place.

    Historical migration models do not carry ``User.has_usable_password``;
    ``is_password_usable(user.password)`` is the same predicate.

    Accepted residual: reversing drops ``is_diagnostic`` from surviving
    diagnostic sessions (classification loss on rollback). Rows stored
    with ``is_diagnostic=True`` re-forward as their stored value.
    """
    from django.contrib.auth.hashers import is_password_usable

    from game.services import DIAGNOSTIC_SERVICE_USERNAME

    user_model = apps.get_model("accounts", "User")
    user = user_model.objects.filter(username=DIAGNOSTIC_SERVICE_USERNAME).first()
    if user is None:
        return
    if is_password_usable(user.password):
        return
    user.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_service_account_flag"),
        ("game", "0009_diagnostic_session_foundation"),
    ]

    operations = [
        migrations.RunPython(
            ensure_diagnostic_service_user_forward,
            unensure_diagnostic_service_user,
        ),
    ]
