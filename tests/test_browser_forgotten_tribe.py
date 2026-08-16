"""The Forgotten Tribe gift markers and the harbour-placement prompt, in a real
browser.

The new client code is the gift-star pass in board-renderer.js and the
gift_harbor option in choices.js. The regression it guards against is a marked
coast edge that never draws its star, a claim that leaves the star behind, or a
gift harbour that resolves itself on a timeout because the prompt never reached
the player — every one of them invisible to the unit suite, which sees the
server state (the gift claimed, the choice opened) as perfectly correct.

The player-visible proof, all through the real canvas and the real buttons:
a gold star painted on an unclaimed gift edge, the same star gone once a ship
has claimed it, and the harbour-placement panel standing up with a spot to pick
so the player places the reward rather than the clock placing it.

Run: pytest tests/test_browser_forgotten_tribe.py -m slow -q
"""

import os
import random

import pytest
from browser_harness import (
    Player,
    browser_session,
    build_ship,
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


def _forgotten_tribe_game():
    """A started Forgotten Tribe game with Alice poised to claim a harbour gift.

    Alice holds a settlement on the barren-island coast where a harbour gift is
    marked — the ship she lays there both connects to her settlement and reaches
    the gift — and a second coastal settlement on the main land, so once the
    harbour is claimed she is guaranteed a legal spot to place it and the prompt
    is a real question rather than a held gift. Returns the game and the gift
    edge so the test drives the ship onto exactly that edge.
    """
    defn = maps.parse_map(map_store.read_map("forgotten-tribe"))
    rules = dict(rules_module.preset_rules("forgotten_tribe"))
    rules["turn_order"] = "lobby"
    rules["board_layout"] = "custom"
    rules["board_map"] = "forgotten-tribe"
    game = Game(["Alice", "Bob"], [], rng=random.Random(12345), rules=rules,
                map_definition=defn)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.set_dice_rolled()

    edge_key = next(
        key for key in sorted(game.gift_edges)
        if game.gift_edges[key]["gift"] == "harbor"
    )
    island_vertex = game.edges[edge_key].neighbors["vertices"][0]
    give_building(game, "Alice", island_vertex)
    give_building(game, "Alice", _main_coastal_vertex(game, island_vertex))

    # A ship is wood + sheep; the build-ship button greys out unless she can
    # pay, exactly as a player's would.
    game.get_player("Alice").resources = {"wood": 2, "sheep": 2}
    return game, edge_key


def _main_coastal_vertex(game, avoid):
    """A free main-land intersection with a sea side, to seat a second harbour."""
    for key, vertex in sorted(game.vertices.items()):
        if key == avoid or vertex.building or not vertex.neighbors["hexes"]:
            continue
        if not any(game.is_main_land(h) for h in vertex.neighbors["hexes"]):
            continue
        if any(game.is_sea_edge(e) for e in vertex.neighbors["edges"]):
            return key
    raise AssertionError("no free main-land coastal intersection on this board")


# Gold (star-fill) pixels in a box centred on where the renderer floats the gift
# star — seaward of the edge midpoint, the same offset drawGiftMarker uses. Gold
# stands well clear of the dark ocean and the pale barren desert around it, so a
# rising count is the star appearing and a count near zero is it gone. Colour,
# not bare alpha: the ocean under the star is opaque, so counting any paint would
# never fall once the claim removed the marker.
_GIFT_STAR_GOLD = """
([edgeKey, radius]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    const layout = window.BoardRenderer.computeLayout(board);
    const pos = layout.edgePositions[edgeKey];
    if (!pos) { return -1; }
    const landKeys = (board.edges[edgeKey].neighbors || {}).hexes || [];
    let sx = 0, sy = 0, n = 0;
    for (const key of landKeys) {
        const h = layout.hexPositions[key];
        if (h) { sx += h.x; sy += h.y; n += 1; }
    }
    let ox = 0, oy = -1;
    if (n) {
        const dx = pos.centerX - sx / n;
        const dy = pos.centerY - sy / n;
        const len = Math.hypot(dx, dy) || 1;
        ox = dx / len; oy = dy / len;
    }
    const client = window.BoardRenderer.boardToClient(
        canvas, pos.centerX + ox * 14 + layout.offsetX,
        pos.centerY + oy * 14 + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = canvas.width / rect.width;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const data = canvas.getContext('2d')
        .getImageData(x - radius, y - radius, radius * 2, radius * 2).data;
    let gold = 0;
    for (let i = 0; i < data.length; i += 4) {
        const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
        if (a > 0 && r > 160 && g > 110 && g < 205 && b < 130 && (r - b) > 60) {
            gold += 1;
        }
    }
    return gold;
}
"""


@pytest.fixture(scope="module")
def browser():
    with browser_session() as engine:
        yield engine


def test_a_gift_marker_shows_then_a_ship_claims_it_and_the_harbour_prompt_opens(
        browser, tmp_path):
    game, edge_key = _forgotten_tribe_game()
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

        # The gift star is on the unclaimed edge, and no prompt is up yet.
        before = alice.page.evaluate(_GIFT_STAR_GOLD, [edge_key, 11])
        assert before > 20, f"the gift star did not draw (gold {before})"
        assert alice.page.query_selector("#choice-panel.hidden") is not None, \
            "a harbour prompt showed before anything was claimed"

        # Alice sails a ship onto the marked edge, through the real fold, button
        # and canvas. Claiming the gift is the server's answer to that build.
        build_ship(alice, [edge_key])
        alice.page.wait_for_function(
            "key => window.__catanDebug.getBoard().claimed_gift_edges.includes(key)",
            arg=edge_key, timeout=8000,
        )
        next_frame(alice.page)

        # The star is gone the moment the gift is claimed.
        after = alice.page.evaluate(_GIFT_STAR_GOLD, [edge_key, 11])
        assert after < 6, f"the gift star stayed after the claim (gold {after})"

        # The harbour-placement prompt is up for Alice, with real spots to pick,
        # rather than resolving itself on a timeout.
        alice.page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)
        assert "harbour" in alice.page.inner_text("#choice-prompt").lower()
        option = alice.page.get_attribute(".choice-option", "data-choice-option")
        assert option, "the harbour prompt offered no placement spot"

        # Picking a spot round-trips through make_choice and lands a real port on
        # the chosen edge — the harbour a player can then trade at.
        alice.page.click(".choice-option")
        alice.page.wait_for_function(
            "key => Boolean(window.__catanDebug.getBoard().edges[key].port)",
            arg=option, timeout=8000,
        )
        assert alice.noisy_errors() == [], alice.noisy_errors()
    finally:
        stop_server(proc)
