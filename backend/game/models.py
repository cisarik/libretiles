import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class GameSession(models.Model):
    """A single Libre Tiles game session."""

    STATUS_CHOICES = [
        ("waiting", "Waiting for opponent"),
        ("active", "Active"),
        ("finished", "Finished"),
        ("abandoned", "Abandoned"),
    ]
    MODE_CHOICES = [
        ("vs_ai", "Human vs AI"),
        ("vs_human", "Human vs Human"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    game_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default="vs_ai")
    variant_slug = models.CharField(max_length=50, default="english")

    board_state = models.JSONField(
        default=list,
        help_text="15x15 grid as list of 15 strings",
    )
    blanks = models.JSONField(default=list, help_text="List of {row, col} for blank tiles")
    premium_used = models.JSONField(default=list, help_text="List of {row, col} for used premiums")
    bag_tiles = models.TextField(default="", help_text="Remaining tiles in order")
    bag_seed = models.IntegerField(default=0)
    total_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("0"))

    current_turn_slot = models.IntegerField(null=True, blank=True, default=None)
    consecutive_passes = models.IntegerField(default=0)

    ai_model = models.ForeignKey(
        "catalog.AIModel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="AI model for vs_ai games",
    )
    ai_prompt = models.ForeignKey(
        "catalog.AIPrompt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="AI prompt preset for vs_ai games",
    )

    game_over = models.BooleanField(default=False)
    game_end_reason = models.CharField(max_length=50, blank=True, default="")
    winner_slot = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "game_session"

    def __str__(self) -> str:
        return f"Game {self.public_id.hex[:8]} ({self.status})"


class PlayerSlot(models.Model):
    """A player slot in a game session (0 or 1)."""

    game = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="slots")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="game_slots",
    )
    slot = models.IntegerField(help_text="0 or 1")
    rack = models.JSONField(default=list, help_text="Current rack letters as list of strings")
    score = models.IntegerField(default=0)
    pass_streak = models.IntegerField(default=0)
    is_ai = models.BooleanField(default=False)

    class Meta:
        unique_together = ("game", "slot")
        ordering = ["slot"]
        db_table = "game_player_slot"

    def __str__(self) -> str:
        name = "AI" if self.is_ai else (self.user.username if self.user else "???")  # type: ignore[union-attr]
        return f"Slot {self.slot}: {name} (score={self.score})"


class Move(models.Model):
    """A single move in a game session."""

    KIND_CHOICES = [
        ("place", "Place tiles"),
        ("exchange", "Exchange tiles"),
        ("pass", "Pass turn"),
        ("give_up", "Give up"),
    ]

    game = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="moves")
    player_slot = models.ForeignKey(PlayerSlot, on_delete=models.CASCADE, related_name="moves")
    seq = models.IntegerField(help_text="Move sequence number (1-based)")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)

    placements = models.JSONField(
        default=list,
        help_text='List of {row, col, letter, blank_as} for "place" moves',
    )
    words_formed = models.JSONField(
        default=list,
        help_text="List of {word, coords, score} for words created by this move",
    )
    tiles_exchanged = models.IntegerField(default=0, help_text="Number of tiles exchanged")
    points = models.IntegerField(default=0)

    ai_metadata = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw AI response metadata for debugging",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seq"]
        unique_together = ("game", "seq")
        db_table = "game_move"

    def __str__(self) -> str:
        return f"Move #{self.seq} ({self.kind}, +{self.points}pts)"


class ChatMessage(models.Model):
    """A persisted in-game chat message for human multiplayer sessions."""

    game = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="chat_messages")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="game_chat_messages",
    )
    body = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        db_table = "game_chat_message"

    def __str__(self) -> str:
        username = self.user.username if self.user else "Unknown"  # type: ignore[union-attr]
        return f"{username}: {self.body[:40]}"
