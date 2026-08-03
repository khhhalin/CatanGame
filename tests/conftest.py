import os
import random
import sys
import tempfile

import pytest

SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

os.environ.setdefault("CATAN_CONFIG", "testing")
# Point runtime state at a throwaway directory *before* app is imported, so a
# test run never reads or writes the real users.json. Without this, players
# from previous sessions leak in and fill the game.
os.environ["CATAN_DATA_DIR"] = tempfile.mkdtemp(prefix="catan-test-")

from game.game import Game  # noqa: E402


@pytest.fixture
def socket_app():
    """An app of its own for one test, built from the testing config.

    Going through the factory is what keeps tests from sharing one app: each
    one gets its own configuration rather than whatever the first import
    happened to build.
    """
    from app import create_app
    return create_app('testing')


@pytest.fixture(autouse=True)
def clean_user_file():
    """Start every test from an empty lobby."""
    import state
    if os.path.exists(state.DATA_FILE):
        os.remove(state.DATA_FILE)
    yield
    if os.path.exists(state.DATA_FILE):
        os.remove(state.DATA_FILE)


class ScriptedRandom(random.Random):
    """A Random whose dice come from a fixed list.

    Lets a test say "now a 7 is rolled" instead of looping until chance
    obliges, which is what makes robber and discard rules testable at all.
    Shuffles still behave normally (seeded), so board generation stays valid.
    """

    def __init__(self, rolls=None, seed=12345):
        super().__init__(seed)
        self.rolls = list(rolls or [])

    def randint(self, a, b):
        if self.rolls and (a, b) == (1, 6):
            return self.rolls.pop(0)
        return super().randint(a, b)


@pytest.fixture
def rng():
    """Seeded RNG: every test replays identically."""
    return random.Random(12345)


@pytest.fixture
def fresh_game(rng):
    """A two-player game, board generated, still in setup."""
    return Game(["Alice", "Bob"], [], rng=rng)


@pytest.fixture
def started_game(fresh_game):
    fresh_game.start()
    return fresh_game


@pytest.fixture
def playing_game(started_game):
    """A game past setup, so build costs and turn rules apply.

    Derived by driving the real engine rather than hand-setting fields: a
    hand-built state can encode a position the engine could never reach, and
    then the test proves nothing.
    """
    started_game.game_phase = "playing"
    started_game.start_turn()
    return started_game


@pytest.fixture
def give():
    """Put exact resources in a player's hand."""
    def _give(game, player_name, **resources):
        player = game.get_player(player_name)
        player.resources = dict(resources)
        return player
    return _give
