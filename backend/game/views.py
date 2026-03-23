from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.services import charge_ai_move

from . import services
from .serializers import (
    ApplyAIMoveSerializer,
    CreateGameSerializer,
    ExchangeSerializer,
    GameHistoryQuerySerializer,
    QueueCancelSerializer,
    QueueJoinSerializer,
    SubmitMoveSerializer,
    UpdateGameAIModelSerializer,
    ValidateMoveSerializer,
    ValidateWordsSerializer,
)


def _service_error_response(error: Exception) -> Response:
    if isinstance(error, services.GameNotFoundError):
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    raise error


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
        return Response(result)


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
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class GameHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):  # type: ignore[no-untyped-def]
        serializer = GameHistoryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = services.list_games_for_user(
            user_id=request.user.id,
            game_mode=serializer.validated_data["game_mode"],
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
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
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
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
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
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
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
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        result["state"] = services.get_game_state_for_user(game_id, request.user.id)
        return Response(result)


class AIContextView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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
            )
        except Exception as error:
            return _service_error_response(error)

        if result.get("ok") and serializer.validated_data.get("ai_metadata"):
            from .models import Move

            last_move = Move.objects.filter(game__public_id=game_id).order_by("-seq").first()
            if last_move:
                last_move.ai_metadata = serializer.validated_data["ai_metadata"]
                last_move.save(update_fields=["ai_metadata"])

        if result.get("ok"):
            from .models import GameSession, Move

            result["state"] = services.get_game_state_for_user(game_id, request.user.id)
            session = GameSession.objects.select_related("ai_model").get(public_id=game_id)
            billing = charge_ai_move(
                user=request.user,
                game=session,
                ai_model=session.ai_model,
                ai_metadata=serializer.validated_data.get("ai_metadata"),
            )
            result["billing"] = billing
            if isinstance(result.get("state"), dict):
                result["state"]["last_move_billing"] = billing
            if serializer.validated_data.get("ai_metadata"):
                last_move = Move.objects.filter(game__public_id=game_id).order_by("-seq").first()
                if last_move and isinstance(last_move.ai_metadata, dict):
                    last_move.ai_metadata["billing"] = billing
                    last_move.save(update_fields=["ai_metadata"])

        return Response(result, status=200 if result.get("ok") else 400)


class AIPassView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):  # type: ignore[no-untyped-def]
        try:
            result = services.submit_pass_for_ai(game_id, request.user.id)
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
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
            )
        except Exception as error:
            return _service_error_response(error)
        if not result["ok"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        result["state"] = services.get_game_state_for_user(game_id, request.user.id)
        return Response(result)
