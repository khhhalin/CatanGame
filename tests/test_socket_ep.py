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
