"""The Fishermen of Catan panel, in a real browser.

The new client code is fish.js and its strip: the panel shows the player's own
fish tokens (private) and the spend ladder, and a benefit button fires the
matching handler. The regression it guards against is the panel never appearing,
the hand rendering blank, or a spend button emitting nothing — invisible to the
unit suite, which only sees the handler once it is called. The player-visible
proof is a fish token in the hand and a free road appearing after a spend.

A base game must show no fish panel at all.

Run: pytest tests/test_browser_fishermen.py -m slow -q
"""

import os
import random

import pytest
from browser_harness import (
    Player,
    browser_session,
    next_frame,
    start_server,
    stop_server,
    wait_for_board_painted,
)
from game import map_store, maps, persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}


def _fishermen_game():
    """A started Fishermen game, Alice mid-turn holding a 2- and a 3-fish token
    (enough for the 5-fish free road) and no free roads yet, so the spend is an
    isolated change."""
    chosen = dict(rules_module.TB_FISHERMEN_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('fishermen'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    game.tb.hands['Alice'] = [2, 3]
    game.free_roads_remaining = 0
    return game


def _base_game():
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def _join(browser, url):
    alice = Player(browser, url, "Alice", viewport=VIEWPORT)
    alice.page.check("#role-player")
    alice.page.fill("#username", "Alice")
    alice.page.click("#join-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    wait_for_board_painted(alice)
    next_frame(alice.page)
    return alice


def test_the_fish_panel_shows_a_hand_and_spends_for_a_free_road(browser, tmp_path):
    persistence.save(_fishermen_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The Fishermen panel is up and shows Alice's two fish tokens.
        assert alice.page.query_selector("#right-fish:not(.hidden)") is not None, \
            "the Fishermen panel did not appear"
        tokens = alice.page.query_selector_all("#fish-hand .fish-token")
        assert len(tokens) == 2, "Alice's two fish tokens did not render"

        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().free_roads_remaining"
        ) == 0

        # Spend the 5-fish free road (no pick needed): the button fires at once.
        alice.page.click("#fish-free-road")

        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().free_roads_remaining === 1",
            timeout=5000,
        )
        # The spent fish leave the hand.
        alice.page.wait_for_function(
            "() => (window.__catanDebug.getBoard().tb.fish_hand || []).length === 0",
            timeout=5000,
        )
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_fish_panel(browser, tmp_path):
    persistence.save(_base_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-fish.hidden") is not None, \
            "the Fishermen panel showed in a base game"
    finally:
        stop_server(proc)
