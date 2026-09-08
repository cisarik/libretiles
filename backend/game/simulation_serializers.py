from __future__ import annotations

from typing import Any

from rest_framework import serializers

from catalog.selection import get_selectable_models, get_selectable_prompts
from gamecore.variant_store import list_installed_variants

from .serializers import ApplyAIMoveSerializer, ExchangeSerializer


class StrictSerializer(serializers.Serializer[dict[str, Any]]):
    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")
        unknown = sorted(set(data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({key: "Unknown field." for key in unknown})
        return super().to_internal_value(data)  # type: ignore[no-any-return]


class SimulationSlotSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=["cpu", "llm"])
    provider = serializers.CharField(max_length=50, required=False)
    model_id = serializers.CharField(max_length=200, required=False)
    prompt_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind = attrs["kind"]
        if kind == "cpu":
            extra = set(attrs) - {"kind"}
            if extra:
                raise serializers.ValidationError({key: "Forbidden for CPU." for key in extra})
            return {"kind": "cpu"}
        if "provider" not in attrs or "model_id" not in attrs:
            raise serializers.ValidationError("LLM slots require provider and model_id.")
        model = next(
            (
                item
                for item in get_selectable_models()
                if item.provider == attrs["provider"] and item.model_id == attrs["model_id"]
            ),
            None,
        )
        if model is None:
            raise serializers.ValidationError("Unknown or unavailable model pair.")
        prompt_id = attrs.get("prompt_id")
        if prompt_id is not None and not any(
            item.id == prompt_id for item in get_selectable_prompts()
        ):
            raise serializers.ValidationError("Unknown or unavailable prompt preset.")
        return attrs


class SimulationCreateSerializer(StrictSerializer):
    slot0 = SimulationSlotSerializer()
    slot1 = SimulationSlotSerializer()
    variant_slug = serializers.CharField(max_length=50)
    seed = serializers.IntegerField(min_value=0, max_value=2_147_483_647, required=False)
    ai_timeout = serializers.IntegerField(min_value=1, max_value=600, default=120)
    ai_max_steps = serializers.IntegerField(min_value=5, max_value=100, default=50)
    judge_mode = serializers.ChoiceField(choices=["dictionary", "ai"], default="dictionary")
    judge_model_id = serializers.CharField(max_length=200, required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["judge_mode"] == "ai":
            model_id = attrs.get("judge_model_id")
            if not model_id or not any(item.model_id == model_id for item in get_selectable_models()):
                raise serializers.ValidationError({"judge_model_id": "Select an available AI judge model."})
        else:
            attrs["judge_model_id"] = None
        return attrs

    def validate_variant_slug(self, value: str) -> str:
        playable = {item.slug for item in list_installed_variants()}
        if value not in playable:
            raise serializers.ValidationError("Unknown or unavailable variant.")
        return value


class SimulationStepSerializer(StrictSerializer):
    expected_move_count = serializers.IntegerField(min_value=0)


class SimulationStopSerializer(StrictSerializer):
    pass


class SimulationActionSerializer(StrictSerializer):
    operation = serializers.ChoiceField(
        choices=["context", "candidates", "playability", "validate", "place", "exchange", "pass", "release"]
    )
    lease_id = serializers.UUIDField()
    expected_move_count = serializers.IntegerField(min_value=0)
    placements = serializers.ListField(child=serializers.DictField(), required=False)
    letters = serializers.ListField(child=serializers.CharField(), required=False)
    ai_metadata = serializers.DictField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        operation = attrs["operation"]
        allowed = {"operation", "lease_id", "expected_move_count"}
        if operation in {"validate", "place"}:
            allowed.add("placements")
        if operation == "exchange":
            allowed.add("letters")
        if operation in {"place", "exchange", "pass"}:
            allowed.add("ai_metadata")
        unexpected = sorted(set(attrs) - allowed)
        if unexpected:
            raise serializers.ValidationError(
                {key: f"Forbidden for operation {operation}." for key in unexpected}
            )
        if operation in {"validate", "place"}:
            move_serializer = ApplyAIMoveSerializer(
                data={
                    "placements": attrs.get("placements", []),
                    **({"ai_metadata": attrs.get("ai_metadata")} if operation == "place" else {}),
                }
            )
            move_serializer.is_valid(raise_exception=True)
            attrs["placements"] = move_serializer.validated_data["placements"]
            if operation == "place":
                attrs["ai_metadata"] = move_serializer.validated_data.get("ai_metadata")
        elif operation == "exchange":
            exchange_serializer = ExchangeSerializer(
                data={"letters": attrs.get("letters", []), "ai_metadata": attrs.get("ai_metadata")}
            )
            exchange_serializer.is_valid(raise_exception=True)
            attrs.update(exchange_serializer.validated_data)
        return attrs
