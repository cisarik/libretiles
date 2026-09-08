from __future__ import annotations

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from .admin_views import _AdminAPIView
from .analytics import build_admin_analytics
from .analytics_serializers import AdminAnalyticsQuerySerializer, AdminAnalyticsResponseSerializer


class AdminAnalyticsView(_AdminAPIView):
    def get(self, request: Request) -> Response:
        if any(len(values) != 1 for _key, values in request.query_params.lists()):
            return Response({"detail": "Repeated query parameters are not allowed."}, status=400)
        unknown = set(request.query_params) - {"days", "source", "variant_slug"}
        if unknown:
            return Response({"detail": "Unknown query parameter."}, status=400)
        query = AdminAnalyticsQuerySerializer(data=request.query_params)
        if not query.is_valid():
            return Response(query.errors, status=status.HTTP_400_BAD_REQUEST)
        payload = build_admin_analytics(**query.validated_data)
        response = AdminAnalyticsResponseSerializer(data=payload)
        response.is_valid(raise_exception=True)
        return Response(response.validated_data)
