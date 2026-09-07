"""Public tile tracking: the validated unseen-pool builder for late-game search.

Every context is deduced from strictly PUBLIC information (variant
distribution, board tokens, acting rack, opponent rack SIZE). The builder
fails closed: any inconsistency returns ``None`` and the caller degrades to
the ordinary midgame search.
"""

from __future__ import annotations

from collections import Counter

import pytest

from gamecore.board import Board
from gamecore.tile_tracking import (
    LATE_GAME_MAX_BAG,
    LATE_GAME_PLAYER_COUNT,
    RACK_CAPACITY,
    LateGameContext,
    build_late_game_context,
)
from gamecore.tiles import get_tile_distribution

_ENGLISH = get_tile_distribution("english")
_SLOVAK = get_tile_distribution("slovak")


def _expand(distribution: dict[str, int]) -> list[str]:
    tiles: list[str] = []
    for token in sorted(distribution):
        tiles.extend([token] * distribution[token])
    return tiles


def _fill_board(tokens: list[str]) -> Board:
    """Row-major board fill; unassigned blanks would be malformed, so assign."""
    board = Board()
    for index, token in enumerate(tokens):
        cell = board.cells[index // 15][index % 15]
        cell.token = token
        cell.blank_as = "E" if token == "?" else None
    return board


def _scenario(
    distribution: dict[str, int],
    variant: str,
    *,
    rack_size: int = 7,
    opponent_size: int = 7,
    bag_size: int = 7,
) -> tuple[Board, list[str], list[str], list[str]]:
    """Split the full physical inventory into rack/opponent/bag/board."""
    tiles = _expand(distribution)
    rack = tiles[:rack_size]
    opponent = tiles[rack_size : rack_size + opponent_size]
    bag = tiles[rack_size + opponent_size : rack_size + opponent_size + bag_size]
    on_board = tiles[rack_size + opponent_size + bag_size :]
    return _fill_board(on_board), rack, opponent, bag


def _build(
    board: Board,
    rack: list[str],
    *,
    variant: str,
    bag_remaining: int,
    opponent_rack_size: int,
    **overrides: object,
) -> LateGameContext | None:
    kwargs: dict[str, object] = {
        "board": board,
        "acting_rack": rack,
        "variant": variant,
        "bag_remaining": bag_remaining,
        "player_count": 2,
        "opponent_rack_size": opponent_rack_size,
        "consecutive_scoreless_turns": 0,
    }
    kwargs.update(overrides)
    return build_late_game_context(**kwargs)  # type: ignore[arg-type]


# ---- inventory subtraction across variants ---------------------------------


@pytest.mark.parametrize(
    "distribution,variant",
    [(_ENGLISH, "english"), (_SLOVAK, "slovak")],
)
def test_unseen_pool_is_distribution_minus_board_and_acting_rack(
    distribution: dict[str, int], variant: str
) -> None:
    board, rack, opponent, bag = _scenario(distribution, variant)
    context = _build(
        board, rack, variant=variant, bag_remaining=len(bag), opponent_rack_size=len(opponent)
    )
    assert context is not None
    assert context.unseen_counter == Counter(bag) + Counter(opponent)
    assert context.unseen_total == len(bag) + len(opponent)
    assert context.bag_remaining == len(bag)
    assert context.opponent_rack_size == len(opponent)
    # Canonical ordering with positive counts only.
    assert list(context.unseen_tiles) == sorted(context.unseen_tiles)
    assert all(count > 0 for _token, count in context.unseen_tiles)


def test_multigraph_tokens_subtract_one_physical_tile_each() -> None:
    # No shipped variant carries multigraph tile tokens today; the invariant
    # is still contractual (one physical tile per token, regardless of its
    # code-point length), so a synthetic variant proves it.
    from gamecore.variant_store import VariantDefinition, VariantLetter

    variant = VariantDefinition(
        slug="synthetic-multigraph",
        language="Synthetic",
        letters=tuple(
            sorted(
                (
                    VariantLetter("A", 6, 1),
                    VariantLetter("CH", 2, 5),
                    VariantLetter("S", 5, 1),
                    VariantLetter("Z", 2, 4),
                    VariantLetter("?", 1, 0),
                ),
                key=lambda lt: lt.letter,
            )
        ),
        dictionary_file="collins2019.txt",
    )
    board = Board()
    board.cells[7][7].token = "CH"
    board.cells[7][8].token = "A"
    rack = ["A", "S", "S"]
    # 16 tiles total; board holds 2, rack 3 -> 11 unseen = bag 5 + opponent 6.
    context = build_late_game_context(
        board=board,
        acting_rack=rack,
        variant=variant,
        bag_remaining=5,
        player_count=2,
        opponent_rack_size=6,
        consecutive_scoreless_turns=0,
    )
    assert context is not None
    # The board CH consumed ONE physical tile, not a C and an H.
    assert context.unseen_counter["CH"] == 1
    assert context.unseen_counter == Counter(
        {"A": 4, "CH": 1, "S": 3, "Z": 2, "?": 1}
    )


def test_assigned_blank_subtracts_the_blank_not_its_assignment() -> None:
    tiles = _expand(_ENGLISH)
    tiles.remove("?")  # one blank goes on the board, assigned as Z
    rack = tiles[:7]
    opponent = tiles[7:14]
    bag = tiles[14:19]
    board = _fill_board(tiles[19:])
    board.cells[14][14].token = "?"
    board.cells[14][14].blank_as = "Z"
    context = _build(
        board, rack, variant="english", bag_remaining=len(bag), opponent_rack_size=len(opponent)
    )
    assert context is not None
    # Blank inventory dropped by exactly one; the Z inventory is untouched.
    unseen = Counter(bag) + Counter(opponent)
    assert context.unseen_counter["?"] == unseen["?"]
    assert context.unseen_counter["Z"] == unseen["Z"]
    assert context.unseen_counter == unseen


# ---- eligibility bounds ------------------------------------------------------


@pytest.mark.parametrize("bag_size", [0, 1, 7])
def test_bag_counts_zero_one_seven_are_eligible(bag_size: int) -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english", bag_size=bag_size)
    context = _build(
        board, rack, variant="english", bag_remaining=bag_size, opponent_rack_size=len(opponent)
    )
    assert context is not None
    assert context.bag_remaining == bag_size


def test_bag_count_eight_is_not_late_game() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english", bag_size=8)
    assert LATE_GAME_MAX_BAG == 7
    assert (
        _build(board, rack, variant="english", bag_remaining=8, opponent_rack_size=len(opponent))
        is None
    )


def test_empty_bag_expands_unseen_into_exact_opponent_rack() -> None:
    board, rack, opponent, _bag = _scenario(_ENGLISH, "english", bag_size=0)
    context = _build(
        board, rack, variant="english", bag_remaining=0, opponent_rack_size=len(opponent)
    )
    assert context is not None
    assert context.exact_opponent_rack() == tuple(sorted(opponent))


def test_nonempty_bag_never_deduces_an_opponent_rack() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english", bag_size=3)
    context = _build(
        board, rack, variant="english", bag_remaining=3, opponent_rack_size=len(opponent)
    )
    assert context is not None
    assert context.exact_opponent_rack() is None


def test_wrong_player_count_is_rejected() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english")
    assert LATE_GAME_PLAYER_COUNT == 2
    for players in (1, 3, 4):
        assert (
            _build(
                board,
                rack,
                variant="english",
                bag_remaining=len(bag),
                opponent_rack_size=len(opponent),
                player_count=players,
            )
            is None
        )


# ---- fail-closed validation --------------------------------------------------


def test_malformed_board_cell_fails_closed() -> None:
    tiles = _expand(_ENGLISH)
    tiles.remove("?")
    rack = tiles[:7]
    opponent = tiles[7:14]
    bag = tiles[14:19]
    board = _fill_board(tiles[19:])
    # An occupied blank without an assignment must never read as empty.
    board.cells[14][14].token = "?"
    board.cells[14][14].blank_as = None
    assert (
        _build(board, rack, variant="english", bag_remaining=len(bag), opponent_rack_size=len(opponent))
        is None
    )


def test_negative_residual_fails_closed() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english")
    # English owns exactly one Z; a rack holding three is a physical
    # impossibility and must not vanish through Counter arithmetic.
    overdraw = ["Z", "Z", "Z"] + rack[:4]
    assert (
        _build(
            board,
            overdraw,
            variant="english",
            bag_remaining=len(bag),
            opponent_rack_size=len(opponent),
        )
        is None
    )


def test_foreign_tokens_fail_closed() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english")
    foreign_rack = ["Ω"] + rack[:6]
    assert (
        _build(
            board,
            foreign_rack,
            variant="english",
            bag_remaining=len(bag),
            opponent_rack_size=len(opponent),
        )
        is None
    )
    board.cells[14][14].token = "Ω"
    assert (
        _build(board, rack, variant="english", bag_remaining=len(bag), opponent_rack_size=len(opponent))
        is None
    )


def test_residual_sum_mismatch_fails_closed() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english")
    assert (
        _build(
            board,
            rack,
            variant="english",
            bag_remaining=len(bag) - 1,
            opponent_rack_size=len(opponent),
        )
        is None
    )


def test_non_integer_and_out_of_range_scalars_fail_closed() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english")
    good = {
        "variant": "english",
        "bag_remaining": len(bag),
        "opponent_rack_size": len(opponent),
    }
    assert _build(board, rack, **good) is not None  # type: ignore[arg-type]
    assert _build(board, rack, **{**good, "bag_remaining": True}) is None  # type: ignore[arg-type]
    assert _build(board, rack, **{**good, "bag_remaining": -1}) is None  # type: ignore[arg-type]
    assert _build(board, rack, **{**good, "opponent_rack_size": 8}) is None  # type: ignore[arg-type]
    assert (
        _build(board, rack, **{**good, "consecutive_scoreless_turns": -1})  # type: ignore[arg-type]
        is None
    )
    assert (
        _build(board, rack, **{**good, "opponent_action_rules": "oracle"})  # type: ignore[arg-type]
        is None
    )
    assert RACK_CAPACITY == 7
    assert (
        _build(board, rack + ["A"], variant="english", bag_remaining=len(bag), opponent_rack_size=7)
        is None
    )


def test_unknown_variant_fails_closed() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english")
    assert (
        _build(board, rack, variant="klingon", bag_remaining=len(bag), opponent_rack_size=7)
        is None
    )


def test_opponent_action_rules_are_the_two_shipped_values() -> None:
    board, rack, opponent, bag = _scenario(_ENGLISH, "english")
    for rules in ("ai_scoring", "human_open"):
        context = _build(
            board,
            rack,
            variant="english",
            bag_remaining=len(bag),
            opponent_rack_size=len(opponent),
            opponent_action_rules=rules,
        )
        assert context is not None
        assert context.opponent_action_rules == rules
