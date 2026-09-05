"""Atomic tile tokens in the pure game engine (slice F1 / MTT-F1)."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import PrefixIndex, load_prefix_index
from gamecore.legality import evaluate_scoring_move
from gamecore.move_search import (
    DEFAULT_MAX_ELAPSED_MS,
    DEFAULT_RANKED_MAX_ELAPSED_MS,
    _RankedSearcher,
    find_legal_scoring_move,
)
from gamecore.scoring import apply_premium_consumption, score_words
from gamecore.state import (
    build_ai_state_dict,
    build_save_state_dict,
    restore_bag_from_save,
    restore_board_from_save,
)
from gamecore.tiles import TileBag
from gamecore.types import Placement, WordFound
from gamecore.variant_store import (
    VariantManifestError,
    _load_variant_from_path,
    load_two_tile_words,
    load_variant,
)
from gamecore.word_authority import WordAuthority, variant_entry_predicate

_TWO_TILE_SHA256 = "e2587f15c19c9046d013d161a06ba54deab0d05bee9f2dd2ac47c3d151048402"
_BASELINE_FIRST20 = {
    ("english", 1): [
        "M", "H", "O", "L", "A", "E", "I", "A", "A", "S",
        "I", "H", "T", "L", "X", "U", "O", "D", "S", "G",
    ],
    ("english", 42): [
        "I", "I", "U", "A", "O", "L", "?", "P", "D", "S",
        "R", "A", "N", "N", "R", "I", "K", "V", "R", "H",
    ],
    ("slovak", 1): [
        "O", "K", "R", "O", "A", "E", "L", "A", "A", "Y",
        "M", "K", "Ä", "O", "Ŕ", "Ý", "S", "D", "X", "J",
    ],
    ("slovak", 42): [
        "M", "M", "Č", "A", "R", "O", "?", "T", "D", "V",
        "T", "A", "O", "O", "T", "N", "N", "Ď", "V", "K",
    ],
}

_SLOVAK_ALPHABET_WITHOUT_TILES = ("DZ", "DŽ", "CH", "Q", "W")
_SLOVAK_PLAYABLE_ORDER = (
    "A", "Á", "Ä", "B", "C", "Č", "D", "Ď", "E", "É", "F", "G", "H",
    "I", "Í", "J", "K", "L", "Ĺ", "Ľ", "M", "N", "Ň", "O", "Ó", "Ô",
    "P", "R", "Ŕ", "S", "Š", "T", "Ť", "U", "Ú", "V", "X", "Y", "Ý",
    "Z", "Ž",
)


def _nfc_casefold(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


def _write_variant(
    tmp_path: Path,
    *,
    letters: list[dict[str, object]],
    alphabet_order: list[str],
    slug: str = "synthetic",
    extra: dict[str, object] | None = None,
) -> Path:
    payload: dict[str, object] = {
        "language": "Synthetic",
        "slug": slug,
        "dictionary_file": "collins2019.txt",
        "alphabet_order": alphabet_order,
        "letters": letters,
    }
    if extra:
        payload.update(extra)
    path = tmp_path / f"{slug}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load(tmp_path: Path, **kwargs: object):
    return _load_variant_from_path(_write_variant(tmp_path, **kwargs))  # type: ignore[arg-type]


def _hu_letters() -> list[dict[str, object]]:
    return [
        {"letter": "?", "count": 2, "points": 0},
        {"letter": "A", "count": 8, "points": 1},
        {"letter": "E", "count": 8, "points": 1},
        {"letter": "T", "count": 4, "points": 1},
        {"letter": "L", "count": 4, "points": 1},
        {"letter": "N", "count": 4, "points": 1},
        {"letter": "SZ", "count": 2, "points": 5},
        {"letter": "GY", "count": 2, "points": 5},
    ]


def _hu_alphabet() -> list[str]:
    return ["A", "E", "GY", "L", "N", "SZ", "T"]


# --- 1. Loader positives and negatives -------------------------------------------------


def test_loader_accepts_multi_codepoint_token(tmp_path: Path) -> None:
    variant = _load(
        tmp_path,
        letters=[
            {"letter": "?", "count": 1, "points": 0},
            {"letter": "A", "count": 1, "points": 1},
            {"letter": "SZ", "count": 2, "points": 3},
        ],
        alphabet_order=["A", "SZ"],
    )
    assert variant.distribution["SZ"] == 2
    assert variant.tile_points["SZ"] == 3
    assert variant.playable_letters == ("A", "SZ")
    assert variant.lexical_contribution("SZ") == "SZ"
    assert variant.tile_display("SZ") == "SZ"


@pytest.mark.parametrize(
    ("raw_letter", "code"),
    [
        ("S Z", "whitespace"),
        ("SZ\n", "whitespace"),
        ("SZ\x00", "control"),
        ("sz", "noncanonical"),
        ("BLANK", "blank_alias"),
        ("A" * 17, "too_long"),
    ],
)
def test_loader_rejects_bad_tokens_with_distinguishable_codes(
    tmp_path: Path, raw_letter: str, code: str
) -> None:
    path = _write_variant(
        tmp_path,
        letters=[
            {"letter": "?", "count": 1, "points": 0},
            {"letter": raw_letter, "count": 1, "points": 1},
        ],
        alphabet_order=["A"],
    )
    with pytest.raises(VariantManifestError) as caught:
        _load_variant_from_path(path)
    assert caught.value.code == code


def test_loader_rejects_duplicate_token(tmp_path: Path) -> None:
    path = _write_variant(
        tmp_path,
        letters=[
            {"letter": "A", "count": 1, "points": 1},
            {"letter": "A", "count": 1, "points": 1},
        ],
        alphabet_order=["A"],
    )
    with pytest.raises(VariantManifestError) as caught:
        _load_variant_from_path(path)
    assert caught.value.code == "duplicate_token"


def test_loader_rejects_missing_alphabet_order(tmp_path: Path) -> None:
    payload = {
        "language": "Synthetic",
        "slug": "no-alpha",
        "dictionary_file": "collins2019.txt",
        "letters": [{"letter": "A", "count": 1, "points": 1}],
    }
    path = tmp_path / "no-alpha.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(VariantManifestError) as caught:
        _load_variant_from_path(path)
    assert caught.value.code == "missing_alphabet_order"


def test_loader_rejects_duplicate_and_non_nfc_alphabet_order(tmp_path: Path) -> None:
    path = _write_variant(
        tmp_path,
        letters=[{"letter": "A", "count": 1, "points": 1}],
        alphabet_order=["A", "A"],
    )
    with pytest.raises(VariantManifestError) as caught:
        _load_variant_from_path(path)
    assert caught.value.code == "duplicate_alphabet"

    decomposed = unicodedata.normalize("NFD", "Á")
    path2 = _write_variant(
        tmp_path,
        letters=[{"letter": "A", "count": 1, "points": 1}],
        alphabet_order=["A", decomposed],
        slug="nfd",
    )
    with pytest.raises(VariantManifestError) as caught_nfc:
        _load_variant_from_path(path2)
    assert caught_nfc.value.code == "non_nfc"


# --- 2. Subset invariant both directions ----------------------------------------------


def test_tile_absent_from_alphabet_order_is_rejected(tmp_path: Path) -> None:
    path = _write_variant(
        tmp_path,
        letters=[
            {"letter": "A", "count": 1, "points": 1},
            {"letter": "SZ", "count": 1, "points": 1},
        ],
        alphabet_order=["A"],
    )
    with pytest.raises(VariantManifestError) as caught:
        _load_variant_from_path(path)
    assert caught.value.code == "tile_not_in_alphabet"


def test_alphabet_letter_without_tile_is_accepted_on_slovak() -> None:
    variant = load_variant("slovak")
    for token in _SLOVAK_ALPHABET_WITHOUT_TILES:
        assert token in variant.alphabet_order
        assert token not in variant.distribution
    assert variant.playable_letters == _SLOVAK_PLAYABLE_ORDER
    assert len(variant.playable_letters) == 41
    assert len(variant.alphabet_order) == 46
    assert "CH" not in variant.playable_letters


# --- 3. L·L canary --------------------------------------------------------------------


def test_interpunct_token_loads_places_scores_and_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "L·L"
    assert token.isalpha() is False
    assert len(token) == 3
    # ⭐ ON THE AUTHORITY PATH. This used to reach its verdict through an
    # INJECTED CALLABLE, which bypassed service authority entirely and so could
    # not prove that a token containing a nonletter survives the real index. The
    # variant now resolves against a throwaway assets root holding a REAL
    # temporary lexicon, and `WordAuthority.for_variant` derives the entry
    # predicate from the variant's own declared nonletters. ⛔ No shipped asset
    # is written to and no shipped index is broadened.
    root = tmp_path / "assets"
    (root / "dicts").mkdir(parents=True)
    (root / "variants").mkdir(parents=True)
    (root / "dicts" / "interpunct.txt").write_text("L·LA\nAAAA\n", encoding="utf-8")
    monkeypatch.setattr("gamecore.variant_store.get_assets_path", lambda: root)
    variant = _load(
        tmp_path,
        letters=[
            {"letter": "?", "count": 1, "points": 0},
            {"letter": "A", "count": 4, "points": 1},
            {"letter": token, "count": 2, "points": 8},
        ],
        alphabet_order=["A", token],
        extra={"dictionary_file": "interpunct.txt"},
    )
    assert token in variant.distribution
    authority = WordAuthority.for_variant(variant)
    assert variant_entry_predicate(variant) is not None
    assert authority.contains_main("L·LA") is True

    board = Board(get_premiums_path())
    placements = [Placement(7, 7, token), Placement(7, 8, "A")]
    board.place_letters(placements)
    assert board.cells[7][7].letter == token
    assert board.cells[7][7].token == token
    assert board.cells[7][7].blank_as is None
    assert board.cells[7][8].letter == "A"
    words = board.build_words_for_move(placements)
    assert words[0].tokens == [token, "A"]
    assert words[0].word == "L·LA"
    # TWO physical tiles, four code points.
    assert len(words[0].tokens) == 2
    assert authority.route(words[0]) == "main"
    assert authority.accepts_formed_word(words[0]) is True
    total, _ = score_words(
        board, placements, [(w.word, w.letters) for w in words], variant=variant
    )
    assert total > 0
    board.clear_letters(placements)

    legality = evaluate_scoring_move(
        board,
        [token, "A"],
        placements,
        authority=authority,
        letters=frozenset(variant.playable_letters),
        variant=variant,
    )
    assert legality.ok
    assert "L·LA" in legality.words
    assert legality.words_found[0].tokens == [token, "A"]
    # And the advisory string query still rejects it, because a bare string has
    # no tile boundaries and `L·LA` is not alphabetic.
    assert authority.accepts_word_query("L·LA") is False


def test_prefix_index_cache_includes_predicate_identity(tmp_path: Path) -> None:
    path = tmp_path / "tiny.txt"
    path.write_text("hello\nL·L\n", encoding="utf-8")

    def keep_alpha(normalized: str) -> bool:
        return normalized.isalpha()

    def keep_all(normalized: str) -> bool:
        return True

    alpha = load_prefix_index(path, entry_predicate=keep_alpha)
    everything = load_prefix_index(path, entry_predicate=keep_all)
    assert alpha is not everything
    assert alpha.contains("hello")
    assert not alpha.contains("L·L")
    assert everything.contains("hello")
    assert everything.contains("L·L")


# --- 4. Slovak two-tile invariant + physical-2 / lexical-3 routing --------------------


def test_osameniu_stays_legal_and_am_complete_word_is_rejected() -> None:
    authority = WordAuthority.for_variant(load_variant("slovak"))
    osameniu = WordFound("OSAMENIU", [(7, col) for col in range(8)], list("OSAMENIU"))
    assert authority.route(osameniu) == "main"
    assert authority.accepts_formed_word(osameniu) is True
    am = WordFound("AM", [(7, 7), (7, 8)], ["A", "M"])
    assert authority.route(am) == "two_tile"
    assert authority.accepts_formed_word(am) is False
    ja = WordFound("JA", [(7, 7), (7, 8)], ["J", "A"])
    assert authority.route(ja) == "two_tile"
    assert authority.accepts_formed_word(ja) is True


def test_physical_two_lexical_three_routes_to_two_tile_authority(tmp_path: Path) -> None:
    index = PrefixIndex(
        words=("osameniu",),
        membership=frozenset({"osameniu"}),
        normalize=_nfc_casefold,
    )
    authority = WordAuthority.from_index(index, two_tile_words=frozenset({"ács"}))
    two_tile = WordFound("ÁCS", [(7, 7), (7, 8)], ["Á", "CS"])
    assert len(two_tile.tokens) == 2
    assert len("".join(two_tile.tokens)) == 3
    assert authority.route(two_tile) == "two_tile"
    assert authority.accepts_formed_word(two_tile) is True
    three_tile = WordFound("ÁCS", [(7, 7), (7, 8), (7, 9)], ["Á", "C", "S"])
    assert authority.route(three_tile) == "main"
    assert authority.accepts_formed_word(three_tile) is False

    board = Board(get_premiums_path())
    placements = [Placement(7, 7, "Á"), Placement(7, 8, "CS")]
    points_variant = _load(
        tmp_path,
        letters=[
            {"letter": "Á", "count": 1, "points": 4},
            {"letter": "CS", "count": 1, "points": 5},
        ],
        alphabet_order=["Á", "CS"],
        slug="acs-points",
    )
    legality = evaluate_scoring_move(
        board,
        ["Á", "CS"],
        placements,
        authority=authority,
        letters=frozenset({"Á", "CS"}),
        variant=points_variant,
    )
    assert legality.ok
    assert legality.words == ("ÁCS",)


def test_two_tile_prefix_union_reaches_acs_without_reverse_segmentation() -> None:
    index = PrefixIndex(words=(), membership=frozenset(), normalize=_nfc_casefold)
    authority = WordAuthority.from_index(index, two_tile_words=frozenset({"ács"}))
    assert authority.has_prefix("Á")
    assert authority.has_prefix("ÁCS")
    assert not authority.has_main_prefix("ÁCS")


# --- 5. Hungarian synthetic engine, search, scoring -----------------------------------


def test_hungarian_synthetic_draw_exchange_place_score_bingo_no_split(
    tmp_path: Path,
) -> None:
    variant = _load(
        tmp_path,
        letters=_hu_letters(),
        alphabet_order=_hu_alphabet(),
        extra={"vowels": ["A", "E"]},
    )
    bag = TileBag(seed=1, variant=variant)
    drawn = []
    while bag.remaining():
        drawn.extend(bag.draw(1))
    assert drawn.count("SZ") == 2
    assert drawn.count("GY") == 2
    assert "S" not in drawn
    assert "Z" not in drawn

    bag2 = TileBag(
        seed=0,
        tiles=["A", "A", "A", "A", "A", "A", "A", "A"],
        variant=variant,
    )
    exchanged = bag2.exchange(["SZ"])
    combined = exchanged + bag2.tiles
    assert combined.count("SZ") == 1
    assert "S" not in combined
    assert "Z" not in combined

    board = Board(get_premiums_path())
    placements = [
        Placement(7, 4, "A"),
        Placement(7, 5, "GY"),
        Placement(7, 6, "A"),
        Placement(7, 7, "SZ"),
        Placement(7, 8, "A"),
        Placement(7, 9, "T"),
        Placement(7, 10, "E"),
    ]
    word = "AGYASZATE"
    # Migrated fixture, identical expectations: the injected callables became one
    # authority over the same tiny lexicon.
    authority = WordAuthority.from_words((word,))

    legality = evaluate_scoring_move(
        board,
        ["A", "GY", "A", "SZ", "A", "T", "E"],
        placements,
        authority=authority,
        letters=frozenset(variant.playable_letters),
        variant=variant,
    )
    assert legality.ok
    assert legality.total_score >= 50
    board.place_letters(list(placements))
    assert board.cells[7][7].letter == "SZ"
    assert board.cells[7][7].token == "SZ"
    assert board.cells[7][8].letter == "A"
    assert board.get_letter(7, 7) != "S"
    words_found = board.build_words_for_move(list(placements))
    assert words_found[0].tokens == ["A", "GY", "A", "SZ", "A", "T", "E"]
    assert "S" not in words_found[0].tokens
    total_before, _ = score_words(
        board,
        list(placements),
        [(w.word, w.letters) for w in words_found],
        variant=variant,
    )
    apply_premium_consumption(board, list(placements))
    assert board.cells[7][7].premium_used is True
    total_after, _ = score_words(
        board,
        list(placements),
        [(w.word, w.letters) for w in words_found],
        variant=variant,
    )
    assert total_before > total_after

    empty = Board(get_premiums_path())
    search = find_legal_scoring_move(
        empty,
        ["A", "SZ"],
        authority=WordAuthority.from_words(("ASZ", "SZA")),
        blank_letters=variant.playable_letters,
        variant=variant,
    )
    assert search.status == "found"
    assert search.witness is not None
    assert any(item.letter == "SZ" for item in search.witness)
    assert all(item.letter != "S" and item.letter != "Z" for item in search.witness)


# --- 6. Draw ordering -----------------------------------------------------------------


def test_starting_draw_blank_lowest_slovak_a_acute_beats_z_english_unchanged() -> None:
    slovak = load_variant("slovak")
    english = load_variant("english")
    assert slovak.starting_draw_order_key("?") < slovak.starting_draw_order_key("A")
    assert slovak.slot0_wins_starting_draw("Á", "Z") is True
    assert slovak.slot0_wins_starting_draw("Z", "Á") is False
    assert ("Á" <= "Z") is False
    assert english.slot0_wins_starting_draw("A", "Z") is True
    assert english.slot0_wins_starting_draw("Z", "A") is False
    assert english.slot0_wins_starting_draw("B", "C") is True
    assert slovak.slot0_wins_starting_draw("A", "A") is True
    assert english.slot0_wins_starting_draw("?", "A") is True


# --- 7. Save schema 4 -----------------------------------------------------------------


def test_save_schema_4_round_trip_and_rejects_legacy() -> None:
    board = Board(get_premiums_path())
    board.cells[7][7].token = "SZ"
    board.cells[7][8].token = "GY"
    board.cells[8][7].token = "?"
    board.cells[8][7].blank_as = "SZ"
    board.cells[7][7].premium_used = True
    bag = TileBag(seed=1, tiles=["A", "SZ", "GY", "?"], variant="english")
    state = build_save_state_dict(
        board=board,
        player_racks={"0": ["SZ", "A"], "1": ["GY", "?"]},
        bag=bag,
        scores={"0": 10, "1": 0},
        current_turn=0,
        seed=1,
        variant_slug="english",
    )
    assert state["schema_version"] == "4"
    assert state["grid"][7][7] == "SZ"
    assert state["grid"][7][8] == "GY"
    assert state["grid"][8][7] == "SZ"
    assert isinstance(state["player_racks"]["0"], list)
    assert state["player_racks"]["0"] == ["SZ", "A"]
    assert isinstance(state["bag"], list)
    assert state["bag"] == ["A", "SZ", "GY", "?"]

    restored_board = restore_board_from_save(state, get_premiums_path())
    assert restored_board.cells[7][7].letter == "SZ"
    assert restored_board.cells[7][8].letter == "GY"
    assert restored_board.cells[8][7].letter == "SZ"
    assert restored_board.cells[8][7].is_blank is True
    assert restored_board.cells[7][7].token == "SZ"
    assert restored_board.cells[8][7].token == "?"
    assert restored_board.cells[8][7].blank_as == "SZ"
    assert restored_board.cells[8][7].realized_token == "SZ"
    restored_bag = restore_bag_from_save(state)
    assert restored_bag.tiles == ["A", "SZ", "GY", "?"]

    english_board = Board(get_premiums_path())
    english_board.cells[7][7].token = "A"
    english_board.cells[7][8].token = "T"
    ai = build_ai_state_dict(english_board, ["Q", "I"], 1, 2, "HUMAN")
    assert list(ai.keys()) == ["grid", "blanks", "ai_rack", "human_score", "ai_score", "turn"]
    assert all(isinstance(row, str) and len(row) == 15 for row in ai["grid"])
    assert ai["grid"][7][7] == "A"
    assert ai["ai_rack"] == "QI"

    for bad in ("2", "3", None, 4, "4.0", ""):
        with pytest.raises(ValueError, match="schema_version"):
            restore_board_from_save({"schema_version": bad, "grid": []}, get_premiums_path())
        with pytest.raises(ValueError, match="schema_version"):
            restore_bag_from_save({"schema_version": bad, "bag": []})
    with pytest.raises(ValueError, match="schema_version"):
        restore_bag_from_save({"bag": []})


# --- 8. Seeded-bag promise ------------------------------------------------------------


def test_seeded_bag_first_twenty_draws_match_baseline_1b7b05d() -> None:
    for (slug, seed), expected in _BASELINE_FIRST20.items():
        bag = TileBag(seed=seed, variant=slug)
        assert bag.draw(20) == expected


# --- 9. Two-tile asset rename ---------------------------------------------------------


def test_two_tile_asset_renamed_with_identical_bytes() -> None:
    new_path = get_assets_path() / "dicts" / "slovak_two_tile_words.txt"
    old_path = get_assets_path() / "dicts" / "slovak_two_letter.txt"
    assert new_path.is_file()
    assert not old_path.exists()
    digest = hashlib.sha256(new_path.read_bytes()).hexdigest()
    assert digest == _TWO_TILE_SHA256
    rows = [
        line.strip()
        for line in new_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(rows) == 103
    assert all(len(item) == 2 for item in rows)
    loaded = load_two_tile_words(load_variant("slovak"))
    assert loaded is not None
    assert len(loaded) == 103


# --- 10. Frozen search caps -----------------------------------------------------------


def test_frozen_search_elapsed_caps() -> None:
    assert DEFAULT_MAX_ELAPSED_MS == 2000
    assert DEFAULT_RANKED_MAX_ELAPSED_MS == 750


# --- 4.9 vowels mechanism, Slovak residual left undeclared ----------------------------


def test_declared_vowels_change_leave_quality_slovak_stays_on_default(
    tmp_path: Path,
) -> None:
    slovak = load_variant("slovak")
    assert "vowels" not in json.loads(
        (get_assets_path() / "variants" / "slovak.json").read_text(encoding="utf-8")
    )
    assert "vowels" not in json.loads(
        (get_assets_path() / "variants" / "english.json").read_text(encoding="utf-8")
    )
    declared = _load(
        tmp_path,
        letters=[
            {"letter": "Á", "count": 1, "points": 4},
            {"letter": "B", "count": 1, "points": 4},
        ],
        alphabet_order=["Á", "B"],
        extra={"vowels": ["Á", "A", "E", "I", "O", "U"]},
        slug="vowel-probe",
    )

    def _leave(variant: object) -> tuple[int, int, int]:
        searcher = _RankedSearcher(
            board=Board(get_premiums_path()),
            rack=["Á", "B"],
            authority=WordAuthority.from_words(("ÁB", "BÁ")),
            bag_count=10,
            top_k=1,
            max_nodes=1,
            max_elapsed_ms=10,
            max_unique_placements=1,
            tile_points={"Á": 4, "B": 4},
            blank_letters=("Á", "B"),
            variant=variant,
        )
        return searcher._leave_components([])

    default_leave = _leave(slovak)
    declared_leave = _leave(declared)
    assert default_leave != declared_leave
    # Residual: Á is not in default AEIOU, so it counts as a consonant.
    _burden, _dup, default_imbalance = default_leave
    _burden2, _dup2, declared_imbalance = declared_leave
    assert default_imbalance == 2
    assert declared_imbalance == 0
