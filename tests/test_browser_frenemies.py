"""Catan: Frenemies — the favour-token panel, earning, and a guild redemption.

The whole favour economy is read off the board payload: a token count that never
reached the client, a rule gate that hid the panel, or a redeem button wired to
nothing would leave the economy invisible while the server scored it, and the
unit suite would still pass because the server state is perfectly correct.

This test pins the real client surface: the panel appears with the bag and the
viewer's tokens, gifting a resource through the UI earns a favour the readout
shows, and redeeming a Merchant favour moves a resource into the hand the server
tracks. The board is confirmed painted with pixels first, so none of the DOM
assertions are passing over a blank canvas.

Run: pytest tests/test_browser_frenemies.py -m slow -v
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
from game import persistence
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow

VIEWPORT = {"width": 1600, "height": 1000}


def _frenemies_game():
    """A base-board Frenemies game past setup, Alice to move.

    Alice holds a wood to gift and a usable Merchant token to redeem; Bob is on
    no visible points, so he is a legal gift recipient.
    """
    rules = dict(rules_module.preset_rules("frenemies"))
    rules["turn_order"] = "lobby"
    game = Game(["Alice", "Bob"], [], rng=random.Random(7), rules=rules)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.set_dice_rolled()
    game.get_player("Alice").resources = {"wood": 1}
    game.favour_usable["Alice"] = {"merchant": 1}
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


def test_the_frenemies_panel_earns_a_favour_and_redeems_at_the_guild(browser, tmp_path):
    game = _frenemies_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The panel is up and shows the bag and Alice's Merchant token.
        assert alice.page.query_selector("#right-frenemies:not(.hidden)") is not None, \
            "the Frenemies panel did not appear"
        status = alice.page.inner_text("#frenemies-status")
        assert "Bag" in status and "Merchant" in status, status
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().frenemies.counts.Alice") == 1

        # Earn: gift a wood to Bob through the UI and the readout gains a favour.
        bag_before = alice.page.evaluate(
            "() => window.__catanDebug.getBoard().frenemies.bag_remaining")
        alice.page.click("#frenemies-gift")
        alice.page.click(".frenemies-gift-to[data-recipient='Bob']")
        alice.page.click(".frenemies-gift-res[data-resource='wood']")
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().frenemies.counts.Alice === 2",
            timeout=10000,
        )
        bag_after = alice.page.evaluate(
            "() => window.__catanDebug.getBoard().frenemies.bag_remaining")
        assert bag_after == bag_before - 1, (bag_before, bag_after)

        # Redeem the Merchant favour for an ore: it arrives in Alice's hand and
        # the token is spent.
        redeem_btn = "#frenemies-redeem-merchant:not([disabled])"
        assert alice.page.query_selector(redeem_btn) is not None, \
            "the Merchant redeem button was not enabled"
        alice.page.click("#frenemies-redeem-merchant")
        alice.page.click("#frenemies-merchant-ore")
        alice.page.wait_for_function(
            "() => (window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').resources.ore || 0) === 1",
            timeout=10000,
        )
        favours = alice.page.evaluate(
            "() => window.__catanDebug.getBoard().frenemies.your_favours.usable.merchant || 0")
        assert favours == 0, "the Merchant token was not spent"

        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
