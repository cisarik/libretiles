from rest_framework import generics, permissions

from .models import AIModel
from .serializers import AIModelSerializer


class AIModelListView(generics.ListAPIView):
    """Public list of active AI models with pricing."""

    serializer_class = AIModelSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return AIModel.objects.filter(is_active=True)
