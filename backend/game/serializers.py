from rest_framework import serializers

from catalog.selection import get_selectable_models


class CreateGameSerializer(serializers.Serializer):
    game_mode = serializers.ChoiceField(choices=["vs_ai"], default="vs_ai")
    ai_model_id = serializers.IntegerField(required=False, allow_null=True)
    ai_model_model_id = serializers.CharField(required=False, allow_blank=False, max_length=200)
    variant_slug = serializers.CharField(default="english", max_length=50)

    def validate(self, attrs: dict) -> dict:
        if attrs.get("game_mode") != "vs_ai":
            return attrs

        selectable_models = get_selectable_models()
        selectable_db_ids = {model.id for model in selectable_models}
        selectable_model_ids = {model.model_id for model in selectable_models}

        ai_model_id = attrs.get("ai_model_id")
        if ai_model_id is not None and ai_model_id not in selectable_db_ids:
            raise serializers.ValidationError({"ai_model_id": "Unknown or unavailable AI model."})

        ai_model_model_id = attrs.get("ai_model_model_id")
        if ai_model_model_id and ai_model_model_id not in selectable_model_ids:
            raise serializers.ValidationError(
                {"ai_model_model_id": "Unknown or unavailable AI model."}
            )

        return attrs


class QueueJoinSerializer(serializers.Serializer):
    variant_slug = serializers.CharField(default="english", max_length=50)


class QueueCancelSerializer(serializers.Serializer):
    game_id = serializers.CharField(required=True, max_length=100)


class SubmitMoveSerializer(serializers.Serializer):
    placements = serializers.ListField(
        child=serializers.DictField(), min_length=1, max_length=7
    )


class ExchangeSerializer(serializers.Serializer):
    letters = serializers.ListField(
        child=serializers.CharField(max_length=1), min_length=1, max_length=7
    )


class ValidateMoveSerializer(serializers.Serializer):
    placements = serializers.ListField(child=serializers.DictField(), min_length=1)


class ValidateWordsSerializer(serializers.Serializer):
    words = serializers.ListField(child=serializers.CharField(max_length=50), min_length=1)


class ApplyAIMoveSerializer(serializers.Serializer):
    placements = serializers.ListField(child=serializers.DictField())
    ai_metadata = serializers.DictField(required=False, allow_null=True)


class UpdateGameAIModelSerializer(serializers.Serializer):
    ai_model_model_id = serializers.CharField(required=True, allow_blank=False, max_length=200)

    def validate_ai_model_model_id(self, value: str) -> str:
        selectable_model_ids = {model.model_id for model in get_selectable_models()}
        if value not in selectable_model_ids:
            raise serializers.ValidationError("Unknown or unavailable AI model.")
        return value
