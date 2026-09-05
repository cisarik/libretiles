"""Variant-neutral Slovak full-game harness and leftover-scoring regressions."""

from __future__ import annotations

import os
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter

import pytest

from accounts.models import User
from game.models import GameSession, PlayerSlot
from game.services import _check_endgame
from gamecore.assets import get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import load_prefix_index
from gamecore.game import Game, GameEndReason, PlayerState, apply_final_scoring
from gamecore.legality import evaluate_scoring_move, placements_to_dicts
from gamecore.move_search import DEFAULT_MAX_NODES, find_legal_scoring_move
from gamecore.tiles import TileBag, get_tile_distribution, get_tile_points
from gamecore.types import Placement, WordFound
from gamecore.variant_store import load_two_tile_words, load_variant
from gamecore.word_authority import WordAuthority

_VARIANT = load_variant("slovak")
_INDEX = load_prefix_index(_VARIANT.dictionary_path)
_ALLOWLIST = load_two_tile_words(_VARIANT)
assert _ALLOWLIST is not None
_PLAYABLE = frozenset(_VARIANT.playable_letters)
_EXPECTED_TILES = Counter(get_tile_distribution("slovak"))
_TILE_POINTS = get_tile_points("slovak")
_ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES,
}
_ACCEPTANCE_SEARCH_MAX_ELAPSED_MS = 10_000
_SLOVAK_LEFTOVER_RACK = ["Á", "Ľ", "O", "S", "N", "U", "Ô"]
_SLOVAK_LEFTOVER_POINTS = 25
_ENGLISH_LEFTOVER_POINTS = 4
_OPT_IN_ENV = "LIBRETILES_RUN_SLOVAK_FULL_GAME"


# Migrated fixture, identical expectations: the two injected callables became
# the one authority for the same variant and the same two-tile lexicon.
_AUTHORITY = WordAuthority.for_variant(_VARIANT)
assert _AUTHORITY.contains_main == _INDEX.contains
assert _AUTHORITY.two_tile_words == _ALLOWLIST


def _tile_counter(game: Game) -> Counter[str]:
    tiles = Counter(game.bag.tiles)
    for player in game.players:
        tiles.update(player.rack)
    for row in game.board.cells:
        for cell in row:
            if cell.letter:
                tiles.update(["?" if cell.is_blank else cell.letter])
    return tiles


def _fingerprint(game: Game) -> tuple[object, ...]:
    board = tuple(
        (cell.letter, cell.is_blank, cell.premium, cell.premium_used)
        for row in game.board.cells
        for cell in row
    )
    return (
        board,
        tuple(game.bag.tiles),
        tuple(tuple(player.rack) for player in game.players),
        tuple(player.score for player in game.players),
        game.current_index,
        game.consecutive_scoreless_turns,
    )


def _rack_points(rack: list[str]) -> int:
    return sum(_TILE_POINTS.get(tile, 0) for tile in rack)


def _assert_slovak_unicode_placements(placements: Sequence[Placement]) -> None:
    payload = placements_to_dicts(placements)
    rebuilt: list[Placement] = []
    for item in payload:
        letter = item["letter"]
        assert isinstance(letter, str)
        letter_nfc = unicodedata.normalize("NFC", letter)
        assert letter == letter_nfc
        row = int(item["row"])
        col = int(item["col"])
        if letter == "?":
            blank_as = item.get("blank_as")
            assert isinstance(blank_as, str)
            blank_nfc = unicodedata.normalize("NFC", blank_as)
            assert blank_as == blank_nfc
            assert len(blank_nfc) == 1
            assert blank_nfc.isalpha()
            assert blank_nfc in _PLAYABLE
            rebuilt.append(Placement(row, col, "?", blank_nfc))
        else:
            assert len(letter_nfc) == 1
            assert letter_nfc.isalpha()
            assert letter_nfc in _PLAYABLE
            rebuilt.append(Placement(row, col, letter_nfc))
    assert placements_to_dicts(rebuilt) == payload


def _assert_b2_complete_words(words: Sequence[WordFound]) -> None:
    # Routing is by PHYSICAL tile count, not by code-point length. Slovak tiles
    # are all one code point, so the SSS B2 expectation is unchanged.
    for word in words:
        if len(word.tokens) == 2:
            folded = unicodedata.normalize("NFC", word.word).casefold()
            assert folded in _ALLOWLIST, f"complete two-letter word {word.word!r} not in SSS B2"


@dataclass(frozen=True)
class SimulationResult:
    seed: int
    plies: int
    end_reason: GameEndReason
    scores: dict[str, int]
    leftover_points: dict[str, int]


def _simulate(seed: int, *, max_plies: int = 200) -> SimulationResult:
    bag = TileBag(seed=seed, variant="slovak")
    players = [
        PlayerState(name="P0", rack=bag.draw(7)),
        PlayerState(name="P1", rack=bag.draw(7)),
    ]
    game = Game(
        board=Board(get_premiums_path()),
        bag=bag,
        players=players,
        starting_index=seed % 2,
    )
    placement_scores = [0, 0]
    fingerprints = {_fingerprint(game)}
    terminal_transitions = 0

    assert sum(_EXPECTED_TILES.values()) == 100
    assert _tile_counter(game) == _EXPECTED_TILES, f"seed={seed} initial conservation"

    for ply in range(1, max_plies + 1):
        assert not game.ended, f"seed={seed} ply={ply} entered loop after terminal"
        acting_index = game.current_index
        acting = game.current_player()
        score_before = tuple(player.score for player in players)
        rack_before = acting.rack.copy()
        bag_before = game.bag.remaining()
        scoreless_before = game.consecutive_scoreless_turns
        pass_streak_before = acting.pass_streak
        assert _tile_counter(game) == _EXPECTED_TILES, (
            f"seed={seed} ply={ply} pre-action conservation"
        )

        search = find_legal_scoring_move(
            game.board,
            rack_before,
            authority=_AUTHORITY,
            max_nodes=DEFAULT_MAX_NODES,
            max_elapsed_ms=_ACCEPTANCE_SEARCH_MAX_ELAPSED_MS,
            blank_letters=_VARIANT.playable_letters,
            variant="slovak",
        )
        context = (
            f"seed={seed} ply={ply} status={search.status} nodes={search.nodes} "
            f"elapsed_ms={search.elapsed_ms}"
        )

        if search.status == "indeterminate":
            pytest.fail(f"{context}: bounded search must not authorize a non-scoring action")

        if search.status == "found":
            assert search.witness is not None, context
            _assert_slovak_unicode_placements(search.witness)
            legality = evaluate_scoring_move(
                game.board,
                rack_before,
                search.witness,
                authority=_AUTHORITY,
                letters=_PLAYABLE,
                variant="slovak",
            )
            assert legality.ok, f"{context}: witness failed re-certification: {legality}"
            assert legality.total_score == search.total_score, context
            _assert_b2_complete_words(legality.words_found)
            awarded = game.play_move(search.witness)
            assert awarded == legality.total_score, context
            placement_scores[acting_index] += awarded
            assert game.consecutive_scoreless_turns == 0, context
            assert acting.pass_streak == 0, context
            if not game.ended:
                assert acting.score - score_before[acting_index] == awarded, context
        elif bag_before >= 7:
            assert search.status == "none" and search.complete is True, context
            game.exchange_turn(rack_before)
            assert game.consecutive_scoreless_turns == scoreless_before + 1, context
            assert acting.pass_streak == 0, context
            if not game.ended:
                assert tuple(player.score for player in players) == score_before, context
        else:
            assert search.status == "none" and search.complete is True, context
            game.pass_turn()
            assert game.consecutive_scoreless_turns == scoreless_before + 1, context
            assert acting.pass_streak == pass_streak_before + 1, context
            if not game.ended:
                assert tuple(player.score for player in players) == score_before, context

        assert _tile_counter(game) == _EXPECTED_TILES, (
            f"{context}: post-action conservation differs: {_tile_counter(game)}"
        )
        if game.ended:
            terminal_transitions += 1
            assert game.current_index == acting_index, context
        else:
            assert game.current_index == (acting_index + 1) % len(players), context

        fingerprint = _fingerprint(game)
        assert fingerprint not in fingerprints, f"{context}: repeated full position"
        fingerprints.add(fingerprint)

        if game.ended:
            assert terminal_transitions == 1, context
            assert game.end_reason in _ALLOWED_END_REASONS, context
            assert game.end_reason is not None, context

            expected_scores = placement_scores.copy()
            leftovers = [_rack_points(player.rack) for player in players]
            for index, leftover in enumerate(leftovers):
                expected_scores[index] -= leftover
            if game.end_reason is GameEndReason.BAG_EMPTY_AND_PLAYER_OUT:
                finishers = [index for index, player in enumerate(players) if not player.rack]
                assert len(finishers) == 1, context
                finisher = finishers[0]
                expected_scores[finisher] += sum(
                    leftover for index, leftover in enumerate(leftovers) if index != finisher
                )
            else:
                assert all(player.rack for player in players), context

            assert [player.score for player in players] == expected_scores, context
            assert game.leftover_points == {
                player.name: leftover for player, leftover in zip(players, leftovers, strict=True)
            }, context
            top_score = max(expected_scores)
            leaders = [index for index, score in enumerate(expected_scores) if score == top_score]
            expected_winner = players[leaders[0]].name if len(leaders) == 1 else None
            assert game.winner_name == expected_winner, context
            return SimulationResult(
                seed=seed,
                plies=ply,
                end_reason=game.end_reason,
                scores=game.scores(),
                leftover_points=dict(game.leftover_points),
            )

    pytest.fail(f"seed={seed}: game did not terminate within {max_plies} plies")


def test_slovak_bag_has_one_hundred_sss_tiles() -> None:
    assert sum(_EXPECTED_TILES.values()) == 100
    assert len(_ALLOWLIST) == 103


def test_apply_final_scoring_uses_slovak_tile_points_for_leftover_rack() -> None:
    slovak_player = PlayerState(name="SK", rack=list(_SLOVAK_LEFTOVER_RACK), score=100)
    english_player = PlayerState(name="EN", rack=list(_SLOVAK_LEFTOVER_RACK), score=100)

    leftover_slovak = apply_final_scoring([slovak_player], variant="slovak")
    leftover_english = apply_final_scoring([english_player])

    assert leftover_slovak == {"SK": _SLOVAK_LEFTOVER_POINTS}
    assert leftover_english == {"EN": _ENGLISH_LEFTOVER_POINTS}
    assert leftover_slovak["SK"] != leftover_english["EN"]
    assert slovak_player.score == 100 - _SLOVAK_LEFTOVER_POINTS
    assert english_player.score == 100 - _ENGLISH_LEFTOVER_POINTS


def test_slovak_full_game_terminates_with_variant_scoring() -> None:
    started = perf_counter()
    result = _simulate(0)
    elapsed = perf_counter() - started
    print(
        f"slovak-full-game seed={result.seed} plies={result.plies} "
        f"elapsed={elapsed:.3f}s end_reason={result.end_reason.name} "
        f"scores={result.scores} leftover={result.leftover_points}",
        flush=True,
    )
    assert result.end_reason in _ALLOWED_END_REASONS
    assert result.plies >= 1


@pytest.mark.django_db
def test_check_endgame_persists_slovak_leftover_points() -> None:
    user = User.objects.create_user(username="slovak-endgame", password="pass1234")
    session = GameSession.objects.create(
        game_mode="vs_ai",
        status="active",
        variant_slug="slovak",
        board_state=[[None] * 15 for _ in range(15)],
        bag_tiles=[],
        consecutive_scoreless_turns=0,
    )
    slot0 = PlayerSlot.objects.create(
        game=session, slot=0, user=user, rack=[], score=100, is_ai=False
    )
    slot1 = PlayerSlot.objects.create(
        game=session,
        slot=1,
        rack=list(_SLOVAK_LEFTOVER_RACK),
        score=100,
        is_ai=True,
    )

    payload = _check_endgame(session)
    session.save()

    slot0.refresh_from_db()
    slot1.refresh_from_db()
    session.refresh_from_db()

    assert payload["game_end_reason"] == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name
    assert payload["leftover_points"] == {"0": 0, "1": _SLOVAK_LEFTOVER_POINTS}
    assert payload["final_scores"] == {"0": 125, "1": 75}
    assert payload["winner_slot"] == 0
    assert session.status == "finished"
    assert session.game_over is True
    assert session.game_end_reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name
    assert slot0.score == 125
    assert slot1.score == 75
    assert session.winner_slot == 0


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get(_OPT_IN_ENV) != "1",
    reason=f"set {_OPT_IN_ENV}=1 for extra Slovak full-game seeds",
)
def test_slovak_full_game_opt_in_matrix() -> None:
    started = perf_counter()
    results = [_simulate(seed) for seed in range(1, 4)]
    elapsed = perf_counter() - started
    distribution = Counter(result.end_reason.name for result in results)
    print(
        f"slovak-full-game-opt-in games={len(results)} elapsed={elapsed:.3f}s "
        f"end_reasons={dict(sorted(distribution.items()))}",
        flush=True,
    )
    assert len(results) == 3
