from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user with preferred AI model and credit balance."""

    preferred_ai_model_id = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Native model id for the preferred free rival, "
            "e.g. 'google/gemma-4-31b-it:free' or 'nvidia/nemotron-3-super-120b-a12b'"
        ),
    )

    class Meta:
        db_table = "accounts_user"

    def __str__(self) -> str:
        return self.username
