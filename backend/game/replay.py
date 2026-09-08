from __future__ import annotations

from copy import deepcopy
from typing import Any

from gamecore.variant_store import load_variant

from .models import DiagnosticPly, GameSession, Move, PlayerSlot
from .serializers import sanitize_ai_metadata


def _racks_and_scores(session: GameSession) -> tuple[list[list[str]], list[int]]:
    # State transitions may have updated separate PlayerSlot instances while
    # the session still carries a prefetched relation cache.
    slots = {slot.slot: slot for slot in session.slots.order_by("slot")}
    racks = [
        list(slots[index].rack) if index in slots and isinstance(slots[index].rack, list) else []
        for index in (0, 1)
    ]
    scores = [int(slots[index].score) if index in slots else 0 for index in (0, 1)]
    return racks, scores


def build_snapshot(session: GameSession) -> dict[str, Any]:
    racks, scores = _racks_and_scores(session)
    return {
        "board": deepcopy(session.board_state),
        "premium_used": deepcopy(session.premium_used),
        "racks": racks,
        "scores": scores,
        "bag_remaining": len(session.bag_tiles) if isinstance(session.bag_tiles, list) else 0,
        "current_turn_slot": session.current_turn_slot,
    }


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


def _player_payload(session: GameSession, slot: PlayerSlot) -> dict[str, Any]:
    model_id, display_name = _model_for_slot(session, slot)
    return {
        "slot": slot.slot,
        "username": slot.user.username if slot.user_id and slot.user is not None else None,
        "score": slot.score,
        "is_ai": slot.is_ai,
        "model_id": model_id,
        "model_display_name": display_name,
    }


def _diagnostic_ply_payload(ply: DiagnosticPly) -> dict[str, Any]:
    return {
        "id": ply.id,
        "run_id": str(ply.run_id),
        "ply_index": ply.ply_index,
        "position_index": ply.position_index,
        "seat_index": ply.seat_index,
        "model_id": ply.model_id,
        "assist_mode": ply.assist_mode,
        "score_authority": ply.score_authority,
        "model_authored": ply.model_authored,
        "first_validate_valid": ply.first_validate_valid,
        "valid_candidate_count": ply.valid_candidate_count,
        "model_legal_score": ply.model_legal_score,
        "ranked_best_score": ply.ranked_best_score,
        "ranked_search_complete": ply.ranked_search_complete,
        "give_up_while_legal": ply.give_up_while_legal,
        "playability_status": ply.playability_status,
        "completion_source": ply.completion_source,
        "terminal_cause": ply.terminal_cause,
        "provider_requests_used": ply.provider_requests_used,
        "steps_consumed": ply.steps_consumed,
        "wall_clock_ms": ply.wall_clock_ms,
        "malformed_or_non_tool": ply.malformed_or_non_tool,
        "fallback_attempt_index": ply.fallback_attempt_index,
        "earlier_attempt_failures": deepcopy(ply.earlier_attempt_failures),
        "executed_runtime_mode": ply.executed_runtime_mode,
        "ai_trace": deepcopy(ply.ai_trace),
        "created_at": ply.created_at.isoformat(),
    }


def _board_delta(move: Move) -> list[dict[str, Any]]:
    if move.kind != "place" or not isinstance(move.placements, list):
        return []
    delta: list[dict[str, Any]] = []
    for item in move.placements:
        if not isinstance(item, dict):
            continue
        blank_as = item.get("blank_as")
        letter = item.get("letter")
        delta.append(
            {
                "row": item.get("row"),
                "col": item.get("col"),
                "token": "?" if blank_as else letter,
                "blank_as": blank_as,
            }
        )
    return delta


def _move_payload(move: Move) -> dict[str, Any]:
    after = move.replay_after if isinstance(move.replay_after, dict) else None
    diagnostic_plies = list(move.diagnostic_plies.all())
    return {
        "seq": move.seq,
        "player_slot": move.player_slot.slot,
        "kind": move.kind,
        "created_at": move.created_at.isoformat(),
        "placements": deepcopy(move.placements) if isinstance(move.placements, list) else [],
        "words_formed": (
            deepcopy(move.words_formed) if isinstance(move.words_formed, list) else []
        ),
        "points": move.points,
        "tiles_exchanged": move.tiles_exchanged,
        "exchanged_tiles": (
            deepcopy(move.exchanged_tiles) if isinstance(move.exchanged_tiles, list) else None
        ),
        "cumulative_scores": deepcopy(after.get("scores")) if after else [None, None],
        "racks": deepcopy(after.get("racks")) if after else [None, None],
        "board_delta": _board_delta(move),
        "ai_metadata": sanitize_ai_metadata(move.ai_metadata),
        "diagnostic_ply": (
            _diagnostic_ply_payload(diagnostic_plies[0])
            if len(diagnostic_plies) == 1
            else None
        ),
    }


def build_replay_payload(session: GameSession) -> dict[str, Any]:
    variant = load_variant(session.variant_slug)
    slots = list(session.slots.all())
    moves = list(session.moves.all())
    initial = (
        deepcopy(session.replay_initial_state)
        if isinstance(session.replay_initial_state, dict)
        else None
    )
    complete = initial is not None and all(
        isinstance(move.replay_before, dict) and isinstance(move.replay_after, dict)
        for move in moves
    )
    current = build_snapshot(session)
    return {
        "replay_schema_version": 1,
        "game_id": str(session.public_id),
        "variant_slug": session.variant_slug,
        "game_mode": session.game_mode,
        "status": session.status,
        "winner_slot": session.winner_slot,
        "game_end_reason": session.game_end_reason,
        "created_at": session.created_at.isoformat(),
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        "tile_points": dict(variant.tile_points),
        "alphabet": list(variant.playable_letters),
        "players": [_player_payload(session, slot) for slot in slots],
        "initial_state": {
            "initial_board": deepcopy(initial.get("board")) if initial else None,
            "initial_racks": deepcopy(initial.get("racks")) if initial else [None, None],
            "initial_scores": deepcopy(initial.get("scores")) if initial else [None, None],
            "starting_turn_slot": initial.get("current_turn_slot") if initial else None,
            "bag_seed": session.bag_seed,
        },
        "plies": [_move_payload(move) for move in moves],
        "final_state": {
            "board": current["board"],
            "racks": current["racks"],
            "scores": current["scores"],
        },
        "replay_status": "complete" if complete else "partial",
    }
