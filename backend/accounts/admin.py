from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm

from .models import User

if TYPE_CHECKING:
    _BaseUserAdmin = BaseUserAdmin[User]
    _AdminPasswordChangeForm = AdminPasswordChangeForm[User]
else:
    _BaseUserAdmin = BaseUserAdmin
    _AdminPasswordChangeForm = AdminPasswordChangeForm


class RefreshBlacklistingAdminPasswordChangeForm(_AdminPasswordChangeForm):
    """Admin password form that also records revocation in the blacklist table."""

    def save(self, commit: bool = True) -> Any:
        user = super().save(commit=commit)
        if commit and isinstance(user, User):
            user.blacklist_outstanding_refresh_tokens()
        return user


@admin.register(User)
class UserAdmin(_BaseUserAdmin):
    change_password_form = RefreshBlacklistingAdminPasswordChangeForm
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
