"""Transport ships, the Explorers & Pirates cargo carriers (expansions.md 864-882).

Each test names a rule a player would notice break: a transport ship built for
the wrong price or off dry land, one built where there is no harbor settlement,
one that sailed further than its movement points or moved twice in a turn, a
hold that took more than one large or two small pieces, and — the sharpest
E&P/Seafarers conflict — a transport ship counted as a route extender. The base
game and Seafarers must be untouched when the rule is off, so those play without
it.

`harbor_settlements` rides along because a transport ship is built and loaded at
a harbor settlement; `transport_ships` grows the board's sea so there are routes
to sail. The two ship models are mutually exclusive at `start_game`, so no test
turns `ships` and `transport_ships` on together.
"""

import random

from game import rules as rules_module
from game.game import Game


def _game(**overrides):
    rules = dict(rules_module.defaults())
    rules['transport_ships'] = True   # grows the sea and enables transports
    rules['harbor_settlements'] = True
    rules['turn_order'] = 'lobby'
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _place_harbor(game, name):
    """Plant a harbor settlement on a coastal vertex and return it."""
    for key in sorted(game.vertices):
        vertex = game.vertices[key]
        if vertex.neighbors.get('hexes') and game.is_coastal_settlement_site(key):
            vertex.building = {'type': 'harbor_settlement', 'player': name, 'basin': []}
            game.get_player(name).harbor_settlements.append(key)
            return key
    raise AssertionError('no coastal vertex on this board')


def _sea_edge_at(game, vertex_key):
    """A sea side meeting this vertex — where a ship is built beside it."""
    for edge_key in game.vertices[vertex_key].neighbors['edges']:
        if game.is_sea_edge(edge_key):
            return edge_key
    raise AssertionError('coastal vertex has no sea edge')


def _fund_ship(game, name):
    """Give a player exactly one transport ship's price: 1 wood + 1 sheep."""
    player = game.get_player(name)
    player.resources = {'wood': 1, 'sheep': 1}


def _build(game, name):
    """Place a harbor, fund a ship and build it. Returns (harbor, ship edge)."""
    harbor = _place_harbor(game, name)
    edge = _sea_edge_at(game, harbor)
    _fund_ship(game, name)
    assert game.build_transport_ship(name, edge)['success']
    return harbor, edge


class TestPrice:
    def test_the_price_is_one_wood_and_one_sheep(self):
        """864: a transport ship is built for 1 lumber and 1 wool, nothing else."""
        assert _game().get_cost('transport_ship') == {'wood': 1, 'sheep': 1}

    def test_building_spends_exactly_the_price(self):
        game = _game()
        harbor = _place_harbor(game, 'Alice')
        edge = _sea_edge_at(game, harbor)
        alice = game.get_player('Alice')
        alice.resources = {'wood': 1, 'sheep': 1, 'ore': 3}  # ore untouched
        assert game.build_transport_ship('Alice', edge)['success']
        assert alice.resources == {'wood': 0, 'sheep': 0, 'ore': 3}


class TestWhereItMayBeBuilt:
    def test_it_is_built_beside_a_harbor_settlement(self):
        game = _game()
        harbor, edge = _build(game, 'Alice')
        ship = game.edges[edge].ship
        assert ship['kind'] == 'transport'
        assert ship['cargo'] == []
        assert edge in game.get_player('Alice').ships

    def test_a_bare_coastline_without_a_harbor_is_refused(self):
        """899: a harbor settlement, not any coast, is the only build site."""
        game = _game()
        # A sea edge with no harbor settlement of Alice's on either end.
        harbor = _place_harbor(game, 'Alice')
        harbor_edges = set(game.vertices[harbor].neighbors['edges'])
        loose = next(
            key for key in sorted(game.edges)
            if game.is_sea_edge(key) and key not in harbor_edges
        )
        _fund_ship(game, 'Alice')
        result = game.build_transport_ship('Alice', loose)
        assert result['code'] == 'NOT_AT_HARBOR'
        assert game.edges[loose].ship is None

    def test_a_land_side_is_refused(self):
        game = _game()
        _place_harbor(game, 'Alice')
        land_edge = next(key for key in sorted(game.edges) if not game.is_sea_edge(key))
        _fund_ship(game, 'Alice')
        assert game.build_transport_ship('Alice', land_edge)['code'] == 'INVALID_PLACEMENT'


class TestMovement:
    def test_a_ship_sails_to_a_reachable_sea_side(self):
        game = _game()
        _harbor, edge = _build(game, 'Alice')
        target = next(iter(game._reachable_sea_edges(edge, 1)))
        assert game.move_transport_ship('Alice', edge, target)['success']
        assert game.edges[edge].ship is None
        assert game.edges[target].ship['kind'] == 'transport'
        assert target in game.get_player('Alice').ships
        assert edge not in game.get_player('Alice').ships

    def test_a_ship_moves_only_once_per_turn(self):
        game = _game()
        _harbor, edge = _build(game, 'Alice')
        first = next(iter(game._reachable_sea_edges(edge, 1)))
        assert game.move_transport_ship('Alice', edge, first)['success']
        second = next(iter(game._reachable_sea_edges(first, 1)))
        result = game.move_transport_ship('Alice', first, second)
        assert result['code'] == 'ALREADY_MOVED'
        assert game.edges[second].ship is None

    def test_the_allowance_returns_next_turn(self):
        game = _game()
        _harbor, edge = _build(game, 'Alice')
        first = next(iter(game._reachable_sea_edges(edge, 1)))
        assert game.move_transport_ship('Alice', edge, first)['success']
        game.start_turn()
        second = next(iter(game._reachable_sea_edges(first, 1)))
        assert game.move_transport_ship('Alice', first, second)['success']

    def test_a_side_beyond_the_movement_points_is_refused(self):
        """874: a ship sails at most `ship_movement_points` sea sides."""
        game = _game(ship_movement_points=1)
        _harbor, edge = _build(game, 'Alice')
        within = game._reachable_sea_edges(edge, 1)
        beyond = game._reachable_sea_edges(edge, 3)
        far = next(key for key in beyond if key not in within)
        result = game.move_transport_ship('Alice', edge, far)
        assert result['code'] == 'OUT_OF_RANGE'
        assert game.edges[far].ship is None


class TestHold:
    def test_the_hold_takes_two_small_pieces(self):
        game = _game()
        harbor, edge = _build(game, 'Alice')
        basin = game.vertices[harbor].building['basin']
        basin.extend([{'type': 'crew', 'size': 'small'}, {'type': 'crew', 'size': 'small'}])
        assert game.load_transport_ship('Alice', edge, 0)['success']
        assert game.load_transport_ship('Alice', edge, 0)['success']
        assert len(game.edges[edge].ship['cargo']) == 2
        assert game.vertices[harbor].building['basin'] == []

    def test_the_hold_rejects_a_third_small_piece(self):
        game = _game()
        harbor, edge = _build(game, 'Alice')
        basin = game.vertices[harbor].building['basin']
        basin.extend([{'type': 'crew', 'size': 'small'}] * 3)
        assert game.load_transport_ship('Alice', edge, 0)['success']
        assert game.load_transport_ship('Alice', edge, 0)['success']
        assert game.load_transport_ship('Alice', edge, 0)['code'] == 'HOLD_FULL'
        assert len(game.edges[edge].ship['cargo']) == 2

    def test_a_large_piece_fills_the_hold_alone(self):
        game = _game()
        harbor, edge = _build(game, 'Alice')
        basin = game.vertices[harbor].building['basin']
        basin.extend([{'type': 'settler', 'size': 'large'}, {'type': 'crew', 'size': 'small'}])
        assert game.load_transport_ship('Alice', edge, 0)['success']
        assert game.load_transport_ship('Alice', edge, 0)['code'] == 'HOLD_FULL'

    def test_unloading_returns_a_piece_to_the_basin(self):
        game = _game()
        harbor, edge = _build(game, 'Alice')
        piece = {'type': 'settler', 'size': 'large'}
        game.vertices[harbor].building['basin'].append(piece)
        assert game.load_transport_ship('Alice', edge, 0)['success']
        assert game.unload_transport_ship('Alice', edge, 0)['success']
        assert game.edges[edge].ship['cargo'] == []
        assert game.vertices[harbor].building['basin'] == [piece]


class TestNeverARoute:
    def test_a_transport_ship_never_extends_a_route(self):
        """866: a transport ship forms no route, so it never joins a network.

        Reaches into `_touches_own_route` directly with `ships` on and a
        transport-kind ship planted, the one state the guard defends — the two
        ship models cannot both be on at a real table.
        """
        rules = dict(rules_module.defaults())
        rules['ships'] = True
        rules['turn_order'] = 'lobby'
        game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
        game.start()
        game.game_phase = 'playing'
        sea_edge = next(key for key in sorted(game.edges) if game.is_sea_edge(key))
        vertex = game.edges[sea_edge].neighbors['vertices'][0]

        game.edges[sea_edge].ship = {'player': 'Alice', 'kind': 'transport', 'cargo': []}
        assert not game._touches_own_route('Alice', vertex)

        game.edges[sea_edge].ship = {'player': 'Alice', 'built_turn': 0}
        assert game._touches_own_route('Alice', vertex)


class TestOffByDefault:
    def test_moving_a_transport_is_refused_when_the_rule_is_off(self):
        rules = dict(rules_module.defaults())
        rules['turn_order'] = 'lobby'
        game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
        game.start()
        game.game_phase = 'playing'
        assert game.build_transport_ship('Alice', 'anything')['code'] == 'RULE_NOT_IN_PLAY'

    def test_the_base_board_grows_no_sea_without_a_ship_rule(self):
        """Neither ships nor transport_ships: the ocean stays scenery."""
        rules = dict(rules_module.defaults())
        game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
        assert not any(game.is_sea_edge(key) for key in game.edges)

    def test_transport_ships_alone_grows_the_sea(self):
        game = _game()
        assert any(game.is_sea_edge(key) for key in game.edges)
