"""The three Helpers advantages that place a piece, completed by tapping the board.

Yngvi (a makeshift road), Hogni (moving an end road) and Gregor (a knight
turned into a building) each need an edge or a vertex. They used to take it as a
key typed into a text box, which no real player can produce. Now activating the
tile opens a pending choice of the legal spots, the board rings them, and the
player taps one - the same board-tap path the other pending choices use.

Every test here drives the real player gesture and asserts the piece landed on
the tapped spot in the board payload every client draws from - never a typed
key. The rings are proven in pixels, because a highlight that is in the payload
and painted nowhere satisfies every DOM assertion there is.

Run: pytest tests/test_browser_helper_placement.py -m slow -v
"""

import os
import random

import pytest
from browser_harness import (
    Player,
    browser_session,
    click_edge,
    click_vertex,
    first_clickable,
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

# Sample the pixels around an edge with and without the choice ring, in one
# call so the page's own render loop cannot repaint between the two frames. A
# ring that paints makes the two differ; a highlight drawn nowhere does not.
SAMPLE_EDGE = """
([edgeKey, ringed]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    window.BoardRenderer.render(board, 'board-canvas', null, null,
                                ringed ? [edgeKey] : []);
    const layout = window.BoardRenderer.computeLayout(board);
    const edge = layout.edgePositions[edgeKey];
    const bx = (edge.x1 + edge.x2) / 2;
    const by = (edge.y1 + edge.y2) / 2;
    const client = window.BoardRenderer.boardToClient(
        canvas, bx + layout.offsetX, by + layout.offsetY
    );
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const x = Math.round((client.x - rect.left) * dpr);
    const y = Math.round((client.y - rect.top) * dpr);
    const half = 18;
    const data = canvas.getContext('2d')
        .getImageData(x - half, y - half, half * 2, half * 2).data;
    return Array.from(data).join(',');
}
"""


def _helpers_game(tile):
    """A started Helpers game, Alice mid-turn holding `tile` with a home built."""
    chosen = dict(rules_module.preset_rules("helpers_of_catan"))
    chosen["turn_order"] = "lobby"  # keep Alice in seat 0 so it is her turn
    game = Game(["Alice", "Bob"], [], rng=random.Random(5), rules=chosen)
    game.start()
    game.game_phase = "playing"
    game.current_player_index = 0
    game.start_turn()
    game.helper_held["Alice"] = {"tile": tile, "side": "sun", "received_turn": None}
    return game


def _home_vertex(game):
    """The first inland intersection, so a building on it has terrain around it."""
    for key in sorted(game.vertices):
        hexes = game.vertices[key].neighbors["hexes"]
        if len(hexes) >= 2 and all(
            game.hexes[h].type not in ("ocean", "desert") for h in hexes
        ):
            return key
    raise AssertionError("no inland intersection on the dealt board")


def _edges_at(game, vertex):
    return [key for key in sorted(game.edges)
            if vertex in game.edges[key].neighbors["vertices"]]


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


def _my_options(page):
    return page.evaluate(
        """() => {
            const b = window.__catanDebug.getBoard();
            const pc = (b.pending_choices || []).find(c => c.player === 'Alice');
            return pc ? pc.options : null;
        }"""
    )


def _road_owner(page, edge):
    return page.evaluate(
        "key => (window.__catanDebug.getBoard().edges[key].road || {}).player || null",
        edge,
    )


def _building(page, vertex):
    return page.evaluate(
        "key => window.__catanDebug.getBoard().vertices[key].building || null",
        vertex,
    )


def test_yngvi_road_is_laid_on_the_tapped_edge(browser, tmp_path):
    game = _helpers_game("yngvi")
    home = _home_vertex(game)
    game.vertices[home].building = {"type": "settlement", "player": "Alice"}
    alice = game.get_player("Alice")
    alice.settlements.append(home)
    # Drop lumber (the form's default), pay a sheep for it; a brick is still owed
    # the ordinary way, so the hand is exactly a brick and a sheep.
    alice.resources = {"brick": 1, "sheep": 1}
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))

    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        page = alice.page
        # Pay a sheep for the dropped lumber, then activate.
        page.select_option("#yngvi-pay", "sheep")
        page.click(".helper-activate")

        page.wait_for_selector("#choice-panel:not(.hidden)", timeout=8000)
        options = _my_options(page)
        assert options, "no legal road side was offered"
        target = first_clickable(alice, "edge", options) or options[0]

        # The offered side is ringed on the board (pixels, not the DOM).
        with_ring = page.evaluate(SAMPLE_EDGE, [target, True])
        without = page.evaluate(SAMPLE_EDGE, [target, False])
        assert with_ring != without, "the candidate path was not ringed"

        assert _road_owner(page, target) is None
        click_edge(alice, target)

        page.wait_for_function(
            "key => (window.__catanDebug.getBoard().edges[key].road || {}).player === 'Alice'",
            arg=target, timeout=8000,
        )
        assert _road_owner(page, target) == "Alice", "the road did not land on the tapped edge"
        # The used tile now owes its exchange-or-flip, the same as every other use.
        page.wait_for_function(
            "() => (window.__catanDebug.getBoard().pending_choices || [])"
            "  .some(c => c.player === 'Alice' && c.kind === 'helper_resolution')",
            timeout=8000,
        )
        assert alice.noisy_errors() == []
    finally:
        stop_server(proc)


def test_hogni_moves_an_end_road_by_two_board_taps(browser, tmp_path):
    game = _helpers_game("hogni")
    home = _home_vertex(game)
    game.vertices[home].building = {"type": "settlement", "player": "Alice"}
    alice = game.get_player("Alice")
    alice.settlements.append(home)
    edges = _edges_at(game, home)
    from_edge, to_edge = edges[0], edges[1]
    game.edges[from_edge].road = {"player": "Alice"}
    alice.roads.append(from_edge)
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))

    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        page = alice.page
        page.click(".helper-activate")

        # First choice: which end road to lift. Tapping it picks it up.
        page.wait_for_function(
            "() => (window.__catanDebug.getBoard().pending_choices || [])"
            "  .some(c => c.player === 'Alice' && c.kind === 'helper_move_road_from')",
            timeout=8000,
        )
        assert from_edge in _my_options(page)
        click_edge(alice, from_edge)

        # The road is lifted, and a second choice offers where to lay it.
        page.wait_for_function(
            "key => (window.__catanDebug.getBoard().edges[key].road || null) === null",
            arg=from_edge, timeout=8000,
        )
        page.wait_for_function(
            "() => (window.__catanDebug.getBoard().pending_choices || [])"
            "  .some(c => c.player === 'Alice' && c.kind === 'helper_move_road_to')",
            timeout=8000,
        )
        assert to_edge in _my_options(page)
        click_edge(alice, to_edge)

        page.wait_for_function(
            "key => (window.__catanDebug.getBoard().edges[key].road || {}).player === 'Alice'",
            arg=to_edge, timeout=8000,
        )
        assert _road_owner(page, to_edge) == "Alice", "the road did not re-lay on the tapped edge"
        assert _road_owner(page, from_edge) is None, "the lifted road stayed put"
        assert alice.noisy_errors() == []
    finally:
        stop_server(proc)


def test_gregor_raises_a_city_on_the_tapped_vertex(browser, tmp_path):
    game = _helpers_game("gregor")
    home = _home_vertex(game)
    game.vertices[home].building = {"type": "settlement", "player": "Alice"}
    alice = game.get_player("Alice")
    alice.settlements.append(home)
    alice.knights_played = 1
    # Gregor's city is 2 ore + 1 wheat, not the usual 3 ore + 2 wheat.
    alice.resources = {"ore": 2, "wheat": 1}
    persistence.save(game, os.path.join(str(tmp_path), "game.json"))

    proc, url = start_server(tmp_path)
    try:
        alice = _join(browser, url)
        page = alice.page
        page.select_option("#gregor-build", "city")
        page.click(".helper-activate")

        page.wait_for_function(
            "() => (window.__catanDebug.getBoard().pending_choices || [])"
            "  .some(c => c.player === 'Alice' && c.kind === 'helper_knight_to_building')",
            timeout=8000,
        )
        assert home in _my_options(page), "Alice's own settlement was not offered for a city"
        assert _building(page, home)["type"] == "settlement"

        click_vertex(alice, home)

        page.wait_for_function(
            "key => window.__catanDebug.getBoard().vertices[key].building.type === 'city'",
            arg=home, timeout=8000,
        )
        assert _building(page, home)["type"] == "city", "the city did not rise on the tapped spot"
        page.wait_for_function(
            "() => (window.__catanDebug.getBoard().pending_choices || [])"
            "  .some(c => c.player === 'Alice' && c.kind === 'helper_resolution')",
            timeout=8000,
        )
        assert alice.noisy_errors() == []
    finally:
        stop_server(proc)
