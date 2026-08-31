from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

from catalog.selection import is_selectable_model

from .authentication import reject_if_issued_before_password_change
from .models import User


class RegisterSerializer(serializers.ModelSerializer[User]):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        password = attrs["password"]
        user = User(
            username=str(attrs.get("username") or ""),
            email=str(attrs.get("email") or ""),
        )
        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data: dict[str, Any]) -> User:
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "preferred_ai_model_id",
            "date_joined",
        )
        read_only_fields = ("id", "date_joined")

    def validate_preferred_ai_model_id(self, value: str) -> str:
        if not value:
            return value
        if not is_selectable_model(value):
            raise serializers.ValidationError("Unknown AI model.")
        return value


class ChangePasswordSerializer(serializers.Serializer[User]):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        user = self.context["request"].user
        validate_password(value, user=user)
        return value

    def save(self, **kwargs: Any) -> User:
        user: User = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "password_changed_at"])
        user.blacklist_outstanding_refresh_tokens()
        return user


class PasswordAwareTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
        if user_id is not None:
            user = (
                get_user_model()
                .objects.filter(**{api_settings.USER_ID_FIELD: user_id})
                .first()
            )
            if user is not None:
                reject_if_issued_before_password_change(refresh, user)
        return super().validate(attrs)
