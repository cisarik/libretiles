import json
import logging
from pathlib import Path
from typing import Any, Literal, TypedDict

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from gamecore.assets import get_assets_path
from gamecore.variant_store import VariantDefinition, _load_variant_from_path, slugify

from . import services
from .serializers import (
    AIPassSerializer,
    ApplyAIMoveSerializer,
    CreateGameSerializer,
    ExchangeSerializer,
    GameHistoryQuerySerializer,
    QueueCancelSerializer,
    QueueJoinSerializer,
    SubmitMoveSerializer,
    UpdateGameAIModelSerializer,
    UpdateGameAIPromptSerializer,
    ValidateMoveSerializer,
    ValidateWordsSerializer,
)

_PLAYABILITY_CONFLICT_CODES = frozenset(
    {
        "legal_scoring_move_exists",
        "playability_unknown",
        "exchange_required",
        "state_conflict",
    }
)
_DEFAULT_VARIANT_SLUG = "english"
_log = logging.getLogger("game")


class VariantSummary(TypedDict):
    slug: str
    display_name: str
    language_code: str | None
    readiness: Literal["playable", "unavailable"]


def _variant_json_dir() -> Path:
    return get_assets_path() / "variants"


def _public_language_code(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _looks_structurally_complete(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    letters = data.get("letters")
    alphabet = data.get("alphabet_order")
    dictionary_file = data.get("dictionary_file")
    if not isinstance(letters, list) or not letters:
        return False
    if not isinstance(alphabet, list) or not alphabet:
        return False
    if not isinstance(dictionary_file, str) or not dictionary_file.strip():
        return False
    return True


def _summary_from_payload(data: dict[str, Any], stem: str) -> VariantSummary | None:
    language = data.get("language") or data.get("name")
    if not isinstance(language, str) or not language.strip():
        return None
    slug_raw = data.get("slug")
    slug = (
        slugify(str(slug_raw))
        if isinstance(slug_raw, str) and slug_raw.strip()
        else slugify(stem)
    )
    return {
        "slug": slug,
        "display_name": language.strip(),
        "language_code": _public_language_code(
            data.get("language_code") or data.get("code")
        ),
        "readiness": "unavailable",
    }


def _variant_resources_ready(variant: VariantDefinition) -> bool:
    if not variant.dictionary_path.is_file():
        return False
    two_path = variant.two_tile_words_path
    return two_path is None or two_path.is_file()


def list_variant_summaries() -> list[VariantSummary]:
    """Public four-field summaries. Never include paths, filenames, or errors."""
    summaries: list[VariantSummary] = []
    try:
        paths = sorted(_variant_json_dir().glob("*.json"))
    except OSError:
        _log.error("variant_list_omitted")
        return []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
            _log.error("variant_list_omitted")
            continue
        if not _looks_structurally_complete(data):
            _log.error("variant_list_omitted")
            continue
        try:
            variant = _load_variant_from_path(path)
        except FileNotFoundError:
            summary = _summary_from_payload(data, path.stem)
            if summary is None:
                _log.error("variant_list_omitted")
                continue
            summaries.append(summary)
            continue
        except Exception:
            _log.error("variant_list_omitted")
            continue
        readiness: Literal["playable", "unavailable"] = (
            "playable" if _variant_resources_ready(variant) else "unavailable"
        )
        summaries.append(
            {
                "slug": variant.slug,
                "display_name": variant.language,
                "language_code": variant.language_code,
                "readiness": readiness,
            }
        )
    summaries.sort(
        key=lambda item: (
            0 if item["slug"] == _DEFAULT_VARIANT_SLUG else 1,
            (item["display_name"] or "").casefold(),
            item["slug"],
        )
    )
    return summaries


def _action_error_status(result: dict[str, Any]) -> int:
    if result.get("code") in _PLAYABILITY_CONFLICT_CODES:
        return status.HTTP_409_CONFLICT
    return status.HTTP_400_BAD_REQUEST


def _service_error_response(error: Exception) -> Response:
    if isinstance(error, services.GameNotFoundError):
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    raise error


class VariantListView(APIView):
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response(list_variant_summaries())


class CreateGameView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = CreateGameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.create_game(
            user_id=request.user.id,
            game_mode=serializer.validated_data["game_mode"],
            ai_model_id=serializer.validated_data.get("ai_model_id"),
            ai_model_model_id=serializer.validated_data.get("ai_model_model_id"),
            ai_prompt_id=serializer.validated_data.get("ai_prompt_id"),
            variant_slug=serializer.validated_data["variant_slug"],
        )
        return Response(result, status=status.HTTP_201_CREATED if result.get("ok", True) else 400)


class QueueJoinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = QueueJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.join_human_queue(
            user_id=request.user.id,
            variant_slug=serializer.validated_data["variant_slug"],
        )
        return Response(result, status=200 if result.get("ok", True) else 400)


class QueueCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = QueueCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.cancel_human_queue(
                game_id=serializer.validated_data["game_id"],
                user_id=request.user.id,
            )
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=_action_error_status(result))
        return Response(result)


class GameHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):  # type: ignore[no-untyped-def]
        serializer = GameHistoryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = services.list_games_for_user(
            user_id=request.user.id,
            game_mode=serializer.validated_data["game_mode"],
            sort=serializer.validated_data["sort"],
            page=serializer.validated_data["page"],
            page_size=serializer.validated_data["page_size"],
        )
        return Response(result)


class GameStateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, game_id):  # type: ignore[no-untyped-def]
        try:
            state = services.get_game_state_for_user(game_id, request.user.id)
        except Exception as error:
            return _service_error_response(error)
        return Response(state)


class GameWSTicketView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        try:
            result = services.build_ws_ticket(game_id=game_id, user_id=request.user.id)
        except Exception as error:
            return _service_error_response(error)
        return Response(result)


class SubmitMoveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = SubmitMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.submit_move_for_user(
                game_id,
                request.user.id,
                serializer.validated_data["placements"],
            )
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=_action_error_status(result))
        result["state"] = services.get_game_state_for_user(game_id, request.user.id)
        return Response(result)


class ExchangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = ExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.submit_exchange_for_user(
                game_id,
                request.user.id,
                serializer.validated_data["letters"],
            )
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=_action_error_status(result))
        result["state"] = services.get_game_state_for_user(game_id, request.user.id)
        return Response(result)


class PassView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        try:
            result = services.submit_pass_for_user(game_id, request.user.id)
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=_action_error_status(result))
        result["state"] = services.get_game_state_for_user(game_id, request.user.id)
        return Response(result)


class GiveUpView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        try:
            result = services.submit_give_up_for_user(game_id=game_id, user_id=request.user.id)
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=_action_error_status(result))
        result["state"] = services.get_game_state_for_user(game_id, request.user.id)
        return Response(result)


class AIContextView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "ai_context"

    def get(self, request, game_id):  # type: ignore[no-untyped-def]
        try:
            context = services.get_ai_context(game_id, request.user.id)
        except Exception as error:
            return _service_error_response(error)
        return Response(context)


class GameAIModelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = UpdateGameAIModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.set_game_ai_model(
                game_id=game_id,
                user_id=request.user.id,
                ai_model_model_id=serializer.validated_data["ai_model_model_id"],
            )
        except Exception as error:
            return _service_error_response(error)
        return Response(result, status=200 if result.get("ok") else 400)


class GameAIPromptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = UpdateGameAIPromptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.set_game_ai_prompt(
                game_id=game_id,
                user_id=request.user.id,
                ai_prompt_id=serializer.validated_data["ai_prompt_id"],
            )
        except Exception as error:
            return _service_error_response(error)
        return Response(result, status=200 if result.get("ok") else 400)


class ValidateMoveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = ValidateMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.validate_move_for_ai(
                game_id,
                request.user.id,
                serializer.validated_data["placements"],
                rack_owner=serializer.validated_data["rack_owner"],
            )
        except Exception as error:
            return _service_error_response(error)
        return Response(result)


class ValidateWordsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = ValidateWordsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.validate_words(
                game_id=game_id,
                user_id=request.user.id,
                words=serializer.validated_data["words"],
            )
        except Exception as error:
            return _service_error_response(error)
        return Response({"results": result})


class ApplyAIMoveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = ApplyAIMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.submit_move_for_ai(
                game_id,
                request.user.id,
                serializer.validated_data["placements"],
                ai_metadata=serializer.validated_data.get("ai_metadata"),
            )
        except Exception as error:
            return _service_error_response(error)

        if result.get("ok"):
            result["state"] = services.get_game_state_for_user(game_id, request.user.id)

        return Response(result, status=200 if result.get("ok") else _action_error_status(result))


class AIPassView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = AIPassSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.submit_pass_for_ai(
                game_id,
                request.user.id,
                ai_metadata=serializer.validated_data.get("ai_metadata"),
            )
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=_action_error_status(result))
        result["state"] = services.get_game_state_for_user(game_id, request.user.id)
        return Response(result)


class AIExchangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        serializer = ExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.submit_exchange_for_ai(
                game_id,
                request.user.id,
                serializer.validated_data["letters"],
                ai_metadata=serializer.validated_data.get("ai_metadata"),
            )
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=_action_error_status(result))
        result["state"] = services.get_game_state_for_user(game_id, request.user.id)
        return Response(result)


class AIPlayabilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, game_id):  # type: ignore[no-untyped-def]
        try:
            result = services.get_ai_playability(game_id, request.user.id)
        except Exception as error:
            return _service_error_response(error)
        if not result.get("ok"):
            return Response(result, status=_action_error_status(result))
        payload = {key: value for key, value in result.items() if key != "ok"}
        return Response(payload)


class AICandidatesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, game_id):  # type: ignore[no-untyped-def]
        try:
            result = services.get_ai_candidates(game_id, request.user.id)
        except Exception as error:
            return _service_error_response(error)
        if not result.get("ok"):
            return Response(result, status=_action_error_status(result))
        payload = {key: value for key, value in result.items() if key != "ok"}
        return Response(payload)
