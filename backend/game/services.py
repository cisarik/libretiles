"""Game service: all game state transitions and validation.

This is the single source of truth for game logic. Views and consumers
delegate to this service; they never manipulate models directly.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.utils import timezone

from catalog.models import AIModel
from catalog.selection import get_selectable_models
from gamecore.board import BOARD_SIZE, Board
from gamecore.game import PlayerState, apply_final_scoring, determine_end_reason
from gamecore.rack import consume_rack
from gamecore.rules import (
    connected_to_existing,
    first_move_must_cover_center,
    extract_all_words,
    no_gaps_in_line,
    placements_in_line,
)
from gamecore.scoring import apply_premium_consumption, score_words
from gamecore.state import build_ai_state_dict
from gamecore.tiles import TileBag
from gamecore.types import Placement
from gamecore.fastdict import load_dictionary

from .models import GameSession, Move, PlayerSlot

_dictionary_fn: Callable[[str], bool] | None = None


def _serialize_last_move(session: GameSession) -> dict[str, Any]:
    last_move = session.moves.order_by("-seq").first()
    if not last_move or last_move.kind != "place":
        return {
            "last_move_cells": [],
            "last_move_points": 0,
            "last_move_words": [],
            "last_move_player_slot": None,
            "last_move_billing": None,
        }

    billing: dict[str, Any] | None = None
    if isinstance(last_move.ai_metadata, dict):
        maybe_billing = last_move.ai_metadata.get("billing")
        if isinstance(maybe_billing, dict):
            billing = maybe_billing

    return {
        "last_move_cells": last_move.placements or [],
        "last_move_points": last_move.points,
        "last_move_words": last_move.words_formed or [],
        "last_move_player_slot": last_move.player_slot.slot if last_move.player_slot_id else None,
        "last_move_billing": billing,
    }


def _get_dictionary() -> Callable[[str], bool]:
    """Lazy-load the primary Collins dictionary into memory (once)."""
    global _dictionary_fn
    if _dictionary_fn is None:
        dict_path = settings.PRIMARY_DICTIONARY_PATH
        _dictionary_fn = load_dictionary(dict_path)
    return _dictionary_fn


def _word_passes_dictionary(contains: Callable[[str], bool], word: str) -> bool:
    """True if *word* is a valid Scrabble play word (Tier 1: local dictionary).

    Rejects empty/whitespace, single letters, and non-ASCII letters defensively.
    All formed words on the board must pass this check (matches desktop scrabgpt intent).
    """
    w = word.strip().casefold()
    if len(w) < 2:
        return False
    if not w.isascii() or not w.isalpha():
        return False
    return bool(contains(w))


def _board_from_session(session: GameSession) -> Board:
    """Reconstruct a Board from the session's persisted state."""
    board = Board(str(settings.PREMIUMS_PATH))
    grid = session.board_state
    if isinstance(grid, list) and len(grid) == 15:
        for r in range(15):
            row = grid[r]
            for c in range(15):
                ch = row[c] if c < len(row) else "."
                if ch != ".":
                    board.cells[r][c].letter = ch
    for pos in session.blanks or []:
        rr, cc = pos["row"], pos["col"]
        board.cells[rr][cc].is_blank = True
    for pos in session.premium_used or []:
        rr, cc = pos["row"], pos["col"]
        board.cells[rr][cc].premium_used = True
    return board


def _bag_from_session(session: GameSession) -> TileBag:
    tiles = list(session.bag_tiles) if session.bag_tiles else []
    return TileBag(seed=session.bag_seed, tiles=tiles, variant=session.variant_slug)


def _persist_board(session: GameSession, board: Board) -> None:
    grid: list[str] = []
    blanks: list[dict[str, int]] = []
    premium_used: list[dict[str, int]] = []
    for r in range(BOARD_SIZE):
        row_chars: list[str] = []
        for c in range(BOARD_SIZE):
            cell = board.cells[r][c]
            if cell.letter:
                row_chars.append(cell.letter)
                if cell.is_blank:
                    blanks.append({"row": r, "col": c})
            else:
                row_chars.append(".")
            if cell.premium_used:
                premium_used.append({"row": r, "col": c})
        grid.append("".join(row_chars))
    session.board_state = grid
    session.blanks = blanks
    session.premium_used = premium_used


def _persist_bag(session: GameSession, bag: TileBag) -> None:
    session.bag_tiles = "".join(bag.tiles)


def _is_board_empty(session: GameSession) -> bool:
    grid = session.board_state
    if not isinstance(grid, list):
        return True
    return all(all(ch == "." for ch in row) for row in grid)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_game(
    *,
    user_id: int,
    game_mode: str = "vs_ai",
    ai_model_id: int | None = None,
    ai_model_model_id: str | None = None,
    variant_slug: str = "english",
) -> dict[str, Any]:
    """Create a new game session with starting draw."""
    seed = random.randint(0, 2**31)
    bag = TileBag(seed=seed, variant=variant_slug)

    # Starting draw to determine who goes first
    a = bag.draw(1)[0]
    b = bag.draw(1)[0]
    bag.put_back([a, b])

    # Lower alphabetical goes first (blank < any letter)
    a_val = "" if a == "?" else a
    b_val = "" if b == "?" else b
    human_first = a_val <= b_val

    human_rack = bag.draw(7)
    ai_rack = bag.draw(7)
    selected_ai_model = None
    if game_mode == "vs_ai":
        selected_ai_model = _resolve_ai_model(
            ai_model_id=ai_model_id,
            ai_model_model_id=ai_model_model_id,
        )

    session = GameSession.objects.create(
        game_mode=game_mode,
        variant_slug=variant_slug,
        board_state=["." * BOARD_SIZE for _ in range(BOARD_SIZE)],
        bag_seed=seed,
        bag_tiles="".join(bag.tiles),
        current_turn_slot=0 if human_first else 1,
        ai_model=selected_ai_model,
    )

    PlayerSlot.objects.create(
        game=session, slot=0, user_id=user_id, rack=human_rack, is_ai=False
    )
    PlayerSlot.objects.create(
        game=session, slot=1, rack=ai_rack, is_ai=(game_mode == "vs_ai")
    )

    return {
        "game_id": str(session.public_id),
        "starting_draw": {"human_tile": a, "ai_tile": b, "human_first": human_first},
        "human_rack": human_rack,
        "current_turn_slot": session.current_turn_slot,
        "ai_model_id": selected_ai_model.model_id if selected_ai_model else None,
        "ai_model_display_name": selected_ai_model.display_name if selected_ai_model else None,
    }


def get_game_state(game_id: str) -> dict[str, Any]:
    """Return full game state for the frontend."""
    session = GameSession.objects.get(public_id=game_id)
    slots = list(session.slots.all().order_by("slot"))
    last_move = _serialize_last_move(session)

    return {
        "game_id": str(session.public_id),
        "status": session.status,
        "game_mode": session.game_mode,
        "variant_slug": session.variant_slug,
        "board": session.board_state,
        "blanks": session.blanks,
        "premium_used": session.premium_used,
        "bag_remaining": len(session.bag_tiles),
        "current_turn_slot": session.current_turn_slot,
        "game_over": session.game_over,
        "game_end_reason": session.game_end_reason,
        "winner_slot": session.winner_slot,
        "ai_model_id": session.ai_model.model_id if session.ai_model else None,
        "ai_model_display_name": session.ai_model.display_name if session.ai_model else None,
        "slots": [
            {
                "slot": s.slot,
                "username": s.user.username if s.user else "AI",
                "score": s.score,
                "rack_count": len(s.rack) if isinstance(s.rack, list) else 0,
                "is_ai": s.is_ai,
                "pass_streak": s.pass_streak,
            }
            for s in slots
        ],
        "move_count": session.moves.count(),
        **last_move,
    }


def get_game_state_for_slot(game_id: str, slot: int) -> dict[str, Any]:
    """Return full game state plus private rack for one slot."""
    state = get_game_state(game_id)
    state["my_rack"] = get_player_rack(game_id, slot)
    return state


def set_game_ai_model(
    *,
    game_id: str,
    user_id: int,
    ai_model_model_id: str,
) -> dict[str, Any]:
    session = GameSession.objects.select_related("ai_model").get(public_id=game_id)
    if not session.slots.filter(user_id=user_id).exists():
        return {"ok": False, "error": "Game not found"}

    selected_ai_model = _resolve_ai_model(
        ai_model_id=None,
        ai_model_model_id=ai_model_model_id,
    )
    if selected_ai_model is None:
        return {"ok": False, "error": "Unknown or unavailable AI model"}

    if session.ai_model_id != selected_ai_model.id:
        session.ai_model = selected_ai_model
        session.save(update_fields=["ai_model", "updated_at"])

    return {
        "ok": True,
        "ai_model_id": selected_ai_model.model_id,
        "ai_model_display_name": selected_ai_model.display_name,
    }


def get_player_rack(game_id: str, slot: int) -> list[str]:
    """Return rack for a specific slot (private data)."""
    ps = PlayerSlot.objects.get(game__public_id=game_id, slot=slot)
    return list(ps.rack) if isinstance(ps.rack, list) else []


def submit_move(
    game_id: str,
    slot: int,
    placements_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate and apply a tile placement move."""
    session = GameSession.objects.select_for_update().get(public_id=game_id)
    if session.game_over:
        return {"ok": False, "error": "Game is already over"}
    if session.current_turn_slot != slot:
        return {"ok": False, "error": "Not your turn"}

    player_slot = session.slots.get(slot=slot)
    board = _board_from_session(session)
    rack = list(player_slot.rack) if isinstance(player_slot.rack, list) else []

    placements = [
        Placement(
            row=p["row"],
            col=p["col"],
            letter=p["letter"],
            blank_as=p.get("blank_as"),
        )
        for p in placements_data
    ]

    # Validate placement rules
    direction = placements_in_line(placements)
    if direction is None:
        return {"ok": False, "error": "Tiles must be in a single row or column"}

    is_first = _is_board_empty(session)
    if is_first:
        if not first_move_must_cover_center(placements):
            return {"ok": False, "error": "First move must cover center square"}
    else:
        if not connected_to_existing(board, placements):
            return {"ok": False, "error": "Move must connect to existing tiles"}

    if not no_gaps_in_line(board, placements, direction):
        return {"ok": False, "error": "Move has gaps"}

    for p in placements:
        if board.cells[p.row][p.col].letter:
            return {"ok": False, "error": f"Cell ({p.row},{p.col}) is occupied"}

    # Place tiles, find words, score
    board.place_letters(placements)
    words_found = extract_all_words(board, placements)
    if not words_found:
        return {"ok": False, "error": "No words formed"}

    words_coords = [(wf.word, wf.letters) for wf in words_found]

    # Word validation (Tier 1: local dictionary — strict)
    contains = _get_dictionary()
    invalid_words = [w for w, _ in words_coords if not _word_passes_dictionary(contains, w)]
    if invalid_words:
        return {
            "ok": False,
            "error": f"Invalid word(s): {', '.join(invalid_words)}",
            "invalid_words": invalid_words,
        }

    total, breakdowns = score_words(board, placements, words_coords)
    bingo = len(placements) == 7
    if bingo:
        total += 50

    apply_premium_consumption(board, placements)

    # Update state
    new_rack = consume_rack(rack, placements)
    bag = _bag_from_session(session)
    draw_count = max(0, 7 - len(new_rack))
    if draw_count and bag.remaining():
        drawn = bag.draw(min(draw_count, bag.remaining()))
        new_rack.extend(drawn)

    player_slot.rack = new_rack
    player_slot.score += total
    player_slot.pass_streak = 0
    player_slot.save()

    _persist_board(session, board)
    _persist_bag(session, bag)
    session.consecutive_passes = 0

    # Record move
    move_seq = session.moves.count() + 1
    Move.objects.create(
        game=session,
        player_slot=player_slot,
        seq=move_seq,
        kind="place",
        placements=placements_data,
        words_formed=[
            {
                "word": bd.word,
                "score": bd.total,
                "multiplier": bd.word_multiplier,
                "coords": [{"row": r, "col": c} for r, c in wf.letters],
            }
            for bd, wf in zip(breakdowns, words_found, strict=False)
        ],
        points=total,
    )

    # Check endgame
    end_info = _check_endgame(session)

    # Advance turn
    if not session.game_over:
        session.current_turn_slot = 1 - session.current_turn_slot

    session.save()

    return {
        "ok": True,
        "points": total,
        "bingo": bingo,
        "words": [{"word": bd.word, "score": bd.total} for bd in breakdowns],
        "new_rack": new_rack,
        "bag_remaining": bag.remaining(),
        "game_over": session.game_over,
        **end_info,
    }


def submit_exchange(
    game_id: str,
    slot: int,
    letters_to_exchange: list[str],
) -> dict[str, Any]:
    """Exchange tiles from rack."""
    session = GameSession.objects.select_for_update().get(public_id=game_id)
    if session.game_over:
        return {"ok": False, "error": "Game is already over"}
    if session.current_turn_slot != slot:
        return {"ok": False, "error": "Not your turn"}

    bag = _bag_from_session(session)
    if bag.remaining() < 7:
        return {"ok": False, "error": "Not enough tiles in bag (need at least 7)"}

    player_slot = session.slots.get(slot=slot)
    rack = list(player_slot.rack) if isinstance(player_slot.rack, list) else []

    # Verify all letters are in rack
    temp_rack = rack.copy()
    for letter in letters_to_exchange:
        if letter in temp_rack:
            temp_rack.remove(letter)
        else:
            return {"ok": False, "error": f"Letter '{letter}' not in rack"}

    new_tiles = bag.exchange(letters_to_exchange)
    new_rack = temp_rack + new_tiles

    player_slot.rack = new_rack
    player_slot.pass_streak += 1
    player_slot.save()

    _persist_bag(session, bag)

    move_seq = session.moves.count() + 1
    Move.objects.create(
        game=session,
        player_slot=player_slot,
        seq=move_seq,
        kind="exchange",
        tiles_exchanged=len(letters_to_exchange),
    )

    end_info = _check_endgame(session)
    if not session.game_over:
        session.current_turn_slot = 1 - session.current_turn_slot
    session.save()

    return {
        "ok": True,
        "new_rack": new_rack,
        "bag_remaining": bag.remaining(),
        "game_over": session.game_over,
        **end_info,
    }


def submit_pass(game_id: str, slot: int) -> dict[str, Any]:
    """Pass the turn."""
    session = GameSession.objects.select_for_update().get(public_id=game_id)
    if session.game_over:
        return {"ok": False, "error": "Game is already over"}
    if session.current_turn_slot != slot:
        return {"ok": False, "error": "Not your turn"}

    player_slot = session.slots.get(slot=slot)
    player_slot.pass_streak += 1
    player_slot.save()

    session.consecutive_passes += 1

    move_seq = session.moves.count() + 1
    Move.objects.create(
        game=session,
        player_slot=player_slot,
        seq=move_seq,
        kind="pass",
    )

    end_info = _check_endgame(session)
    if not session.game_over:
        session.current_turn_slot = 1 - session.current_turn_slot
    session.save()

    return {
        "ok": True,
        "game_over": session.game_over,
        **end_info,
    }


def submit_give_up(*, game_id: str, user_id: int) -> dict[str, Any]:
    """Forfeit the current game as the authenticated human player."""
    session = GameSession.objects.select_for_update().get(public_id=game_id)
    if session.game_over:
        return {"ok": False, "error": "Game is already over"}

    player_slot = session.slots.filter(user_id=user_id).first()
    if player_slot is None:
        return {"ok": False, "error": "Game not found"}

    winner_slot = 1 - player_slot.slot

    move_seq = session.moves.count() + 1
    Move.objects.create(
        game=session,
        player_slot=player_slot,
        seq=move_seq,
        kind="give_up",
    )

    session.game_over = True
    session.status = "abandoned"
    session.game_end_reason = "give_up"
    session.winner_slot = winner_slot
    session.finished_at = timezone.now()
    session.save(
        update_fields=[
            "game_over",
            "status",
            "game_end_reason",
            "winner_slot",
            "finished_at",
            "updated_at",
        ]
    )

    return {
        "ok": True,
        "game_over": True,
        "game_end_reason": session.game_end_reason,
        "winner_slot": session.winner_slot,
        "status": session.status,
        "slot": player_slot.slot,
    }


def get_ai_context(game_id: str) -> dict[str, Any]:
    """Build compact state for AI move generation (called by Vercel API route)."""
    session = GameSession.objects.get(public_id=game_id)
    ai_slot = session.slots.get(is_ai=True)
    human_slot = session.slots.get(is_ai=False)
    board = _board_from_session(session)

    ai_state = build_ai_state_dict(
        board=board,
        ai_rack=list(ai_slot.rack) if isinstance(ai_slot.rack, list) else [],
        human_score=human_slot.score,
        ai_score=ai_slot.score,
        turn="AI",
    )

    compact = (
        "grid:\n"
        + "\n".join(ai_state["grid"])
        + f"\nblanks:{ai_state['blanks']}\n"
        f"ai_rack:{ai_state['ai_rack']}\n"
        f"scores: H={ai_state['human_score']} AI={ai_state['ai_score']}\n"
        f"turn:{ai_state['turn']}\n"
    )

    return {
        "compact_state": compact,
        "ai_state": dict(ai_state),
        "variant": session.variant_slug,
        "ai_model_id": session.ai_model.model_id if session.ai_model else None,
        "ai_model_display_name": session.ai_model.display_name if session.ai_model else None,
        "is_first_move": _is_board_empty(session),
        "ai_move_max_output_tokens": settings.AI_MOVE_MAX_OUTPUT_TOKENS,
        "ai_move_timeout_seconds": settings.AI_MOVE_TIMEOUT_SECONDS,
    }


def validate_move_for_ai(
    game_id: str,
    placements_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate a proposed move without applying it (AI tool endpoint)."""
    session = GameSession.objects.get(public_id=game_id)
    board = _board_from_session(session)

    placements = [
        Placement(
            row=p["row"], col=p["col"], letter=p["letter"], blank_as=p.get("blank_as")
        )
        for p in placements_data
    ]

    direction = placements_in_line(placements)
    if direction is None:
        return {"valid": False, "reason": "Not in a single line"}

    is_first = _is_board_empty(session)
    if is_first and not first_move_must_cover_center(placements):
        return {"valid": False, "reason": "Must cover center"}
    if not is_first and not connected_to_existing(board, placements):
        return {"valid": False, "reason": "Not connected to existing tiles"}
    if not no_gaps_in_line(board, placements, direction):
        return {"valid": False, "reason": "Gaps in line"}
    for p in placements:
        if board.cells[p.row][p.col].letter:
            return {"valid": False, "reason": f"Cell ({p.row},{p.col}) occupied"}

    board.place_letters(placements)
    words_found = extract_all_words(board, placements)
    if not words_found:
        return {"valid": False, "reason": "No words formed"}

    words_coords = [(wf.word, wf.letters) for wf in words_found]
    total, breakdowns = score_words(board, placements, words_coords)
    if len(placements) == 7:
        total += 50

    contains = _get_dictionary()
    word_results = [
        {"word": w, "valid": _word_passes_dictionary(contains, w)} for w, _ in words_coords
    ]

    return {
        "valid": all(wr["valid"] for wr in word_results),
        "total_score": total,
        "words": word_results,
        "breakdowns": [
            {"word": bd.word, "score": bd.total, "multiplier": bd.word_multiplier}
            for bd in breakdowns
        ],
    }


def validate_words(words: list[str]) -> list[dict[str, Any]]:
    """Tier 1 word validation using the local Collins 2019 dictionary."""
    contains = _get_dictionary()
    return [
        {"word": w, "valid": _word_passes_dictionary(contains, w), "source": "collins2019"}
        for w in words
    ]


def _resolve_ai_model(
    *,
    ai_model_id: int | None,
    ai_model_model_id: str | None,
) -> AIModel | None:
    selectable_models = get_selectable_models()

    if ai_model_model_id:
        for model in selectable_models:
            if model.model_id == ai_model_model_id:
                return model

    if ai_model_id is not None:
        for model in selectable_models:
            if model.id == ai_model_id:
                return model

    return selectable_models[0] if selectable_models else None


def _check_endgame(session: GameSession) -> dict[str, Any]:
    """Check if game has ended and apply final scoring if so."""
    slots = list(session.slots.all().order_by("slot"))
    racks = {str(s.slot): list(s.rack) if isinstance(s.rack, list) else [] for s in slots}
    pass_streaks = {str(s.slot): s.pass_streak for s in slots}
    bag_remaining = len(session.bag_tiles)

    reason = determine_end_reason(
        bag_remaining=bag_remaining,
        racks=racks,
        pass_streaks=pass_streaks,
        no_moves_available=False,
    )

    if reason is None:
        return {}

    # Apply final scoring
    players = [
        PlayerState(
            name=str(s.slot),
            rack=list(s.rack) if isinstance(s.rack, list) else [],
            score=s.score,
        )
        for s in slots
    ]
    leftover = apply_final_scoring(players)

    for s, ps in zip(slots, players):
        s.score = ps.score
        s.save()

    session.game_over = True
    session.game_end_reason = reason.name
    session.finished_at = timezone.now()

    scores = {str(s.slot): s.score for s in slots}
    if scores:
        winner_slot = max(scores, key=lambda k: scores[k])
        session.winner_slot = int(winner_slot)

    return {
        "game_end_reason": reason.name,
        "final_scores": {str(s.slot): s.score for s in slots},
        "leftover_points": leftover,
        "winner_slot": session.winner_slot,
    }
