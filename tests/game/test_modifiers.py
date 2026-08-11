"""The modifier funnel: what it applies, and in what order.

What a player would notice if one of these broke: a city collecting the wrong
number of cards, a build costing the wrong resources, or two house rules
touching the same number producing a different answer on Tuesday than they did
on Monday because the modules happened to import in another order.
"""

import random

import pytest
from game import modifiers as modifiers_module
from game import rules as rules_module
from game.game import Game

from tests.conftest import ScriptedRandom


def make_game(rules=None, rng=None):
    return Game(['Alice', 'Bob'], [], rng=rng or random.Random(4242), rules=rules)


class TestTheOrderIsExplicit:
    def test_production_runs_in_this_order_and_no_other(self):
        """Pinned as a list, because the order is the whole point.

        `city_production` decides a city's share, `harbor_settlement_yield`
        holds a harbor settlement to one card, `commodities` replaces half of it
        with a commodity, `gold_field` turns a gold field's share into gold,
        `epidemic` caps whatever came out, and the robber takes the lot. Any
        other sequence pays a different number.
        """
        assert [
            modifier.rule_id
            for modifier in modifiers_module.registered(modifiers_module.PRODUCTION)
        ] == ['city_production', 'harbor_settlement_yield', 'commodities',
              'gold_field', 'epidemic', 'robber']

    def test_two_modifiers_may_not_claim_one_place_in_the_line(self):
        """A tie would be broken by import order, which is not an order."""
        clash = modifiers_module.Modifier(
            'test_clash', modifiers_module.PRODUCTION, 10,
            lambda rules: True, lambda value, rules, context: value,
        )
        with pytest.raises(ValueError, match='order 10'):
            modifiers_module.register(clash)

    def test_a_later_modifier_sees_what_an_earlier_one_did(self):
        """The funnel folds; it does not pick a winner.

        Two modifiers on one number, installed out of order, still compose
        first-then-second — which is what a rule author has to be able to rely
        on before writing the second one.
        """
        doubles = modifiers_module.Modifier(
            'test_doubles', modifiers_module.COST, 90, lambda rules: True,
            lambda value, rules, context: {res: n * 2 for res, n in value.items()},
        )
        adds_one = modifiers_module.Modifier(
            'test_adds_one', modifiers_module.COST, 80, lambda rules: True,
            lambda value, rules, context: {res: n + 1 for res, n in value.items()},
        )
        game = make_game()

        with modifiers_module.installed(doubles), modifiers_module.installed(adds_one):
            # road is 1 wood 1 brick: (1 + 1) * 2, never 1 * 2 + 1.
            assert game.get_cost('road') == {'wood': 4, 'brick': 4}

    def test_a_modifier_may_not_scribble_on_the_value_it_was_handed(self):
        """The base cost table is loaded once and shared by every call."""
        game = make_game()
        game.get_cost('road')['wood'] = 99

        assert game.get_cost('road') == {'wood': 1, 'brick': 1}


class TestNothingChangesWithNothingTicked:
    def test_the_base_game_costs_are_what_comes_out_of_the_funnel(self):
        game = make_game()
        assert game.get_cost('settlement') == {
            'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1,
        }
        assert game.get_cost('city') == {'wheat': 2, 'ore': 3}

    def test_a_settlement_takes_one_card_and_a_city_two(self):
        game = make_game()
        vertex, hex_obj = a_producing_corner(game)

        vertex.building = {'type': 'settlement', 'player': 'Alice'}
        assert game.production_for(vertex, hex_obj, hex_obj.number, False) == {
            'resources': 1, 'commodity': None,
        }
        vertex.building = {'type': 'city', 'player': 'Alice'}
        assert game.production_for(vertex, hex_obj, hex_obj.number, False) == {
            'resources': 2, 'commodity': None,
        }

    def test_the_robber_stops_the_hex_paying_anybody(self):
        game = make_game()
        vertex, hex_obj = a_producing_corner(game)
        vertex.building = {'type': 'city', 'player': 'Alice'}

        assert game.production_for(vertex, hex_obj, hex_obj.number, True) == {
            'resources': 0, 'commodity': None,
        }

    def test_the_dice_are_still_two_dice_rolled(self):
        """The free roll stays two `randint` calls in that order: a seeded game
        has to reproduce the sequence it always has."""
        game = make_game(rng=ScriptedRandom([3, 4]))
        assert game.next_dice() == (3, 4)


class TestDiceSetsAreData:
    def test_every_advertised_set_is_one_the_engine_can_deal(self):
        """A picker offering a dice set nothing can roll is worse than no
        picker. Checked against the table `next_dice` actually draws from."""
        for option in rules_module.RULES_BY_ID['dice_set']['options']:
            combinations = modifiers_module.DICE_SETS[option['id']]
            assert combinations, option['id']
            assert all(1 <= face <= 6 for pair in combinations for face in pair)

    def test_the_standard_set_is_every_combination_of_two_dice(self):
        game = make_game()
        assert sorted(game.dice_combinations()) == sorted(
            (first, second) for first in range(1, 7) for second in range(1, 7)
        )


def a_producing_corner(game):
    """An intersection and one of its hexes that pays out."""
    for vertex in game.vertices.values():
        for hex_key in vertex.neighbors['hexes']:
            hex_obj = game.hexes[hex_key]
            if hex_obj.number is not None and hex_obj.type not in ('desert', 'ocean'):
                return vertex, hex_obj
    raise AssertionError('no producing corner on this board')
