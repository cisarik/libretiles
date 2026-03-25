from decimal import Decimal

from rest_framework import serializers

from .selection import (
    PINNED_MODEL_ID,
    get_cache_read_cost_per_token,
    get_cache_write_cost_per_token,
    get_combined_cost_per_million,
    get_input_cost_per_token,
    get_output_cost_per_token,
)
from .models import AIModel, AIPrompt

_DISPLAY_PRECISION = Decimal("0.01")
_MILLION = Decimal("1000000")


class AIModelSerializer(serializers.ModelSerializer):
    pricing = serializers.JSONField(read_only=True)
    input_cost_per_million = serializers.SerializerMethodField()
    output_cost_per_million = serializers.SerializerMethodField()
    cache_read_cost_per_million = serializers.SerializerMethodField()
    cache_write_cost_per_million = serializers.SerializerMethodField()
    combined_cost_per_million = serializers.SerializerMethodField()
    is_flagship = serializers.SerializerMethodField()

    class Meta:
        model = AIModel
        fields = (
            "id",
            "provider",
            "model_id",
            "display_name",
            "description",
            "quality_tier",
            "cost_per_game",
            "pricing",
            "context_window",
            "max_tokens",
            "input_cost_per_million",
            "output_cost_per_million",
            "cache_read_cost_per_million",
            "cache_write_cost_per_million",
            "combined_cost_per_million",
            "is_flagship",
        )

    def get_input_cost_per_million(self, obj: AIModel) -> str:
        return self._format_cost(get_input_cost_per_token(obj))

    def get_output_cost_per_million(self, obj: AIModel) -> str:
        return self._format_cost(get_output_cost_per_token(obj))

    def get_cache_read_cost_per_million(self, obj: AIModel) -> str:
        return self._format_cost(get_cache_read_cost_per_token(obj))

    def get_cache_write_cost_per_million(self, obj: AIModel) -> str:
        return self._format_cost(get_cache_write_cost_per_token(obj))

    def get_combined_cost_per_million(self, obj: AIModel) -> str:
        return format(get_combined_cost_per_million(obj).quantize(_DISPLAY_PRECISION), "f")

    def get_is_flagship(self, obj: AIModel) -> bool:
        return obj.model_id == PINNED_MODEL_ID

    def _format_cost(self, value: Decimal) -> str:
        return format((value * _MILLION).quantize(_DISPLAY_PRECISION), "f")


class AIPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIPrompt
        fields = (
            "id",
            "name",
            "prompt",
            "fitness",
        )
