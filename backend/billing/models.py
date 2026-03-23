from django.conf import settings
from django.db import models


class CreditBalance(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credit_balance"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_credit_balance"

    def __str__(self) -> str:
        return f"{self.user}: {self.balance} credits"


class Transaction(models.Model):
    TYPE_CHOICES = [
        ("purchase", "Credit purchase"),
        ("game_charge", "Game charge"),
        ("refund", "Refund"),
        ("bonus", "Bonus"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=6)
    description = models.TextField(blank=True, default="")
    stripe_payment_id = models.CharField(max_length=200, blank=True, default="")
    game = models.ForeignKey(
        "game.GameSession", null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "billing_transaction"

    def __str__(self) -> str:
        return f"{self.type}: {self.amount} ({self.user})"
