"""CATAN - The Helpers panel and the activate-then-flip lifecycle, in a browser.

The new client code is helper_tiles.js and its strip in index.html. The
regression it guards against is the panel never appearing, the Activate gesture
emitting nothing, or the exchange-or-flip step never surfacing - all invisible
to the unit suite, which only sees the engine methods once they are called. The
player-visible proof: the panel names the held tile, clicking Activate lands a
real resource in the hand and opens the exchange-or-flip choice, and choosing
Flip turns the tile to its moon side in the panel.

A base game must show no Helpers panel at all.

Run: pytest tests/test_browser_helper_tiles.py -m slow -q
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
from game import persistence, tiles
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}


def _ore_hex(game):
    for key, hex_obj in game.hexes.items():
        if tiles.produces(hex_obj.type) == "ore":
            return key
    raise AssertionError("no ore hex on the dealt board")


def _helpers_game():
    """A started Helpers game: Alice mid-turn holding Kaja, robber on an ore hex."""
    chosen = dict(rules_module.preset_rules("helpers_of_catan"))
    chosen["turn_order"] = "lobby"  # keep Alice in seat 0 so it is her turn
    game = Game(["Alice", "Bob"], [], rng=random.Random(5), rules=chosen)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.start_turn()
    game.helper_held["Alice"] = {"tile": "kaja", "side": "sun", "received_turn": None}
    game.robber_hex = _ore_hex(game)
    return game


def _base_game():
    game = Game(["Alice", "Bob"], [], rng=random.Random(5))
    game.start()
    game.game_phase = "playing"
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


def _alice_ore(page):
    return page.evaluate(
        """() => {
            const board = window.__catanDebug.getBoard();
            const me = (board.players || []).find(p => p.name === 'Alice');
            return (me && me.resources && me.resources.ore) || 0;
        }"""
    )


def test_the_panel_names_the_held_tile(browser, tmp_path):
    game = _helpers_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-helpers:not(.hidden)") is not None, \
            "the Helpers panel did not appear"
        held = alice.page.inner_text("#helper-held")
        assert "Kaja" in held
        assert "Take Robber" in held
        assert "Sun" in held
    finally:
        stop_server(proc)


def test_activating_kaja_lands_a_resource_and_opens_the_choice(browser, tmp_path):
    game = _helpers_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert _alice_ore(alice.page) == 0

        alice.page.click(".helper-activate")
        # The robber sits on ore, so the ore count rises by one for the player.
        alice.page.wait_for_function(
            """() => {
                const board = window.__catanDebug.getBoard();
                const me = (board.players || []).find(p => p.name === 'Alice');
                return me && me.resources && me.resources.ore === 1;
            }""",
            timeout=8000,
        )
        assert _alice_ore(alice.page) == 1

        # The mandatory exchange-or-flip choice is now on screen, offering both.
        alice.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)
        options = alice.page.eval_on_selector_all(
            "#choice-options [data-choice-option]",
            "els => els.map(e => e.dataset.choiceOption)",
        )
        assert "exchange" in options
        assert "flip" in options
    finally:
        stop_server(proc)


def test_flipping_turns_the_tile_to_its_moon_side(browser, tmp_path):
    game = _helpers_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        alice.page.click(".helper-activate")
        alice.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)
        alice.page.click('#choice-options [data-choice-option="flip"]')

        alice.page.wait_for_function(
            """() => document.querySelector('#helper-held')
                     ?.innerText.includes('Moon')""",
            timeout=8000,
        )
        assert "Moon" in alice.page.inner_text("#helper-held")
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_helpers_panel(browser, tmp_path):
    game = _base_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-helpers:not(.hidden)") is None, \
            "the Helpers panel showed on a base game"
    finally:
        stop_server(proc)
