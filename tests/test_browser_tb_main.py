"""Traders & Barbarians main-scenario panel and wagon, in a real browser.

The new client code is tb_main.js and its strip, and the wagon/barbarian art in
board-renderer.js. The regression it guards against is the panel never appearing,
the wagon status rendering blank, the wagon never painting on its intersection,
or the Move-wagon gesture emitting nothing — all invisible to the unit suite,
which only sees the engine methods once they are called. The player-visible proof
is the wagon painted on its intersection, the panel showing the run, and the
wagon moving to a tapped intersection.

A base game must show no Traders & Barbarians panel at all.

Run: pytest tests/test_browser_tb_main.py -m slow -q
"""

import os
import random

import pytest
from browser_harness import (
    Player,
    browser_session,
    click_vertex,
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


def _tb_main_game():
    """A started main-scenario game, Alice mid-turn with her wagon on an interior
    intersection that has a bare adjacent path she can move along."""
    chosen = dict(rules_module.TB_MAIN_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('traders-barbarians'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()

    start = next(v for v, vx in sorted(game.vertices.items())
                 if len(vx.neighbors['hexes']) == 3 and v not in game.trade_plazas)
    dest = None
    for other in game.vertices[start].neighbors['vertices']:
        edge = game._edge_between(start, other)
        if edge is not None and game.edges[edge].road is None \
                and edge not in game.trade_sea_paths and other not in game.trade_plazas:
            dest = other
            break
    assert dest is not None
    game.tb.wagons['Alice'] = start
    game.wagon_points_left = 4
    return game, start, dest


def _base_game():
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


# Painted (non-transparent) pixels around a vertex's wagon glyph — the wagon is
# drawn a touch above the intersection, so paint rising here is the wagon.
_VERTEX_PAINT = """
([vertexKey, radius]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const layout = window.BoardRenderer.computeLayout(board);
    const pos = layout.vertexPositions[vertexKey];
    if (!pos) { return -1; }
    const client = window.BoardRenderer.boardToClient(
        canvas, pos.x + layout.offsetX, (pos.y - 12) + layout.offsetY
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


def test_the_panel_shows_the_run_and_the_wagon_moves(browser, tmp_path):
    game, start, dest = _tb_main_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The panel is up and shows the run.
        assert alice.page.query_selector("#right-tb-main:not(.hidden)") is not None, \
            "the Traders & Barbarians panel did not appear"
        assert "Baggage card" in alice.page.inner_text("#tb-main-status")

        # The wagon is painted on its starting intersection.
        painted = alice.page.evaluate(_VERTEX_PAINT, [start, 12])
        assert painted > 15, f"no wagon painted on its intersection (paint {painted})"

        # Arm the move gesture and tap the adjacent intersection.
        alice.page.click("#tb-move-wagon")
        click_vertex(alice, dest)
        alice.page.wait_for_function(
            "d => window.__catanDebug.getBoard().tb.wagons.Alice === d",
            arg=dest, timeout=8000,
        )
        next_frame(alice.page)
        moved = alice.page.evaluate(_VERTEX_PAINT, [dest, 12])
        assert moved > 15, f"the wagon did not draw at its new intersection (paint {moved})"
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_tb_main_panel(browser, tmp_path):
    persistence.save(_base_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-tb-main.hidden") is not None, \
            "the Traders & Barbarians panel showed in a base game"
    finally:
        stop_server(proc)
