from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Extended user with a preferred AI model."""

    preferred_ai_model_id = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Native model id for the preferred free rival, "
            "e.g. 'google/gemma-4-31b-it:free' or 'nvidia/nemotron-3-super-120b-a12b'"
        ),
    )
    password_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Set when an existing password is changed. Access and refresh tokens "
            "whose iat is strictly before this timestamp's Unix second are rejected."
        ),
    )

    class Meta:
        db_table = "accounts_user"

    def set_password(self, raw_password: str | None) -> None:
        changing_existing = self.pk is not None and self.has_usable_password()
        super().set_password(raw_password)
        if changing_existing:
            self.password_changed_at = timezone.now()

    def blacklist_outstanding_refresh_tokens(self) -> None:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        for outstanding in OutstandingToken.objects.filter(user_id=self.pk):
            BlacklistedToken.objects.get_or_create(token=outstanding)

    def __str__(self) -> str:
        return self.username
