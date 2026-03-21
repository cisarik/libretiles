from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from game.models import GameSession

from .services import charge_ai_move


class ChargeAITurnSerializer(serializers.Serializer):
    game_id = serializers.UUIDField()
    ai_metadata = serializers.DictField(required=False, allow_null=True)


class ChargeAITurnView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = ChargeAITurnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = get_object_or_404(
            GameSession.objects.select_related("ai_model").filter(slots__user=request.user).distinct(),
            public_id=serializer.validated_data["game_id"],
        )
        billing = charge_ai_move(
            user=request.user,
            game=session,
            ai_model=session.ai_model,
            ai_metadata=serializer.validated_data.get("ai_metadata"),
        )
        return Response(billing)
