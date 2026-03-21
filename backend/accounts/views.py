from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.services import ensure_credit_balance

from .models import User
from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):  # type: ignore[no-untyped-def]
        ensure_credit_balance(request.user)
        user = User.objects.get(pk=request.user.pk)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def patch(self, request):  # type: ignore[no-untyped-def]
        ensure_credit_balance(request.user)
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = User.objects.get(pk=request.user.pk)
        return Response(UserSerializer(user).data)
