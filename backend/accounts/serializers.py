from rest_framework import serializers

from billing.services import ensure_credit_balance
from catalog.selection import is_selectable_model

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def create(self, validated_data: dict) -> User:  # type: ignore[override]
        user = User.objects.create_user(**validated_data)
        ensure_credit_balance(user)
        return user


class UserSerializer(serializers.ModelSerializer):
    credit_balance = serializers.DecimalField(
        source="credit_balance.balance",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    credit_updated_at = serializers.DateTimeField(source="credit_balance.updated_at", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "preferred_ai_model_id",
            "credit_balance",
            "credit_updated_at",
            "date_joined",
        )
        read_only_fields = ("id", "date_joined")

    def validate_preferred_ai_model_id(self, value: str) -> str:
        if not value:
            return value
        if not is_selectable_model(value):
            raise serializers.ValidationError("Unknown AI model.")
        return value
