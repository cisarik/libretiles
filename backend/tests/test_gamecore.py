"""Pure gamecore tests — no Django, no network. Must pass on every build."""


from gamecore.assets import get_premiums_path
from gamecore.board import Board
from gamecore.game import (
    Game,
    GameEndReason,
    PlayerState,
    determine_end_reason,
)
from gamecore.rack import consume_rack, restore_rack
from gamecore.rules import (
    first_move_must_cover_center,
    no_gaps_in_line,
    placements_in_line,
)
from gamecore.scoring import score_words
from gamecore.tiles import TileBag, get_tile_points
from gamecore.types import Direction, Placement, Premium
from gamecore.variant_store import load_variant


class TestVariant:
    def test_load_english(self) -> None:
        v = load_variant("english")
        assert v.language == "English"
        assert v.slug == "english"
        assert v.total_tiles == 100
        assert v.tile_points["Q"] == 10
        assert v.tile_points["E"] == 1
        assert v.distribution["E"] == 12

    def test_tile_points(self) -> None:
        pts = get_tile_points("english")
        assert pts["A"] == 1
        assert pts["Z"] == 10
        assert pts["?"] == 0


class TestBoard:
    def test_board_init(self) -> None:
        board = Board(get_premiums_path())
        assert len(board.cells) == 15
        assert len(board.cells[0]) == 15
        assert board.cells[0][0].premium == Premium.TW
        assert board.cells[7][7].premium == Premium.DW

    def test_place_and_clear(self) -> None:
        board = Board(get_premiums_path())
        placements = [Placement(7, 7, "H"), Placement(7, 8, "I")]
        board.place_letters(placements)
        assert board.get_letter(7, 7) == "H"
        assert board.get_letter(7, 8) == "I"
        board.clear_letters(placements)
        assert board.get_letter(7, 7) is None


class TestRules:
    def test_first_move_center(self) -> None:
        assert first_move_must_cover_center([Placement(7, 7, "A")])
        assert not first_move_must_cover_center([Placement(0, 0, "A")])

    def test_placements_in_line(self) -> None:
        assert placements_in_line([Placement(7, 5, "A"), Placement(7, 6, "B")]) == Direction.ACROSS
        assert placements_in_line([Placement(5, 7, "A"), Placement(6, 7, "B")]) == Direction.DOWN
        assert placements_in_line([Placement(5, 5, "A"), Placement(6, 6, "B")]) is None

    def test_no_gaps(self) -> None:
        board = Board(get_premiums_path())
        placements = [Placement(7, 6, "H"), Placement(7, 7, "I")]
        board.place_letters(placements)
        assert no_gaps_in_line(board, placements, Direction.ACROSS)


class TestScoring:
    def test_simple_word_score(self) -> None:
        board = Board(get_premiums_path())
        placements = [Placement(7, 7, "A"), Placement(7, 8, "T")]
        board.place_letters(placements)
        words = board.build_words_for_move(placements)
        words_coords = [(wf.word, wf.letters) for wf in words]
        total, breakdowns = score_words(board, placements, words_coords)
        assert total > 0
        assert len(breakdowns) == 1
        assert breakdowns[0].word == "AT"


class TestTileBag:
    def test_draw_and_remaining(self) -> None:
        bag = TileBag(seed=42, variant="english")
        assert bag.remaining() == 100
        drawn = bag.draw(7)
        assert len(drawn) == 7
        assert bag.remaining() == 93

    def test_exchange(self) -> None:
        bag = TileBag(seed=42, variant="english")
        initial = bag.draw(7)
        new_tiles = bag.exchange(initial[:3])
        assert len(new_tiles) == 3
        assert bag.remaining() == 93

    def test_deterministic_seed(self) -> None:
        bag1 = TileBag(seed=123, variant="english")
        bag2 = TileBag(seed=123, variant="english")
        assert bag1.draw(7) == bag2.draw(7)


class TestRack:
    def test_consume_rack(self) -> None:
        rack = ["A", "B", "C", "D", "E", "F", "G"]
        placements = [Placement(7, 7, "A"), Placement(7, 8, "B")]
        result = consume_rack(rack, placements)
        assert "A" not in result
        assert "B" not in result
        assert len(result) == 5

    def test_restore_rack(self) -> None:
        rack = ["C", "D", "E"]
        placements = [Placement(7, 7, "A"), Placement(7, 8, "B")]
        result = restore_rack(rack, placements)
        assert result == ["C", "D", "E", "A", "B"]


class TestGame:
    def test_simple_game_flow(self) -> None:
        board = Board(get_premiums_path())
        bag = TileBag(seed=42, variant="english")
        p1 = PlayerState(name="Player1", rack=bag.draw(7))
        p2 = PlayerState(name="Player2", rack=bag.draw(7))
        game = Game(board=board, bag=bag, players=[p1, p2])

        assert game.current_player().name == "Player1"
        assert not game.ended

    def test_pass_streak_endgame(self) -> None:
        board = Board(get_premiums_path())
        bag = TileBag(seed=42, variant="english")
        p1 = PlayerState(name="P1", rack=bag.draw(7))
        p2 = PlayerState(name="P2", rack=bag.draw(7))
        game = Game(board=board, bag=bag, players=[p1, p2])

        game.pass_turn()
        game.pass_turn()
        game.pass_turn()
        game.pass_turn()
        assert game.ended
        assert game.end_reason == GameEndReason.ALL_PLAYERS_PASSED_TWICE

    def test_determine_end_reason(self) -> None:
        assert determine_end_reason(
            bag_remaining=0,
            racks={"P1": [], "P2": ["A"]},
            pass_streaks={"P1": 0, "P2": 0},
            no_moves_available=False,
        ) == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT


class TestDictionary:
    def test_primary_dictionary_loads(self) -> None:
        from gamecore.fastdict import load_dictionary
        from django.conf import settings

        contains = load_dictionary(settings.PRIMARY_DICTIONARY_PATH)
        assert contains("hello")
        assert contains("HELLO")
        assert not contains("xyzqw")
        assert contains("aa")
        assert contains("zyzzyva")
