from django.db import models


class AIModel(models.Model):
    """AI model available for gameplay, configured by admin."""

    PROVIDER_CHOICES = [
        ("openai", "OpenAI"),
        ("google", "Google Gemini"),
        ("anthropic", "Anthropic"),
        ("openrouter", "OpenRouter"),
        ("novita", "Novita AI"),
    ]
    QUALITY_CHOICES = [
        ("basic", "Basic"),
        ("standard", "Standard"),
        ("premium", "Premium"),
        ("elite", "Elite"),
    ]

    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    model_id = models.CharField(
        max_length=200,
        unique=True,
        help_text="Gateway model identifier, e.g. 'openai/gpt-5-mini'",
    )
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    quality_tier = models.CharField(max_length=20, choices=QUALITY_CHOICES, default="standard")
    cost_per_game = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Credits charged per game against this model",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "display_name"]
        db_table = "catalog_ai_model"

    def __str__(self) -> str:
        return f"{self.display_name} ({self.provider})"
