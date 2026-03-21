from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .selection import get_selectable_models
from .serializers import AIModelSerializer


class AIModelListView(APIView):
    """Public list of selectable AI models with pricing."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):  # type: ignore[no-untyped-def]
        serializer = AIModelSerializer(get_selectable_models(), many=True)
        return Response(serializer.data)
