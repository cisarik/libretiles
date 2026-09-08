from __future__ import annotations

from game.inspection import capture_move_inspection
from game.serializers import sanitize_ai_metadata
from gamecore.board import Board
from gamecore.rules import extract_all_words
from gamecore.scoring import score_words
from gamecore.types import Placement, Premium
from gamecore.variant_store import load_variant
from gamecore.word_authority import WordAuthority


def test_scoring_inspection_captures_exact_premium_math_before_consumption() -> None:
    board = Board()
    board.cells[7][7].premium = Premium.DW
    board.cells[7][8].premium = Premium.DL
    placements = [Placement(7, 7, "A"), Placement(7, 8, "T")]
    board.place_letters(placements)
    words = extract_all_words(board, placements)

    total, breakdowns = score_words(
        board,
        placements,
        [(word.word, word.letters) for word in words],
        variant="english",
        include_inspection=True,
    )

    assert total == 6
    breakdown = breakdowns[0]
    assert breakdown.base_points == 2
    assert breakdown.letter_bonus_points == 1
    assert breakdown.word_multiplier == 2
    assert breakdown.total == 6
    assert breakdown.physical_cells is not None
    assert [cell.letter_multiplier for cell in breakdown.physical_cells] == [1, 2]
    assert [cell.premium for cell in breakdown.physical_cells] == ["DW", "DL"]
    assert all(cell.premium_applied for cell in breakdown.physical_cells)


def test_move_inspection_records_word_authority_and_lexicon() -> None:
    variant = load_variant("english")
    authority = WordAuthority.for_variant(variant)
    board = Board()
    placements = [Placement(7, 7, "A"), Placement(7, 8, "T")]
    board.place_letters(placements)
    words = extract_all_words(board, placements)
    _total, breakdowns = score_words(
        board,
        placements,
        [(word.word, word.letters) for word in words],
        variant=variant,
        include_inspection=True,
    )

    captured = capture_move_inspection(
        breakdowns=breakdowns,
        words=words,
        authority=authority,
        variant=variant,
    )

    authority_record = captured[0]["inspection"]["authority"]
    assert authority_record == {
        "name": "WordAuthority",
        "valid": True,
        "physical_tile_count": 2,
        "route": "main",
        "main_lexicon_id": "collins2019",
        "two_tile_lexicon_id": None,
        "lexicon_source": "Collins Scrabble Words (2019)",
    }


def test_scoring_detail_is_opt_in() -> None:
    board = Board()
    placements = [Placement(7, 7, "A"), Placement(7, 8, "T")]
    board.place_letters(placements)
    words = extract_all_words(board, placements)
    _total, breakdowns = score_words(
        board,
        placements,
        [(word.word, word.letters) for word in words],
        variant="english",
    )
    assert breakdowns[0].physical_cells is None


def test_inspection_trace_is_bounded_and_drops_unknown_fields() -> None:
    events = [
        {
            "ordinal": index,
            "elapsed_ms": index,
            "phase": "search",
            "tool": "validateMove",
            "placements": [{"row": 7, "col": 7, "letter": "A"}],
            "words": ["AT"],
            "valid": index % 2 == 0,
            "rejection_code": "invalid_word",
            "raw_output": "secret",
        }
        for index in range(70)
    ]
    metadata = sanitize_ai_metadata(
        {
            "inspection_trace": {
                "version": 1,
                "attempts": [
                    {
                        "attempt_index": 0,
                        "provider": "openrouter",
                        "model_id": "model/free",
                        "events": events,
                        "credentials": "secret",
                    }
                ],
            }
        }
    )
    attempt = metadata["inspection_trace"]["attempts"][0]
    assert len(attempt["events"]) == 64
    assert attempt["truncated"] is True
    assert attempt["omitted_event_count"] == 6
    assert "raw_output" not in attempt["events"][0]
    assert "credentials" not in attempt


def test_oversized_or_malformed_trace_does_not_reject_other_metadata() -> None:
    metadata = sanitize_ai_metadata(
        {
            "completion_source": "provider_candidate",
            "inspection_trace": {
                "version": 1,
                "attempts": [{"attempt_index": 0, "events": "not-a-list"}],
            },
        }
    )
    assert metadata["completion_source"] == "provider_candidate"
    assert metadata["inspection_trace"] == {
        "version": 1,
        "attempts": [{"attempt_index": 0, "events": []}],
    }
