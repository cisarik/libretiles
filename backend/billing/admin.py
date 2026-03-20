from django.contrib import admin

from .models import CreditBalance, Transaction


@admin.register(CreditBalance)
class CreditBalanceAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "updated_at")
    search_fields = ("user__username",)
    readonly_fields = ("updated_at",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "amount", "description", "created_at")
    list_filter = ("type",)
    search_fields = ("user__username", "description")
    readonly_fields = ("created_at",)
