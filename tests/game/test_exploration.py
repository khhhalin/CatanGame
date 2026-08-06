"""Exploration and discovery, Explorers & Pirates (expansions.md 883-893).

Each test names a rule a player would notice break: a ship that sails so an end
points at a face-down hex must turn it face up, draw its number token, end that
ship's move and pay the discoverer; a settlement or road beside an undiscovered
hex must be refused; a board with nothing left to discover must play like any
other; and a table not exploring must be untouched, its hidden-looking hex left
alone.

The board comes from a v2 hidden pool — the format that actually deals tiles
face-down — so the setup is the real thing a scenario would use, not a hex flag
poked in by hand. `transport_ships` and `harbor_settlements` ride along because
a ship is what makes a discovery, and they grow the sea a ship sails.
"""

import random

from game import board as board_module
from game import maps
from game import rules as rules_module
from game.game import Game

MAINLAND = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))
# 6 producing tiles (the desert takes none) and one token each.
HIDDEN_POOL = {
    'mode': 'hidden',
    'terrain': {'wood': 2, 'wheat': 2, 'sheep': 1, 'brick': 1, 'desert': 1},
    'numbers': [3, 4, 5, 6, 9, 10],
}
FACEUP_POOL = {
    'mode': 'shuffled',
    'terrain': {'wood': 2, 'wheat': 2, 'sheep': 1, 'brick': 1, 'desert': 1},
    'numbers': [3, 4, 5, 6, 9, 10],
}


def _map(pool) -> dict:
    sea_count = len(maps.frame_hex_keys(3)) - len(MAINLAND)
    return {
        'map_version': 2, 'id': 'explore-map', 'name': 'Explore Map',
        'frame': {'radius': 3},
        'regions': [
            {'id': 'mainland', 'kind': 'main', 'hexes': MAINLAND, 'pool': pool},
            {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
             'pool': {'mode': 'shuffled', 'terrain': {'sea': sea_count}, 'numbers': []}},
        ],
        'harbours': {'mode': 'bag', 'types': {}},
    }


def _game(pool, seed=5, **overrides) -> Game:
    document = _map(pool)
    rules = dict(rules_module.defaults())
    rules['transport_ships'] = True
    rules['harbor_settlements'] = True
    rules['ships_explore'] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], rng=random.Random(seed), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    return game


def _plant_ship(game, name, edge_key):
    game.edges[edge_key].ship = {
        'player': name, 'kind': 'transport', 'cargo': [], 'id': 1, 'built_turn': 0,
    }
    game.get_player(name).ships.append(edge_key)


def _find_discovery_move(game):
    """A (from_edge, to_edge) one sea step apart where to_edge points at hidden.

    `to_edge` has an end that is a corner of an undiscovered hex; `from_edge` is
    an empty sea side one step away to sail off. Mirrors the geometry the real
    game walks.
    """
    for to_edge in sorted(game.edges):
        if not game.is_sea_edge(to_edge) or game.edges[to_edge].ship is not None:
            continue
        ends_touch_hidden = any(
            game.hexes[hk].hidden
            for v in game.edges[to_edge].neighbors['vertices']
            for hk in game.vertices[v].neighbors['hexes']
            if hk in game.hexes
        )
        if not ends_touch_hidden:
            continue
        for from_edge in game._sea_edge_neighbors(to_edge):
            if game.edges[from_edge].ship is None:
                return from_edge, to_edge
    raise AssertionError('no discovery move on this board')


def _hidden_hexes_at(game, edge_key):
    return {
        hk
        for v in game.edges[edge_key].neighbors['vertices']
        for hk in game.vertices[v].neighbors['hexes']
        if hk in game.hexes and game.hexes[hk].hidden
    }


class TestDiscovery:
    def test_moving_a_ship_to_point_at_a_face_down_hex_reveals_it(self):
        """884-887: an end pointing at an undiscovered hex turns it face up and,
        if it is a terrain hex, draws it a number token."""
        game = _game(HIDDEN_POOL)
        from_edge, to_edge = _find_discovery_move(game)
        _plant_ship(game, 'Alice', from_edge)

        expected = _hidden_hexes_at(game, to_edge)
        assert expected  # the move really does point at hidden land

        assert game.move_transport_ship('Alice', from_edge, to_edge)['success']

        for hex_key in expected:
            hex_obj = game.hexes[hex_key]
            assert not hex_obj.hidden
            if maps.takes_a_token(hex_obj.type):
                assert hex_obj.number in maps.TOKEN_VALUES
            else:
                assert hex_obj.number is None

    def test_a_discovery_rewards_the_discoverer(self):
        """887-888: a terrain hex pays 1 of its resource, anything else 2 gold."""
        game = _game(HIDDEN_POOL)
        from_edge, to_edge = _find_discovery_move(game)
        _plant_ship(game, 'Alice', from_edge)
        alice = game.get_player('Alice')
        alice.resources = {}
        alice.gold = 0

        expected = _hidden_hexes_at(game, to_edge)
        want_resource = sum(
            1 for hk in expected if game.hexes[hk].type in maps.RESOURCE_TERRAINS
        )
        want_gold = sum(
            2 for hk in expected if game.hexes[hk].type not in maps.RESOURCE_TERRAINS
        )

        game.move_transport_ship('Alice', from_edge, to_edge)

        assert sum(alice.resources.values()) == want_resource
        assert alice.gold == want_gold

    def test_a_discovery_ends_that_ships_move(self):
        """890: after a discovery the ship may move no farther this turn."""
        game = _game(HIDDEN_POOL)
        from_edge, to_edge = _find_discovery_move(game)
        _plant_ship(game, 'Alice', from_edge)

        game.move_transport_ship('Alice', from_edge, to_edge)
        assert 1 in game.transport_ships_moved

        onward = next(iter(game._reachable_sea_edges(to_edge, 1)))
        assert game.move_transport_ship('Alice', to_edge, onward)['code'] == 'ALREADY_MOVED'


class TestBuildGuards:
    def test_a_settlement_beside_an_undiscovered_hex_is_refused(self):
        """891: no settlement at an intersection beside a face-down hex."""
        game = _game(HIDDEN_POOL)
        vertex_key = next(
            key for key in sorted(game.vertices)
            if any(game.hexes.get(hk) and game.hexes[hk].hidden
                   for hk in game.vertices[key].neighbors['hexes'])
        )
        game.setup_action = 'settlement'
        game.game_phase = 'setup'
        result = game.place_settlement('Alice', vertex_key)
        assert result['code'] == 'UNDISCOVERED_ADJACENT'
        assert game.vertices[vertex_key].building is None

    def test_a_road_beside_an_undiscovered_hex_is_refused(self):
        """891: no road on a path beside a face-down hex."""
        game = _game(HIDDEN_POOL)
        edge_key = next(
            key for key in sorted(game.edges)
            if game.land_hexes_of_edge(key)
            and any(game.hexes.get(hk) and game.hexes[hk].hidden
                    for hk in game.edges[key].neighbors['hexes'])
        )
        game.game_phase = 'setup'
        game.setup_action = 'road'
        game.last_setup_settlement = game.edges[edge_key].neighbors['vertices'][0]
        result = game.build_road('Alice', edge_key)
        assert result['code'] == 'UNDISCOVERED_ADJACENT'
        assert game.edges[edge_key].road is None


class TestNothingLeftToDiscover:
    def test_a_fully_discovered_board_moves_a_ship_normally(self):
        """No hidden hex anywhere: a ship move reveals nothing and pays nothing."""
        game = _game(FACEUP_POOL)
        assert not any(h.hidden for h in game.hexes.values())

        sea_edge = next(key for key in sorted(game.edges) if game.is_sea_edge(key))
        target = next(iter(game._reachable_sea_edges(sea_edge, 1)))
        _plant_ship(game, 'Alice', sea_edge)
        alice = game.get_player('Alice')
        alice.resources = {}
        alice.gold = 0

        assert game.move_transport_ship('Alice', sea_edge, target)['success']
        assert game.discover_from_ship('Alice', target) == []
        assert sum(alice.resources.values()) == 0
        assert alice.gold == 0


class TestOffByDefault:
    def test_the_rule_off_never_discovers_and_leaves_a_hidden_hex_alone(self):
        """A base-game table with a stray hidden flag is untouched: no reveal, no
        reward, no build guard."""
        rules = dict(rules_module.defaults())
        rules['turn_order'] = 'lobby'
        game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules)
        game.start()
        game.game_phase = 'playing'

        # Poke a hex face-down; with the rule off nothing should react to it.
        hex_key = next(iter(game.hexes))
        game.hexes[hex_key].hidden = True
        edge_key = next(
            key for key, edge in game.edges.items()
            if hex_key in edge.neighbors['hexes']
        )

        assert game.discover_from_ship('Alice', edge_key) == []
        assert game.hexes[hex_key].hidden is True
