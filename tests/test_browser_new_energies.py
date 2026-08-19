"""CATAN: New Energies — the footprint/energy panel and a power-plant badge.

The whole New Energies economy — the global footprint, each player's energy, the
event-disc bag and the plants on the board — is read off the board payload. A
count that never reached the client, a rule gate that hid the panel, or a plant
badge that never painted would leave the economy invisible while the server
scored it, and the unit suite would still pass because the server state is
perfectly correct.

This test pins: the panel appears with the global-footprint level, a power-plant
badge is actually painted on the hex it faces (pixels, not DOM), and spending
energy through the panel's control moves energy out of the hand the server
tracks.

Run: pytest tests/test_browser_new_energies.py -m slow -v
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

# Greenish painted pixels in a box at a hex centre — a renewable plant badge is a
# green disc drawn over the tile, so this rising from a plain tile is the badge
# appearing.
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
        if (data[i + 3] > 0 && data[i + 1] > 100 && data[i + 1] > data[i] + 30) {
            greenish += 1;
        }
    }
    return greenish;
}
"""


def _new_energies_game():
    """A New Energies game past setup, Alice to move with a plant and energy.

    Places a city for Alice next to a numbered hex and a renewable plant facing
    it, so the panel and the plant badge have something to show, and gives Alice
    2 energy so the spend control is live. Returns (game, plant_hex).
    """
    rules = dict(rules_module.preset_rules("new_energies"))
    rules["turn_order"] = "lobby"
    game = Game(["Alice", "Bob"], [], rng=random.Random(7), rules=rules)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.set_dice_rolled()
    game.event_phase_done = True  # the event phase already ran this turn

    plant_hex = None
    for vertex_key, vertex in game.vertices.items():
        if vertex.building:
            continue
        numbered = [h for h in vertex.neighbors.get("hexes", [])
                    if game.hexes.get(h) and game.hexes[h].number]
        if numbered:
            vertex.building = {"type": "city", "player": "Alice"}
            game.get_player("Alice").cities.append(vertex_key)
            plant_hex = numbered[0]
            game.power_plants[(vertex_key, plant_hex)] = {
                "player": "Alice", "kind": "renewable"}
            break
    assert plant_hex is not None
    game.get_player("Alice").energy = 2
    return game, plant_hex


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


def test_the_panel_shows_the_footprint_a_plant_paints_and_energy_spends(browser, tmp_path):
    game, plant_hex = _new_energies_game()
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))
    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)

        # The panel is up and carries the global-footprint level.
        assert alice.page.query_selector("#right-new-energies:not(.hidden)") is not None, \
            "the New Energies panel did not appear"
        status = alice.page.inner_text("#new-energies-status")
        assert "Footprint" in status, status

        # A power-plant badge is painted on the hex the plant faces.
        green = alice.page.evaluate(_HEX_BADGE_GREEN, [plant_hex, 18])
        assert green > 10, f"no plant badge painted on the hex (green {green})"

        # Spend 2 energy for a card: energy leaves the hand for the supply.
        assert alice.page.query_selector("#new-energies-buy:not([disabled])") is not None, \
            "the spend-energy button was not enabled"
        alice.page.click("#new-energies-buy")
        alice.page.click(".new-energies-buy-opt[data-card='wheat']")
        alice.page.wait_for_function(
            """() => {
                const ne = window.__catanDebug.getBoard().new_energies;
                return ne && ne.energy && ne.energy.Alice === 0;
            }""",
            timeout=10000,
        )
        board = alice.page.evaluate("() => window.__catanDebug.getBoard()")
        assert board["new_energies"]["energy"]["Alice"] == 0
        me = next(p for p in board["players"] if p["name"] == "Alice")
        assert me["resources"]["wheat"] == 1

        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
