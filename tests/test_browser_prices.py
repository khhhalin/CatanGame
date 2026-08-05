"""What a build costs is the server's answer, read off the buttons.

`panels.js` used to carry its own transcription of `server/data/costs.json`, so
the price on a button and the price the bank charged were two literals free to
disagree — the same failure as the award panel's "needs 5" on a table playing
to 2. The prices now ride in the board payload; if they ever stop, the console
has nothing to gate on and offers a card to a player who cannot pay for it,
which no assertion on server state can see.

Run: pytest tests/test_browser_prices.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import Player, browser_session, start_server, stop_server
from game import persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

TABLE = ["Alice", "Bob"]


@contextmanager
def table(browser, data_dir, hand):
    game = Game(list(TABLE), [], rng=random.Random(7), rules=rules_module.defaults())
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    game.get_player("Alice").resources = dict(hand)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    try:
        player = Player(browser, url, TABLE[0], viewport=VIEWPORT)
        # A join into a running game is answered with the game screen rather
        # than the lobby, so this is not Player.join().
        player.page.check("#role-player")
        player.page.fill("#username", TABLE[0])
        player.page.click("#join-btn")
        player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        yield player
    finally:
        stop_server(proc)


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


@pytest.fixture
def broke_table(browser, tmp_path):
    with table(browser, tmp_path, {}) as player:
        yield player


@pytest.fixture
def paying_table(browser, tmp_path):
    with table(browser, tmp_path, {"wheat": 1, "sheep": 1, "ore": 1}) as player:
        yield player


def button_title(player, selector):
    return player.page.get_attribute(selector, "title")


class TestThePriceOnTheButtonIsTheServersPrice:
    def test_the_card_button_names_the_rulebook_price(self, paying_table):
        """Grain, wool and ore — as the payload priced them, not as the client
        once remembered them. The cost is a button title, and a tooltip is plain
        text that cannot carry the tile icons, so the resources are named in
        words."""
        title = button_title(paying_table, "#buy-dev-card-btn")
        assert title == "Costs 1 wheat 1 sheep 1 ore", title

    def test_a_player_who_can_pay_is_offered_the_card(self, paying_table):
        assert paying_table.page.is_enabled("#buy-dev-card-btn")


class TestAnEmptyHandIsRefusedBeforeTheRoundTrip:
    def test_the_build_buttons_are_greyed_out_with_the_shortfall(self, broke_table):
        """Without prices in the payload nothing is short of anything, and the
        console offers builds the bank will refuse."""
        page = broke_table.page
        assert page.is_disabled("#buy-dev-card-btn")
        assert page.is_disabled("#place-settlement-btn")
        assert page.is_disabled("#place-road-btn")
        assert "you have 0" in button_title(broke_table, "#place-road-btn")

    def test_no_console_errors(self, broke_table):
        assert broke_table.noisy_errors() == [], broke_table.noisy_errors()
