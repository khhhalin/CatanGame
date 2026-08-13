"""Socket layer for Explorers & Pirates: every E&P action is reachable through a
real handler, gated on its rule, and the mission state it changes reaches the
client. These drive real clients through the real handlers — the boundary a
browser actually talks to. The engine's own correctness is the mission and
transport unit suites' job.
"""

import random

import pytest
import state
from extensions import socketio
from game import board as board_module
from game import maps
from game import rules as rules_module
from game.game import Game


@pytest.fixture
def clients(socket_app):
    """Two connected clients in a started two-player base game."""
    alice = socketio.test_client(socket_app)
    bob = socketio.test_client(socket_app)
    alice.emit('join', {'name': 'Alice', 'role': 'player'})
    bob.emit('join', {'name': 'Bob', 'role': 'player'})
    alice.emit('start_game')
    alice.get_received()
    bob.get_received()
    return alice, bob


def events(client, name):
    return [msg['args'][0] for msg in client.get_received() if msg['name'] == name]


def last_error(client):
    errors = events(client, 'error')
    return errors[-1] if errors else None


# Every E&P action, with a minimal well-formed payload. The base game the fixture
# starts has none of these rules on, so each must be refused before it acts.
EP_ACTIONS = [
    ('build_transport_ship', {'name': 'Alice', 'edge': '0,0,0'}),
    ('move_transport_ship', {'name': 'Alice', 'from_edge': '0,0,0', 'to_edge': '3,0,-3'}),
    ('load_transport_ship', {'name': 'Alice', 'edge': '0,0,0', 'basin_index': 0}),
    ('unload_transport_ship', {'name': 'Alice', 'edge': '0,0,0', 'cargo_index': 0}),
    ('build_crew', {'name': 'Alice', 'into': 'hold', 'key': '0,0,0'}),
    ('build_settler', {'name': 'Alice', 'into': 'basin', 'key': '0,0,0'}),
    ('found_settlement_from_ship',
     {'name': 'Alice', 'edge': '0,0,0', 'vertex': '0,0,0'}),
    ('place_pirate_ship', {'name': 'Alice', 'hex': '0,0,0'}),
    ('land_crews_on_lair', {'name': 'Alice', 'ship_edge': '0,0,0', 'lair_hex': '0,0,0'}),
    ('pickup_crews_from_lair', {'name': 'Alice', 'ship_edge': '0,0,0', 'lair_hex': '0,0,0'}),
    ('roll_fish_haul', {'name': 'Alice'}),
    ('catch_fish', {'name': 'Alice', 'ship_edge': '0,0,0', 'shoal_hex': '0,0,0'}),
    ('deliver_fish', {'name': 'Alice', 'ship_edge': '0,0,0', 'council_hex': '0,0,0'}),
    ('befriend_spice_village', {'name': 'Alice', 'ship_edge': '0,0,0', 'spice_hex': '0,0,0'}),
    ('deliver_spices', {'name': 'Alice', 'ship_edge': '0,0,0', 'council_hex': '0,0,0'}),
    ('sell_resources_for_gold', {'name': 'Alice', 'resource': 'wood'}),
    ('buy_resource_with_gold', {'name': 'Alice', 'resource': 'wood'}),
]


class TestEveryActionIsGatedOnItsRule:
    """The base game has none of the E&P rules on, so every E&P action must be
    refused with RULE_NOT_IN_PLAY — proof each handler is registered and checks
    its rule before touching the game. A handler left out of app.py, or one that
    forgot its gate, fails here."""

    @pytest.mark.parametrize('event, payload', EP_ACTIONS,
                             ids=[event for event, _ in EP_ACTIONS])
    def test_the_base_game_refuses_it(self, clients, event, payload):
        alice, _ = clients
        alice.emit(event, payload)
        error = last_error(alice)
        assert error is not None, f"{event} produced no error in a base game"
        assert error['code'] == 'RULE_NOT_IN_PLAY', (
            f"{event} was not gated on its rule: {error}"
        )


def _ep_game():
    """A started, mid-turn Explorers & Pirates game: fish mission on, a hidden
    fish shoal on the mainland, Alice to act with the dice already rolled."""
    mainland = maps.sort_hex_keys('{},{},{}'.format(*c) for c in board_module._hexagon(1))
    sea = len(maps.frame_hex_keys(3)) - len(mainland)
    document = {
        'map_version': 2, 'id': 'ep-socket', 'name': 'EP Socket',
        'frame': {'radius': 3},
        'regions': [
            {'id': 'mainland', 'kind': 'main', 'hexes': mainland,
             'pool': {'mode': 'hidden',
                      'terrain': {'fish': 1, 'wood': 2, 'wheat': 2, 'sheep': 1, 'desert': 1},
                      'numbers': [3, 4, 5, 6, 9]}},
            {'id': 'ocean', 'kind': 'sea', 'hexes': 'remaining',
             'pool': {'mode': 'shuffled', 'terrain': {'sea': sea}, 'numbers': []}},
        ],
        'harbours': {'mode': 'bag', 'types': {}},
    }
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0  # Alice
    game.set_dice_rolled()
    return game


@pytest.fixture
def ep_clients(clients):
    """The connected clients, but the session's game swapped for an E&P one so
    the actions actually reach live mission code."""
    alice, bob = clients
    state.session().game = _ep_game()
    alice.get_received()
    bob.get_received()
    return alice, bob


class TestTheWireReachesTheEngine:
    def test_a_fish_roll_is_accepted_and_carries_the_ep_state(self, ep_clients):
        alice, _ = ep_clients
        alice.emit('roll_fish_haul', {'name': 'Alice'})
        received = alice.get_received()

        assert not [m for m in received if m['name'] == 'error'], 'a fish roll errored'
        boards = [m['args'][0] for m in received if m['name'] == 'board_updated']
        assert boards, 'a successful fish roll did not broadcast the board'

        # The mission destinations now ride along in the board's ep state, which
        # is what the client will draw them from.
        ep = boards[-1]['board']['ep']
        for key in ('fish_shoals', 'lairs', 'spice_hexes'):
            assert key in ep, f'ep state is missing {key} on the wire'

    def test_delivering_to_a_hex_with_no_dock_is_refused_by_the_engine(self, ep_clients):
        alice, _ = ep_clients
        # The centre hex exists but carries no Council dock, so the engine — not
        # the rule gate — refuses this. INVALID_TARGET (not RULE_NOT_IN_PLAY)
        # proves the payload passed the gate and reached the mission code.
        alice.emit('deliver_fish',
                   {'name': 'Alice', 'ship_edge': '0,0,0', 'council_hex': '0,0,0'})
        error = last_error(alice)
        assert error is not None and error['code'] == 'INVALID_TARGET', error


# --- The cargo builds (crew, settler, founding) through the wire --------------
#
# The three handlers the crew→ship→mission chain hangs on. Before these landed
# their engine methods had no socket wrapper at all, so a player could never
# build a crew, a settler, or found a settlement from a ship. Each test drives a
# real success — state actually changed, the cost was charged — not just a
# rejection, and one checks the seat gate holds.

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


def _cargo_game():
    """A started E&P game with the cargo rules on: Alice mid-turn with a harbour
    settlement and a transport ship beside it, the dice already rolled."""
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'cargo_settlers', 'crews'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    harbor = _place_harbor(game, 'Alice')
    edge = _sea_edge_at(game, harbor)
    game.get_player('Alice').resources = {'wood': 1, 'sheep': 1}
    assert game.build_transport_ship('Alice', edge)['success']
    return game, harbor, edge


@pytest.fixture
def cargo_clients(clients):
    """The connected clients over a started cargo game. Returns the clients plus
    the game and the harbour/ship keys the actions target."""
    alice, bob = clients
    game, harbor, edge = _cargo_game()
    state.session().game = game
    alice.get_received()
    bob.get_received()
    return alice, bob, game, harbor, edge


def _outcome(client):
    """Both halves of a client's inbox in one drain: the last error (or None)
    and whether a board was broadcast. `get_received` empties the queue, so the
    two questions must be asked of a single read."""
    received = client.get_received()
    errors = [m['args'][0] for m in received if m['name'] == 'error']
    boards = [m['args'][0] for m in received if m['name'] == 'board_updated']
    return (errors[-1] if errors else None), bool(boards)


class TestCargoBuildsReachTheEngine:
    def test_a_crew_is_built_into_the_ship_hold(self, cargo_clients):
        alice, _bob, game, _harbor, edge = cargo_clients
        game.get_player('Alice').resources = {'ore': 1, 'sheep': 1}
        alice.emit('build_crew', {'name': 'Alice', 'into': 'hold', 'key': edge})

        error, broadcast = _outcome(alice)
        assert error is None, error
        assert broadcast, 'building a crew did not broadcast the board'
        assert game.edges[edge].ship['cargo'] == [{'type': 'crew', 'size': 'small'}]
        assert game.get_player('Alice').crews == 1
        # The ore and wool were charged.
        assert game.get_player('Alice').resources == {'ore': 0, 'sheep': 0}

    def test_a_settler_is_built_into_the_harbor_basin(self, cargo_clients):
        alice, _bob, game, harbor, _edge = cargo_clients
        game.get_player('Alice').resources = {'wood': 1, 'brick': 1, 'wheat': 1, 'sheep': 1}
        alice.emit('build_settler', {'name': 'Alice', 'into': 'basin', 'key': harbor})

        error, broadcast = _outcome(alice)
        assert error is None, error
        assert broadcast, 'building a settler did not broadcast the board'
        assert game.vertices[harbor].building['basin'] == [
            {'type': 'settler', 'size': 'large'}
        ]
        assert game.get_player('Alice').settlers == 1

    def test_a_settler_ship_founds_a_settlement(self, cargo_clients):
        alice, _bob, game, _harbor, _edge = cargo_clients
        # Plant a settler ship at an empty coastal corner and found there.
        found_edge = found_vertex = None
        for edge_key in sorted(game.edges):
            if not game.is_sea_edge(edge_key) or game.edges[edge_key].ship is not None:
                continue
            for vertex_key in game.edges[edge_key].neighbors['vertices']:
                vertex = game.vertices[vertex_key]
                if vertex.building is not None or not vertex.neighbors['hexes']:
                    continue
                if all(game.vertices[n].building is None
                       for n in vertex.neighbors.get('vertices', [])):
                    found_edge, found_vertex = edge_key, vertex_key
                    break
            if found_edge:
                break
        assert found_edge is not None, 'no empty coastal endpoint on this board'
        game.transport_ship_counter += 1
        game.edges[found_edge].ship = {
            'player': 'Alice', 'built_turn': 0, 'kind': 'transport',
            'cargo': [{'type': 'settler', 'size': 'large'}],
            'id': game.transport_ship_counter,
        }
        game.get_player('Alice').ships.append(found_edge)
        game.get_player('Alice').settlers += 1

        alice.emit('found_settlement_from_ship',
                   {'name': 'Alice', 'edge': found_edge, 'vertex': found_vertex})

        error, broadcast = _outcome(alice)
        assert error is None, error
        assert broadcast, 'founding a settlement did not broadcast the board'
        assert game.vertices[found_vertex].building == {
            'type': 'settlement', 'player': 'Alice'
        }
        # The settler ship and its settler are both returned to supply.
        assert game.edges[found_edge].ship is None

    def test_load_and_unload_shuttle_a_piece_between_basin_and_hold(self, cargo_clients):
        # The load/unload handlers were only ever driven to rejection before; this
        # drives a real round trip — a crew from the basin into the hold and back.
        alice, _bob, game, harbor, edge = cargo_clients
        game.vertices[harbor].building['basin'] = [{'type': 'crew', 'size': 'small'}]

        alice.emit('load_transport_ship',
                   {'name': 'Alice', 'edge': edge, 'basin_index': 0})
        error, broadcast = _outcome(alice)
        assert error is None, error
        assert broadcast, 'loading did not broadcast the board'
        assert game.edges[edge].ship['cargo'] == [{'type': 'crew', 'size': 'small'}]
        assert game.vertices[harbor].building['basin'] == []

        alice.emit('unload_transport_ship',
                   {'name': 'Alice', 'edge': edge, 'cargo_index': 0})
        error, broadcast = _outcome(alice)
        assert error is None, error
        assert broadcast, 'unloading did not broadcast the board'
        assert game.edges[edge].ship['cargo'] == []
        assert game.vertices[harbor].building['basin'] == [{'type': 'crew', 'size': 'small'}]

    def test_only_the_seated_player_may_build_a_crew(self, cargo_clients):
        alice, bob, game, _harbor, edge = cargo_clients
        game.get_player('Alice').resources = {'ore': 1, 'sheep': 1}
        # Bob is not the current player, so his build is refused and nothing is
        # built or charged.
        bob.emit('build_crew', {'name': 'Bob', 'into': 'hold', 'key': edge})
        error = last_error(bob)
        assert error is not None and error['code'] == 'NOT_YOUR_TURN', error
        assert game.edges[edge].ship['cargo'] == []
