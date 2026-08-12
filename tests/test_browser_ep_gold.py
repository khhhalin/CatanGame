"""The Explorers & Pirates gold trade, through the strip, in a real browser.

The new client code is the sell/buy pair and their resource pick: a button
reveals five resource tiles, and the tile tapped fires the matching handler with
that resource. The regression it guards against is the pick emitting nothing or
the wrong resource — invisible to the unit suite, which only sees the handler
once it is called. The player-visible proof is the gold count appearing in the
panel when three wood are sold for one gold.

Run: pytest tests/test_browser_ep_gold.py -m slow -q
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


def _started_gold_game():
    """A started Pirate Cove game with gold in play, Alice mid-turn. The caller
    sets her hand and purse; everything else is the shared gold-table set-up."""
    document = map_store.read_map('pirate-cove')
    rules = dict(rules_module.defaults())
    for rule in ('transport_ships', 'harbor_settlements', 'ships_explore', 'gold',
                 'missions', 'mission_fish'):
        rules[rule] = True
    rules['turn_order'] = 'lobby'
    rules['board_layout'] = 'custom'
    rules['board_map'] = document['id']
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=rules,
                map_definition=maps.parse_map(document))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


def _gold_game():
    """Alice holds the three wood a sell costs and no gold yet, so the sell is an
    isolated change."""
    game = _started_gold_game()
    alice = game.get_player('Alice')
    alice.resources = {'wood': 3}
    alice.gold = 0
    return game


def _buy_gold_game():
    """Alice holds four gold and an empty hand, so a 2-gold buy is an isolated
    change: her purse drops by two and the bought card is the only one in hand."""
    game = _started_gold_game()
    alice = game.get_player('Alice')
    alice.resources = {'wood': 0, 'brick': 0, 'sheep': 0, 'wheat': 0, 'ore': 0}
    alice.gold = 4
    return game


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def test_selling_three_wood_through_the_strip_yields_a_gold(browser, tmp_path):
    persistence.save(_gold_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = Player(browser, url, "Alice", viewport=VIEWPORT)
        alice.page.check("#role-player")
        alice.page.fill("#username", "Alice")
        alice.page.click("#join-btn")
        alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        wait_for_board_painted(alice)
        next_frame(alice.page)

        # The gold controls are up, and Alice has no gold to show yet.
        assert alice.page.query_selector("#ep-gold:not(.hidden)") is not None, \
            "the gold trade controls did not appear"
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').gold"
        ) == 0

        # Sell: reveal the pick, then tap wood.
        alice.page.click("#ep-sell-gold")
        alice.page.wait_for_selector("#ep-gold-pick:not(.hidden)", timeout=4000)
        alice.page.click("#ep-gold-pick .ep-gold-res[data-resource='wood']")

        # The three wood become one gold, and the panel now shows it.
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').gold === 1",
            timeout=8000,
        )
        assert "gold" in alice.page.inner_text("#ep-players").lower(), \
            alice.page.inner_text("#ep-players")
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)


def test_buying_a_resource_with_gold_spends_two_and_fills_the_hand(browser, tmp_path):
    """buy_resource_with_gold through the strip: the Buy button reveals the same
    resource pick the sell does, and tapping brick fires the buy. The regression
    it guards against — invisible to the unit suite, which only sees the handler
    once called — is the pick emitting nothing or the wrong resource. The
    player-visible proof is a brick card appearing in the hand fan while the gold
    count in the panel drops from four to two."""
    persistence.save(_buy_gold_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = Player(browser, url, "Alice", viewport=VIEWPORT)
        alice.page.check("#role-player")
        alice.page.fill("#username", "Alice")
        alice.page.click("#join-btn")
        alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        wait_for_board_painted(alice)
        next_frame(alice.page)

        # Four gold, an empty hand: no brick card, and the panel shows the purse.
        assert alice.page.query_selector("#ep-gold:not(.hidden)") is not None, \
            "the gold trade controls did not appear"
        assert alice.page.inner_text(
            "#resource-display .hand-card[data-card='brick'] .hand-card-count") == "0"
        assert "4 gold" in alice.page.inner_text("#ep-players"), \
            alice.page.inner_text("#ep-players")

        # Buy: reveal the pick, then tap brick.
        alice.page.click("#ep-buy-gold")
        alice.page.wait_for_selector("#ep-gold-pick:not(.hidden)", timeout=4000)
        alice.page.click("#ep-gold-pick .ep-gold-res[data-resource='brick']")

        # Two gold become one brick: the hand fan gains the card the player sees,
        # and the panel now reads the lower purse.
        alice.page.wait_for_function(
            "() => document.querySelector("
            "'#resource-display .hand-card[data-card=\\'brick\\'] .hand-card-count')"
            "?.textContent === '1'",
            timeout=8000,
        )
        assert alice.page.evaluate(
            "() => window.__catanDebug.getBoard().players"
            ".find(p => p.name === 'Alice').gold"
        ) == 2
        assert "2 gold" in alice.page.inner_text("#ep-players"), \
            alice.page.inner_text("#ep-players")
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
