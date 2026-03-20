from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import (
    ApplyAIMoveSerializer,
    CreateGameSerializer,
    ExchangeSerializer,
    SubmitMoveSerializer,
    ValidateMoveSerializer,
    ValidateWordsSerializer,
)


class CreateGameView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):  # type: ignore[no-untyped-def]
        ser = CreateGameSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = services.create_game(
            user_id=request.user.id,
            game_mode=ser.validated_data["game_mode"],
            ai_model_id=ser.validated_data.get("ai_model_id"),
            variant_slug=ser.validated_data["variant_slug"],
        )
        return Response(result, status=status.HTTP_201_CREATED)


class GameStateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, game_id):  # type: ignore[no-untyped-def]
        slot = request.query_params.get("slot", "0")
        state = services.get_game_state_for_slot(game_id, int(slot))
        return Response(state)


class SubmitMoveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        ser = SubmitMoveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        slot = int(request.data.get("slot", 0))
        result = services.submit_move(game_id, slot, ser.validated_data["placements"])
        if not result["ok"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        result["state"] = services.get_game_state_for_slot(game_id, slot)
        return Response(result)


class ExchangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        ser = ExchangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        slot = int(request.data.get("slot", 0))
        result = services.submit_exchange(game_id, slot, ser.validated_data["letters"])
        if not result["ok"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        result["state"] = services.get_game_state_for_slot(game_id, slot)
        return Response(result)


class PassView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        slot = int(request.data.get("slot", 0))
        result = services.submit_pass(game_id, slot)
        if not result["ok"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        result["state"] = services.get_game_state_for_slot(game_id, slot)
        return Response(result)


class AIContextView(APIView):
    """Provides compact game state for Vercel AI Gateway route."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, game_id):  # type: ignore[no-untyped-def]
        context = services.get_ai_context(game_id)
        return Response(context)


class ValidateMoveView(APIView):
    """AI tool endpoint: validate placements without applying."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        ser = ValidateMoveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = services.validate_move_for_ai(game_id, ser.validated_data["placements"])
        return Response(result)


class ValidateWordsView(APIView):
    """AI tool endpoint: check words against the primary Collins dictionary."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        ser = ValidateWordsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = services.validate_words(ser.validated_data["words"])
        return Response({"results": result})


class ApplyAIMoveView(APIView):
    """Apply AI-proposed move (re-validates server-side)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        ser = ApplyAIMoveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        viewer_slot_obj = (
            __import__("game.models", fromlist=["PlayerSlot"])
            .PlayerSlot.objects.filter(game__public_id=game_id, user_id=request.user.id)
            .first()
        )
        ai_slot_obj = (
            __import__("game.models", fromlist=["PlayerSlot"])
            .PlayerSlot.objects.filter(game__public_id=game_id, is_ai=True)
            .first()
        )
        if not ai_slot_obj:
            return Response({"ok": False, "error": "No AI slot"}, status=400)

        result = services.submit_move(
            game_id, ai_slot_obj.slot, ser.validated_data["placements"]
        )
        if result.get("ok") and ser.validated_data.get("ai_metadata"):
            last_move = (
                __import__("game.models", fromlist=["Move"])
                .Move.objects.filter(game__public_id=game_id)
                .order_by("-seq")
                .first()
            )
            if last_move:
                last_move.ai_metadata = ser.validated_data["ai_metadata"]
                last_move.save(update_fields=["ai_metadata"])

        if result.get("ok"):
            result["state"] = services.get_game_state_for_slot(
                game_id,
                viewer_slot_obj.slot if viewer_slot_obj else 0,
            )

        return Response(result, status=200 if result.get("ok") else 400)
