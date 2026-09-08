from __future__ import annotations

import re
import uuid
from typing import Any

from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.db.models.functions import Cast, Replace
from django.db.models import CharField, Value
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import PasswordAwareJWTAuthentication

from .admin_serializers import serialize_admin_game
from .models import DiagnosticRun, GameSession, PlayerSlot
from .replay import build_replay_payload


class _AdminAPIView(APIView):
    authentication_classes = [PasswordAwareJWTAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    http_method_names = ["get", "head", "options"]

    def finalize_response(self, request: Request, response: Response, *args: Any, **kwargs: Any) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Authorization, Cookie"
        return response


def _positive_int(raw: str | None, *, default: int, maximum: int | None = None) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("Must be a positive integer") from exc
    if value < 1 or (maximum is not None and value > maximum):
        raise ValueError("Must be a positive integer within the allowed range")
    return value


class AdminGameListView(_AdminAPIView):
    def get(self, request: Request) -> Response:
        try:
            page_number = _positive_int(request.query_params.get("page"), default=1)
            page_size = _positive_int(
                request.query_params.get("page_size"), default=20, maximum=100
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        game_mode = request.query_params.get("game_mode", "all")
        game_status = request.query_params.get("status", "all")
        diagnostic = request.query_params.get("is_diagnostic", "all")
        variant_slug = request.query_params.get("variant_slug", "").strip()
        search = request.query_params.get("search", "").strip()
        if game_mode not in {"all", "vs_ai", "vs_human"}:
            return Response({"detail": "Invalid game_mode"}, status=400)
        if game_status not in {"all", "waiting", "active", "finished", "abandoned"}:
            return Response({"detail": "Invalid status"}, status=400)
        if diagnostic not in {"all", "true", "false"}:
            return Response({"detail": "Invalid is_diagnostic"}, status=400)
        if len(variant_slug) > 50 or len(search) > 150:
            return Response({"detail": "Query parameter is too long"}, status=400)

        queryset = (
            GameSession.objects.select_related("ai_model")
            .prefetch_related(
                "slots__user",
                "slots__ai_model",
                "slots__diagnostic_target",
                Prefetch(
                    "diagnostic_runs",
                    queryset=DiagnosticRun.objects.order_by("created_at", "id"),
                ),
            )
            .annotate(move_count=Count("moves", distinct=True))
        )
        if game_mode != "all":
            queryset = queryset.filter(game_mode=game_mode)
        if game_status != "all":
            queryset = queryset.filter(status=game_status)
        if diagnostic != "all":
            queryset = queryset.filter(is_diagnostic=diagnostic == "true")
        if variant_slug:
            queryset = queryset.filter(variant_slug=variant_slug)
        if search:
            username_match = PlayerSlot.objects.filter(
                game_id=OuterRef("pk"), user__username__icontains=search
            )
            queryset = queryset.annotate(username_match=Exists(username_match))
            predicate = Q(username_match=True)
            compact = search.replace("-", "")
            if re.fullmatch(r"[0-9a-fA-F]+", compact):
                queryset = queryset.annotate(
                    public_id_text=Replace(
                        Cast("public_id", output_field=CharField()), Value("-"), Value("")
                    )
                )
                predicate |= Q(public_id_text__istartswith=compact)
            queryset = queryset.filter(predicate)

        paginator = Paginator(queryset.order_by("-created_at", "-pk"), page_size)
        page = paginator.get_page(page_number)
        return Response(
            {
                "count": paginator.count,
                "page": page.number,
                "total_pages": paginator.num_pages,
                "page_size": page_size,
                "results": [serialize_admin_game(session) for session in page.object_list],
            }
        )


class AdminGameReplayView(_AdminAPIView):
    def get(self, request: Request, game_id: str) -> Response:
        try:
            parsed = uuid.UUID(game_id)
        except (ValueError, AttributeError):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            session = (
                GameSession.objects.select_related("ai_model")
                .prefetch_related(
                    "slots__user",
                    "slots__ai_model",
                    "slots__diagnostic_target",
                    "moves__player_slot",
                    "moves__diagnostic_plies",
                    "moves__diagnostic_plies__run",
                )
                .get(public_id=parsed)
            )
        except GameSession.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(build_replay_payload(session))
