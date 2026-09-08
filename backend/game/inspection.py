from __future__ import annotations

from pathlib import Path
from typing import Any

from gamecore.types import ScoreBreakdown, WordFound
from gamecore.variant_store import VariantDefinition
from gamecore.word_authority import WordAuthority


def _lexicon_source(variant: VariantDefinition) -> str:
    provenance = variant.lexicon_provenance
    if provenance is not None and provenance.upstream:
        return provenance.upstream
    return variant.source


def capture_word_inspection(
    *,
    breakdown: ScoreBreakdown,
    word: WordFound,
    authority: WordAuthority,
    variant: VariantDefinition,
) -> dict[str, Any]:
    cells = breakdown.physical_cells or []
    route = authority.route(word)
    return {
        "version": 1,
        "physical_cells": [
            {
                "row": cell.row,
                "col": cell.col,
                "token": cell.token,
                "blank_as": cell.blank_as,
                "base_points": cell.base_points,
                "is_new": cell.is_new,
                "premium": cell.premium,
                "premium_applied": cell.premium_applied,
                "letter_multiplier": cell.letter_multiplier,
            }
            for cell in cells
        ],
        "base_points": breakdown.base_points,
        "letter_bonus_points": breakdown.letter_bonus_points,
        "word_multiplier": breakdown.word_multiplier,
        "word_total": breakdown.total,
        "authority": {
            "name": "WordAuthority",
            "valid": True,
            "physical_tile_count": len(word.tokens),
            "route": route,
            "main_lexicon_id": Path(variant.dictionary_file).stem,
            "two_tile_lexicon_id": (
                Path(variant.two_tile_words_file).stem
                if route == "two_tile" and variant.two_tile_words_file
                else None
            ),
            "lexicon_source": _lexicon_source(variant),
        },
    }


def capture_move_inspection(
    *,
    breakdowns: list[ScoreBreakdown],
    words: list[WordFound],
    authority: WordAuthority,
    variant: VariantDefinition,
) -> list[dict[str, Any]]:
    return [
        {
            "word": breakdown.word,
            "score": breakdown.total,
            "multiplier": breakdown.word_multiplier,
            "coords": [{"row": row, "col": col} for row, col in word.letters],
            "inspection": capture_word_inspection(
                breakdown=breakdown,
                word=word,
                authority=authority,
                variant=variant,
            ),
        }
        for breakdown, word in zip(breakdowns, words, strict=False)
    ]
