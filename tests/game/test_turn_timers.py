"""One clock per phase of a turn, and the table's say over how long each is.

The tester asked for a clock each for the dice roll, the discard, the robber
and the rest of the turn. Before this there were two: a dice clock and a round
clock that started at the roll and ran straight through a discard and a robber
move, so a player who spent a minute paying a 7 lost that minute of their turn.
"""

import time

import pytest
from game.game import Game


def acting(game):
    return game.current_player_name()


def other_player(game, name):
    return next(player.name for player in game.players if player.name != name)


@pytest.fixture
def rolled_seven(playing_game):
    """A 7 has been rolled: Bob owes a discard and the robber is unmoved."""
    playing_game.set_dice_rolled()
    playing_game.get_player('Bob').resources = {'wood': 5, 'ore': 5}
    playing_game.check_discard_required()
    playing_game.must_move_robber = True
    return playing_game


class TestWhichClockIsRunning:
    def test_the_dice_clock_runs_before_the_roll(self, playing_game):
        assert playing_game.timer_phase() == 'dice'
        assert playing_game.timer_remaining() == playing_game.dice_roll_time_limit

    def test_the_turn_clock_takes_over_at_the_roll(self, playing_game):
        playing_game.set_dice_rolled()

        assert playing_game.timer_phase() == 'turn'
        assert playing_game.timer_remaining() == playing_game.round_time_limit

    def test_an_unpaid_discard_owns_the_clock(self, rolled_seven):
        assert rolled_seven.timer_phase() == 'discard'
        assert rolled_seven.timer_remaining() == rolled_seven.discard_time_limit

    def test_the_robber_clock_starts_when_the_discards_are_paid(self, rolled_seven):
        rolled_seven.discard('Bob', {'wood': 5})

        assert rolled_seven.timer_phase() == 'robber'
        assert rolled_seven.timer_remaining() == rolled_seven.robber_time_limit

    def test_a_slow_discard_does_not_eat_the_turn(self, rolled_seven):
        """The whole point of splitting them: the turn clock has not started
        while a 7 is still being paid, so paying it slowly costs the player
        their discard clock and nothing else."""
        rolled_seven.timer_phase()  # latch the discard clock, then run it out
        rolled_seven.clock_started_time = time.time() - rolled_seven.discard_time_limit
        assert rolled_seven.timer_expired()

        rolled_seven.discard('Bob', {'wood': 5})
        rolled_seven.must_move_robber = False

        assert rolled_seven.timer_phase() == 'turn'
        assert rolled_seven.timer_remaining() == rolled_seven.round_time_limit

    def test_nothing_is_timed_during_setup(self, started_game):
        assert started_game.timer_phase() is None
        assert started_game.timer_remaining() is None


class TestTheTableSetsTheDurations:
    def _game(self, rules):
        return Game(['Alice', 'Bob'], [], rules=rules)

    def test_every_clock_is_a_lobby_setting(self):
        game = self._game({
            'dice_timer_seconds': 20,
            'discard_timer_seconds': 45,
            'robber_timer_seconds': 40,
            'turn_timer_seconds': 300,
            'choice_timer_seconds': 25,
        })

        assert game.dice_roll_time_limit == 20
        assert game.discard_time_limit == 45
        assert game.robber_time_limit == 40
        assert game.round_time_limit == 300
        assert game.choice_time_limit == 25

    def test_zero_leaves_the_server_default_in_place(self):
        """The config is still the fallback, so a table that changed nothing
        plays to whatever this deployment was configured with."""
        class Config:
            DICE_ROLL_SECONDS = 9
            ROUND_SECONDS = 99

        game = Game(['Alice', 'Bob'], [], config=Config,
                    rules={'dice_timer_seconds': 0, 'turn_timer_seconds': 0})

        assert game.dice_roll_time_limit == 9
        assert game.round_time_limit == 99
