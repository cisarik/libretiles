from django.db import models


class AIModel(models.Model):
    """AI model available for gameplay, configured by admin."""

    QUALITY_CHOICES = [
        ("basic", "Basic"),
        ("standard", "Standard"),
        ("premium", "Premium"),
        ("elite", "Elite"),
    ]

    provider = models.CharField(max_length=50)
    model_id = models.CharField(
        max_length=200,
        unique=True,
        help_text=(
            "Native model id for this provider, "
            "e.g. 'google/gemma-4-31b-it:free' or 'nvidia/nemotron-3-super-120b-a12b'"
        ),
    )
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    quality_tier = models.CharField(max_length=20, choices=QUALITY_CHOICES, default="standard")
    openrouter_managed = models.BooleanField(
        default=False,
        help_text="If enabled, sync updates display name and description from OpenRouter.",
    )
    openrouter_available = models.BooleanField(
        default=True,
        help_text="True when the model exists in the latest OpenRouter free catalog sync.",
    )
    model_type = models.CharField(max_length=20, blank=True, default="language")
    context_window = models.PositiveIntegerField(null=True, blank=True)
    max_tokens = models.PositiveIntegerField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "display_name"]
        db_table = "catalog_ai_model"

    def __str__(self) -> str:
        return f"{self.display_name} ({self.provider})"


class AIPrompt(models.Model):
    """Prompt preset available for AI move generation."""

    name = models.CharField(max_length=100, unique=True)
    prompt = models.TextField()
    fitness = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        db_table = "catalog_ai_prompt"

    def __str__(self) -> str:
        return self.name
