"""Barbarian Attack panel, board figures and knight placement, in a real browser.

The new client code is barbarian_attack.js and its strip, the barbarian/knight
art in board-renderer.js, and the `barbarian_knight` edge kind in placement.js.
The regression it guards against is the panel never appearing, the war status
rendering blank, the barbarians never painting on the coast, or the Buy-card and
place-knight gestures emitting nothing — all invisible to the unit suite, which
only sees the engine methods once they are called. The player-visible proof is a
barbarian figure painted on the coast, the panel counting it, and a knight
appearing on a castle path after a card is bought and placed.

A base game must show no Barbarian Attack panel at all.

Run: pytest tests/test_browser_barbarian_attack.py -m slow -q
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
from game import map_store, maps, persistence, tb_decks
from game import rules as rules_module
from game.game import Game

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}


def _barbarian_game():
    """A started Barbarian Attack game, Alice mid-turn with the resources for a
    card and a Knighthood forced to the top of the deck."""
    chosen = dict(rules_module.TB_BARBARIAN_ATTACK_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('barbarian-attack'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    game.get_player('Alice').resources = {'ore': 1, 'sheep': 1, 'wheat': 1}
    # The top card (drawn with pop) is a Knighthood, so buying it owes a knight.
    game.tb.ba_deck.append(tb_decks.KNIGHTHOOD)
    # A coastal hex with a barbarian on it, for the paint check.
    coast = next(k for k in game.tb.coastal_hexes if game.hexes[k].number == 2)
    return game, coast


def _barbarian_game_with_knight():
    """A started Barbarian Attack game, Alice mid-turn with one of her knights
    already standing on a castle path and a legal (adjacent, free) path to move
    it to."""
    chosen = dict(rules_module.TB_BARBARIAN_ATTACK_RULES)
    chosen['turn_order'] = 'lobby'
    defn = maps.parse_map(map_store.read_map('barbarian-attack'))
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5), rules=chosen,
                map_definition=defn)
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    from_edge = game.tb.castle_paths[0]
    game.tb.knights[from_edge] = 'Alice'
    dest = next(edge for edge in game.edges[from_edge].neighbors['edges']
                if edge not in game.tb.knights)
    return game, from_edge, dest


def _base_game():
    game = Game(['Alice', 'Bob'], [], rng=random.Random(5))
    game.start()
    game.game_phase = 'playing'
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


# Painted (non-transparent) pixels in a box around a hex's barbarian badge — the
# badge sits above the tile centre, so this rising from the plain tile is the
# barbarian figure appearing.
_HEX_BADGE_PAINT = """
([hexKey, radius]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const layout = window.BoardRenderer.computeLayout(board);
    const pos = layout.hexPositions[hexKey];
    if (!pos) { return -1; }
    const cfg = window.BoardRenderer.BOARD_CONFIG || { hexRadius: 60 };
    const badgeY = pos.y - (cfg.hexRadius || 60) * 0.52;
    const client = window.BoardRenderer.boardToClient(
        canvas, pos.x + layout.offsetX, badgeY + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = canvas.width / rect.width;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const data = canvas.getContext('2d')
        .getImageData(x - radius, y - radius, radius * 2, radius * 2).data;
    let reddish = 0;
    for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] > 0 && data[i] > 90 && data[i] > data[i + 1] + 30) {
            reddish += 1;
        }
    }
    return reddish;
}
"""

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


def test_the_panel_shows_the_war_and_a_knight_is_placed(browser, tmp_path):
    game, coast = _barbarian_game()
    castle_path = game.tb.castle_paths[0]
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The panel is up and counts the two opening barbarians on the coast.
        assert alice.page.query_selector("#right-barbarian-attack:not(.hidden)") is not None, \
            "the Barbarian Attack panel did not appear"
        assert "Barbarians on the coast" in alice.page.inner_text("#barbarian-status")

        # A barbarian figure is painted on the '2' coast.
        reddish = alice.page.evaluate(_HEX_BADGE_PAINT, [coast, 16])
        assert reddish > 10, f"no barbarian figure painted on the coast (reddish {reddish})"

        # Buy a card: the forced Knighthood owes a knight placement.
        knight_before = alice.page.evaluate(_EDGE_PAINT, [castle_path, 12])
        alice.page.click("#barbarian-buy-card")
        alice.page.wait_for_function(
            "() => { const c = window.__catanDebug.getBoard().tb.pending_card;"
            "        return c && c.card === 'knighthood'; }",
            timeout=8000,
        )
        # The place-knight button appears; arm it and tap a castle path.
        alice.page.wait_for_selector("#barbarian-place-knight:not(.hidden)", timeout=8000)
        alice.page.click("#barbarian-place-knight")
        assert first_clickable(alice, 'edge', [castle_path]) == castle_path, \
            "the castle path was not a clickable target once armed"
        click_edge(alice, castle_path)
        confirm_placement(alice)

        # The knight lands on the path and paints itself on the board.
        alice.page.wait_for_function(
            "edge => window.__catanDebug.getBoard().tb.knights[edge] === 'Alice'",
            arg=castle_path, timeout=8000,
        )
        next_frame(alice.page)
        knight_after = alice.page.evaluate(_EDGE_PAINT, [castle_path, 12])
        assert knight_after > knight_before + 15, \
            f"the knight did not draw (paint {knight_before} -> {knight_after})"
    finally:
        stop_server(proc)


def test_a_knight_is_moved_across_the_board(browser, tmp_path):
    """Arm Move knight, tap one of your knights, tap a legal path: the disc
    leaves the source path and paints itself on the destination, and the board
    state records the new position. Fails before the client gesture exists —
    there is no way to pick a placed knight up and move it through the UI.
    """
    game, from_edge, dest = _barbarian_game_with_knight()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The knight starts painted on its castle path and nothing on the target.
        source_before = alice.page.evaluate(_EDGE_PAINT, [from_edge, 12])
        dest_before = alice.page.evaluate(_EDGE_PAINT, [dest, 12])
        assert source_before > 15, \
            f"the knight was not painted on its path to begin with ({source_before})"

        # Arm Move knight, tap the knight (pick it up), then tap the destination.
        alice.page.wait_for_selector("#barbarian-move-knight:not(.hidden)", timeout=8000)
        alice.page.click("#barbarian-move-knight")
        click_edge(alice, from_edge)
        click_edge(alice, dest)
        confirm_placement(alice)

        # The engine records the move: gone from the source, held on the target.
        alice.page.wait_for_function(
            "([src, dst]) => { const k = window.__catanDebug.getBoard().tb.knights;"
            "                  return k[dst] === 'Alice' && !k[src]; }",
            arg=[from_edge, dest], timeout=8000,
        )
        next_frame(alice.page)

        # And the board shows it: the disc has left the source and reached the target.
        source_after = alice.page.evaluate(_EDGE_PAINT, [from_edge, 12])
        dest_after = alice.page.evaluate(_EDGE_PAINT, [dest, 12])
        assert source_after < source_before - 15, \
            f"the knight did not leave the source path (paint {source_before} -> {source_after})"
        assert dest_after > dest_before + 15, \
            f"the knight did not reach the destination (paint {dest_before} -> {dest_after})"
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_barbarian_panel(browser, tmp_path):
    persistence.save(_base_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-barbarian-attack.hidden") is not None, \
            "the Barbarian Attack panel showed in a base game"
    finally:
        stop_server(proc)
