"""Bug: the log never said who the roll paid.

A roll logged "Alice rolled 3 + 3 = 6" and stopped there, so no player could
tell what arrived — which is also how a production bug hides: the tester
reported the Cities & Knights starting commodity as a bug partly because
nothing ever stated what a roll had handed out.

`distribute_resources` already built the answer and threw it away.
"""

import random

from game import rules as rules_module
from game.game import Game

from tests.conftest import ScriptedRandom


def _game(rng=None, **overrides):
    rules = dict(rules_module.defaults())
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=rng or random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _settle(game, name, building_type='settlement', number=None, skip=0):
    """Put one building on a producing hex and force that hex's number.

    `skip` walks past intersections already used, so two players can be seated
    on the same number without landing on the same vertex.
    """
    for vertex_key in sorted(game.vertices):
        vertex = game.vertices[vertex_key]
        if vertex.building:
            continue
        for hex_key in vertex.neighbors.get('hexes', []):
            hex_obj = game.hexes.get(hex_key)
            if hex_obj and hex_obj.number and hex_obj.type not in ('desert', 'ocean'):
                if skip:
                    skip -= 1
                    break
                if number is not None:
                    hex_obj.number = number
                vertex.building = {'type': building_type, 'player': name}
                return hex_obj.number, hex_obj.type
    raise AssertionError("no producing hex adjacent to any free vertex")


class TestDistributionReportsWhatItPaid:
    def test_it_names_every_player_and_card(self):
        game = _game()
        number, terrain = _settle(game, 'Alice', number=6)
        gained = game.distribute_resources(number)
        assert gained == {'Alice': {terrain: 1}}

    def test_a_roll_that_paid_nobody_reports_an_empty_result(self):
        """Distinguishable from "nothing was computed": the caller has to be
        able to say "that roll paid nobody" rather than staying silent."""
        game = _game()
        _settle(game, 'Alice', number=6)
        assert game.distribute_resources(5) == {}

    def test_a_commodity_is_named_alongside_the_resource(self):
        game = _game(commodities=True, city_production=2)
        number, _terrain = _settle(game, 'Alice', 'city', number=6)
        # Forced rather than searched for: a shuffled board rarely puts a city
        # on the forest the walk finds first, and a test that skips when it
        # does not is a test that pins nothing on most runs.
        for hex_obj in game.hexes.values():
            if hex_obj.number == number and hex_obj.type not in ('desert', 'ocean'):
                hex_obj.type = 'wood'
        gained = game.distribute_resources(number)
        # Line 323: a city on forest takes one lumber and one paper.
        assert gained['Alice'] == {'paper': 1, 'wood': 1}


class TestTheRollCarriesIt:
    def test_roll_dice_reports_the_production(self):
        game = _game(rng=ScriptedRandom([3, 3]))
        _number, terrain = _settle(game, 'Alice', number=6)
        result = game.roll_dice(game.players[game.current_player_index].name)
        assert result['total'] == 6
        assert result['gained'] == {'Alice': {terrain: 1}}

    def test_a_seven_pays_nobody(self):
        game = _game(rng=ScriptedRandom([3, 4]))
        _settle(game, 'Alice', number=6)
        result = game.roll_dice(game.players[game.current_player_index].name)
        assert result['total'] == 7
        assert result['gained'] == {}
