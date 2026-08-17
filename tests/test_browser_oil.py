"""Catan: Oil Springs — the oil/disaster panel and a sequester action.

Oil, the disaster track and the Oil Spring tiles are read entirely off the
board payload; a count that never reached the client, a rule gate that hid the
panel, or a badge that never painted would leave the whole economy invisible
while the server scored it, and the unit suite would still pass because the
server state is perfectly correct.

This test pins: the panel appears with the disaster track, an oil-drop badge is
actually painted on an Oil Spring tile (pixels, not DOM), and clicking Sequester
moves oil out of the hand into the sequestered total the server tracks.

Run: pytest tests/test_browser_oil.py -m slow -v
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

# The wood Oil Spring on the fixed Oil Springs board (a 9). Asserted against the
# generated board in tests/game/test_oil_springs.py.
WOOD_SPRING = "0,6,-6"

# Greenish painted pixels in a box at a hex centre — the oil-drop badge is a
# green glyph on a dark disc drawn over the tile, so this rising from a plain
# tile is the badge appearing.
_HEX_BADGE_GREEN = """
([hexKey, radius]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const layout = window.BoardRenderer.computeLayout(board);
    const pos = layout.hexPositions[hexKey];
    if (!pos) { return -1; }
    const client = window.BoardRenderer.boardToClient(
        canvas, pos.x + layout.offsetX, pos.y + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = canvas.width / rect.width;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const data = canvas.getContext('2d')
        .getImageData(x - radius, y - radius, radius * 2, radius * 2).data;
    let greenish = 0;
    for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] > 0 && data[i + 1] > 120 && data[i + 1] > data[i] + 40) {
            greenish += 1;
        }
    }
    return greenish;
}
"""


def _oil_game():
    """An Oil Springs game past setup, Alice to move with oil in hand."""
    defn = maps.parse_map(map_store.read_map("oil-springs"))
    rules = dict(rules_module.preset_rules("oil_springs"))
    rules["turn_order"] = "lobby"
    game = Game(["Alice", "Bob"], [], rng=random.Random(7), rules=rules,
                map_definition=defn)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.set_dice_rolled()
    game.get_player("Alice").oil = 2
    game.get_player("Bob").oil = 1
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


def test_the_oil_panel_shows_the_track_badges_the_springs_and_sequesters(browser, tmp_path):
    game = _oil_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The panel is up and carries the disaster track.
        assert alice.page.query_selector("#right-oil:not(.hidden)") is not None, \
            "the Oil Springs panel did not appear"
        status = alice.page.inner_text("#oil-status")
        assert "Disaster" in status, status

        # An oil-drop badge is painted on the wood Oil Spring tile.
        green = alice.page.evaluate(_HEX_BADGE_GREEN, [WOOD_SPRING, 16])
        assert green > 10, f"no oil badge painted on the spring (green {green})"

        # Sequester one oil: it leaves the hand for the sequestered total.
        assert alice.page.query_selector("#oil-sequester:not([disabled])") is not None, \
            "the Sequester button was not enabled"
        alice.page.click("#oil-sequester")
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().oil.oil.Alice === 1",
            timeout=10000,
        )
        board = alice.page.evaluate("() => window.__catanDebug.getBoard().oil")
        assert board["oil"]["Alice"] == 1
        assert board["sequestered"]["Alice"] == 1

        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
