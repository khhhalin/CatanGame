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


def run_out_the_clock(game):
    """Back-date the running clock so this pass of the watchdog expires it."""
    game.timer_phase()  # latch the phase the game is in, then run it out
    game.clock_started_time = time.time() - game.timer_limit_for(game.clock_phase) - 1


class TestTheWatchdogNeedsNoSeat:
    def test_an_expired_dice_timer_rolls_for_the_absent_player(self, playing_clients):
        alice, bob, game = playing_clients
        run_out_the_clock(game)

        turns._watchdog_tick()

        assert game.has_rolled_dice, "the server rolled with no socket to attribute it to"
        assert events(alice, 'dice_rolled'), "and the table was told"
        assert events(bob, 'dice_rolled')

    def test_an_expired_round_ends_the_turn(self, playing_clients):
        alice, _bob, game = playing_clients
        before = game.players[game.current_player_index].name
        game.set_dice_rolled()
        run_out_the_clock(game)

        turns._watchdog_tick()

        assert game.players[game.current_player_index].name != before
        assert events(alice, 'turn_changed')


class TestEachClockExpiresItsOwnPhase:
    """The watchdog once `continue`d on a pending robber, so a turn could never
    end and the flag leaked into the next player's turn. Each phase now has a
    clock of its own and one pass expires exactly the one that is running."""

    @pytest.fixture
    def seven_rolled(self, playing_clients):
        alice, bob, game = playing_clients
        game.set_dice_rolled()
        game.get_player('Bob').resources = {'wood': 5, 'ore': 5}
        game.check_discard_required()
        game.must_move_robber = True
        return alice, bob, game

    def test_the_discard_clock_discards_and_leaves_the_robber_alone(self, seven_rolled):
        alice, _bob, game = seven_rolled
        run_out_the_clock(game)

        turns._watchdog_tick()

        assert game.players_needing_discard == {}
        assert game.get_player('Bob').total_cards() == 5
        assert game.must_move_robber, "the robber has a clock of its own to run"
        assert events(alice, 'discard_completed')

    def test_the_robber_clock_settles_the_robber_and_not_the_turn(self, seven_rolled):
        _alice, _bob, game = seven_rolled
        before = game.players[game.current_player_index].name
        game.players_needing_discard = {}
        run_out_the_clock(game)

        turns._watchdog_tick()

        assert not game.must_move_robber
        assert not game.must_choose_victim
        assert game.players[game.current_player_index].name == before, \
            "the robber's clock is not the turn's"

    def test_the_turn_clock_only_runs_once_nothing_is_pending(self, seven_rolled):
        """The whole sequence, one pass each: discard, robber, then the turn."""
        _alice, _bob, game = seven_rolled
        before = game.players[game.current_player_index].name

        for _ in range(3):
            run_out_the_clock(game)
            turns._watchdog_tick()

        assert game.players[game.current_player_index].name != before
        assert not game.must_move_robber, "and nothing leaked into the next turn"
        assert game.players_needing_discard == {}
