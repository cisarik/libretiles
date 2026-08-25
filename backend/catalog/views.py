from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .selection import get_selectable_models, get_selectable_prompts
from .serializers import AIModelSerializer, AIPromptSerializer


class AIModelListView(APIView):
    """Public list of selectable AI models."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):  # type: ignore[no-untyped-def]
        models = get_selectable_models()
        serializer = AIModelSerializer(
            models,
            many=True,
            context={"flagship_pk": models[0].pk if models else None},
        )
        return Response(serializer.data)


class AIPromptListView(APIView):
    """Public list of selectable AI prompts."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):  # type: ignore[no-untyped-def]
        serializer = AIPromptSerializer(get_selectable_prompts(), many=True)
        return Response(serializer.data)
