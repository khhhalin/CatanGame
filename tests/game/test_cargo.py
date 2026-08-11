"""Cargo pieces — settlers and crews (expansions.md 903-928).

Each test names a rule a player would notice break: a settler priced wrong or
built onto bare land, a settler ship that founds a settlement for free (and one
that must be refused an occupied or open-sea corner), a crew priced wrong, a
hold or basin that overflowed its two slots, an exhausted supply that still
handed out a piece, and the base game handing out cargo it never asked for.

`cargo_settlers`/`crews` ride on `transport_ships` + `harbor_settlements` (their
`DEPENDENCIES`), so every fixture turns those on too. There are no mission
destinations yet (Wave 4), so crew placement is tested against a stubbed
`is_crew_destination` — see `TestCrewPlacement`.
"""

import random

from game import rules as rules_module
from game.game import Game


def _game(**overrides):
    rules = dict(rules_module.defaults())
    rules['transport_ships'] = True
    rules['harbor_settlements'] = True
    rules['cargo_settlers'] = True
    rules['crews'] = True
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
    for edge_key in game.vertices[vertex_key].neighbors['edges']:
        if game.is_sea_edge(edge_key):
            return edge_key
    raise AssertionError('coastal vertex has no sea edge')


def _build_ship(game, name):
    """Plant a harbor, build a transport ship beside it. Returns (harbor, edge)."""
    harbor = _place_harbor(game, name)
    edge = _sea_edge_at(game, harbor)
    game.get_player(name).resources = {'wood': 1, 'sheep': 1}
    assert game.build_transport_ship(name, edge)['success']
    return harbor, edge


class TestPrices:
    def test_a_settler_costs_a_settlement(self):
        """906: a settler costs the same as a settlement — 1/1/1/1."""
        game = _game()
        assert game.get_cost('settler') == game.get_cost('settlement')

    def test_a_crew_costs_one_ore_and_one_wool(self):
        """920: a crew costs 1 ore and 1 wool."""
        assert _game().get_cost('crew') == {'ore': 1, 'sheep': 1}


class TestBuildingSettlers:
    def test_a_settler_is_built_into_a_harbor_basin(self):
        game = _game()
        harbor = _place_harbor(game, 'Alice')
        alice = game.get_player('Alice')
        alice.resources = {'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1, 'ore': 3}
        assert game.build_settler('Alice', 'basin', harbor)['success']
        assert game.vertices[harbor].building['basin'] == [
            {'type': 'settler', 'size': 'large'}
        ]
        assert alice.settlers == 1
        assert alice.resources == {'wood': 0, 'brick': 0, 'wheat': 0, 'sheep': 0, 'ore': 3}

    def test_a_settler_is_built_into_a_ship_hold(self):
        game = _game()
        _harbor, edge = _build_ship(game, 'Alice')
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1}
        assert game.build_settler('Alice', 'hold', edge)['success']
        assert game.edges[edge].ship['cargo'] == [{'type': 'settler', 'size': 'large'}]

    def test_a_large_settler_fills_the_basin_alone(self):
        """910: a settler needs an empty basin; a second piece cannot join it."""
        game = _game()
        harbor = _place_harbor(game, 'Alice')
        alice = game.get_player('Alice')
        alice.resources = {'wood': 2, 'brick': 2, 'wheat': 2, 'sheep': 2}
        assert game.build_settler('Alice', 'basin', harbor)['success']
        assert game.build_settler('Alice', 'basin', harbor)['code'] == 'HOLD_FULL'

    def test_the_supply_limit_is_respected(self):
        """849: a player cannot build more settlers than max_settlers."""
        game = _game(max_settlers=0)
        harbor = _place_harbor(game, 'Alice')
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1}
        assert game.build_settler('Alice', 'basin', harbor)['code'] == 'NO_PIECES_LEFT'


class TestBuildingCrews:
    def test_a_crew_is_built_into_a_basin_at_its_price(self):
        game = _game()
        harbor = _place_harbor(game, 'Alice')
        alice = game.get_player('Alice')
        alice.resources = {'ore': 1, 'sheep': 1, 'wood': 2}
        assert game.build_crew('Alice', 'basin', harbor)['success']
        assert game.vertices[harbor].building['basin'] == [
            {'type': 'crew', 'size': 'small'}
        ]
        assert alice.crews == 1
        assert alice.resources == {'ore': 0, 'sheep': 0, 'wood': 2}

    def test_a_basin_takes_two_crews_not_three(self):
        """925: a basin (like a hold) holds up to two small pieces."""
        game = _game()
        harbor = _place_harbor(game, 'Alice')
        game.get_player('Alice').resources = {'ore': 3, 'sheep': 3}
        assert game.build_crew('Alice', 'basin', harbor)['success']
        assert game.build_crew('Alice', 'basin', harbor)['success']
        assert game.build_crew('Alice', 'basin', harbor)['code'] == 'HOLD_FULL'


def _empty_coastal_endpoint(game):
    """A sea edge with one empty, coastal, distance-legal endpoint. Returns
    (edge_key, vertex_key)."""
    for edge_key in sorted(game.edges):
        if not game.is_sea_edge(edge_key):
            continue
        for vertex_key in game.edges[edge_key].neighbors['vertices']:
            vertex = game.vertices[vertex_key]
            if vertex.building is not None or not vertex.neighbors['hexes']:
                continue
            neighbours = vertex.neighbors.get('vertices', [])
            if all(game.vertices[n].building is None for n in neighbours):
                return edge_key, vertex_key
    raise AssertionError('no empty coastal endpoint on this board')


def _open_sea_endpoint(game):
    """A sea edge with an endpoint out at open sea (touching no land)."""
    for edge_key in sorted(game.edges):
        if not game.is_sea_edge(edge_key):
            continue
        for vertex_key in game.edges[edge_key].neighbors['vertices']:
            if not game.vertices[vertex_key].neighbors['hexes']:
                return edge_key, vertex_key
    raise AssertionError('no open-sea endpoint on this board')


def _plant_settler_ship(game, name, edge_key):
    """Put a settler ship (one settler in the hold) on an edge for `name`."""
    game.transport_ship_counter += 1
    game.edges[edge_key].ship = {
        'player': name,
        'built_turn': 0,
        'kind': 'transport',
        'cargo': [{'type': 'settler', 'size': 'large'}],
        'id': game.transport_ship_counter,
    }
    player = game.get_player(name)
    player.ships.append(edge_key)
    player.settlers += 1


class TestFounding:
    def test_a_settler_ship_founds_a_free_settlement(self):
        """915-916: found a settlement by returning the ship and its settler."""
        game = _game()
        edge, vertex = _empty_coastal_endpoint(game)
        _plant_settler_ship(game, 'Alice', edge)
        alice = game.get_player('Alice')
        alice.resources = {}  # founding costs nothing

        result = game.found_settlement_from_ship('Alice', edge, vertex)
        assert result['success']
        assert game.vertices[vertex].building == {'type': 'settlement', 'player': 'Alice'}
        assert vertex in alice.settlements
        assert game.edges[edge].ship is None          # ship returned to supply
        assert edge not in alice.ships
        assert alice.settlers == 0                     # settler returned to supply

    def test_an_occupied_corner_is_refused(self):
        game = _game()
        edge, vertex = _empty_coastal_endpoint(game)
        game.vertices[vertex].building = {'type': 'settlement', 'player': 'Bob'}
        _plant_settler_ship(game, 'Alice', edge)
        result = game.found_settlement_from_ship('Alice', edge, vertex)
        assert result['code'] == 'OCCUPIED'
        assert game.edges[edge].ship is not None       # ship not consumed

    def test_an_open_sea_corner_is_refused(self):
        """913: a settler ship founds only at the corner of a terrain hex."""
        game = _game()
        edge, vertex = _open_sea_endpoint(game)
        _plant_settler_ship(game, 'Alice', edge)
        result = game.found_settlement_from_ship('Alice', edge, vertex)
        assert result['code'] == 'INVALID_PLACEMENT'
        assert game.edges[edge].ship is not None

    def test_a_ship_without_a_settler_cannot_found(self):
        game = _game()
        edge, vertex = _empty_coastal_endpoint(game)
        _plant_settler_ship(game, 'Alice', edge)
        game.edges[edge].ship['cargo'] = []            # emptied hold
        result = game.found_settlement_from_ship('Alice', edge, vertex)
        assert result['code'] == 'NO_SETTLER'


class TestCrewPlacement:
    """A crew rides a ship and is landed on a mission destination only (928).

    No mission provides a destination yet (Wave 4), so `is_crew_destination`
    always returns False and the happy path is exercised against a stub. The
    real limit: until the mission agents land, no vertex is ever a legal crew
    destination in a running game.
    """

    def test_a_crew_lands_on_a_stubbed_destination(self):
        game = _game()
        edge, vertex = _empty_coastal_endpoint(game)
        game.transport_ship_counter += 1
        game.edges[edge].ship = {
            'player': 'Alice', 'built_turn': 0, 'kind': 'transport',
            'cargo': [{'type': 'crew', 'size': 'small'}],
            'id': game.transport_ship_counter,
        }
        game.get_player('Alice').ships.append(edge)
        game.is_crew_destination = lambda vertex_key: vertex_key == vertex

        result = game.place_crew_on_destination('Alice', edge, vertex)
        assert result['success']
        assert game.edges[edge].ship['cargo'] == []

    def test_a_plain_vertex_is_no_destination(self):
        game = _game()
        edge, vertex = _empty_coastal_endpoint(game)
        game.transport_ship_counter += 1
        game.edges[edge].ship = {
            'player': 'Alice', 'built_turn': 0, 'kind': 'transport',
            'cargo': [{'type': 'crew', 'size': 'small'}],
            'id': game.transport_ship_counter,
        }
        game.get_player('Alice').ships.append(edge)
        result = game.place_crew_on_destination('Alice', edge, vertex)
        assert result['code'] == 'NOT_A_DESTINATION'


class TestOffByDefault:
    def test_building_a_settler_is_refused_when_the_rule_is_off(self):
        rules = dict(rules_module.defaults())
        rules['turn_order'] = 'lobby'
        game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
        game.start()
        game.game_phase = 'playing'
        assert game.build_settler('Alice', 'basin', 'anything')['code'] == 'RULE_NOT_IN_PLAY'

    def test_building_a_crew_is_refused_when_the_rule_is_off(self):
        rules = dict(rules_module.defaults())
        rules['turn_order'] = 'lobby'
        game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
        game.start()
        game.game_phase = 'playing'
        assert game.build_crew('Alice', 'basin', 'anything')['code'] == 'RULE_NOT_IN_PLAY'
