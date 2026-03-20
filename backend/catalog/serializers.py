from rest_framework import serializers

from .models import AIModel


class AIModelSerializer(serializers.ModelSerializer):
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
        )
