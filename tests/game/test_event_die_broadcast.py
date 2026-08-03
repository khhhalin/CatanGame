"""Bug G: the barbarian track moved on the roll but was only announced later.

The tester saw the counter update on end turn. The board snapshot did already go
out with the roll, so the fix is a dedicated `event_die` message the client can
act on without diffing a whole board.
"""

import pytest
import state
from extensions import socketio
from game import cities_knights as ck_module


@pytest.fixture
def ck_clients(socket_app):
    alice = socketio.test_client(socket_app)
    bob = socketio.test_client(socket_app)
    alice.emit('join', {'name': 'Alice', 'role': 'player'})
    bob.emit('join', {'name': 'Bob', 'role': 'player'})
    alice.emit('set_rules', {'rules': {'cities_and_knights': True}})
    alice.emit('start_game')

    game = state.session().game
    game.game_phase = 'playing'
    game.start_turn()
    alice.get_received()
    bob.get_received()
    return alice, bob


def roll_as_current(ck_clients, face):
    """Roll for whoever's turn it is with the event die forced to `face`."""
    game = state.session().game
    name = game.players[game.current_player_index].name
    game.roll_event_die = lambda: face
    client = ck_clients[0] if name == 'Alice' else ck_clients[1]
    client.emit('roll_dice', {'name': name})
    return client


def events(client, name):
    return [msg['args'][0] for msg in client.get_received() if msg['name'] == name]


class TestEventDieIsAnnouncedOnTheRoll:
    def test_a_barbarian_face_reports_the_new_position(self, ck_clients):
        client = roll_as_current(ck_clients, ck_module.EVENT_BARBARIAN)

        payload = events(client, 'event_die')[-1]
        assert payload['barbarian'] is True
        assert payload['position'] == 1
        assert payload['track_length'] == ck_module.BARBARIAN_TRACK_LENGTH

    def test_the_whole_table_hears_it_not_just_the_roller(self, ck_clients):
        roll_as_current(ck_clients, ck_module.EVENT_BARBARIAN)

        assert events(ck_clients[0], 'event_die')
        assert events(ck_clients[1], 'event_die')

    def test_a_city_gate_is_reported_too(self, ck_clients):
        client = roll_as_current(ck_clients, ck_module.TRADE)

        payload = events(client, 'event_die')[-1]
        assert payload['barbarian'] is False
        assert payload['face'] == ck_module.TRADE

    def test_who_drew_is_public_but_not_what(self, ck_clients):
        game = state.session().game
        game.ck.improvements['Alice']['trade'] = 5
        game.ck.progress_decks['trade'] = ['merchant']

        client = roll_as_current(ck_clients, ck_module.TRADE)

        payload = events(client, 'event_die')[-1]
        assert payload['drew'] == ['Alice']
        assert 'merchant' not in str(payload)
