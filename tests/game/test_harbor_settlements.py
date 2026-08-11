"""Harbor settlements, the Explorers & Pirates coastal upgrade (expansions.md 894-902).

Each test names a payout or a refusal a player would notice go wrong: a harbor
settlement that scored the wrong number of points, one built for the wrong price
or on dry land, one that a player kept building past their supply, or a harbor
settlement double-producing like a city. The base game must be untouched when
the rule is off, so the last class plays without it.

Ships are switched on alongside so the board grows its sea and coastal
intersections exist to upgrade; the coastal test itself is the harbor-settlement
rule's, read from that geometry.
"""

import random

from game import rules as rules_module
from game.game import Game


def _game(**overrides):
    rules = dict(rules_module.defaults())
    rules['ships'] = True  # so the board generates the sea and coastal sites exist
    rules['turn_order'] = 'lobby'
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _coastal_vertex(game):
    """A vertex that borders land and touches a sea side — a harbor's home."""
    for key in sorted(game.vertices):
        vertex = game.vertices[key]
        if vertex.neighbors.get('hexes') and game.is_coastal_settlement_site(key):
            return key
    raise AssertionError('no coastal vertex on this board')


def _inland_vertex(game):
    """A vertex touching only land — no sea side meets it."""
    for key in sorted(game.vertices):
        vertex = game.vertices[key]
        if vertex.neighbors.get('hexes') and not game.is_coastal_settlement_site(key):
            return key
    raise AssertionError('no inland vertex on this board')


def _settle(game, name, vertex_key):
    """Put a plain settlement for a player on a vertex, the way setup would."""
    game.vertices[vertex_key].building = {'type': 'settlement', 'player': name}
    game.get_player(name).settlements.append(vertex_key)


def _fund(game, name):
    """Give a player exactly one harbor settlement's price: 2 grain + 2 ore."""
    player = game.get_player(name)
    player.resources['wheat'] = 2
    player.resources['ore'] = 2


class TestBuildingOne:
    def test_the_price_is_two_grain_and_two_ore(self):
        """894: the upgrade costs 2 grain and 2 ore, and nothing else moves."""
        assert _game().get_cost('harbor_settlement') == {'wheat': 2, 'ore': 2}

    def test_upgrading_spends_the_price_and_leaves_nothing_over(self):
        game = _game(harbor_settlements=True)
        _fund(game, 'Alice')
        game.get_player('Alice').resources['sheep'] = 1  # untouched by the upgrade
        vertex = _coastal_vertex(game)
        _settle(game, 'Alice', vertex)
        assert game.build_harbor_settlement('Alice', vertex)['success']
        player = game.get_player('Alice')
        assert player.resources == {'wheat': 0, 'ore': 0, 'sheep': 1}
        assert player.harbor_settlements == [vertex]
        assert vertex not in player.settlements
        assert game.vertices[vertex].building['type'] == 'harbor_settlement'
        assert game.vertices[vertex].building['basin'] == []

    def test_it_replaces_the_settlement_and_is_worth_two(self):
        """894: a harbor settlement scores 2, so a 1-point settlement gains 1."""
        game = _game(harbor_settlements=True)
        _fund(game, 'Alice')
        vertex = _coastal_vertex(game)
        _settle(game, 'Alice', vertex)
        assert game.victory_points_for('Alice') == 1  # the plain settlement
        assert game.build_harbor_settlement('Alice', vertex)['success']
        assert game.victory_points_for('Alice') == 2  # not 1, and not 3


class TestWhereItMayNotGo:
    def test_a_landlocked_settlement_is_refused(self):
        """895: a harbor settlement stands where land meets sea, never inland."""
        game = _game(harbor_settlements=True)
        _fund(game, 'Alice')
        vertex = _inland_vertex(game)
        _settle(game, 'Alice', vertex)
        result = game.build_harbor_settlement('Alice', vertex)
        assert result['code'] == 'NOT_COASTAL'
        assert game.get_player('Alice').harbor_settlements == []
        assert game.vertices[vertex].building['type'] == 'settlement'

    def test_the_supply_runs_out(self):
        """849: a player has only so many harbor settlements to build."""
        game = _game(harbor_settlements=True, max_harbor_settlements=1)
        alice = game.get_player('Alice')
        coastal = [
            key for key in sorted(game.vertices)
            if game.vertices[key].neighbors.get('hexes')
            and game.is_coastal_settlement_site(key)
        ]
        first, second = coastal[0], coastal[1]
        _settle(game, 'Alice', first)
        _settle(game, 'Alice', second)
        _fund(game, 'Alice')
        assert game.build_harbor_settlement('Alice', first)['success']
        alice.resources['wheat'], alice.resources['ore'] = 2, 2
        refused = game.build_harbor_settlement('Alice', second)
        assert refused['code'] == 'NO_PIECES_LEFT'
        assert alice.harbor_settlements == [first]

    def test_the_rule_off_refuses_the_build(self):
        game = _game(harbor_settlements=False)
        _fund(game, 'Alice')
        vertex = _coastal_vertex(game)
        _settle(game, 'Alice', vertex)
        assert game.build_harbor_settlement('Alice', vertex)['code'] == 'RULE_NOT_IN_PLAY'


class TestProduction:
    def test_a_harbor_settlement_yields_one_not_two(self):
        """901: it produces a settlement's one card, never a city's two.

        A city on the same wood hex would bank two; a harbor settlement banks
        one. Without the yield modifier — or if it were scored as a city — this
        would read two.
        """
        game = _game(harbor_settlements=True)
        _fund(game, 'Alice')
        vertex_key = _coastal_vertex(game)
        vertex = game.vertices[vertex_key]
        _settle(game, 'Alice', vertex_key)
        assert game.build_harbor_settlement('Alice', vertex_key)['success']
        # Force an adjacent land hex to a known wood/number so the roll pays it.
        land = next(
            game.hexes[hex_key]
            for hex_key in vertex.neighbors['hexes']
            if hex_key in game.hexes and game.hexes[hex_key].type not in ('ocean', 'desert')
        )
        land.type, land.number = 'wood', 8
        game.distribute_resources(8)
        assert game.get_player('Alice').resources.get('wood') == 1

    def test_the_modifier_holds_the_yield_at_one(self):
        """The production funnel itself pins a harbor settlement to one card."""
        game = _game(harbor_settlements=True)
        vertex_key = _coastal_vertex(game)
        vertex = game.vertices[vertex_key]
        vertex.building = {'type': 'harbor_settlement', 'player': 'Alice', 'basin': []}
        land = next(
            game.hexes[hex_key]
            for hex_key in vertex.neighbors['hexes']
            if hex_key in game.hexes and game.hexes[hex_key].type not in ('ocean', 'desert')
        )
        produced = game.production_for(vertex, land, land.number, robber_here=False)
        assert produced['resources'] == 1


class TestBaseGameUntouched:
    def test_a_player_starts_with_no_harbor_settlements(self):
        assert Game(['Alice', 'Bob'], [], {}).get_player('Alice').harbor_settlements == []

    def test_the_upgrade_does_not_exist_without_the_rule(self):
        """With the rule off, a coastal settlement scores its plain 1 point."""
        game = _game(harbor_settlements=False)
        _fund(game, 'Alice')
        vertex = _coastal_vertex(game)
        _settle(game, 'Alice', vertex)
        assert game.victory_points_for('Alice') == 1
        assert game.build_harbor_settlement('Alice', vertex)['success'] is False
