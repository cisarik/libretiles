from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "preferred_ai_model_id", "date_joined", "is_active")
    list_filter = ("is_active", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (  # type: ignore[operator]
        ("Game Settings", {"fields": ("preferred_ai_model_id",)}),
    )
