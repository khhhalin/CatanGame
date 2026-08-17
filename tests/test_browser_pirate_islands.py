"""The Pirate Islands panel, board fleet and fortresses, in a real browser.

The new client code is pirate_islands.js and its strip in index.html, and the
fleet-ship and fortress art in board-renderer.js. The regression it guards
against is the panel never appearing, the fleet never painting on its track hex,
the fortresses never painting on the western islands, or the Build-warship and
Attack-fortress gestures emitting nothing — all invisible to the unit suite,
which only sees the engine methods once they are called. The player-visible proof
is the black fleet ship painted on the sea, a dark fortress keep painted on a
western island, the panel counting your warships, and the warship count ticking
up and the fortress falling when the buttons are clicked.

A base game must show no Pirate Islands panel at all.

Run: pytest tests/test_browser_pirate_islands.py -m slow -q
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
from seafarers_board import build_ships_along

pytestmark = pytest.mark.slow
VIEWPORT = {"width": 1600, "height": 1000}


def _pirate_game():
    """A started Pirate Islands game: Alice mid-turn with a Knight to reveal, two
    ships (one on her fortress edge, one plain) and one warship already."""
    defn = maps.parse_map(map_store.read_map("pirate-islands"))
    chosen = dict(rules_module.preset_rules("pirate_islands"))
    chosen["turn_order"] = "lobby"
    chosen["board_layout"] = "custom"
    chosen["board_map"] = "pirate-islands"
    game = Game(["Alice", "Bob", "Carol", "Dave"], [], rng=random.Random(5),
                rules=chosen, map_definition=defn)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0  # Alice
    game.start_turn()
    game.set_dice_rolled()

    alice = game.get_player("Alice")
    alice.dev_cards["knight"]["count"] = 1
    vertex_key, _fort = game.own_fortress("Alice")
    edges = sorted(game.vertices[vertex_key].neighbors["edges"])[:2]
    build_ships_along(game, "Alice", edges)  # two ships: one plain to convert
    game.player_warships["Alice"] = 1
    return game, game.pirate_fleet_hex(), vertex_key


def _capture_game():
    """A started Pirate Islands game where Alice can win one fight to recapture:
    her route reaches her fortress, it is down to its last chit, and she has more
    warships than any die can roll."""
    defn = maps.parse_map(map_store.read_map("pirate-islands"))
    chosen = dict(rules_module.preset_rules("pirate_islands"))
    chosen["turn_order"] = "lobby"
    chosen["board_layout"] = "custom"
    chosen["board_map"] = "pirate-islands"
    game = Game(["Alice", "Bob", "Carol", "Dave"], [], rng=random.Random(5),
                rules=chosen, map_definition=defn)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.start_turn()
    game.set_dice_rolled()

    vertex_key, fort = game.own_fortress("Alice")
    fort["chits"] = 1
    build_ships_along(game, "Alice",
                      [sorted(game.vertices[vertex_key].neighbors["edges"])[0]])
    game.player_warships["Alice"] = 7  # more than any die face -> always wins
    return game


def _base_game():
    game = Game(["Alice", "Bob"], [], rng=random.Random(5))
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.set_dice_rolled()
    return game


# Near-black painted pixels in a box around a hex centre: the black fleet ship
# rising from a plain blue sea tile.
_HEX_DARK_PAINT = """
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
    let dark = 0;
    for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] > 0 && data[i] < 55 && data[i + 1] < 55 && data[i + 2] < 55) {
            dark += 1;
        }
    }
    return dark;
}
"""

# Near-black painted pixels in a box around an intersection: the dark fortress
# keep on its western-island tile.
_VERTEX_DARK_PAINT = """
([vertexKey, radius]) => {
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
    let dark = 0;
    for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] > 0 && data[i] < 55 && data[i + 1] < 55 && data[i + 2] < 55) {
            dark += 1;
        }
    }
    return dark;
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


def test_panel_fleet_and_fortresses_are_shown(browser, tmp_path):
    game, fleet_hex, fortress_vertex = _pirate_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        assert alice.page.query_selector("#right-pirate:not(.hidden)") is not None, \
            "the Pirate Islands panel did not appear"
        status = alice.page.inner_text("#pirate-status")
        assert "Warships" in status
        assert "Fortress chits" in status

        # The black fleet ship is painted on its sea track hex.
        ship = alice.page.evaluate(_HEX_DARK_PAINT, [fleet_hex, 22])
        assert ship > 10, f"no fleet ship painted on the sea (dark pixels {ship})"

        # A dark fortress keep is painted on the western island.
        keep = alice.page.evaluate(_VERTEX_DARK_PAINT, [fortress_vertex, 12])
        assert keep > 10, f"no fortress keep painted on the island (dark pixels {keep})"
    finally:
        stop_server(proc)


def test_building_a_warship_ticks_the_count_up(browser, tmp_path):
    game, _fleet_hex, _fortress_vertex = _pirate_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        button = alice.page.query_selector(".pirate-build-warship")
        assert button is not None, "the Build warship button did not appear"
        button.click()
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().pirate_islands.warships.Alice === 2",
            timeout=8000,
        )
    finally:
        stop_server(proc)


def test_attacking_the_fortress_recaptures_it(browser, tmp_path):
    persistence.save(_capture_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        button = alice.page.query_selector(".pirate-attack-fortress")
        assert button is not None, "the Attack fortress button did not appear"
        button.click()
        # More warships than any die: the last chit falls and the fortress is
        # recaptured on the board every tab is drawn from.
        alice.page.wait_for_function(
            "() => window.__catanDebug.getBoard().pirate_islands.fortresses"
            ".find(f => f.owner === 'Alice').captured === true",
            timeout=8000,
        )
    finally:
        stop_server(proc)


def test_a_base_game_shows_no_pirate_panel(browser, tmp_path):
    persistence.save(_base_game(), os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        assert alice.page.query_selector("#right-pirate.hidden") is not None, \
            "the Pirate Islands panel showed in a base game"
    finally:
        stop_server(proc)
