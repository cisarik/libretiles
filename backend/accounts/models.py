from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user with preferred AI model and credit balance."""

    preferred_ai_model_id = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Gateway model ID the user prefers (e.g. 'openai/gpt-5-mini')",
    )

    class Meta:
        db_table = "accounts_user"

    def __str__(self) -> str:
        return self.username
