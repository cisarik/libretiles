from rest_framework import serializers

from .selection import DEFAULT_FREE_MODEL_ID
from .models import AIModel, AIPrompt


class AIModelSerializer(serializers.ModelSerializer):
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
            "context_window",
            "max_tokens",
            "is_flagship",
        )

    def get_is_flagship(self, obj: AIModel) -> bool:
        return obj.model_id == DEFAULT_FREE_MODEL_ID


class AIPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIPrompt
        fields = (
            "id",
            "name",
            "prompt",
            "fitness",
        )
