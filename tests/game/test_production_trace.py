"""A roll says which house rules changed what it paid.

A player who collects 1 card where they expected 2 is otherwise told nothing
and reports it as a bug — the Cities & Knights starting commodity was reported
exactly that way. The trace names only rules that actually changed a value, so
a table playing the base game hears nothing.
"""

import random

from game import rules as rules_module
from game.game import Game


def _game(**overrides):
    rules = dict(rules_module.defaults())
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _settle(game, name, building_type='settlement', number=None):
    """Put one building on a producing hex, and set that hex's number.

    The number is forced rather than discovered: a shuffled board rarely puts a
    6 or an 8 where the walk finds it first, and a test that skips when it does
    not is a test that pins nothing on most runs.
    """
    for vertex in (game.vertices[key] for key in sorted(game.vertices)):
        for hex_key in vertex.neighbors.get('hexes', []):
            hex_obj = game.hexes.get(hex_key)
            if hex_obj and hex_obj.number and hex_obj.type not in ('desert', 'ocean'):
                if number is not None:
                    hex_obj.number = number
                vertex.building = {'type': building_type, 'player': name}
                return hex_obj.number
    raise AssertionError("no producing hex adjacent to any vertex")


class TestTheTraceNamesOnlyWhatChanged:
    def test_a_base_game_roll_names_nothing(self):
        """Nothing to explain, so nothing is said."""
        game = _game()
        number = _settle(game, 'Alice')
        game.distribute_resources(number)
        assert game.production_modifiers == set()

    def test_epidemic_is_named_when_it_cuts_a_city(self):
        game = _game(epidemic=True, city_production=2)
        number = _settle(game, 'Alice', 'city', number=6)
        game.distribute_resources(number)
        assert 'epidemic' in game.production_modifiers

    def test_epidemic_is_silent_on_a_number_it_does_not_touch(self):
        """It applies on every roll and changes nothing outside 6 and 8."""
        game = _game(epidemic=True, city_production=2)
        number = _settle(game, 'Alice', 'city', number=5)
        game.distribute_resources(number)
        assert 'epidemic' not in game.production_modifiers

    def test_the_trace_describes_one_roll_only(self):
        """It must not carry a rule over from the previous turn."""
        game = _game(epidemic=True, city_production=2)
        number = _settle(game, 'Alice', 'city', number=6)
        game.distribute_resources(number)
        game.distribute_resources(7)
        assert game.production_modifiers == set()


class TestTheRollReportsIt:
    def test_roll_dice_carries_the_trace(self):
        game = _game()
        result = game.roll_dice('Alice')
        assert result['modifiers'] == []

    def test_the_board_reports_what_is_left_of_a_dice_deck(self):
        """A count, never the order — the order would make the draw certain."""
        game = _game(dice_deck=True)
        game.roll_dice('Alice')
        board = game.get_board_data('Alice')
        assert board['dice_deck_remaining'] == len(game.dice_deck)
        assert board['dice_deck_remaining'] > 0

    def test_no_deck_means_nothing_left(self):
        game = _game()
        board = game.get_board_data('Alice')
        assert board['dice_deck_remaining'] == 0
