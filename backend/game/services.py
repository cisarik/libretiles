"""Game service: all game state transitions and validation.

Views and websocket consumers delegate to this service; they never manipulate
game state directly.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.core import signing
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from catalog.models import AIModel
from catalog.selection import get_selectable_models
from gamecore.board import BOARD_SIZE, Board
from gamecore.fastdict import load_dictionary
from gamecore.game import PlayerState, apply_final_scoring, determine_end_reason
from gamecore.rack import consume_rack
from gamecore.rules import (
    connected_to_existing,
    extract_all_words,
    first_move_must_cover_center,
    no_gaps_in_line,
    placements_in_line,
)
from gamecore.scoring import apply_premium_consumption, score_words
from gamecore.state import build_ai_state_dict
from gamecore.tiles import TileBag
from gamecore.types import Placement

from .models import ChatMessage, GameSession, Move, PlayerSlot
from . import realtime

CHAT_HISTORY_LIMIT = 50
WS_TICKET_SALT = "game.websocket.ticket"
WS_TICKET_MAX_AGE_SECONDS = int(getattr(settings, "GAME_WS_TICKET_MAX_AGE_SECONDS", 60))
_dictionary_fn: Callable[[str], bool] | None = None


class GameNotFoundError(Exception):
    """Raised when a user is not allowed to access a game."""


def _empty_board_state() -> list[str]:
    return ["." * BOARD_SIZE for _ in range(BOARD_SIZE)]


def _serialize_last_move(session: GameSession) -> dict[str, Any]:
    last_move = session.moves.select_related("player_slot").order_by("-seq").first()
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
    global _dictionary_fn
    if _dictionary_fn is None:
        _dictionary_fn = load_dictionary(settings.PRIMARY_DICTIONARY_PATH)
    return _dictionary_fn


def _word_passes_dictionary(contains: Callable[[str], bool], word: str) -> bool:
    w = word.strip().casefold()
    if len(w) < 2:
        return False
    if not w.isascii() or not w.isalpha():
        return False
    return bool(contains(w))


def _board_from_session(session: GameSession) -> Board:
    board = Board(str(settings.PREMIUMS_PATH))
    grid = session.board_state
    if isinstance(grid, list) and len(grid) == BOARD_SIZE:
        for r in range(BOARD_SIZE):
            row = grid[r]
            for c in range(BOARD_SIZE):
                ch = row[c] if c < len(row) else "."
                if ch != ".":
                    board.cells[r][c].letter = ch
    for pos in session.blanks or []:
        board.cells[pos["row"]][pos["col"]].is_blank = True
    for pos in session.premium_used or []:
        board.cells[pos["row"]][pos["col"]].premium_used = True
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


def _serialize_slot(slot: PlayerSlot) -> dict[str, Any]:
    username: str | None
    if slot.is_ai:
        username = slot.user.username if slot.user else "AI"  # type: ignore[union-attr]
    else:
        username = slot.user.username if slot.user else None  # type: ignore[union-attr]

    return {
        "slot": slot.slot,
        "username": username,
        "score": slot.score,
        "rack_count": len(slot.rack) if isinstance(slot.rack, list) else 0,
        "is_ai": slot.is_ai,
        "pass_streak": slot.pass_streak,
    }


def _serialize_chat_message(
    message: ChatMessage,
    *,
    slot_by_user_id: dict[int, int],
    current_user_id: int,
) -> dict[str, Any]:
    author_slot = slot_by_user_id.get(message.user_id or -1)
    return {
        "id": message.id,
        "author_slot": author_slot,
        "author_username": message.user.username if message.user else "Unknown",  # type: ignore[union-attr]
        "body": message.body,
        "created_at": message.created_at.isoformat(),
        "mine": message.user_id == current_user_id,
    }


def _build_state(session: GameSession, *, current_user_id: int, my_slot: PlayerSlot) -> dict[str, Any]:
    slots = list(session.slots.all().order_by("slot"))
    slot_by_user_id = {
        slot.user_id: slot.slot
        for slot in slots
        if slot.user_id is not None
    }
    recent_messages = list(
        session.chat_messages.select_related("user").order_by("-created_at")[:CHAT_HISTORY_LIMIT]
    )
    recent_messages.reverse()

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
        "my_slot": my_slot.slot,
        "my_rack": list(my_slot.rack) if isinstance(my_slot.rack, list) else [],
        "ai_model_id": session.ai_model.model_id if session.ai_model else None,
        "ai_model_display_name": session.ai_model.display_name if session.ai_model else None,
        "slots": [_serialize_slot(slot) for slot in slots],
        "move_count": session.moves.count(),
        "chat_messages": [
            _serialize_chat_message(
                message,
                slot_by_user_id=slot_by_user_id,
                current_user_id=current_user_id,
            )
            for message in recent_messages
        ],
        **_serialize_last_move(session),
    }


def _load_session_for_user(
    *,
    game_id: str,
    user_id: int,
    select_for_update: bool = False,
) -> tuple[GameSession, PlayerSlot]:
    queryset = GameSession.objects.select_related("ai_model").prefetch_related(
        "slots__user",
        "chat_messages__user",
    )
    if select_for_update:
        queryset = queryset.select_for_update()

    try:
        session = queryset.get(public_id=game_id, slots__user_id=user_id)
    except GameSession.DoesNotExist as exc:
        raise GameNotFoundError("Game not found") from exc

    player_slot = session.slots.filter(user_id=user_id).first()
    if player_slot is None:
        raise GameNotFoundError("Game not found")
    return session, player_slot


def _load_vs_ai_session(
    *,
    game_id: str,
    user_id: int,
    select_for_update: bool = False,
) -> tuple[GameSession, PlayerSlot, PlayerSlot]:
    session, player_slot = _load_session_for_user(
        game_id=game_id,
        user_id=user_id,
        select_for_update=select_for_update,
    )
    if session.game_mode != "vs_ai":
        raise GameNotFoundError("Game not found")
    ai_slot = session.slots.filter(is_ai=True).first()
    if ai_slot is None:
        raise GameNotFoundError("Game not found")
    return session, player_slot, ai_slot


def _serialize_ai_starting_draw(draw: dict[str, Any]) -> dict[str, Any]:
    return {
        "human_tile": draw["slot0_tile"],
        "ai_tile": draw["slot1_tile"],
        "human_first": draw["slot0_first"],
    }


def _perform_starting_draw(bag: TileBag) -> dict[str, Any]:
    slot0_tile = bag.draw(1)[0]
    slot1_tile = bag.draw(1)[0]
    bag.put_back([slot0_tile, slot1_tile])

    slot0_value = "" if slot0_tile == "?" else slot0_tile
    slot1_value = "" if slot1_tile == "?" else slot1_tile
    return {
        "slot0_tile": slot0_tile,
        "slot1_tile": slot1_tile,
        "slot0_first": slot0_value <= slot1_value,
    }


def _initialize_session(session: GameSession, *, slot0: PlayerSlot, slot1: PlayerSlot) -> dict[str, Any]:
    seed = random.randint(0, 2**31)
    bag = TileBag(seed=seed, variant=session.variant_slug)
    draw = _perform_starting_draw(bag)

    slot0.rack = bag.draw(7)
    slot1.rack = bag.draw(7)
    slot0.score = 0
    slot1.score = 0
    slot0.pass_streak = 0
    slot1.pass_streak = 0
    slot0.save(update_fields=["rack", "score", "pass_streak"])
    slot1.save(update_fields=["rack", "score", "pass_streak"])

    session.board_state = _empty_board_state()
    session.blanks = []
    session.premium_used = []
    session.bag_seed = seed
    session.bag_tiles = "".join(bag.tiles)
    session.current_turn_slot = 0 if draw["slot0_first"] else 1
    session.consecutive_passes = 0
    session.status = "active"
    session.game_over = False
    session.game_end_reason = ""
    session.winner_slot = None
    session.started_at = timezone.now()
    session.finished_at = None
    session.save(
        update_fields=[
            "board_state",
            "blanks",
            "premium_used",
            "bag_seed",
            "bag_tiles",
            "current_turn_slot",
            "consecutive_passes",
            "status",
            "game_over",
            "game_end_reason",
            "winner_slot",
            "started_at",
            "finished_at",
            "updated_at",
        ]
    )
    return draw


def _check_active_turn(session: GameSession, player_slot: PlayerSlot) -> str | None:
    if session.status == "waiting":
        return "Game is waiting for an opponent"
    if session.game_over:
        return "Game is already over"
    if session.status != "active":
        return "Game is not active"
    if session.current_turn_slot is None or session.current_turn_slot != player_slot.slot:
        return "Not your turn"
    return None


def _create_move(
    *,
    session: GameSession,
    player_slot: PlayerSlot,
    kind: str,
    placements: list[dict[str, Any]] | None = None,
    words_formed: list[dict[str, Any]] | None = None,
    tiles_exchanged: int = 0,
    points: int = 0,
) -> Move:
    return Move.objects.create(
        game=session,
        player_slot=player_slot,
        seq=session.moves.count() + 1,
        kind=kind,
        placements=placements or [],
        words_formed=words_formed or [],
        tiles_exchanged=tiles_exchanged,
        points=points,
    )


def _next_turn_for(slot: int) -> int:
    return 1 - slot


def _check_endgame(session: GameSession) -> dict[str, Any]:
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

    players = [
        PlayerState(
            name=str(slot.slot),
            rack=list(slot.rack) if isinstance(slot.rack, list) else [],
            score=slot.score,
        )
        for slot in slots
    ]
    leftover = apply_final_scoring(players)

    for slot, player in zip(slots, players, strict=False):
        slot.score = player.score
        slot.save(update_fields=["score"])

    session.game_over = True
    session.status = "finished"
    session.game_end_reason = reason.name
    session.finished_at = timezone.now()

    scores = {str(slot.slot): slot.score for slot in slots}
    if scores:
        session.winner_slot = int(max(scores, key=lambda key: scores[key]))

    return {
        "game_end_reason": reason.name,
        "final_scores": {str(slot.slot): slot.score for slot in slots},
        "leftover_points": leftover,
        "winner_slot": session.winner_slot,
    }


def _submit_move_locked(
    *,
    session: GameSession,
    player_slot: PlayerSlot,
    placements_data: list[dict[str, Any]],
) -> dict[str, Any]:
    error = _check_active_turn(session, player_slot)
    if error:
        return {"ok": False, "error": error}

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

    direction = placements_in_line(placements)
    if direction is None:
        return {"ok": False, "error": "Tiles must be in a single row or column"}

    is_first = _is_board_empty(session)
    if is_first:
        if not first_move_must_cover_center(placements):
            return {"ok": False, "error": "First move must cover center square"}
    elif not connected_to_existing(board, placements):
        return {"ok": False, "error": "Move must connect to existing tiles"}

    if not no_gaps_in_line(board, placements, direction):
        return {"ok": False, "error": "Move has gaps"}

    for placement in placements:
        if board.cells[placement.row][placement.col].letter:
            return {
                "ok": False,
                "error": f"Cell ({placement.row},{placement.col}) is occupied",
            }

    board.place_letters(placements)
    words_found = extract_all_words(board, placements)
    if not words_found:
        return {"ok": False, "error": "No words formed"}

    words_coords = [(word.word, word.letters) for word in words_found]
    contains = _get_dictionary()
    invalid_words = [word for word, _ in words_coords if not _word_passes_dictionary(contains, word)]
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

    new_rack = consume_rack(rack, placements)
    bag = _bag_from_session(session)
    draw_count = max(0, 7 - len(new_rack))
    if draw_count and bag.remaining():
        new_rack.extend(bag.draw(min(draw_count, bag.remaining())))

    player_slot.rack = new_rack
    player_slot.score += total
    player_slot.pass_streak = 0
    player_slot.save(update_fields=["rack", "score", "pass_streak"])

    _persist_board(session, board)
    _persist_bag(session, bag)
    session.consecutive_passes = 0

    _create_move(
        session=session,
        player_slot=player_slot,
        kind="place",
        placements=placements_data,
        words_formed=[
            {
                "word": breakdown.word,
                "score": breakdown.total,
                "multiplier": breakdown.word_multiplier,
                "coords": [{"row": row, "col": col} for row, col in word.letters],
            }
            for breakdown, word in zip(breakdowns, words_found, strict=False)
        ],
        points=total,
    )

    end_info = _check_endgame(session)
    if not session.game_over:
        session.current_turn_slot = _next_turn_for(player_slot.slot)
    session.save()

    realtime.publish_game_state_refresh(session, event_name="game_state")
    return {
        "ok": True,
        "points": total,
        "bingo": bingo,
        "words": [{"word": breakdown.word, "score": breakdown.total} for breakdown in breakdowns],
        "new_rack": new_rack,
        "bag_remaining": bag.remaining(),
        "game_over": session.game_over,
        **end_info,
    }


def _submit_exchange_locked(
    *,
    session: GameSession,
    player_slot: PlayerSlot,
    letters_to_exchange: list[str],
) -> dict[str, Any]:
    error = _check_active_turn(session, player_slot)
    if error:
        return {"ok": False, "error": error}

    bag = _bag_from_session(session)
    if bag.remaining() < 7:
        return {"ok": False, "error": "Not enough tiles in bag (need at least 7)"}

    rack = list(player_slot.rack) if isinstance(player_slot.rack, list) else []
    remaining_rack = rack.copy()
    for letter in letters_to_exchange:
        if letter in remaining_rack:
            remaining_rack.remove(letter)
        else:
            return {"ok": False, "error": f"Letter '{letter}' not in rack"}

    new_rack = remaining_rack + bag.exchange(letters_to_exchange)
    player_slot.rack = new_rack
    player_slot.pass_streak += 1
    player_slot.save(update_fields=["rack", "pass_streak"])

    _persist_bag(session, bag)
    session.consecutive_passes += 1
    _create_move(
        session=session,
        player_slot=player_slot,
        kind="exchange",
        tiles_exchanged=len(letters_to_exchange),
    )

    end_info = _check_endgame(session)
    if not session.game_over:
        session.current_turn_slot = _next_turn_for(player_slot.slot)
    session.save()

    realtime.publish_game_state_refresh(session, event_name="game_state")
    return {
        "ok": True,
        "new_rack": new_rack,
        "bag_remaining": bag.remaining(),
        "game_over": session.game_over,
        **end_info,
    }


def _submit_pass_locked(*, session: GameSession, player_slot: PlayerSlot) -> dict[str, Any]:
    error = _check_active_turn(session, player_slot)
    if error:
        return {"ok": False, "error": error}

    player_slot.pass_streak += 1
    player_slot.save(update_fields=["pass_streak"])
    session.consecutive_passes += 1
    _create_move(session=session, player_slot=player_slot, kind="pass")

    end_info = _check_endgame(session)
    if not session.game_over:
        session.current_turn_slot = _next_turn_for(player_slot.slot)
    session.save()

    realtime.publish_game_state_refresh(session, event_name="game_state")
    return {"ok": True, "game_over": session.game_over, **end_info}


def create_game(
    *,
    user_id: int,
    game_mode: str = "vs_ai",
    ai_model_id: int | None = None,
    ai_model_model_id: str | None = None,
    variant_slug: str = "english",
) -> dict[str, Any]:
    if game_mode != "vs_ai":
        return {"ok": False, "error": "Human multiplayer starts from the queue"}

    selected_ai_model = _resolve_ai_model(
        ai_model_id=ai_model_id,
        ai_model_model_id=ai_model_model_id,
    )
    session = GameSession.objects.create(
        game_mode="vs_ai",
        status="active",
        variant_slug=variant_slug,
        board_state=_empty_board_state(),
        blanks=[],
        premium_used=[],
        current_turn_slot=None,
        ai_model=selected_ai_model,
    )
    human_slot = PlayerSlot.objects.create(game=session, slot=0, user_id=user_id, is_ai=False, rack=[])
    ai_slot = PlayerSlot.objects.create(game=session, slot=1, is_ai=True, rack=[])
    draw = _initialize_session(session, slot0=human_slot, slot1=ai_slot)

    human_slot.refresh_from_db()
    return {
        "game_id": str(session.public_id),
        "starting_draw": _serialize_ai_starting_draw(draw),
        "human_rack": list(human_slot.rack) if isinstance(human_slot.rack, list) else [],
        "current_turn_slot": session.current_turn_slot,
        "ai_model_id": selected_ai_model.model_id if selected_ai_model else None,
        "ai_model_display_name": selected_ai_model.display_name if selected_ai_model else None,
    }


def get_player_slot_for_user(game_id: str, user_id: int) -> int:
    _, player_slot = _load_session_for_user(game_id=game_id, user_id=user_id)
    return player_slot.slot


def get_game_state_for_user(game_id: str, user_id: int) -> dict[str, Any]:
    session, player_slot = _load_session_for_user(game_id=game_id, user_id=user_id)
    return _build_state(session, current_user_id=user_id, my_slot=player_slot)


def _history_opponent_label(*, session: GameSession, my_slot: PlayerSlot) -> str:
    opponent_slot = next(
        (slot for slot in session.slots.all() if slot.slot != my_slot.slot),
        None,
    )
    if session.game_mode == "vs_ai":
        if session.ai_model:
            return session.ai_model.display_name
        if opponent_slot and opponent_slot.user:
            return opponent_slot.user.username
        return "AI"
    if opponent_slot is None or opponent_slot.user is None:
        return "Waiting opponent"
    return opponent_slot.user.username


def _history_outcome(
    *,
    session: GameSession,
    my_slot: PlayerSlot,
    give_up_slot_by_game_id: dict[int, int],
) -> str:
    if session.status == "waiting":
        return "waiting"
    if session.status == "active" and not session.game_over:
        return "in_progress"
    if session.game_end_reason == "give_up":
        if give_up_slot_by_game_id.get(session.id) == my_slot.slot:
            return "gave_up"
    if session.winner_slot is None:
        return "abandoned"
    return "won" if session.winner_slot == my_slot.slot else "lost"


def _serialize_game_history_item(
    *,
    session: GameSession,
    my_slot: PlayerSlot,
    give_up_slot_by_game_id: dict[int, int],
) -> dict[str, Any]:
    opponent_slot = next(
        (slot for slot in session.slots.all() if slot.slot != my_slot.slot),
        None,
    )
    return {
        "game_id": str(session.public_id),
        "game_mode": session.game_mode,
        "status": session.status,
        "outcome": _history_outcome(
            session=session,
            my_slot=my_slot,
            give_up_slot_by_game_id=give_up_slot_by_game_id,
        ),
        "opponent_label": _history_opponent_label(session=session, my_slot=my_slot),
        "ai_model_display_name": session.ai_model.display_name if session.ai_model else None,
        "my_score": my_slot.score,
        "opponent_score": opponent_slot.score if opponent_slot else 0,
        "move_count": int(getattr(session, "move_count", 0)),
        "is_my_turn": (
            session.status == "active"
            and not session.game_over
            and session.current_turn_slot == my_slot.slot
        ),
        "winner_slot": session.winner_slot,
        "game_end_reason": session.game_end_reason,
        "created_at": session.created_at.isoformat(),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        "updated_at": session.updated_at.isoformat(),
    }


def list_games_for_user(
    *,
    user_id: int,
    game_mode: str = "all",
    page: int = 1,
    page_size: int = 8,
) -> dict[str, Any]:
    queryset = (
        GameSession.objects.filter(slots__user_id=user_id)
        .select_related("ai_model")
        .prefetch_related("slots__user")
        .annotate(move_count=Count("moves", distinct=True))
        .order_by("-updated_at")
    )
    if game_mode != "all":
        queryset = queryset.filter(game_mode=game_mode)

    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    sessions = list(page_obj.object_list)

    my_slot_by_game_id: dict[int, PlayerSlot] = {}
    for session in sessions:
        my_slot = next((slot for slot in session.slots.all() if slot.user_id == user_id), None)
        if my_slot is not None:
            my_slot_by_game_id[session.id] = my_slot

    give_up_slot_by_game_id: dict[int, int] = {}
    give_up_game_ids = [session.id for session in sessions if session.game_end_reason == "give_up"]
    if give_up_game_ids:
        give_up_slot_by_game_id = {
            row["game_id"]: row["player_slot__slot"]
            for row in Move.objects.filter(game_id__in=give_up_game_ids, kind="give_up")
            .values("game_id", "player_slot__slot")
        }

    items = [
        _serialize_game_history_item(
            session=session,
            my_slot=my_slot_by_game_id[session.id],
            give_up_slot_by_game_id=give_up_slot_by_game_id,
        )
        for session in sessions
        if session.id in my_slot_by_game_id
    ]

    return {
        "items": items,
        "page": page_obj.number,
        "page_size": page_obj.paginator.per_page,
        "total": page_obj.paginator.count,
        "total_pages": page_obj.paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "game_mode": game_mode,
    }


def set_game_ai_model(
    *,
    game_id: str,
    user_id: int,
    ai_model_model_id: str,
) -> dict[str, Any]:
    session, _player_slot, _ai_slot = _load_vs_ai_session(game_id=game_id, user_id=user_id)
    selected_ai_model = _resolve_ai_model(ai_model_id=None, ai_model_model_id=ai_model_model_id)
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


def build_ws_ticket(*, game_id: str, user_id: int) -> dict[str, Any]:
    _load_session_for_user(game_id=game_id, user_id=user_id)
    ticket = signing.dumps(
        {"game_id": game_id, "user_id": user_id},
        salt=WS_TICKET_SALT,
        compress=True,
    )
    return {
        "ok": True,
        "ticket": ticket,
        "expires_in": WS_TICKET_MAX_AGE_SECONDS,
    }


def verify_ws_ticket(*, game_id: str, ticket: str) -> int:
    payload = signing.loads(
        ticket,
        salt=WS_TICKET_SALT,
        max_age=WS_TICKET_MAX_AGE_SECONDS,
    )
    payload_game_id = str(payload.get("game_id", ""))
    payload_user_id = int(payload.get("user_id"))
    if payload_game_id != game_id:
        raise GameNotFoundError("Game not found")
    _load_session_for_user(game_id=game_id, user_id=payload_user_id)
    return payload_user_id


def join_human_queue(*, user_id: int, variant_slug: str = "english") -> dict[str, Any]:
    with transaction.atomic():
        existing_waiting = (
            GameSession.objects.select_for_update()
            .filter(
                game_mode="vs_human",
                status="waiting",
                variant_slug=variant_slug,
                slots__user_id=user_id,
            )
            .order_by("created_at")
            .first()
        )
        if existing_waiting is not None:
            state = get_game_state_for_user(str(existing_waiting.public_id), user_id)
            return {"ok": True, "waiting": True, "matched": False, "state": state}

        waiting_queryset = (
            GameSession.objects.select_for_update()
            .filter(game_mode="vs_human", status="waiting", variant_slug=variant_slug)
            .order_by("created_at")
            .prefetch_related("slots__user", "chat_messages__user")
        )
        if connection.vendor == "postgresql":
            waiting_queryset = waiting_queryset.select_for_update(skip_locked=True)

        for session in waiting_queryset:
            slots = list(session.slots.all().order_by("slot"))
            if any(slot.user_id == user_id for slot in slots):
                continue
            open_slot = next((slot for slot in slots if not slot.is_ai and slot.user_id is None), None)
            assigned_count = sum(1 for slot in slots if slot.user_id is not None)
            if open_slot is None or assigned_count != 1:
                continue

            open_slot.user_id = user_id
            open_slot.save(update_fields=["user"])
            slot0 = next(slot for slot in slots if slot.slot == 0)
            slot1 = open_slot if open_slot.slot == 1 else next(slot for slot in slots if slot.slot == 1)
            _initialize_session(session, slot0=slot0, slot1=slot1)
            realtime.publish_game_state_refresh(session, event_name="match_found")
            state = get_game_state_for_user(str(session.public_id), user_id)
            return {"ok": True, "waiting": False, "matched": True, "state": state}

        session = GameSession.objects.create(
            game_mode="vs_human",
            status="waiting",
            variant_slug=variant_slug,
            board_state=_empty_board_state(),
            blanks=[],
            premium_used=[],
            current_turn_slot=None,
        )
        PlayerSlot.objects.create(game=session, slot=0, user_id=user_id, is_ai=False, rack=[])
        PlayerSlot.objects.create(game=session, slot=1, is_ai=False, rack=[])
        state = get_game_state_for_user(str(session.public_id), user_id)
        return {"ok": True, "waiting": True, "matched": False, "state": state}


def cancel_human_queue(*, game_id: str, user_id: int) -> dict[str, Any]:
    with transaction.atomic():
        session, player_slot = _load_session_for_user(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        if session.game_mode != "vs_human" or session.status != "waiting":
            return {"ok": False, "error": "Queue entry is no longer waiting"}
        if player_slot.slot != 0:
            return {"ok": False, "error": "Only the waiting host can cancel"}
        second_player = session.slots.exclude(pk=player_slot.pk).filter(user__isnull=False).exists()
        if second_player:
            return {"ok": False, "error": "Queue entry is no longer waiting"}

        session.status = "abandoned"
        session.game_over = True
        session.game_end_reason = "queue_cancelled"
        session.finished_at = timezone.now()
        session.save(
            update_fields=["status", "game_over", "game_end_reason", "finished_at", "updated_at"]
        )
        realtime.publish_game_state_refresh(session, event_name="game_state")
        return {"ok": True}


def submit_move_for_user(
    game_id: str,
    user_id: int,
    placements_data: list[dict[str, Any]],
) -> dict[str, Any]:
    with transaction.atomic():
        session, player_slot = _load_session_for_user(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        return _submit_move_locked(
            session=session,
            player_slot=player_slot,
            placements_data=placements_data,
        )


def submit_exchange_for_user(
    game_id: str,
    user_id: int,
    letters_to_exchange: list[str],
) -> dict[str, Any]:
    with transaction.atomic():
        session, player_slot = _load_session_for_user(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        return _submit_exchange_locked(
            session=session,
            player_slot=player_slot,
            letters_to_exchange=letters_to_exchange,
        )


def submit_pass_for_user(game_id: str, user_id: int) -> dict[str, Any]:
    with transaction.atomic():
        session, player_slot = _load_session_for_user(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        return _submit_pass_locked(session=session, player_slot=player_slot)


def submit_give_up_for_user(*, game_id: str, user_id: int) -> dict[str, Any]:
    with transaction.atomic():
        session, player_slot = _load_session_for_user(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        if session.status == "waiting":
            return {"ok": False, "error": "Game has not started"}
        if session.game_over:
            return {"ok": False, "error": "Game is already over"}

        winner_slot = _next_turn_for(player_slot.slot)
        _create_move(session=session, player_slot=player_slot, kind="give_up")
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
        realtime.publish_game_state_refresh(session, event_name="game_state")
        return {
            "ok": True,
            "game_over": True,
            "game_end_reason": session.game_end_reason,
            "winner_slot": session.winner_slot,
            "status": session.status,
        }


def submit_move_for_ai(
    game_id: str,
    user_id: int,
    placements_data: list[dict[str, Any]],
) -> dict[str, Any]:
    with transaction.atomic():
        session, _player_slot, ai_slot = _load_vs_ai_session(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        return _submit_move_locked(
            session=session,
            player_slot=ai_slot,
            placements_data=placements_data,
        )


def submit_exchange_for_ai(
    game_id: str,
    user_id: int,
    letters_to_exchange: list[str],
) -> dict[str, Any]:
    with transaction.atomic():
        session, _player_slot, ai_slot = _load_vs_ai_session(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        return _submit_exchange_locked(
            session=session,
            player_slot=ai_slot,
            letters_to_exchange=letters_to_exchange,
        )


def submit_pass_for_ai(game_id: str, user_id: int) -> dict[str, Any]:
    with transaction.atomic():
        session, _player_slot, ai_slot = _load_vs_ai_session(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        return _submit_pass_locked(session=session, player_slot=ai_slot)


def get_ai_context(game_id: str, user_id: int) -> dict[str, Any]:
    session, human_slot, ai_slot = _load_vs_ai_session(game_id=game_id, user_id=user_id)
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
    user_id: int,
    placements_data: list[dict[str, Any]],
) -> dict[str, Any]:
    session, _player_slot = _load_session_for_user(game_id=game_id, user_id=user_id)
    board = _board_from_session(session)
    placements = [
        Placement(
            row=p["row"],
            col=p["col"],
            letter=p["letter"],
            blank_as=p.get("blank_as"),
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
    for placement in placements:
        if board.cells[placement.row][placement.col].letter:
            return {
                "valid": False,
                "reason": f"Cell ({placement.row},{placement.col}) occupied",
            }

    board.place_letters(placements)
    words_found = extract_all_words(board, placements)
    if not words_found:
        return {"valid": False, "reason": "No words formed"}

    words_coords = [(word.word, word.letters) for word in words_found]
    total, breakdowns = score_words(board, placements, words_coords)
    if len(placements) == 7:
        total += 50

    contains = _get_dictionary()
    word_results = [
        {"word": word, "valid": _word_passes_dictionary(contains, word)}
        for word, _letters in words_coords
    ]

    return {
        "valid": all(word_result["valid"] for word_result in word_results),
        "total_score": total,
        "words": word_results,
        "breakdowns": [
            {
                "word": breakdown.word,
                "score": breakdown.total,
                "multiplier": breakdown.word_multiplier,
            }
            for breakdown in breakdowns
        ],
    }


def validate_words(*, game_id: str, user_id: int, words: list[str]) -> list[dict[str, Any]]:
    _load_session_for_user(game_id=game_id, user_id=user_id)
    contains = _get_dictionary()
    return [
        {"word": word, "valid": _word_passes_dictionary(contains, word), "source": "collins2019"}
        for word in words
    ]


def create_chat_message_for_user(*, game_id: str, user_id: int, body: str) -> dict[str, Any]:
    text = body.strip()
    if not text:
        return {"ok": False, "error": "Message cannot be empty"}

    with transaction.atomic():
        session, player_slot = _load_session_for_user(
            game_id=game_id,
            user_id=user_id,
            select_for_update=True,
        )
        if session.game_mode != "vs_human" or session.status != "active":
            return {"ok": False, "error": "Chat is unavailable"}

        message = ChatMessage.objects.create(
            game=session,
            user_id=user_id,
            body=text[:500],
        )
        payload = {
            "id": message.id,
            "author_slot": player_slot.slot,
            "author_username": player_slot.user.username if player_slot.user else "Unknown",  # type: ignore[union-attr]
            "body": message.body,
            "created_at": message.created_at.isoformat(),
            "mine": False,
        }
        realtime.publish_chat_message(session, payload=payload)
        return {"ok": True, "message": payload}
