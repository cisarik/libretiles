from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from billing.models import CreditBalance
from billing.services import ensure_credit_balance

from .models import User


class CreditBalanceInline(admin.StackedInline):
    model = CreditBalance
    extra = 0
    can_delete = False
    verbose_name_plural = "Credits"
    fields = ("balance", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "credit_balance_value",
        "preferred_ai_model_id",
        "date_joined",
        "is_active",
    )
    list_filter = ("is_active", "is_staff")
    inlines = (CreditBalanceInline,)
    fieldsets = BaseUserAdmin.fieldsets + (  # type: ignore[operator]
        ("Game Settings", {"fields": ("preferred_ai_model_id",)}),
    )

    def get_inline_instances(self, request, obj=None):  # type: ignore[no-untyped-def]
        if obj is not None:
            ensure_credit_balance(obj)
        return super().get_inline_instances(request, obj)

    @admin.display(description="Balance")
    def credit_balance_value(self, obj: User) -> str:
        balance = getattr(obj, "credit_balance", None)
        if balance is None:
            return "—"
        return f"${balance.balance:.2f}"
