import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import CheckConstraint, Q, UniqueConstraint, Value

from .diagnostic_targets import CREDENTIAL_ENV_NAMES, canonical_hostname, validate_target_save


def default_structured_board() -> list[list[None]]:
    """15x15 empty cell grid: each cell is null until a token is placed."""
    return [[None] * 15 for _ in range(15)]


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
        default=default_structured_board,
        help_text="15x15 structured cell grid: null or {token, blank_as}",
    )
    premium_used = models.JSONField(default=list, help_text="List of {row, col} for used premiums")
    bag_tiles = models.JSONField(default=list, help_text="Ordered remaining tile tokens")
    bag_seed = models.IntegerField(default=0)
    replay_initial_state = models.JSONField(
        null=True,
        blank=True,
        editable=False,
        help_text=(
            "Initial state snapshot {board, premium_used, racks, bag_remaining, "
            "scores, turn_slot}"
        ),
    )

    current_turn_slot = models.IntegerField(null=True, blank=True, default=None)
    consecutive_scoreless_turns = models.IntegerField(default=0)
    is_diagnostic = models.BooleanField(default=False)
    bag_rng_state = models.JSONField(null=True, blank=True, default=None)

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


class DiagnosticAllowedHost(models.Model):
    """Hostname allowlist row for diagnostic-only OpenAI-compatible targets.

    Canonical ASCII hostnames only. A hostname is immutable after insert;
    activation is the editable surface. Add-host performs no DNS, no HTTP,
    and no runner spawn.
    ⛔ No column name may contain a ``SECRET_KEY_FRAGMENTS`` substring.
    """

    hostname = models.CharField(
        max_length=253,
        unique=True,
        help_text="Canonical ASCII hostname; exact-match only (no wildcard or suffix)",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="diagnostic_allowed_hosts",
        help_text="Staff user who registered the host",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "game_diagnostic_allowed_host"
        verbose_name = "Diagnostic allowed host"
        verbose_name_plural = "Diagnostic allowed hosts"

    def __str__(self) -> str:
        return f"{self.hostname} ({'active' if self.is_active else 'inactive'})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        canonical = canonical_hostname(self.hostname)
        if self.pk is not None:
            existing = DiagnosticAllowedHost.objects.filter(pk=self.pk).first()
            if existing is not None and existing.hostname != self.hostname:
                raise ValidationError("Diagnostic allowed host hostnames are immutable")
        self.hostname = canonical
        super().save(*args, **kwargs)


class DiagnosticTarget(models.Model):
    """Diagnostic-only OpenAI-compatible HTTPS target registered in admin.

    Connection settings (``base_url``, ``allowed_host``, ``model_id``,
    ``credential_env_name``) freeze once any PlayerSlot references the
    target. ``save()`` validates new or changed connection settings and
    reactivation; deactivation and renaming need no DNS. No secret value is
    ever stored: ``credential_env_name`` is one of a closed public name set.
    ⛔ No column name may contain a ``SECRET_KEY_FRAGMENTS`` substring.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    base_url = models.CharField(max_length=300)
    allowed_host = models.ForeignKey(
        DiagnosticAllowedHost,
        on_delete=models.PROTECT,
        related_name="targets",
    )
    model_id = models.CharField(max_length=200, help_text="Model id metadata, never a URL")
    credential_env_name = models.CharField(
        max_length=64,
        choices=[(name, name) for name in CREDENTIAL_ENV_NAMES],
        help_text="Closed credential environment-name set; the value itself is never stored",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="diagnostic_targets",
        help_text="Staff user who registered the target",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "game_diagnostic_target"
        verbose_name = "Diagnostic target"
        verbose_name_plural = "Diagnostic targets"

    def __str__(self) -> str:
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        with transaction.atomic():
            previous: DiagnosticTarget | None = None
            if self.pk is not None:
                previous = (
                    DiagnosticTarget.objects.select_for_update()
                    .filter(pk=self.pk)
                    .first()
                )
            validate_target_save(self, previous=previous)
            super().save(*args, **kwargs)


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
    rack = models.JSONField(default=list, help_text="Current rack tokens as list of strings")
    score = models.IntegerField(default=0)
    pass_streak = models.IntegerField(default=0)
    is_ai = models.BooleanField(default=False)
    ai_model = models.ForeignKey(
        "catalog.AIModel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="player_slots",
        help_text="Per-seat AI model for diagnostic two-AI sessions",
    )
    ai_prompt = models.ForeignKey(
        "catalog.AIPrompt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="player_slots",
        help_text="Per-seat AI prompt for diagnostic two-AI sessions",
    )
    diagnostic_target = models.ForeignKey(
        "DiagnosticTarget",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="player_slots",
        help_text="Diagnostic-only OpenAI-compatible target; exclusive with ai_model",
    )

    class Meta:
        unique_together = ("game", "slot")
        ordering = ["slot"]
        db_table = "game_player_slot"
        constraints = [
            CheckConstraint(
                condition=Q(ai_model__isnull=True) | Q(diagnostic_target__isnull=True),
                name="game_player_slot_model_xor_target",
            ),
        ]

    def __str__(self) -> str:
        name = "AI" if self.is_ai else (self.user.username if self.user else "???")
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
    replay_before = models.JSONField(
        null=True,
        blank=True,
        editable=False,
        help_text="State snapshot before move",
    )
    replay_after = models.JSONField(
        null=True,
        blank=True,
        editable=False,
        help_text="State snapshot after move",
    )
    exchanged_tiles = models.JSONField(
        null=True,
        blank=True,
        editable=False,
        help_text="Exact list of tile tokens exchanged",
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
        username = self.user.username if self.user else "Unknown"
        return f"{username}: {self.body[:40]}"


class ConsumedWsTicket(models.Model):
    """Single-use record for a consumed websocket ticket.

    Stores only a stable hash of the ticket string, never the ticket itself.
    The unique constraint is the replay barrier across processes.
    """

    ticket_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "game_consumed_ws_ticket"

    def __str__(self) -> str:
        return f"ConsumedWsTicket {self.ticket_hash[:8]}"


class DiagnosticRun(models.Model):
    """Persisted diagnostic job bound to a two-AI GameSession."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("abandoned", "Abandoned"),
        ("blocked_dependency", "Blocked by dependency"),
    ]
    ASSIST_MODE_CHOICES = [
        ("assisted", "Assisted"),
        ("authorship", "Authorship"),
    ]
    INSTRUMENT_CHOICES = [
        ("position-set", "Position set"),
        ("full-game", "Full game"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="queued")
    assist_mode = models.CharField(max_length=16, choices=ASSIST_MODE_CHOICES)
    instrument = models.CharField(
        max_length=16,
        choices=INSTRUMENT_CHOICES,
        default="full-game",
    )
    variant_slug = models.CharField(max_length=50)
    seat0_model_id = models.CharField(max_length=200)
    seat1_model_id = models.CharField(max_length=200)
    prompt = models.ForeignKey(
        "catalog.AIPrompt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="diagnostic_runs",
    )
    session = models.ForeignKey(
        GameSession,
        on_delete=models.CASCADE,
        related_name="diagnostic_runs",
    )
    position_set_digest = models.CharField(max_length=64, blank=True, default="")
    max_plies = models.IntegerField(default=0)
    max_provider_requests = models.IntegerField(default=0)
    max_wall_clock_seconds = models.IntegerField(default=0)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    pid = models.IntegerField(null=True, blank=True)
    diagnostic_end_reason = models.CharField(max_length=64, blank=True, default="")
    executed_runtime_mode = models.CharField(max_length=16, blank=True, default="")
    score_authority = models.CharField(max_length=16, blank=True, default="")
    report_path = models.CharField(max_length=512, blank=True, default="")
    log_path = models.CharField(max_length=512, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="diagnostic_runs",
    )
    parameters_json = models.JSONField(default=dict)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "game_diagnostic_run"
        constraints = [
            UniqueConstraint(
                Value(1),
                condition=Q(status__in=["queued", "running"]),
                name="unique_inflight_diagnostic_run",
            )
        ]

    def __str__(self) -> str:
        return f"DiagnosticRun {self.id.hex[:8]} ({self.status})"


class DiagnosticPly(models.Model):
    """One persisted ply of a DiagnosticRun.

    Relational shape B of ``game.diagnostics.PlyMetricRecord``: every
    dataclass field has a column, nullable where the dataclass is Optional
    (None always means not measured — never an invented boolean).
    ⛔ No column name may contain a ``SECRET_KEY_FRAGMENTS`` substring.
    """

    run = models.ForeignKey(
        DiagnosticRun,
        on_delete=models.CASCADE,
        related_name="plies",
    )
    move = models.ForeignKey(
        "Move",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="diagnostic_plies",
        editable=False,
    )
    replay_before = models.JSONField(null=True, blank=True, editable=False)
    replay_after = models.JSONField(null=True, blank=True, editable=False)
    ai_trace = models.JSONField(null=True, blank=True, editable=False)
    ply_index = models.IntegerField(help_text="0-based ply ordinal within the run")
    position_index = models.IntegerField(
        null=True,
        blank=True,
        help_text="Position-set ordinal; None for full-game plies",
    )

    seat_index = models.IntegerField()
    model_id = models.CharField(max_length=200)
    assist_mode = models.CharField(max_length=16)
    score_authority = models.CharField(max_length=16)
    model_authored = models.BooleanField(null=True, blank=True)
    first_validate_valid = models.BooleanField(null=True, blank=True)
    valid_candidate_count = models.IntegerField(null=True, blank=True)
    model_legal_score = models.IntegerField(null=True, blank=True)
    ranked_best_score = models.IntegerField(null=True, blank=True)
    ranked_search_complete = models.BooleanField(null=True, blank=True)
    give_up_while_legal = models.BooleanField(null=True, blank=True)
    playability_status = models.CharField(max_length=32, null=True, blank=True)
    completion_source = models.CharField(max_length=64, null=True, blank=True)
    terminal_cause = models.CharField(max_length=64, null=True, blank=True)
    provider_requests_used = models.IntegerField(null=True, blank=True)
    steps_consumed = models.IntegerField(null=True, blank=True)
    wall_clock_ms = models.IntegerField(null=True, blank=True)
    malformed_or_non_tool = models.BooleanField(null=True, blank=True)
    fallback_attempt_index = models.IntegerField(null=True, blank=True)
    earlier_attempt_failures = models.JSONField(null=True, blank=True)
    executed_runtime_mode = models.CharField(max_length=16, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "game_diagnostic_ply"
        ordering = ["ply_index"]
        constraints = [
            UniqueConstraint(fields=["run", "ply_index"], name="unique_diagnostic_ply_index"),
        ]

    def __str__(self) -> str:
        return f"DiagnosticPly run={self.run_id} ply={self.ply_index} seat={self.seat_index}"
