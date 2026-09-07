"""Public-information tile tracking for late-game strategic search.

Pure Python, no Django imports. The builder deduces the UNSEEN tile pool from
strictly public information: the variant distribution, the physical tokens on
the board, and the acting player's own rack. It never reads bag order and it
never reads the opponent's rack contents; Django callers supply only the
opponent rack SIZE. With an empty bag the unseen multiset IS the opponent's
exact rack; with a nonempty bag it stays one combined bag+opponent pool and no
particular tile is ever assigned to the opponent.

An invalid or inconsistent position returns ``None``: strategic analysis is
then unavailable and the ordinary ranked search proceeds unchanged. An
unavailable context never establishes "no legal move".
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .board import Board
from .game import Game
from .tiles import _resolve_variant
from .variant_store import VariantDefinition

LATE_GAME_MAX_BAG = 7
RACK_CAPACITY = 7
LATE_GAME_PLAYER_COUNT = 2

OpponentActionRules = Literal["ai_scoring", "human_open"]
OPPONENT_ACTION_RULES: tuple[str, ...] = ("ai_scoring", "human_open")


@dataclass(frozen=True)
class LateGameContext:
    """Validated public late-game information for one acting seat.

    ``unseen_tiles`` holds the combined bag+opponent multiset in canonical
    (sorted-token) order. Every count is positive and the total equals
    ``bag_remaining + opponent_rack_size`` by construction.
    """

    bag_remaining: int
    unseen_tiles: tuple[tuple[str, int], ...]
    opponent_rack_size: int
    consecutive_scoreless_turns: int
    opponent_action_rules: OpponentActionRules

    @property
    def unseen_counter(self) -> Counter[str]:
        return Counter(dict(self.unseen_tiles))

    @property
    def unseen_total(self) -> int:
        return sum(count for _token, count in self.unseen_tiles)

    def exact_opponent_rack(self) -> tuple[str, ...] | None:
        """The opponent's exact physical rack — ONLY when the bag is empty.

        With any tile still in the bag the deduction does not exist, and this
        returns ``None`` rather than guessing.
        """
        if self.bag_remaining != 0:
            return None
        rack: list[str] = []
        for token, count in self.unseen_tiles:
            rack.extend([token] * count)
        return tuple(rack)


def _is_uint(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def build_late_game_context(
    *,
    board: Board,
    acting_rack: Sequence[str],
    variant: VariantDefinition | str | None,
    bag_remaining: int,
    player_count: int,
    opponent_rack_size: int,
    consecutive_scoreless_turns: int,
    opponent_action_rules: str = "ai_scoring",
) -> LateGameContext | None:
    """Build a validated ``LateGameContext`` or return ``None``.

    Eligibility: exactly two players and ``0 <= bag_remaining <= 7``. The
    inventory deduction subtracts board tokens and the acting rack from the
    variant distribution while PRESERVING negative counts, so an overdraw or a
    foreign token fails the residual check instead of vanishing through
    ``Counter`` arithmetic.
    """
    if player_count != LATE_GAME_PLAYER_COUNT:
        return None
    if not _is_uint(bag_remaining) or bag_remaining > LATE_GAME_MAX_BAG:
        return None
    if not _is_uint(opponent_rack_size) or opponent_rack_size > RACK_CAPACITY:
        return None
    if not _is_uint(consecutive_scoreless_turns):
        return None
    rules: OpponentActionRules
    if opponent_action_rules == "ai_scoring":
        rules = "ai_scoring"
    elif opponent_action_rules == "human_open":
        rules = "human_open"
    else:
        return None
    if len(acting_rack) > RACK_CAPACITY:
        return None

    try:
        resolved = _resolve_variant(variant)
    except Exception:
        return None
    distribution = resolved.distribution
    unseen: Counter[str] = Counter(distribution)

    # Physical tokens only: an assigned blank removes one "?", never its
    # blank_as assignment; a multigraph tile removes exactly one token.
    for row in board.cells:
        for cell in row:
            if cell.token is None:
                continue
            if cell.is_malformed:
                return None
            if cell.token not in distribution:
                return None
            unseen[cell.token] -= 1

    for tile in acting_rack:
        if not isinstance(tile, str) or tile not in distribution:
            return None
        unseen[tile] -= 1

    if any(count < 0 for count in unseen.values()):
        return None
    remaining = {token: count for token, count in unseen.items() if count > 0}
    if sum(remaining.values()) != bag_remaining + opponent_rack_size:
        return None

    return LateGameContext(
        bag_remaining=bag_remaining,
        unseen_tiles=tuple(sorted(remaining.items())),
        opponent_rack_size=opponent_rack_size,
        consecutive_scoreless_turns=consecutive_scoreless_turns,
        opponent_action_rules=rules,
    )


def late_game_context_for_game(
    game: Game,
    *,
    acting_index: int,
    variant: VariantDefinition | str | None = None,
    opponent_action_rules: str = "ai_scoring",
) -> LateGameContext | None:
    """Shared ``Game``-object builder for self-play and position mounting.

    Public information only: the opponent's rack contributes its SIZE, never
    its contents. Returns ``None`` outside late-game eligibility.
    """
    if len(game.players) != 2 or acting_index not in (0, 1):
        return None
    opponent = game.players[1 - acting_index]
    return build_late_game_context(
        board=game.board,
        acting_rack=game.players[acting_index].rack,
        variant=variant if variant is not None else game.bag.variant_slug,
        bag_remaining=game.bag.remaining(),
        player_count=len(game.players),
        opponent_rack_size=len(opponent.rack),
        consecutive_scoreless_turns=game.consecutive_scoreless_turns,
        opponent_action_rules=opponent_action_rules,
    )
