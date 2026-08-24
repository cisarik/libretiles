from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from catalog.selection import is_selectable_model

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def create(self, validated_data: dict) -> User:  # type: ignore[override]
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
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


class ChangePasswordSerializer(serializers.Serializer):
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

    def save(self, **kwargs) -> User:  # type: ignore[override]
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
