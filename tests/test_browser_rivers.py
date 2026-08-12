"""The Rivers of Catan panel and bridge building, in a real browser.

The new client code is rivers.js and its strip, plus the bridge edge kind in
placement.js and the bridge art in board-renderer.js. The regression it guards
against is the panel never appearing, the coin total rendering blank, or the
Build bridge gesture emitting nothing — invisible to the unit suite, which only
sees build_bridge once it is called. The player-visible proof is the coin total
climbing to 3 in the panel and the bridge painting itself onto the board.

A base game must show no Rivers panel at all.

Run: pytest tests/test_browser_rivers.py -m slow -q
"""

import os
import random

import pytest
from browser_harness import (
    Player,
    browser_session,
    click_edge,
    confirm_placement,
    first_clickable,
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


def _rivers_game():
    """A started Rivers game, Alice mid-turn with a settlement beside a bridge
    site and exactly the brick and lumber for one bridge, no coins yet."""
    chosen = dict(rules_module.TB_RIVERS_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('rivers'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    edge = sorted(game.bridge_sites)[0]
    vertex = game.edges[edge].neighbors['vertices'][0]
    game.vertices[vertex].building = {'type': 'settlement', 'player': 'Alice'}
    game.get_player('Alice').settlements.append(vertex)
    game.get_player('Alice').resources = {'brick': 2, 'wood': 1}
    game.get_player('Alice').gold = 0
    return game, edge


def _base_game():
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


# Painted (non-transparent) pixels in a box around an edge's midpoint — a bridge
# piece is drawn here, so this rising from near-nothing to a solid count is the
# bridge appearing on the board.
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


def test_the_rivers_panel_shows_coins_and_builds_a_bridge(browser, tmp_path):
    game, edge = _rivers_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The Rivers panel is up and shows Alice's coin total (zero to start).
        assert alice.page.query_selector("#right-rivers:not(.hidden)") is not None, \
            "the Rivers panel did not appear"
        assert "Your coins" in alice.page.inner_text("#rivers-coins")

        before = alice.page.evaluate(_EDGE_PAINT, [edge, 14])

        # Arm the bridge gesture, aim at the crossing site, and confirm.
        alice.page.click("#rivers-build-bridge")
        assert first_clickable(alice, 'edge', [edge]) == edge, \
            "the bridge site was not a clickable target once armed"
        click_edge(alice, edge)
        confirm_placement(alice)

        # The bridge pays 3 gold and lands as a road carrying kind='bridge'.
        alice.page.wait_for_function(
            "edge => (window.__catanDebug.getBoard().edges[edge].road || {}).kind"
            " === 'bridge'",
            arg=edge, timeout=8000,
        )
        alice.page.wait_for_function(
            "() => (window.__catanDebug.getBoard().players.find(p => p.is_you)"
            "        || {}).gold === 3",
            timeout=8000,
        )
        # The panel shows the new total, and the bridge has painted itself on.
        next_frame(alice.page)
        assert "3" in alice.page.inner_text("#rivers-coins")
        after = alice.page.evaluate(_EDGE_PAINT, [edge, 14])
        assert after > before + 20, f"the bridge did not draw (paint {before} -> {after})"
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_rivers_panel(browser, tmp_path):
    persistence.save(_base_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-rivers.hidden") is not None, \
            "the Rivers panel showed in a base game"
    finally:
        stop_server(proc)
