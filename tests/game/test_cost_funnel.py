"""Every price in the game comes out of `Game.get_cost`.

What a player would notice if this broke: a knight, a wall or a city
improvement charging something the table never agreed to — either the wrong
price outright, or the right one while a house rule that makes building
cheaper is quietly skipped for half the board.

The Cities & Knights prices used to be module constants paid straight out of a
hand, so a cost modifier reached a ship and not a knight. These tests pin both
halves: the prices are unchanged with nothing ticked, and one modifier now
reaches all of them.
"""

import random

import pytest
from game import cities_knights as ck
from game import modifiers as modifiers_module
from game import rules as rules_module
from game.game import Game


def ck_game(extra=None):
    rules = rules_module.preset_rules('cities_and_knights')
    rules.update(extra or {})
    return Game(['Alice', 'Bob'], [], rng=random.Random(7), rules=rules)


def road_and_vertex(game, name='Alice'):
    """Give a player one road, and return a vacant intersection on it."""
    for edge_key, edge in sorted(game.edges.items()):
        if edge.road or edge.ship:
            continue
        vertices = edge.neighbors.get('vertices', [])
        free = [key for key in vertices if game.vertices[key].building is None]
        if len(free) == len(vertices) == 2:
            edge.road = {'player': name}
            game.get_player(name).roads.append(edge_key)
            return free[0]
    pytest.fail('no free edge on this board')


def city_for(game, name='Alice'):
    """Put a city on the board for a player who needs one to improve."""
    for vertex_key, vertex in sorted(game.vertices.items()):
        if vertex.building is None:
            vertex.building = {'type': 'city', 'player': name}
            game.get_player(name).cities.append(vertex_key)
            return vertex_key
    pytest.fail('no free vertex on this board')


def doubling(order=95):
    """A modifier that doubles every price, whatever is being bought."""
    return modifiers_module.Modifier(
        'test_everything_costs_double', modifiers_module.COST, order,
        lambda rules: True,
        lambda value, rules, context: {card: n * 2 for card, n in value.items()},
    )


class TestThePricesAreWhatTheyAlwaysWere:
    """The refactor's whole claim: with no modifier active, nothing moved.

    Pinned against the rulebook rather than against the table the engine reads,
    which is the point — a literal checked against a copy of itself passes
    forever.
    """

    def test_a_knight_costs_a_sheep_and_an_ore(self):
        assert ck_game().get_cost('build_knight') == {'sheep': 1, 'ore': 1}

    def test_activating_a_knight_costs_a_grain(self):
        assert ck_game().get_cost('activate_knight') == {'wheat': 1}

    def test_promoting_a_knight_costs_a_sheep_and_an_ore(self):
        assert ck_game().get_cost('promote_knight') == {'sheep': 1, 'ore': 1}

    def test_a_city_wall_costs_two_brick(self):
        assert ck_game().get_cost('city_wall') == {'brick': 2}

    def test_medicine_upgrades_a_settlement_for_two_ore_and_a_grain(self):
        assert ck_game().get_cost('medicine_city') == {'ore': 2, 'wheat': 1}

    def test_an_improvement_costs_its_level_in_the_track_commodity(self):
        """Level 1 costs 1, level 5 costs 5 — in cloth, coin or paper by track."""
        game = ck_game()
        assert [
            game.get_cost(ck.improvement_build_type(ck.TRADE), level=level)
            for level in range(1, 6)
        ] == [{'cloth': level} for level in range(1, 6)]
        assert game.get_cost(ck.improvement_build_type(ck.POLITICS), level=2) == {'coin': 2}
        assert game.get_cost(ck.improvement_build_type(ck.SCIENCE), level=3) == {'paper': 3}

    def test_a_price_per_level_must_be_asked_for_by_level(self):
        """A missing level would price the whole track at nothing."""
        with pytest.raises(ValueError, match='level'):
            ck_game().get_cost(ck.improvement_build_type(ck.TRADE))


class TestOneModifierReachesEveryBuild:
    """A cost rule used to reach a ship and not a knight."""

    def test_a_knight_is_charged_the_modified_price(self):
        game = ck_game()
        vertex = road_and_vertex(game)
        game.get_player('Alice').resources = {'sheep': 2, 'ore': 2}

        with modifiers_module.installed(doubling()):
            assert game.build_knight('Alice', vertex)['success'] is True

        assert game.get_player('Alice').resources == {'sheep': 0, 'ore': 0}

    def test_a_knight_nobody_can_pay_for_is_refused_at_the_new_price(self):
        game = ck_game()
        vertex = road_and_vertex(game)
        game.get_player('Alice').resources = {'sheep': 1, 'ore': 1}

        with modifiers_module.installed(doubling()):
            result = game.build_knight('Alice', vertex)

        assert result['success'] is False
        # The refusal quotes the price actually being charged, not the one
        # printed on the box.
        assert result['error'] == 'A knight costs 2 sheep and 2 ore'

    def test_activating_and_promoting_are_charged_the_modified_price(self):
        game = ck_game()
        vertex = road_and_vertex(game)
        player = game.get_player('Alice')
        player.resources = {'sheep': 1, 'ore': 1}
        assert game.build_knight('Alice', vertex)['success'] is True

        player.resources = {'wheat': 2, 'sheep': 2, 'ore': 2}
        with modifiers_module.installed(doubling()):
            assert game.activate_knight('Alice', vertex)['success'] is True
            assert game.promote_knight('Alice', vertex)['success'] is True

        assert player.resources == {'wheat': 0, 'sheep': 0, 'ore': 0}

    def test_a_city_wall_is_charged_the_modified_price(self):
        game = ck_game()
        vertex = city_for(game)
        game.get_player('Alice').resources = {'brick': 4}

        with modifiers_module.installed(doubling()):
            assert game.build_city_wall('Alice', vertex)['success'] is True

        assert game.get_player('Alice').resources == {'brick': 0}

    def test_an_improvement_is_charged_the_modified_price(self):
        game = ck_game()
        city_for(game)
        player = game.get_player('Alice')
        player.commodities = {'cloth': 2}

        with modifiers_module.installed(doubling()):
            result = game.buy_improvement('Alice', ck.TRADE)

        assert result['success'] is True
        assert player.commodities == {'cloth': 0}

    def test_the_hook_is_told_which_level_is_being_priced(self):
        """A rule that makes only the top of a track cheaper has to be able to
        tell level 5 from level 1."""
        seen = []
        watcher = modifiers_module.Modifier(
            'test_watches_levels', modifiers_module.COST, 96, lambda rules: True,
            lambda value, rules, context: (seen.append(context.get('level')) or value),
        )
        game = ck_game()
        with modifiers_module.installed(watcher):
            game.get_cost(ck.improvement_build_type(ck.SCIENCE), level=4)
            game.get_cost('city_wall')

        assert seen == [4, None]


class TestPayingStillTakesFromTheRightPile:
    def test_a_resource_price_goes_back_to_the_bank(self):
        game = ck_game()
        vertex = city_for(game)
        # Out of the bank, so returning them is not capped at the pile's limit.
        assert game.bank.take('brick', 2) is True
        game.get_player('Alice').resources = {'brick': 2}
        before = game.bank.get_all()['brick']

        assert game.build_city_wall('Alice', vertex)['success'] is True
        assert game.bank.get_all()['brick'] == before + 2

    def test_a_commodity_price_comes_out_of_the_commodity_pile(self):
        """Commodities are not bank stock: the bank counts five resources, and
        one spent on an improvement is simply gone."""
        game = ck_game()
        city_for(game)
        game.get_player('Alice').commodities = {'cloth': 1}

        assert game.buy_improvement('Alice', ck.TRADE)['success'] is True
        assert game.get_player('Alice').commodities == {'cloth': 0}
        assert set(game.bank.get_all()) == {'wood', 'brick', 'sheep', 'wheat', 'ore'}

    def test_a_commodity_price_is_refused_when_the_pile_is_short(self):
        game = ck_game()
        city_for(game)
        player = game.get_player('Alice')
        # A hand full of the resource the track does not want buys nothing.
        player.resources = {'wood': 9, 'brick': 9, 'sheep': 9, 'wheat': 9, 'ore': 9}
        player.commodities = {'cloth': 0}

        result = game.buy_improvement('Alice', ck.TRADE)
        assert result['success'] is False
        assert result['error'] == 'Need 1 cloth to reach level 1'
