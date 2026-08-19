"""Catan for Two in the browser: the token readout, the neutral pieces, a spend.

Three things a player would notice and the unit suite cannot see, because the
server state is perfectly correct while each is invisible: the trade-token count
on the scoreboard, a neutral colour's piece actually painted on the board, and a
token-action spend dropping the count. A count that never reached the client, a
colour missing from the renderer's lookup (so a neutral piece drew as the grey
fallback or not at all), or a button wired to nothing would each pass every unit
test and fail a real game.

Run: pytest tests/test_browser_catan_for_two.py -m slow -v
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


def _catan_for_two_game():
    """A Catan for Two game past setup, Alice on turn, both level on points."""
    rules = dict(rules_module.preset_rules("catan_for_two"))
    rules["turn_order"] = "lobby"
    game = Game(["Alice", "Bob"], [], rng=random.Random(7), rules=rules)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = next(
        i for i, p in enumerate(game.players) if p.name == "Alice"
    )
    game.set_dice_rolled()
    # Keep the robber off the desert so the token-action move is legal.
    game.robber_hex = next(
        key for key, hx in game.hexes.items() if hx.type not in ("desert", "ocean")
    )
    return game


# Pixels close to a target colour in a box around a vertex — a settlement is
# filled in its owner's colour, so this rising to a solid count at the neutral
# settlement's corner is that neutral piece painted in its own colour.
_VERTEX_COLOUR = """
([vertexKey, rgb, tol, radius]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const layout = window.BoardRenderer.computeLayout(board);
    const pos = layout.vertexPositions[vertexKey];
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
    let hits = 0;
    for (let i = 0; i < data.length; i += 4) {
        if (Math.abs(data[i] - rgb[0]) <= tol
            && Math.abs(data[i + 1] - rgb[1]) <= tol
            && Math.abs(data[i + 2] - rgb[2]) <= tol
            && data[i + 3] > 0) { hits += 1; }
    }
    return hits;
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


def test_token_readout_neutral_pieces_and_a_spend(browser, tmp_path):
    game = _catan_for_two_game()
    # The dark-slate neutral colour is distinctive enough to count on the board.
    neutral = next(n for n in game.neutral_players if n.color == "#34495e")
    neutral_vertex = neutral.settlements[0]

    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # 1) The scoreboard states each player's trade-token count.
        labels = alice.page.eval_on_selector_all(
            "#game-players [aria-label*='trade tokens']",
            "els => els.map(e => e.getAttribute('aria-label'))",
        )
        assert labels.count("5 trade tokens") == 2, labels

        # 2) The neutral colour's opening settlement is actually painted in its
        # own colour on the board (not the grey fallback, not nothing).
        hits = alice.page.evaluate(
            _VERTEX_COLOUR, [neutral_vertex, [52, 73, 94], 24, 14]
        )
        assert hits > 20, f"neutral settlement not painted in its colour: {hits}"

        # 3) Spending a token moves the robber and drops the count. Alice and Bob
        # are level on points, so the action costs the trailing/level price of 1.
        alice.page.wait_for_selector("#token-actions:not([hidden])", timeout=5000)
        alice.page.click("#spend-token-robber-btn")
        alice.page.wait_for_function(
            "() => {"
            "  const els = Array.from("
            "    document.querySelectorAll(\"#game-players [aria-label*='trade tokens']\"));"
            "  return els.some(e => e.getAttribute('aria-label') === '4 trade tokens'); }",
            timeout=5000,
        )
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
