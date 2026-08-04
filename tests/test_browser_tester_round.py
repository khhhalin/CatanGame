"""What a human tester found by playing, driven back through a real browser.

Four complaints, each one a thing a player could see and could not do:

  - a hand of cloth, coin and paper could not be discarded on a 7. The engine
    has taken commodities in a discard for as long as they have counted toward
    the hand limit; the dialog had five inputs, so a player over the limit on
    commodities alone could not comply at all and the table stopped;
  - Buy Card was offered on a table playing progress cards and then refused by
    the server, which is the "click, then be told" pattern every other action
    in this client has already stopped doing;
  - every player's state should be readable at once. The scoreboard row was a
    run of abbreviations and left out the pieces entirely;
  - there is now a sound on every placement, so there has to be a way to turn
    it off, and it has to survive a reload.

The hands here are arranged with the real engine and written to the save file
the server restores on boot, the way `test_browser_knights.py` does: a discard
of commodities cannot be reached by rolling, and a browser test that waits for
the right 7 is not a gate.

Run: pytest tests/test_browser_tester_round.py -m slow -v
"""

import os
import random
from contextlib import contextmanager

import pytest
from browser_harness import (
    Player,
    build_road,
    build_settlement,
    edges_next_to,
    launch_browser,
    legal_setup_vertices,
    start_server,
    stop_server,
)
from game import persistence
from game import rules as rules_module
from game.game import Game
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1920, "height": 1080}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(REPO, "test-artifacts", "ui", "tester-round")

TABLE = ["Alice", "Bob"]

GAME_SEED = 20260804

EMPTY_HAND = {"wood": 0, "brick": 0, "sheep": 0, "wheat": 0, "ore": 0}

# Every expansion at once, which is the worst case the rail has to survive:
# the most folds, the most awards and four scoreboard rows. Built by merging
# the two presets rather than by copying a rule list into here — a list copied
# from the catalogue passes even when the catalogue has moved on.
EVERY_EXPANSION = {
    **rules_module.preset_rules("cities_and_knights"),
    **{
        rule: value
        for rule, value in rules_module.preset_rules("seafarers").items()
        # The seafaring preset turns the C&K rules back off; only what it adds
        # is wanted here.
        if value is not False
    },
}

SET_RULES = """
async rules => {
    const socket = (await import('/static/js/socket.js')).socket;
    socket.emit('set_rules', { rules });
}
"""


def shot(player, label):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, f"{label}.png")
    player.page.screenshot(path=path, full_page=False)
    return path


# --- Arranging a hand ------------------------------------------------------


def build_game(build):
    """A started Cities & Knights game, mid-turn, with `build` applied."""
    game = Game(
        list(TABLE), [], rng=random.Random(7),
        rules=rules_module.preset_rules("cities_and_knights"),
    )
    game.game_state = "started"
    game.game_phase = "playing"
    game.start_turn()
    game.set_dice_rolled()
    return game, build(game)


@contextmanager
def table(browser, data_dir, build):
    """A running server restored from `build`, with both players connected."""
    game, marks = build_game(build)
    persistence.save(game, os.path.join(str(data_dir), "game.json"))

    proc, url = start_server(data_dir)
    tabs = {}
    try:
        for name in TABLE:
            player = Player(browser, url, name, viewport=VIEWPORT)
            # Not Player.join(): that waits for the lobby, and a join into a
            # running game is answered with the game screen instead.
            player.page.check("#role-player")
            player.page.fill("#username", name)
            player.page.click("#join-btn")
            player.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
            tabs[name] = player
        yield tabs[game.current_player_name()], marks
    finally:
        stop_server(proc)


def a_hand_of_commodities_owing_a_discard(game):
    """Six commodity cards, no resources at all, and three owed to the bank.

    The exact shape of the tester's report: on a 7 the hand limit counts
    commodities, so this hand is over the limit and every card that could pay
    the debt is a commodity.
    """
    actor = game.current_player_name()
    player = game.get_player(actor)
    player.resources.update(EMPTY_HAND)
    player.commodities.update({"cloth": 2, "coin": 2, "paper": 2})
    game.players_needing_discard = {actor: 3}
    return {"actor": actor}


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        engine = launch_browser(playwright)
        yield engine
        engine.close()


@pytest.fixture
def owes_a_commodity_discard(browser, tmp_path):
    with table(browser, tmp_path, a_hand_of_commodities_owing_a_discard) as live:
        yield live


# --- 1. Discarding commodities --------------------------------------------


class TestACommodityHandCanPayADiscard:
    """The tester's report: "a player over the limit on cloth, coin or paper
    cannot comply at all"."""

    def test_the_dialog_opens_with_an_input_for_every_card_the_limit_counts(
        self, owes_a_commodity_discard
    ):
        player, _ = owes_a_commodity_discard
        player.page.wait_for_selector("#discard-modal.show", timeout=8000)
        for card in ("wood", "brick", "sheep", "wheat", "ore",
                     "cloth", "coin", "paper"):
            assert player.page.is_visible(f"#discard-{card}"), (
                f"the discard dialog has no input for {card}"
            )
        shot(player, "discard-commodities-light")

    def test_a_discard_of_commodities_is_accepted(self, owes_a_commodity_discard):
        """Before the fix there was nothing to type into: the hand was six
        commodities, the dialog offered five resources, and no entry summed to
        the three cards owed."""
        player, marks = owes_a_commodity_discard
        player.page.wait_for_selector("#discard-modal.show", timeout=8000)

        player.page.fill("#discard-cloth", "2")
        player.page.fill("#discard-paper", "1")
        player.page.click("#submit-discard-btn")

        player.page.wait_for_function(
            "() => !document.getElementById('discard-modal').classList.contains('show')",
            timeout=8000,
        )
        player.page.wait_for_function(
            "() => window.__catanDebug.getBoard()"
            "        .players.find(p => p.is_you).commodity_count === 3",
            timeout=8000,
        )
        held = player.me()["commodities"]
        assert held == {"cloth": 0, "coin": 2, "paper": 1}, held

    def test_the_total_counts_commodities_too(self, owes_a_commodity_discard):
        """A discard that is short is refused by the client with the count it
        wants, and nothing is sent."""
        player, _ = owes_a_commodity_discard
        player.page.wait_for_selector("#discard-modal.show", timeout=8000)

        player.page.fill("#discard-cloth", "1")
        player.page.click("#submit-discard-btn")
        player.page.wait_for_timeout(400)

        assert player.page.is_visible("#discard-modal.show"), (
            "a short discard closed the dialog"
        )
        assert any("exactly 3" in text for text in player.notices()), player.notices()

    def test_no_console_errors(self, owes_a_commodity_discard):
        player, _ = owes_a_commodity_discard
        assert player.noisy_errors() == [], player.noisy_errors()
