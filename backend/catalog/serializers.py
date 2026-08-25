from rest_framework import serializers

from .models import AIModel, AIPrompt


class AIModelSerializer(serializers.ModelSerializer):
    is_flagship = serializers.SerializerMethodField()
    recommended = serializers.SerializerMethodField()

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
            "released_at",
            "is_flagship",
            "recommended",
        )

    def get_is_flagship(self, obj: AIModel) -> bool:
        return obj.pk == self.context.get("flagship_pk")

    def get_recommended(self, obj: AIModel) -> bool:
        return self.get_is_flagship(obj)


class AIPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIPrompt
        fields = (
            "id",
            "name",
            "prompt",
            "fitness",
        )
