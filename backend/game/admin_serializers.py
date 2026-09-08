from __future__ import annotations

from typing import Any

from .models import DiagnosticRun, GameSession, PlayerSlot


def _model_for_slot(session: GameSession, slot: PlayerSlot) -> tuple[str | None, str | None]:
    if not slot.is_ai:
        return None, None
    if slot.diagnostic_target_id and slot.diagnostic_target is not None:
        model_id = slot.diagnostic_target.model_id
        return model_id, model_id
    model = slot.ai_model or session.ai_model
    if model is None:
        return None, None
    return model.model_id, model.display_name


def serialize_admin_game(session: GameSession) -> dict[str, Any]:
    slots = list(session.slots.all())
    runs = list(session.diagnostic_runs.all())
    latest: DiagnosticRun | None = runs[-1] if runs else None
    slot_payload = []
    for slot in slots:
        model_id, model_display_name = _model_for_slot(session, slot)
        slot_payload.append(
            {
                "slot": slot.slot,
                "username": slot.user.username if slot.user_id and slot.user else None,
                "score": slot.score,
                "is_ai": slot.is_ai,
                "model_id": model_id,
                "model_display_name": model_display_name,
            }
        )
    diagnostic = None
    if latest is not None:
        diagnostic = {
            "run_id": str(latest.id),
            "status": latest.status,
            "assist_mode": latest.assist_mode,
            "instrument": latest.instrument,
            "model_ids": [latest.seat0_model_id, latest.seat1_model_id],
        }
    return {
        "game_id": str(session.public_id),
        "game_mode": session.game_mode,
        "variant_slug": session.variant_slug,
        "status": session.status,
        "is_diagnostic": session.is_diagnostic,
        "created_at": session.created_at.isoformat(),
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        "move_count": int(getattr(session, "move_count", 0)),
        "winner_slot": session.winner_slot,
        "game_end_reason": session.game_end_reason,
        "slots": slot_payload,
        "diagnostic": diagnostic,
        "diagnostic_run_count": len(runs),
    }
