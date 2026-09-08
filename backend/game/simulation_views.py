from __future__ import annotations

from typing import Any

from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import PasswordAwareJWTAuthentication

from . import simulations
from .simulation_serializers import (
    SimulationActionSerializer,
    SimulationCreateSerializer,
    SimulationStepSerializer,
    SimulationStopSerializer,
)


class _SimulationAPIView(APIView):
    authentication_classes = [PasswordAwareJWTAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    http_method_names = ["get", "post", "head", "options"]

    def finalize_response(self, request: Request, response: Response, *args: Any, **kwargs: Any) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Authorization, Cookie"
        return response

    def service_error(self, error: Exception) -> Response:
        if isinstance(error, simulations.SimulationNotFoundError):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if isinstance(error, simulations.SimulationConflictError):
            payload: dict[str, Any] = {"detail": str(error), "code": "state_conflict"}
            if error.game_id:
                payload["game_id"] = error.game_id
            return Response(payload, status=status.HTTP_409_CONFLICT)
        raise error


class SimulationCreateView(_SimulationAPIView):
    throttle_scope = "admin_simulation_create"

    def post(self, request: Request) -> Response:
        serializer = SimulationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = request.user.id
        assert user_id is not None
        try:
            simulation = simulations.create_playground_simulation(
                created_by_id=user_id, **serializer.validated_data
            )
        except Exception as error:
            return self.service_error(error)
        return Response(
            simulations.serialize_simulation_state(
                simulations.get_playground_simulation(str(simulation.game.public_id))
            ),
            status=status.HTTP_201_CREATED,
        )


class SimulationStateView(_SimulationAPIView):
    def get(self, request: Request, game_id: str) -> Response:
        try:
            simulation = simulations.get_playground_simulation(game_id)
        except Exception as error:
            return self.service_error(error)
        return Response(simulations.serialize_simulation_state(simulation))


class SimulationStepView(_SimulationAPIView):
    throttle_scope = "admin_simulation_step"

    def post(self, request: Request, game_id: str) -> Response:
        serializer = SimulationStepSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = request.user.id
        assert user_id is not None
        try:
            result = simulations.step_playground_simulation(
                game_id=game_id,
                user_id=user_id,
                expected_move_count=serializer.validated_data["expected_move_count"],
            )
        except Exception as error:
            return self.service_error(error)
        return Response(result)


class SimulationActionView(_SimulationAPIView):
    throttle_scope = "admin_simulation_step"

    def post(self, request: Request, game_id: str) -> Response:
        serializer = SimulationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = request.user.id
        assert user_id is not None
        try:
            result = simulations.simulation_action(
                game_id=game_id, user_id=user_id, data=serializer.validated_data
            )
        except Exception as error:
            return self.service_error(error)
        return Response(result, status=200 if result.get("ok", True) else 409)


class SimulationStopView(_SimulationAPIView):
    def post(self, request: Request, game_id: str) -> Response:
        serializer = SimulationStopSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = request.user.id
        assert user_id is not None
        try:
            simulation = simulations.stop_playground_simulation(
                game_id=game_id, user_id=user_id
            )
        except Exception as error:
            return self.service_error(error)
        return Response(simulations.serialize_simulation_state(simulation))
