"""What the board actually paints, checked in a real browser.

Every bug this file covers left the game logic perfectly correct and the DOM
perfectly correct, and was only ever visible in the pixels:

  - harbours drew twice, 18 markers for the 9 harbours in the box, because the
    renderer read `vertex.port` (a compatibility mirror on both ends of the
    coastal edge) instead of `edge.port` (the harbour itself);
  - Cities & Knights knights had no board art at all, so a player could own
    six of them and see nothing;
  - a knight and a building share an intersection, and the first drawing of
    them put one on top of the other.

A canvas satisfies every DOM assertion while painting nothing, so everything
here counts pixels or counts draw calls.

Run: pytest tests/test_browser_visuals.py -m slow -v
"""

import pytest
from browser_harness import (
    Player,
    launch_browser,
    start_server,
    stop_server,
)
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.slow

# The box holds 9 harbours; the 5-6 player extension adds two more.
HARBOURS_IN_THE_BOX = 9
HARBOURS_ON_THE_LARGE_MAP = 11

# Half-width, in CSS pixels, of the patch sampled around a vertex. Wide enough
# to hold a knight that has stepped off the point, tight enough that a
# neighbouring intersection is not in it.
VERTEX_PATCH = 34


# --- Driving ---------------------------------------------------------------
#
# Defined here rather than in browser_harness.py: this suite is the only one
# that needs to choose a map or read the canvas back, and the harness is shared
# with three other suites.

SET_RULES = """
async rules => {
    // The rules picker has no control for a choice rule yet, so the map cannot
    // be chosen by clicking. The socket module is a singleton, and importing
    // it again returns the same live connection the page is using.
    const socket = (await import('/static/js/socket.js')).socket;
    socket.emit('set_rules', { rules });
}
"""

# One frame, with fillText intercepted. Counting the labels a render *asks*
# for is what pins "one marker per harbour" - counting blobs of ink cannot
# tell one harbour from two overlapping ones.
COUNT_HARBOUR_MARKERS = """
() => {
    const proto = CanvasRenderingContext2D.prototype;
    const original = proto.fillText;
    const drawn = [];
    proto.fillText = function (text, ...rest) {
        drawn.push(String(text));
        return original.call(this, text, ...rest);
    };
    try {
        window.BoardRenderer.render(
            window.__catanDebug.getBoard(), 'board-canvas', null, null
        );
    } finally {
        proto.fillText = original;
    }
    return drawn.filter(text => text === '2:1' || text === '3:1').length;
}
"""

# Render, then read back the pixels around one vertex. Both in one call so the
# page's own render loop cannot repaint between them.
RENDER_AND_SAMPLE = """
([vertexKey, half]) => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    window.BoardRenderer.render(board, 'board-canvas', null, null);

    const layout = window.BoardRenderer.computeLayout(board);
    const point = layout.vertexPositions[vertexKey];
    const rect = canvas.getBoundingClientRect();
    const client = window.BoardRenderer.boardToClient(
        canvas, point.x + layout.offsetX, point.y + layout.offsetY
    );
    const ratio = canvas.width / rect.width;
    const centreX = Math.round((client.x - rect.left) * ratio);
    const centreY = Math.round((client.y - rect.top) * ratio);
    const reach = Math.round(half * ratio);

    const x = Math.max(0, centreX - reach);
    const y = Math.max(0, centreY - reach);
    const width = Math.min(canvas.width - x, reach * 2);
    const height = Math.min(canvas.height - y, reach * 2);
    return Array.from(canvas.getContext('2d').getImageData(x, y, width, height).data);
}
"""

PUT_KNIGHTS = """
([owner, knights]) => {
    const board = window.__catanDebug.getBoard();
    board.cities_knights.knights[owner] = knights;
    return board.cities_knights.knights[owner].length;
}
"""

PUT_BUILDING = """
([vertexKey, owner, kind]) => {
    const board = window.__catanDebug.getBoard();
    board.vertices[vertexKey].building = kind ? { player: owner, type: kind } : null;
}
"""

# Aim at the exact middle of every edge in turn and ask the hit-tester what it
# hit. Round-tripped through client coordinates on purpose: that trip is where
# the floating-point noise that used to decide a tie comes from.
RESOLVE_EVERY_EDGE = """
factor => {
    const canvas = document.getElementById('board-canvas');
    const board = window.__catanDebug.getBoard();
    window.BoardRenderer.fitToView();
    if (factor !== 1) {
        window.BoardRenderer.zoomAt(factor, canvas.clientWidth / 2, canvas.clientHeight / 2);
    }
    window.BoardRenderer.render(board, 'board-canvas', null, null);

    const layout = window.BoardRenderer.computeLayout(board);
    const wrong = [];
    for (const key in layout.edgePositions) {
        const pos = layout.edgePositions[key];
        const client = window.BoardRenderer.boardToClient(
            canvas, pos.centerX + layout.offsetX, pos.centerY + layout.offsetY
        );
        const point = window.BoardRenderer.clientToBoard(canvas, client.x, client.y);
        const hit = window.BoardRenderer.findNearestEdge(board, point.x, point.y);
        if (hit !== key) {
            wrong.push(`${key} resolved to ${hit}`);
        }
    }

    // These fixtures are shared, so hand the camera back the way it was found.
    window.BoardRenderer.fitToView();
    window.BoardRenderer.render(board, 'board-canvas', null, null);
    return wrong;
}
"""

# The bounding box of everything painted, against the middle of the canvas.
INK_BOUNDS = """
() => {
    const canvas = document.getElementById('board-canvas');
    const data = canvas.getContext('2d')
        .getImageData(0, 0, canvas.width, canvas.height).data;
    let minX = canvas.width, maxX = -1, minY = canvas.height, maxY = -1;
    for (let y = 0; y < canvas.height; y += 1) {
        for (let x = 0; x < canvas.width; x += 1) {
            if (data[(y * canvas.width + x) * 4 + 3] !== 0) {
                if (x < minX) { minX = x; }
                if (x > maxX) { maxX = x; }
                if (y < minY) { minY = y; }
                if (y > maxY) { maxY = y; }
            }
        }
    }
    return { minX, maxX, minY, maxY, width: canvas.width, height: canvas.height };
}
"""


# The rules the Cities & Knights preset ticks. Named here rather than
# passing the retired `cities_and_knights` flag, which only still works
# because saves and old clients are migrated.
CITIES_AND_KNIGHTS = {"commodities": True, "city_improvements": True, "metropolis": True,
     "knights": True, "barbarians": True, "city_walls": True,
     "progress_cards": True, "setup_second_city": True,
     "victory_target": 13}


def start_table(browser, url, rules=None):
    """Two joined players with a game running, on a map of our choosing."""
    alice = Player(browser, url, "Alice")
    bob = Player(browser, url, "Bob")
    alice.join()
    bob.join()
    if rules:
        alice.page.evaluate(SET_RULES, rules)
        alice.page.wait_for_timeout(400)
    alice.page.click("#start-game-btn")
    alice.page.wait_for_selector("#game-screen:not(.hidden)", timeout=10000)
    alice.page.wait_for_timeout(600)
    return alice, bob


def differing_pixels(before, after):
    """How many samples of the two patches disagree."""
    assert len(before) == len(after), "patches must be the same size to compare"
    return sum(1 for index in range(0, len(before), 4)
               if before[index:index + 4] != after[index:index + 4])


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = launch_browser(play)
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def default_board(browser, tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("visuals-default"))
    alice, _ = start_table(browser, url)
    yield alice
    stop_server(proc)


@pytest.fixture(scope="module")
def large_board(browser, tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("visuals-large"))
    alice, _ = start_table(browser, url, {"board_layout": "large"})
    yield alice
    stop_server(proc)


@pytest.fixture(scope="module")
def knights_board(browser, tmp_path_factory):
    proc, url = start_server(tmp_path_factory.mktemp("visuals-ck"))
    alice, _ = start_table(browser, url, CITIES_AND_KNIGHTS)
    yield alice
    stop_server(proc)


class TestHarboursAreDrawnOnce:
    """Regression: 18 harbour markers appeared for the 9 harbours in the box.

    `vertex.port` mirrors a harbour onto *both* intersections of its coastal
    edge, so a renderer that walks the vertices paints every harbour twice.
    """

    def test_the_payload_still_mirrors_every_harbour_onto_two_vertices(self, default_board):
        """The trap is still there, so the test below is still testing it."""
        board = default_board.board()
        edge_ports = [edge for edge in board["edges"].values() if edge.get("port")]
        vertex_ports = [v for v in board["vertices"].values() if v.get("port")]
        assert len(edge_ports) == HARBOURS_IN_THE_BOX
        assert len(vertex_ports) == HARBOURS_IN_THE_BOX * 2

    def test_exactly_nine_markers_are_drawn(self, default_board):
        drawn = default_board.page.evaluate(COUNT_HARBOUR_MARKERS)
        assert drawn == HARBOURS_IN_THE_BOX, f"drew {drawn} harbour markers"

    def test_the_large_map_draws_its_eleven(self, large_board):
        board = large_board.board()
        assert len([e for e in board["edges"].values() if e.get("port")]) \
            == HARBOURS_ON_THE_LARGE_MAP
        drawn = large_board.page.evaluate(COUNT_HARBOUR_MARKERS)
        assert drawn == HARBOURS_ON_THE_LARGE_MAP, f"drew {drawn} harbour markers"


class TestKnightsAreVisible:
    """Regression: knights had no board art at all.

    A tester reported owning knights and seeing nothing on the board. The
    panel listed them; the canvas never drew them.
    """

    def _sample(self, player, vertex_key):
        return player.page.evaluate(RENDER_AND_SAMPLE, [vertex_key, VERTEX_PATCH])

    def _empty_vertex(self, player):
        board = player.board()
        return next(key for key, vertex in sorted(board["vertices"].items())
                    if not vertex.get("building"))

    def test_a_knight_paints_pixels_at_its_vertex(self, knights_board):
        vertex = self._empty_vertex(knights_board)
        before = self._sample(knights_board, vertex)

        knights_board.page.evaluate(
            PUT_KNIGHTS, ["Alice", [{"vertex": vertex, "rank": 1, "active": True}]]
        )
        after = self._sample(knights_board, vertex)

        changed = differing_pixels(before, after)
        assert changed > 150, f"a knight only changed {changed} pixels at {vertex}"

    def test_rank_changes_what_is_drawn(self, knights_board):
        """Basic, strong and mighty have to be told apart on the board."""
        vertex = self._empty_vertex(knights_board)
        patches = []
        for rank in (1, 2, 3):
            knights_board.page.evaluate(
                PUT_KNIGHTS, ["Alice", [{"vertex": vertex, "rank": rank, "active": True}]]
            )
            patches.append(self._sample(knights_board, vertex))

        assert differing_pixels(patches[0], patches[1]) > 20, "basic and strong look alike"
        assert differing_pixels(patches[1], patches[2]) > 20, "strong and mighty look alike"

    def test_an_inactive_knight_looks_different_from_an_active_one(self, knights_board):
        vertex = self._empty_vertex(knights_board)
        knights_board.page.evaluate(
            PUT_KNIGHTS, ["Alice", [{"vertex": vertex, "rank": 2, "active": True}]]
        )
        active = self._sample(knights_board, vertex)
        knights_board.page.evaluate(
            PUT_KNIGHTS, ["Alice", [{"vertex": vertex, "rank": 2, "active": False}]]
        )
        inactive = self._sample(knights_board, vertex)

        changed = differing_pixels(active, inactive)
        assert changed > 100, f"active and inactive differ by only {changed} pixels"

    def test_a_knight_does_not_cover_the_building_it_stands_with(self, knights_board):
        """They share an intersection, so one of them has to step aside."""
        vertex = self._empty_vertex(knights_board)
        knights_board.page.evaluate(PUT_KNIGHTS, ["Alice", []])
        knights_board.page.evaluate(PUT_BUILDING, [vertex, "Alice", "settlement"])
        settlement_only = self._sample(knights_board, vertex)

        knights_board.page.evaluate(
            PUT_KNIGHTS, ["Alice", [{"vertex": vertex, "rank": 3, "active": True}]]
        )
        with_knight = self._sample(knights_board, vertex)

        # The knight is there...
        assert differing_pixels(settlement_only, with_knight) > 150

        # ...and the settlement is still whole. Sampled as the middle of the
        # patch, which is the vertex, which is where the building is drawn.
        knights_board.page.evaluate(PUT_BUILDING, [vertex, "Alice", None])
        knights_board.page.evaluate(PUT_KNIGHTS, ["Alice", []])
        bare = self._sample(knights_board, vertex)

        side = int((len(bare) // 4) ** 0.5)
        covered = 0
        for row in range(side // 2 - 6, side // 2 + 6):
            for column in range(side // 2 - 6, side // 2 + 6):
                index = (row * side + column) * 4
                if settlement_only[index:index + 4] != with_knight[index:index + 4]:
                    covered += 1
        assert covered == 0, f"the knight painted over {covered} pixels of the building"


class TestTheLargeMapIsCentred:
    """The 5-6 player island has a row of 6, so it cannot be both that shape
    and centred on the origin. The layout has to fit the board's real bounds.
    """

    def test_the_board_sits_in_the_middle_of_its_canvas(self, large_board):
        bounds = large_board.page.evaluate(INK_BOUNDS)
        ink_x = (bounds["minX"] + bounds["maxX"]) / 2
        ink_y = (bounds["minY"] + bounds["maxY"]) / 2
        assert abs(ink_x - bounds["width"] / 2) <= 6, f"off-centre horizontally: {bounds}"
        assert abs(ink_y - bounds["height"] / 2) <= 6, f"off-centre vertically: {bounds}"

    def test_the_default_board_is_centred_too(self, default_board):
        bounds = default_board.page.evaluate(INK_BOUNDS)
        ink_x = (bounds["minX"] + bounds["maxX"]) / 2
        assert abs(ink_x - bounds["width"] / 2) <= 6, f"off-centre horizontally: {bounds}"


class TestEveryEdgeHitTestsToItself:
    """Regression: a road landed on the edge next to the one that was clicked.

    Two board keys used to name one physical hex side, so a click sat at
    distance zero from both and which one won re-rolled with the camera scale.
    The renderer papered over it with a tie-breaking epsilon in findNearest*;
    the board now holds one Edge per side, so the epsilon is gone and this is
    what says it may stay gone.
    """

    def _misses(self, player, factor):
        return player.page.evaluate(RESOLVE_EVERY_EDGE, factor)

    def test_at_the_fitted_scale(self, default_board):
        assert self._misses(default_board, 1) == []

    def test_and_when_zoomed_in(self, default_board):
        """The old failure was scale-dependent, so one scale proves nothing."""
        assert self._misses(default_board, 2.2) == []

    def test_and_on_the_large_map(self, large_board):
        assert self._misses(large_board, 1) == []


class TestTerrainFollowsTheTheme:
    def test_a_hex_is_repainted_when_the_theme_changes(self, default_board):
        """The terrain fills are CSS custom properties, and a canvas inherits
        nothing: the renderer has to read them again when the theme flips."""
        board = default_board.board()
        land = next(key for key, hex_data in sorted(board["hexes"].items())
                    if hex_data["type"] not in ("ocean", "desert"))

        def hex_pixel(theme):
            default_board.page.evaluate(
                "t => document.documentElement.setAttribute('data-theme', t)", theme
            )
            return default_board.page.evaluate("""
                key => {
                    const canvas = document.getElementById('board-canvas');
                    const boardData = window.__catanDebug.getBoard();
                    window.BoardRenderer.render(boardData, 'board-canvas', null, null);
                    const layout = window.BoardRenderer.computeLayout(boardData);
                    const point = layout.hexPositions[key];
                    const rect = canvas.getBoundingClientRect();
                    const client = window.BoardRenderer.boardToClient(
                        canvas, point.x + layout.offsetX, point.y + layout.offsetY
                    );
                    const ratio = canvas.width / rect.width;
                    // Off the number token, still well inside the hex.
                    const x = Math.round((client.x - rect.left) * ratio);
                    const y = Math.round((client.y - rect.top) * ratio + 24 * ratio);
                    const data = canvas.getContext('2d').getImageData(x, y, 1, 1).data;
                    return [data[0], data[1], data[2]];
                }
            """, land)

        light = hex_pixel("light")
        dark = hex_pixel("dark")
        default_board.page.evaluate(
            "() => document.documentElement.removeAttribute('data-theme')"
        )
        assert light != dark, f"terrain ignored the theme: {light} in both"


class TestNothingBrokeOnTheWay:
    def test_no_console_errors(self, default_board, knights_board, large_board):
        for player in (default_board, knights_board, large_board):
            assert player.noisy_errors() == [], f"{player.name}: {player.noisy_errors()}"
