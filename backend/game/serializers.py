import unicodedata
from typing import Any

from rest_framework import serializers

from catalog.selection import (
    get_selectable_models,
    get_selectable_prompts,
    is_selectable_model,
)
from gamecore.variant_store import list_installed_variants

COMPLETION_SOURCES = frozenset(
    {
        "provider_candidate",
        "backend_ranked_candidate",
        "repair_candidate",
        "backend_witness_rescue",
        "genuine_no_move_exchange",
        "genuine_no_move_pass",
    }
)
ALLOWED_AI_METADATA_KEYS = frozenset(
    {
        "prompt_id",
        "prompt_name",
        "prompt_version",
        "requested_provider",
        "requested_model_id",
        "runtime_provider",
        "runtime_model_id",
        "attempts",
        "valid_candidate_count",
        "rejected_candidate_count",
        "terminal_cause",
        "probe_status",
        "repair_attempted",
        "completion_source",
        "attempt_provider_requests",
        "turn_provider_requests",
        "provider_requests_used",
        "usage",
    }
)
FORBIDDEN_AI_METADATA_KEYS = frozenset(
    {
        "response_headers",
        "headers",
        "provider_metadata",
        "raw",
        "raw_output",
        "model_output",
        "tool_arguments",
        "tool_args",
        "prompt",
        "prompt_text",
        "rack",
        "board",
        "credentials",
        "token",
        "tokens",
        "authorization",
        "api_key",
        "cookie",
        "cookies",
    }
)
_IDENT_MAX = 200
_USAGE_KEYS = ("inputTokens", "outputTokens", "totalTokens")


def _bounded_ident(value: object) -> str | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and 0 < len(value) <= _IDENT_MAX:
        return value
    return None


def _bounded_text(value: object, *, max_len: int = 80) -> str | None:
    if isinstance(value, str) and 0 < len(value) <= max_len:
        return value
    return None


def _bounded_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _sanitize_usage(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, int] = {}
    for key in _USAGE_KEYS:
        parsed = _bounded_int(value.get(key))
        if parsed is not None:
            out[key] = parsed
    return out or None


def _sanitize_attempts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, object]] = []
    for item in value[:3]:
        if not isinstance(item, dict):
            continue
        record: dict[str, object] = {}
        outcome = _bounded_text(item.get("outcome_code"))
        if outcome is not None:
            record["outcome_code"] = outcome
        count = _bounded_int(item.get("request_count"))
        if count is not None:
            record["request_count"] = count
        if record:
            records.append(record)
    return records


def sanitize_ai_metadata(value: object) -> dict[str, Any]:
    """Keep allowlisted diagnostic keys; drop unknown and forbidden keys."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key, raw in value.items():
        if key in FORBIDDEN_AI_METADATA_KEYS or key not in ALLOWED_AI_METADATA_KEYS:
            continue
        if key in {
            "prompt_id",
            "prompt_name",
            "prompt_version",
            "requested_provider",
            "requested_model_id",
            "runtime_provider",
            "runtime_model_id",
        }:
            parsed = _bounded_ident(raw)
            if parsed is not None:
                out[key] = parsed
        elif key in {"valid_candidate_count", "rejected_candidate_count",
                     "attempt_provider_requests", "turn_provider_requests",
                     "provider_requests_used"}:
            parsed_int = _bounded_int(raw)
            if parsed_int is not None:
                out[key] = parsed_int
        elif key in {"terminal_cause", "probe_status"}:
            parsed_text = _bounded_text(raw)
            if parsed_text is not None:
                out[key] = parsed_text
        elif key == "repair_attempted":
            if isinstance(raw, bool):
                out[key] = raw
        elif key == "completion_source":
            if isinstance(raw, str) and raw in COMPLETION_SOURCES:
                out[key] = raw
        elif key == "attempts":
            attempts = _sanitize_attempts(raw)
            if attempts:
                out[key] = attempts
        elif key == "usage":
            usage = _sanitize_usage(raw)
            if usage is not None:
                out[key] = usage
    return out


class CreateGameSerializer(serializers.Serializer[dict[str, Any]]):
    game_mode = serializers.ChoiceField(choices=["vs_ai"], default="vs_ai")
    ai_model_id = serializers.IntegerField(required=False, allow_null=True)
    ai_model_model_id = serializers.CharField(required=False, allow_blank=False, max_length=200)
    ai_prompt_id = serializers.IntegerField(required=False, allow_null=True)
    variant_slug = serializers.CharField(default="english", max_length=50)

    def validate_variant_slug(self, value: str) -> str:
        slug = value.strip()
        installed = {variant.slug for variant in list_installed_variants()}
        if slug not in installed:
            raise serializers.ValidationError("unknown_variant")
        return slug

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("game_mode") != "vs_ai":
            return attrs

        selectable_models = get_selectable_models()
        selectable_db_ids = {model.id for model in selectable_models}
        selectable_prompt_ids = {prompt.id for prompt in get_selectable_prompts()}

        ai_model_id = attrs.get("ai_model_id")
        if ai_model_id is not None and ai_model_id not in selectable_db_ids:
            raise serializers.ValidationError({"ai_model_id": "Unknown or unavailable AI model."})

        ai_model_model_id = attrs.get("ai_model_model_id")
        if ai_model_model_id and not is_selectable_model(ai_model_model_id):
            raise serializers.ValidationError(
                {"ai_model_model_id": "Unknown or unavailable AI model."}
            )

        ai_prompt_id = attrs.get("ai_prompt_id")
        if ai_prompt_id is not None and ai_prompt_id not in selectable_prompt_ids:
            raise serializers.ValidationError({"ai_prompt_id": "Unknown or unavailable AI prompt."})

        return attrs


class QueueJoinSerializer(serializers.Serializer[dict[str, Any]]):
    variant_slug = serializers.CharField(default="english", max_length=50)

    def validate_variant_slug(self, value: str) -> str:
        slug = value.strip()
        installed = {variant.slug for variant in list_installed_variants()}
        if slug not in installed:
            raise serializers.ValidationError("unknown_variant")
        return slug


class QueueCancelSerializer(serializers.Serializer[dict[str, Any]]):
    game_id = serializers.CharField(required=True, max_length=100)


class GameHistoryQuerySerializer(serializers.Serializer[dict[str, Any]]):
    game_mode = serializers.ChoiceField(
        choices=["all", "vs_ai", "vs_human"],
        required=False,
        default="all",
    )
    sort = serializers.ChoiceField(
        choices=["updated"],
        required=False,
        default="updated",
    )
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=25, default=8)


class SubmitMoveSerializer(serializers.Serializer[dict[str, Any]]):
    placements = serializers.ListField(
        child=serializers.DictField(), min_length=1, max_length=7
    )


class ExchangeSerializer(serializers.Serializer[dict[str, Any]]):
    letters = serializers.ListField(
        child=serializers.CharField(max_length=1), min_length=1, max_length=7
    )
    ai_metadata = serializers.DictField(required=False, allow_null=True)

    def validate_ai_metadata(self, value: object) -> dict[str, Any]:
        return sanitize_ai_metadata(value)


class ValidateMoveSerializer(serializers.Serializer[dict[str, Any]]):
    placements = serializers.ListField(child=serializers.DictField(), min_length=1)
    rack_owner = serializers.ChoiceField(
        choices=["player", "ai"],
        required=False,
        default="player",
    )


class ValidateWordsSerializer(serializers.Serializer[dict[str, Any]]):
    words = serializers.ListField(child=serializers.CharField(max_length=50), min_length=1)


def _nfc_uppercase_letter(value: object, *, allow_blank: bool) -> str:
    if not isinstance(value, str):
        raise serializers.ValidationError("Must be a single uppercase letter.")
    nfc = unicodedata.normalize("NFC", value)
    if allow_blank and nfc == "?":
        return nfc
    if len(nfc) == 1 and nfc.isalpha() and nfc == nfc.upper():
        return nfc
    raise serializers.ValidationError("Must be a single uppercase letter.")


class PlacementSerializer(serializers.Serializer[dict[str, Any]]):
    row = serializers.IntegerField(min_value=0, max_value=14)
    col = serializers.IntegerField(min_value=0, max_value=14)
    letter = serializers.CharField()
    blank_as = serializers.CharField(required=False)

    def validate_letter(self, value: str) -> str:
        return _nfc_uppercase_letter(value, allow_blank=True)

    def validate_blank_as(self, value: str) -> str:
        return _nfc_uppercase_letter(value, allow_blank=False)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise serializers.ValidationError("Invalid placement.")
        allowed = set(self.fields)
        unknown = sorted(set(data.keys()) - allowed)
        if unknown:
            raise serializers.ValidationError({key: "Unknown field." for key in unknown})
        letter = data.get("letter")
        if letter == "?":
            if "blank_as" not in data:
                raise serializers.ValidationError(
                    {"blank_as": "This field is required for blank tiles."}
                )
        elif "blank_as" in data:
            raise serializers.ValidationError(
                {"blank_as": "This field is forbidden for non-blank tiles."}
            )
        return super().to_internal_value(data)  # type: ignore[no-any-return]


class ApplyAIMoveSerializer(serializers.Serializer[dict[str, Any]]):
    placements = PlacementSerializer(many=True)
    ai_metadata = serializers.DictField(required=False, allow_null=True)

    def validate_placements(self, placements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not placements:
            raise serializers.ValidationError("At least one placement is required.")
        if len(placements) > 7:
            raise serializers.ValidationError("At most seven placements are allowed.")
        cells = [(item["row"], item["col"]) for item in placements]
        if len(cells) != len(set(cells)):
            raise serializers.ValidationError("Duplicate cells are not allowed.")
        return placements

    def validate_ai_metadata(self, value: object) -> dict[str, Any]:
        return sanitize_ai_metadata(value)


class AIPassSerializer(serializers.Serializer[dict[str, Any]]):
    ai_metadata = serializers.DictField(required=False, allow_null=True)

    def validate_ai_metadata(self, value: object) -> dict[str, Any]:
        return sanitize_ai_metadata(value)


class UpdateGameAIModelSerializer(serializers.Serializer[dict[str, Any]]):
    ai_model_model_id = serializers.CharField(required=True, allow_blank=False, max_length=200)

    def validate_ai_model_model_id(self, value: str) -> str:
        if not is_selectable_model(value):
            raise serializers.ValidationError("Unknown or unavailable AI model.")
        return value


class UpdateGameAIPromptSerializer(serializers.Serializer[dict[str, Any]]):
    ai_prompt_id = serializers.IntegerField(required=True)

    def validate_ai_prompt_id(self, value: int) -> int:
        selectable_prompt_ids = {prompt.id for prompt in get_selectable_prompts()}
        if value not in selectable_prompt_ids:
            raise serializers.ValidationError("Unknown or unavailable AI prompt.")
        return value
