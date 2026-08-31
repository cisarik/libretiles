from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .serializers import ChangePasswordSerializer, RegisterSerializer, UserSerializer

# urls.py binds SimpleJWT's views directly; attach scopes here so login/refresh
# are covered without changing the URLconf (not on this slice's allowlist).
setattr(TokenObtainPairView, "throttle_scope", "auth_login")
setattr(TokenRefreshView, "throttle_scope", "auth_refresh")


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
