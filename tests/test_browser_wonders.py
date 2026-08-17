"""The Wonders of Catan panel, in a real browser: the five Wonders with their
per-level cost and start requirement, this player's chosen Wonder and level, and
a Build button that raises it another level.

The new client code is wonders.js and its strip in index.html. The regression it
guards against is the panel never appearing, the cost tiles never rendering, or
the Build button emitting nothing — invisible to the unit suite, which only sees
build_wonder_level once it is called. The player-visible proof is the panel
standing up with every Wonder's cost and requirement and the level ticking up
when Raise is clicked.

A base game must show no Wonders panel at all.

Run: pytest tests/test_browser_wonders.py -m slow -q
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
from seafarers_board import give_building

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}

WONDER_NAMES = ["Cathedral", "Great Bridge", "Great Wall", "Monument", "Theater"]


def _wonders_game():
    """A started Wonders game where Alice has raised the Theater to level 1 and
    holds the hand for one more level, her turn, dice rolled."""
    defn = maps.parse_map(map_store.read_map("wonders-of-catan"))
    chosen = dict(rules_module.preset_rules("wonders_of_catan"))
    chosen["turn_order"] = "lobby"
    chosen["board_layout"] = "custom"
    chosen["board_map"] = "wonders-of-catan"
    game = Game(["Alice", "Bob"], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0  # Alice
    game.start_turn()
    game.set_dice_rolled()
    # Two cities meet the Theater's requirement; start it, then leave Alice a
    # second level's worth of cards in hand for the browser to spend on Raise.
    cities = [key for key in sorted(game.vertices)
              if game.vertices[key].neighbors["hexes"]
              and not game.is_wonder_marker(key)][:2]
    for vertex_key in cities:
        give_building(game, "Alice", vertex_key, "city")
    game.get_player("Alice").resources = {"sheep": 3, "brick": 1, "wood": 1}
    assert game.build_wonder_level("Alice", "theater")["success"]
    game.get_player("Alice").resources = {"sheep": 3, "brick": 1, "wood": 1}
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


def test_the_panel_shows_every_wonder_its_cost_and_your_level(browser, tmp_path):
    persistence.save(_wonders_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        assert alice.page.query_selector("#right-wonders:not(.hidden)") is not None, \
            "the Wonders panel did not appear"
        panel_text = alice.page.inner_text("#right-wonders")
        for name in WONDER_NAMES:
            assert name in panel_text, f"{name} missing from the panel"
        # Two of the printed requirements, so a card's requirement really renders.
        assert "Two cities" in panel_text
        assert "strait" in panel_text
        # Alice's own progress: the Theater at level 1 of 4.
        assert "Theater" in alice.page.inner_text("#wonders-status")
        assert "1 / 4" in alice.page.inner_text("#wonders-status")
        # Every Wonder costs five cards, so five rows of five tiles are drawn.
        tiles = alice.page.eval_on_selector_all(
            "#wonders-list .wonders-cost .tile", "els => els.length")
        assert tiles == 25, f"expected 25 cost tiles, saw {tiles}"
    finally:
        stop_server(proc)


def test_raising_a_wonder_advances_the_level(browser, tmp_path):
    persistence.save(_wonders_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        # Only the started Wonder offers a build; Raise spends the hand and the
        # level ticks to 2 on the board every tab is drawn from.
        raise_btn = alice.page.query_selector('.wonders-build[data-wonder="theater"]')
        assert raise_btn is not None, "the Raise button did not appear"
        raise_btn.click()
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().wonders.players.Alice.level === 2",
            timeout=8000,
        )
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_wonders_panel(browser, tmp_path):
    persistence.save(_base_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-wonders.hidden") is not None, \
            "the Wonders panel showed in a base game"
    finally:
        stop_server(proc)
