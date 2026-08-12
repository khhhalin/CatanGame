"""The Caravans panel, a rendered camel, and the voting round, in a real browser.

The new client code is caravans.js and its strip, the camel art in
board-renderer.js, and the camel_placement option in choices.js. The regression
it guards against is the panel never appearing, a placed camel never drawing on
the board, or the bid form emitting nothing — invisible to the unit suite, which
only sees bid_camel and place_camel once they are called. The player-visible
proof is the camel painting itself onto the board and the bid form standing up.

A base game must show no Caravans panel at all.

Run: pytest tests/test_browser_caravans.py -m slow -q
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


def _caravans_game():
    """A started Caravans game with one camel already grown on the first arrow."""
    chosen = dict(rules_module.TB_CARAVANS_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('caravans'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    edge = game.oasis_arrows[0]
    game.place_camel(edge)
    return game, edge


def _voting_game():
    """A started Caravans game with a camel voting round open, Alice the finisher."""
    chosen = dict(rules_module.TB_CARAVANS_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('caravans'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    game.camel_owed = True
    game.advance_turn('Alice')  # opens the vote, holds the turn open
    return game


def _base_game():
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


# Painted (non-transparent) pixels in a box around an edge's midpoint — a camel
# is drawn just off the midpoint, so this rising from near-nothing to a solid
# count is the camel appearing on the board.
_EDGE_PAINT = """
([edgeKey, radius]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const layout = window.BoardRenderer.computeLayout(board);
    const pos = layout.edgePositions[edgeKey];
    if (!pos) { return -1; }
    const client = window.BoardRenderer.boardToClient(
        canvas, pos.centerX + layout.offsetX, pos.centerY + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = canvas.width / rect.width;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const data = canvas.getContext('2d')
        .getImageData(x - radius, y - radius, radius * 2, radius * 2).data;
    let painted = 0;
    for (let i = 3; i < data.length; i += 4) {
        if (data[i] > 0) { painted += 1; }
    }
    return painted;
}
"""


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


def test_the_panel_shows_a_camel_that_is_drawn_on_the_board(browser, tmp_path):
    game, edge = _caravans_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The Caravans panel is up and shows the camel that has been placed.
        assert alice.page.query_selector("#right-caravans:not(.hidden)") is not None, \
            "the Caravans panel did not appear"
        assert "Camels" in alice.page.inner_text("#caravans-status")
        # The camel is painted on its path.
        next_frame(alice.page)
        painted = alice.page.evaluate(_EDGE_PAINT, [edge, 14])
        assert painted > 20, f"the camel did not draw (paint {painted})"
    finally:
        stop_server(proc)


def test_the_voting_round_shows_a_bid_form(browser, tmp_path):
    persistence.save(_voting_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        # The vote is open and Alice, the finisher, is asked to bid.
        alice.page.wait_for_selector("#caravans-vote:not(.hidden)", timeout=8000)
        assert alice.page.query_selector("#caravans-bid") is not None, \
            "the bid button did not appear"
        # Passing removes Alice from the bidders still owed; the panel then waits
        # on Bob rather than offering her the form again.
        alice.page.click("#caravans-pass")
        alice.page.wait_for_function(
            "() => { const v = window.__catanDebug.getBoard().tb.camel_vote;"
            "        return v && !v.pending.includes('Alice'); }",
            timeout=8000,
        )
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_caravans_panel(browser, tmp_path):
    persistence.save(_base_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-caravans.hidden") is not None, \
            "the Caravans panel showed in a base game"
    finally:
        stop_server(proc)
