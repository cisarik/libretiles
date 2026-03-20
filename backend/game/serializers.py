from rest_framework import serializers


class CreateGameSerializer(serializers.Serializer):
    game_mode = serializers.ChoiceField(choices=["vs_ai", "vs_human"], default="vs_ai")
    ai_model_id = serializers.IntegerField(required=False, allow_null=True)
    variant_slug = serializers.CharField(default="english", max_length=50)


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
