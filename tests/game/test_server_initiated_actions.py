"""The server acting with no socket behind it.

Every game action is now attributed to the seat the sending connection holds.
The watchdog has no connection at all: it rolls for a player who walked away and
ends the turn they abandoned. If anything on that path starts reading `request`,
the table stalls with a "working outside of request context" nobody sees — which
is exactly the failure the watchdog exists to prevent.
"""

import time

import pytest
import state
from extensions import socketio
from handlers import turns


@pytest.fixture
def playing_clients(socket_app):
    """Two seated clients in a started game, past setup."""
    alice = socketio.test_client(socket_app)
    bob = socketio.test_client(socket_app)
    alice.emit('join', {'name': 'Alice', 'role': 'player'})
    bob.emit('join', {'name': 'Bob', 'role': 'player'})
    alice.emit('start_game')

    game = state.session().game
    game.game_phase = 'playing'
    game.start_turn()
    alice.get_received()
    bob.get_received()
    return alice, bob, game


def events(client, name):
    return [msg['args'][0] for msg in client.get_received() if msg['name'] == name]


class TestTheWatchdogNeedsNoSeat:
    def test_an_expired_dice_timer_rolls_for_the_absent_player(self, playing_clients):
        alice, bob, game = playing_clients
        game.turn_start_time = time.time() - game.dice_roll_time_limit - 1

        turns._watchdog_tick()

        assert game.has_rolled_dice, "the server rolled with no socket to attribute it to"
        assert events(alice, 'dice_rolled'), "and the table was told"
        assert events(bob, 'dice_rolled')

    def test_an_expired_round_ends_the_turn(self, playing_clients):
        alice, _bob, game = playing_clients
        before = game.players[game.current_player_index].name
        game.set_dice_rolled()
        game.dice_rolled_time = time.time() - game.round_time_limit - 1

        turns._watchdog_tick()

        assert game.players[game.current_player_index].name != before
        assert events(alice, 'turn_changed')
