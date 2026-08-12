"""Socket layer for the Fishermen of Catan: the fish-spend and boot-pass actions
are reachable through real handlers, gated on their rule, and the state they
change reaches the client. These drive real clients through the real handlers —
the boundary a browser actually talks to. The engine's own correctness is
`tests/game/test_fishing.py`'s job.
"""

import random

import pytest
import state
from extensions import socketio
from game import map_store, maps
from game import rules as rules_module
from game.game import Game


@pytest.fixture
def clients(socket_app):
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


TB_ACTIONS = [
    ('spend_fish', {'name': 'Alice', 'benefit': 'bank_card', 'tokens': [2, 2],
                    'resource': 'ore'}),
    ('pass_old_boot', {'name': 'Alice', 'target': 'Bob'}),
]


class TestEveryActionIsGatedOnItsRule:
    @pytest.mark.parametrize('event, payload', TB_ACTIONS,
                             ids=[event for event, _ in TB_ACTIONS])
    def test_the_base_game_refuses_it(self, clients, event, payload):
        alice, _ = clients
        alice.emit(event, payload)
        error = last_error(alice)
        assert error is not None, f"{event} produced no error in a base game"
        assert error['code'] == 'RULE_NOT_IN_PLAY', (
            f"{event} was not gated on its rule: {error}"
        )


def _fishermen_game():
    chosen = dict(rules_module.TB_FISHERMEN_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('fishermen'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0  # Alice
    game.set_dice_rolled()
    return game


@pytest.fixture
def fishermen_clients(clients):
    alice, bob = clients
    game = _fishermen_game()
    game.tb.hands['Alice'] = [2, 2]
    state.session().game = game
    alice.get_received()
    bob.get_received()
    return alice, bob


class TestTheWireReachesTheEngine:
    def test_spending_fish_for_a_bank_card_pays_out_and_broadcasts(self, fishermen_clients):
        alice, _ = fishermen_clients
        before = state.session().game.get_player('Alice').resources.get('ore', 0)

        alice.emit('spend_fish', {'name': 'Alice', 'benefit': 'bank_card',
                                  'tokens': [2, 2], 'resource': 'ore'})
        received = alice.get_received()

        assert not [m for m in received if m['name'] == 'error'], 'the spend errored'
        boards = [m['args'][0] for m in received if m['name'] == 'board_updated']
        assert boards, 'a successful spend did not broadcast the board'

        game = state.session().game
        assert game.get_player('Alice').resources['ore'] == before + 1
        assert game.tb.held_fish('Alice') == 0
        # The fish state rides along for the client to draw.
        assert boards[-1]['board']['tb']['supply_count'] >= 0

    def test_a_hand_only_shows_its_owner_their_fish(self, fishermen_clients):
        alice, bob = fishermen_clients
        # Trigger a broadcast the pair both receive.
        alice.emit('spend_fish', {'name': 'Alice', 'benefit': 'bank_card',
                                  'tokens': [2, 2], 'resource': 'ore'})
        alice.get_received()
        bob_boards = [m['args'][0] for m in bob.get_received()
                      if m['name'] == 'board_updated']
        assert bob_boards, 'Bob never saw the board'
        tb = bob_boards[-1]['board']['tb']
        # Bob sees counts, never Alice's tokens.
        assert tb['fish_hand'] is None or 'Alice' not in (tb.get('fish_hand') or {})

    def test_an_underpaid_benefit_is_refused_by_the_engine(self, fishermen_clients):
        alice, _ = fishermen_clients
        alice.emit('spend_fish', {'name': 'Alice', 'benefit': 'free_dev',
                                  'tokens': [2, 2], 'resource': None})
        error = last_error(alice)
        assert error is not None and error['code'] == 'NOT_ENOUGH_FISH', error
