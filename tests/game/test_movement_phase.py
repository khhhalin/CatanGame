"""The movement phase — no building or trading after a ship moves (851-862).

E&P fixes the turn order production -> trade/build -> movement: once you move a
transport ship you are in the movement phase, and nothing more may be built or
traded that turn. The one documented exception is founding a settlement with a
settler ship, which is allowed during movement.

Each test names a rule a player would notice break: a build or a trade that went
through after a ship had already sailed, a settler ship that could no longer
found once movement began, a phase that never reset so the next player was
locked out, and — the real regression risk — the guard firing at a table not
playing `movement_phase` at all, or confusing a robber move with a ship move.

`movement_phase` rides on `transport_ships` (+ `harbor_settlements` for the
build site, `cargo_settlers` for the founding exception), so the fixtures turn
those on. The two ship models are mutually exclusive at `start_game`, so no test
turns Seafarers `ships` on beside them.
"""

import random

from game import rules as rules_module
from game.game import Game


def _game(**overrides):
    rules = dict(rules_module.defaults())
    rules['transport_ships'] = True
    rules['harbor_settlements'] = True
    rules['cargo_settlers'] = True
    rules['movement_phase'] = True
    rules['turn_order'] = 'lobby'
    rules.update(overrides)
    game = Game(['Alice', 'Bob'], [], {}, rules=rules, rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    return game


def _place_harbor(game, name):
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
    """Plant a harbor and build a transport ship beside it. Returns (harbor, edge)."""
    harbor = _place_harbor(game, name)
    edge = _sea_edge_at(game, harbor)
    game.get_player(name).resources = {'wood': 1, 'sheep': 1}
    assert game.build_transport_ship(name, edge)['success']
    return harbor, edge


def _move_a_ship(game, name, edge):
    """Sail the ship one step; return the edge it lands on."""
    target = next(iter(game._reachable_sea_edges(edge, 1)))
    assert game.move_transport_ship(name, edge, target)['success']
    return target


def _empty_coastal_endpoint(game):
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


def _plant_settler_ship(game, name, edge_key):
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


class TestBeforeMovement:
    def test_building_and_trading_are_open_before_a_ship_moves(self):
        """The turn opens in production/build: a ship is built, a bank trade
        settles, all while `turn_phase` is not yet 'movement'."""
        game = _game()
        _harbor, _edge = _build_ship(game, 'Alice')  # a build, and it went through
        assert game.turn_phase != 'movement'
        game.get_player('Alice').resources = {'wood': 4}
        assert game.propose_trade('Alice', {'wood': 4}, {'brick': 1})['success']


class TestAfterMovement:
    def test_moving_a_ship_enters_the_movement_phase(self):
        game = _game()
        _harbor, edge = _build_ship(game, 'Alice')
        _move_a_ship(game, 'Alice', edge)
        assert game.turn_phase == 'movement'

    def test_every_build_is_refused_once_a_ship_has_moved(self):
        """852, 861: nothing is built after movement begins. The guard is on
        each engine build method, so it fires before the target is even read."""
        game = _game()
        harbor, edge = _build_ship(game, 'Alice')
        _move_a_ship(game, 'Alice', edge)

        alice = game.get_player('Alice')
        alice.resources = {'wood': 9, 'brick': 9, 'wheat': 9, 'sheep': 9, 'ore': 9}
        some_edge = next(iter(game.edges))
        some_vertex = next(iter(game.vertices))

        assert game.build_road('Alice', some_edge)['code'] == 'MOVEMENT_STARTED'
        assert game.place_settlement('Alice', some_vertex)['code'] == 'MOVEMENT_STARTED'
        assert game.upgrade_city('Alice', some_vertex)['code'] == 'MOVEMENT_STARTED'
        assert game.build_harbor_settlement('Alice', some_vertex)['code'] == 'MOVEMENT_STARTED'
        assert game.build_transport_ship('Alice', some_edge)['code'] == 'MOVEMENT_STARTED'
        assert game.build_settler('Alice', 'basin', harbor)['code'] == 'MOVEMENT_STARTED'

    def test_trading_is_refused_once_a_ship_has_moved(self):
        game = _game()
        _harbor, edge = _build_ship(game, 'Alice')
        _move_a_ship(game, 'Alice', edge)
        game.get_player('Alice').resources = {'wood': 4}
        assert game.propose_trade('Alice', {'wood': 4}, {'brick': 1})['code'] == 'MOVEMENT_STARTED'

    def test_founding_a_settlement_with_a_settler_ship_is_the_exception(self):
        """913-916: a settler ship may still found a settlement during movement,
        the one build the movement phase allows."""
        game = _game()
        edge, vertex = _empty_coastal_endpoint(game)
        _plant_settler_ship(game, 'Alice', edge)
        game.get_player('Alice').resources = {}
        game.turn_phase = 'movement'  # a ship has already moved this turn

        result = game.found_settlement_from_ship('Alice', edge, vertex)
        assert result['success']
        assert game.vertices[vertex].building == {'type': 'settlement', 'player': 'Alice'}


class TestReset:
    def test_start_turn_reopens_building_for_the_next_player(self):
        """The next player is back in the build phase: the lock does not carry
        across the turn boundary."""
        game = _game()
        _harbor, edge = _build_ship(game, 'Alice')
        _move_a_ship(game, 'Alice', edge)
        assert game.turn_phase == 'movement'

        game.start_turn()
        assert game.turn_phase == 'production'
        # The edge the ship left is empty and still beside the harbor, so a fresh
        # build lands rather than bouncing on MOVEMENT_STARTED.
        game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}
        assert game.build_transport_ship('Alice', edge)['success']


class TestRuleOff:
    def test_a_moved_ship_never_locks_building_with_the_rule_off(self):
        """The gate is `movement_phase`, not the mere fact a ship moved: with the
        rule off the turn structure is exactly the base game's, so a table
        playing transport ships without the phase rule keeps building freely."""
        game = _game(movement_phase=False)
        _harbor, edge = _build_ship(game, 'Alice')
        landing = _move_a_ship(game, 'Alice', edge)
        assert landing  # the ship did move
        # No phase lock: the vacated edge, still beside the harbor, accepts a
        # new ship even though a ship has moved this turn.
        game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}
        assert game.build_transport_ship('Alice', edge)['success']

    def test_moving_the_robber_is_not_moving_a_ship(self):
        """A 7 that sends the robber across the board must not be mistaken for
        the movement phase: only a transport ship's move locks the turn."""
        game = _game()
        game.must_move_robber = True
        land = next(
            key for key, hex_obj in game.hexes.items()
            if hex_obj.type not in ('ocean', 'desert') and key != game.robber_hex
        )
        assert game.move_robber('Alice', land)['success']
        assert game.turn_phase == 'production'
