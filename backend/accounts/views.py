from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .serializers import ChangePasswordSerializer, RegisterSerializer, UserSerializer


class ScopedTokenObtainPairView(TokenObtainPairView):
    throttle_scope = "auth_login"


class ScopedTokenRefreshView(TokenRefreshView):
    throttle_scope = "auth_refresh"


class RegisterView(generics.CreateAPIView[User]):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_register"


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth_me"

    def get(self, request):  # type: ignore[no-untyped-def]
        user = User.objects.get(pk=request.user.pk)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def patch(self, request):  # type: ignore[no-untyped-def]
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = User.objects.get(pk=request.user.pk)
        return Response(UserSerializer(user).data)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth_change_password"

    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            first_error = next(
                (
                    str(message)
                    for messages in serializer.errors.values()
                    for message in messages
                ),
                "Unable to change password.",
            )
            return Response({"ok": False, "error": first_error}, status=400)

        serializer.save()
        return Response({"ok": True})


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):  # type: ignore[no-untyped-def]
        raw = request.data.get("refresh")
        if not isinstance(raw, str) or not raw.strip():
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            refresh = RefreshToken(raw)  # type: ignore[arg-type]
        except TokenError:
            return Response(
                {"detail": "Token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        token_user_id = refresh.get(api_settings.USER_ID_CLAIM)
        if str(token_user_id) != str(request.user.pk):
            return Response(
                {"detail": "Token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            refresh.blacklist()
        except TokenError:
            return Response(
                {"detail": "Token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response({"ok": True}, status=status.HTTP_200_OK)
