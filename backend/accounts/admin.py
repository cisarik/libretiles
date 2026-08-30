from typing import TYPE_CHECKING

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User

if TYPE_CHECKING:
    _BaseUserAdmin = BaseUserAdmin[User]
else:
    _BaseUserAdmin = BaseUserAdmin


@admin.register(User)
class UserAdmin(_BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "preferred_ai_model_id",
        "date_joined",
        "is_active",
    )
    list_filter = ("is_active", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (  # type: ignore[operator]
        ("Game Settings", {"fields": ("preferred_ai_model_id",)}),
    )
