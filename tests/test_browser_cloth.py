"""The Cloth for Catan scoreboard shows each player's bolts of cloth.

Cloth is banked off the board, not held as a card, so the only place a player
reads how much they have — and whether they are one bolt short of the next
victory point — is the scoreboard chip this suite pins. A count that never
reached the client, a rule gate that hid the chip, or a missing glyph would all
leave that number invisible while the server quietly scored it, and the unit
suite would still pass because the server state is perfectly correct.

Run: pytest tests/test_browser_cloth.py -m slow -v
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


def _cloth_game():
    """A Cloth for Catan game past setup, with bolts already banked."""
    defn = maps.parse_map(map_store.read_map("cloth-for-catan"))
    rules = dict(rules_module.preset_rules("cloth_for_catan"))
    rules["turn_order"] = "lobby"
    rules["board_layout"] = "custom"
    rules["board_map"] = "cloth-for-catan"
    game = Game(["Alice", "Bob"], [], rng=random.Random(7), rules=rules,
                map_definition=defn)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.set_dice_rolled()

    # A settlement each so the board has content and the scoreboard has cards.
    for name in ("Alice", "Bob"):
        vertex = next(
            key for key, vertex in sorted(game.vertices.items())
            if vertex.neighbors["hexes"]
            and any(game.is_main_land(h) for h in vertex.neighbors["hexes"])
            and not vertex.building
            and not any((game.vertices.get(n) and game.vertices[n].building)
                        for n in vertex.neighbors["vertices"])
        )
        game.vertices[vertex].building = {"type": "settlement", "player": name}
        game.get_player(name).settlements.append(vertex)

    # Alice holds three bolts (a pair scores 1 VP, one bolt spare); Bob holds one.
    game.cloth_tokens = {"Alice": 3, "Bob": 1}
    return game


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def test_the_scoreboard_shows_each_players_bolts_of_cloth(browser, tmp_path):
    game = _cloth_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = Player(browser, url, "Alice", viewport=VIEWPORT)
        alice.page.check("#role-player")
        alice.page.fill("#username", "Alice")
        alice.page.click("#join-btn")
        alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
        wait_for_board_painted(alice)
        next_frame(alice.page)

        # The chip carries the count in its aria-label, so a player using a
        # screen reader hears the same number the sighted player sees.
        labels = alice.page.eval_on_selector_all(
            "#game-players [aria-label*='bolts of cloth']",
            "els => els.map(e => e.getAttribute('aria-label'))",
        )
        assert "3 bolts of cloth" in labels, labels
        assert "1 bolts of cloth" in labels, labels
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
