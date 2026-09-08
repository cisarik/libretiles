from __future__ import annotations

from typing import Any, cast

from rest_framework import serializers

from gamecore.variant_store import list_installed_variants


class AdminAnalyticsQuerySerializer(serializers.Serializer[dict[str, Any]]):
    days = serializers.IntegerField(min_value=1, max_value=365, default=30)
    analytics_source = serializers.ChoiceField(
        choices=["all", "gameplay", "playground", "diagnostic"], default="all"
    )
    variant_slug = serializers.CharField(max_length=50, default="all")

    def validate_variant_slug(self, value: str) -> str:
        if value == "all":
            return value
        if value not in {variant.slug for variant in list_installed_variants()}:
            raise serializers.ValidationError("Unknown or unavailable variant.")
        return value

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        normalized = {
            key: data.get(key)
            for key in ("days", "variant_slug")
            if data.get(key) is not None
        }
        if data.get("source") is not None:
            normalized["analytics_source"] = data.get("source")
        values = super().to_internal_value(normalized)
        values["source"] = values.pop("analytics_source")
        return cast(dict[str, Any], values)


class AdminAnalyticsResponseSerializer(serializers.Serializer[dict[str, Any]]):
    analytics_schema_version = serializers.IntegerField(min_value=1, max_value=1)
    as_of = serializers.DateTimeField()
    filters = serializers.DictField()
    summary = serializers.DictField()
    models = serializers.ListField(child=serializers.DictField())
    presets = serializers.ListField(child=serializers.DictField())
    recommendations = serializers.DictField()
    coverage = serializers.DictField()
