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


def _gold_game():
    """A started Pirate Cove game with gold in play, Alice mid-turn holding the
    three wood a sell costs and no gold yet, so the sell is an isolated change."""
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
    alice = game.get_player('Alice')
    alice.resources = {'wood': 3}
    alice.gold = 0
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
